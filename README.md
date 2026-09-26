# vimbench — benchmark LLMs on vim editing skill

The model is given a **start buffer**, a **target buffer**, and a natural-language
instruction. It must output a **vim keystroke sequence** that transforms one into
the other. The harness replays the keystrokes into real headless vim and scores
the resulting buffer. No judge model, no flaky tests — exact byte comparison,
millisecond-scale per task.

## How it works

```
model output (notation) → notation_to_bytes → vi -u NONE -N -n -s keys buf.txt
                          (+ safety suffix <Esc>:wq!) → diff buf.txt vs target
```

1. `harness.py` translates the human-readable notation into raw bytes and feeds
   them to vim's `-s` script mode (`-u NONE -N -n`: no vimrc, nocompatible, no
   swapfile). A safety suffix `<Esc>:wq!` is appended so vim always saves and
   exits — a model that forgets `:wq` or leaves insert mode still terminates,
   it just scores on whatever state it left behind.
2. `tasks.py` holds the seed set: 30 tasks across 4 tiers, each with a verified
   reference solution (see `verify.py` / `run.py --verify`).
3. `scorer.py` computes pass/fail, partial credit, and keystroke efficiency.
4. `run.py` is the CLI: `--verify`, `--demo`, or `--solutions solutions.json`.

## Usage examples

All commands run from `~/workspace/vimbench`.

**1. Verify every reference solution** (validates the task set itself):

```
python run.py --verify
# OK   t1-delete-second-line
# OK   t1-swap-first-two
# ...
# 30/30 verified
```

**2. Watch the scoring work** — three synthetic models over all 30 seed tasks
(reference = optimal, verbose = correct but wasteful, sloppy = 6 wrong answers):

```
python run.py --demo
# === reference ===
# pass rate: 30/30 (100%)   avg efficiency (passed): 1.0   avg partial: 1.0
# === verbose ===
# pass rate: 30/30 (100%)   avg efficiency (passed): 0.966 ...
# === sloppy ===
# pass rate: 24/30 (80%)    avg efficiency (passed): 1.0 ...
```

**3. Replay keystrokes by hand** — see exactly what the harness does with a
candidate answer:

```
python -c "
from harness import run_vim
final, err = run_vim('alpha\nbeta\ngamma\n', 'jdd:wq<CR>')
print(repr(final), err)
"
# 'alpha\ngamma\n' None
```

**4. Score your own solutions file** — a JSON map of `{task_id: keystrokes}`:

```
# solutions.json
{"t1-delete-second-line": "jdd:wq<CR>", "t1-swap-first-two": "ddp:wq<CR>"}

python run.py --solutions solutions.json --out my_results.json
```

**5. Generate fresh tasks** (contamination-proof; only verified tasks are kept):

```
python synthesize.py --count 4   # 4 per template -> tasks_synth.json
python run.py --demo --task-set all   # seed + generated, 102 tasks
```

**6. Try the multi-turn track** — chunked-reference solves across turns,
flail fails, recover deletes the wrong line then fixes it:

```
python multiturn.py
```

**7. Run a real model** (see [LLM runner](#llm-runner) for cloud and local options):

```
python llm_runner.py --provider mock --max-tasks 5     # pipeline check, no keys
python llm_runner.py --provider anthropic --track multi --max-tasks 30 --out claude.json
python llm_runner.py --provider local --model qwen2.5-coder:7b --max-tasks 30
```

**8. Compare several models head-to-head** (see [Leaderboard](#leaderboard)):

```
python leaderboard.py --track single --task-set all --max-tasks 50 \
    --model "qwen2.5-coder,http://localhost:11434/v1,qwen2.5-coder:7b" \
    --model "mistral,http://localhost:11434/v1,mistral:7b" \
    --model "claude,anthropic:,claude-sonnet-4-6"
```

## Keystroke notation

| Token | Bytes | Token | Bytes |
|---|---|---|---|
| `<Esc>` | `0x1b` | `<CR>` | `0x0d` (Enter) |
| `<Tab>` | `0x09` | `<Space>` | ` ` |
| `<BS>` | `0x08` | `<NL>` | `0x0a` |
| `<C-X>` | Ctrl+X (any letter) | `<<` | literal `<` |

Everything else is literal UTF-8. Example: `f"ci"goodbye<Esc>:wq<CR>`

## Task tiers

- **Tier 1 — mechanical** (10): delete/swap/join/yank lines, `gUU`, `:g/^/m0` reverse.
- **Tier 2 — motions, text objects, macros** (10): `ci"`, `di(`, `qa...q`, visual
  block `<C-V>`, `f`/`t` compositions, `*`-style search + change.
- **Tier 3 — ex commands** (10→6): `:%s` with backrefs, `:g/err/t$`, `:sort u`,
  `:g/todo/s/.*/\U&/`, ranges (`:2,3m0`).
- **Tier 4 — composed** (4): CSV column swap, trailing-whitespace strip,
  email extraction, dedent+strip.

## Scoring

- **passed**: final buffer matches target byte-for-byte.
- **partial**: `difflib` similarity ratio on failure (0..1) — distinguishes
  "deleted the wrong line" from "mangled the buffer".
- **efficiency**: `min(1, reference_keystrokes / model_keystrokes)` on pass,
  else 0. The golf dimension: two models can both pass while one uses 14
  keystrokes and the other 32.

Aggregate: pass rate, mean efficiency over passed tasks, mean partial credit.

## Anti-cheat & determinism

- Pinned invocation: `vi -u NONE -N -n --cmd 'set shell=/bin/false'`. No plugins,
  no vimrc, no swapfiles.
- `set shell=/bin/false` neuters `:!cmd` / `:r !cmd` — this measures vim skill,
  not shell skill.
- 10s timeout per task; hangs (runaway macros) score as failures.
- Every task is **verified solvable by construction**: `run.py --verify` replays
  each reference through the real harness and asserts an exact match.

## Portability notes (vim-tiny quirks found while building)

The local vim is 9.1 *tiny* (`-eval`, among others). Two things to know if you
port this to full vim:

- `:g/{pat}/d` with multiple matching lines behaves erratically in tiny
  (deletions land on wrong lines). Verified-safe formulations used instead:
  `:%s/.*{pat}.*//` + `:g/^$/d`, `:g/{pat}/t$`, `:g/{pat}/s/.../`. Single-match
  `:g/2/d` is fine.
- `:v` (inverse global) is unreliable in tiny; avoided entirely.
- No `+eval` means no `\=` in `:s` replacement and no `:sort` sortkeys —
  plain `:sort` / `:sort u` work.

On full vim all reference solutions remain valid; the task set is a subset of
what full vim supports, so scores transfer upward.

## Demo results

`run.py --demo` scores three synthetic models over all 30 seed tasks (~1.4s total):

| model | pass | avg efficiency |
|---|---|---|
| reference (optimal) | 30/30 | 1.000 |
| verbose (correct, wasteful) | 30/30 | 0.966 |
| sloppy (6 wrong solutions) | 24/30 | 1.000 |

The efficiency column is the point: binary pass/fail can't separate
`yyddp` from `ddp`, but the golf score can.

## Task synthesis

`synthesize.py` generates tasks programmatically from 18 transform templates
(delete line N, swap adjacent, sort, substitute, strip whitespace, …), each
with a generated reference solution. Only tasks whose reference replays to an
exact match through the real harness are kept — verification by construction,
so the pool is contamination-proof and effectively infinite:

```
python synthesize.py --count 4   # -> tasks_synth.json (72 tasks, tiers 1-4)
```

`run.py --demo --task-set all` and `llm_runner.py --task-set all` include them.

## Multi-turn track

`multiturn.py` implements the agentic track: the agent sends one keystroke
batch per turn, sees the resulting buffer, and can adapt — up to 8 turns.
Scoring adds `turns_used`; efficiency is measured over total keystrokes.

**Persistence rule:** only the buffer persists between turns. Each turn starts
a fresh vim process, so registers, marks, undo history, and `:set` options are
reset (this vim-tiny build is compiled `-viminfo`, so register persistence is
impossible). A macro recorded in turn 1 cannot be replayed in turn 2; `:set`
must be re-issued in the same turn that depends on it.

`python multiturn.py` demos three agents: chunked-reference (multi-turn solve),
flail (fails), and recover — which deletes the wrong line on turn 1, restores
it from the start buffer on turn 2, and completes on turn 3. Single-shot would
score that run 0; the track rewards the recovery.

## LLM runner

`llm_runner.py` prompts a real model and scores it on either track:

```
export ANTHROPIC_API_KEY=...   # or OPENAI_API_KEY
python llm_runner.py --provider anthropic --track single --task-set all \
    --max-tasks 50 --out claude_results.json
```

### Local models (LM Studio, Ollama, ...)

`--provider local` talks to any OpenAI-compatible `/v1/chat/completions`
endpoint — LM Studio, Ollama, vLLM, llama.cpp server, etc. No API key needed,
`temperature=0` for deterministic evals:

```
# LM Studio (default base URL http://localhost:1234/v1)
python llm_runner.py --provider local --model <model-id> \
    --track single --task-set all --max-tasks 50 --out local_results.json

# Ollama
python llm_runner.py --provider local \
    --base-url http://localhost:11434/v1 --model qwen2.5-coder:7b \
    --track multi --max-tasks 30 --out ollama_multi.json
```

`--base-url` and `--model` can also come from `LOCAL_LLM_URL` /
`LOCAL_LLM_MODEL` env vars, and `--timeout` adjusts the per-request HTTP
timeout (local models can be slow; default 120s). If the server isn't
reachable you get a plain-English error naming the URL.

Note: the local server runs wherever you point `--base-url` — if your models
live on your laptop rather than this machine, use its LAN address instead of
localhost. The `--model` value must match a model the server has loaded
(LM Studio: the model ID shown in the server panel; Ollama: the tag name).

Providers are pluggable (`BaseProvider.complete(task, prompt)`); `--provider
mock` returns reference solutions to validate the pipeline end-to-end. The
prompt includes the notation spec, few-shot examples, and (multi-turn) the
current buffer plus batch history. Model output is parsed tolerantly
(fenced code blocks accepted) and `DONE` ends a multi-turn run.

## Leaderboard

`leaderboard.py` runs several models back-to-back on the **same** task set and
prints a comparison table. A model that fails (server down, bad key) becomes an
error row instead of aborting the run. Results go to `leaderboard.json` with
per-model summaries plus full per-task details.

```
# contenders in a JSON file: {name, base_url|provider, model}
python leaderboard.py --models-file models.json \
    --track single --task-set all --max-tasks 50

# ...or inline (repeatable): --model "name,base_url,model-id"
# (use the provider name as base_url for cloud entries)
python leaderboard.py --track multi --max-tasks 30 \
    --model "qwen2.5-coder,http://localhost:11434/v1,qwen2.5-coder:7b" \
    --model "mistral,http://localhost:11434/v1,mistral:7b" \
    --model "claude,anthropic:,claude-sonnet-4-6"
```

`models.json`:

```json
[
  {"name": "qwen2.5-coder", "base_url": "http://localhost:11434/v1",
   "model": "qwen2.5-coder:7b"},
  {"name": "claude", "provider": "anthropic", "model": "claude-sonnet-4-6"}
]
```

Example output (from a demo run: a perfect reference solution, a stub local
model served over HTTP, and an unreachable server):

```
model       pass   pass%  eff    part   time
----------  -----  -----  -----  -----  ----
reference   30/30  100%   1.000  1.000  0s
stub-local  1/30   3%     1.000  0.467  0s
unreachable  ERROR: could not reach a local LLM at http://127.0.0.1:19999/v1 (is
```

On the multi-turn track the table gains a `turns` column (average turns used).

## Future work

- **Real-model leaderboard**: run the suite over frontier models on both
  tracks; calibrate difficulty against human vim-golf baselines per tier.
- **Full-vim port**: rerun under full vim/neovim; add `+eval` tasks
  (`\=`, `:sort` with keys).
- **Harder synthesis**: multi-step composed templates, larger buffers,
  distractor content, adversarial near-miss targets.
- **Persistent-vim multi-turn**: drive one vim process over a pty (tmux-style)
  so registers/marks/options persist — closer to a real session, at the cost
  of determinism.
