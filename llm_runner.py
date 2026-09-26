"""LLM runner: prompt a language model for vim keystroke sequences and score
them on either track. Providers are pluggable; no third-party deps (urllib).

Set ANTHROPIC_API_KEY or OPENAI_API_KEY to run against real models.
Use --provider local for LM Studio, Ollama, vLLM, llama.cpp server, or any
other OpenAI-compatible endpoint (--base-url, --model).
Without any of these, MockProvider validates the pipeline end-to-end.
"""
import json
import os
import sys
import urllib.request

sys.path.insert(0, "/home/hatch/workspace/vimbench")
from harness import run_vim, keystroke_count
from scorer import score_task, summarize
from multiturn import run_multiturn, summarize_multiturn

NOTATION_HELP = """Keystroke notation: <Esc> = Escape, <CR> = Enter, <Tab>, <Space>,
<BS> = Backspace, <C-X> = Ctrl+X (e.g. <C-V> starts visual block mode),
<< = a literal '<' character. Everything else is literal text typed as-is."""

SYSTEM = ("You are a vim expert. Your job is to transform a text buffer from "
          "its start state into a target state using vim keystrokes.\n" + NOTATION_HELP)


def build_prompt(task, buffer=None, turn=None, history=None):
    buf = buffer if buffer is not None else task["start"]
    p = [f"Instruction: {task['instruction']}", "",
         "Current buffer:", "```", buf.rstrip("\n"), "```", "",
         "Target buffer:", "```", task["target"].rstrip("\n"), "```", ""]
    if turn is not None:
        p.append(f"(turn {turn}; previous batches: "
                 + (", ".join(h["keys"] for h in history) or "none") + ")")
        p.append("")
    p.append("Output ONLY the keystroke sequence for this "
             + ("turn" if turn else "transformation")
             + ", no explanation. End with :wq<CR> to save and quit. "
               "In the multi-turn track you may also output exactly DONE "
               "when the buffer matches the target.")
    return "\n".join(p)


FEWSHOT = [
    ("Delete the second line.", "a\nb\nc\n", "a\nc\n", "jdd:wq<CR>"),
    ("Replace every occurrence of 'foo' with 'bar' in the whole file.",
     "foo 1\nfoo 2\n", "bar 1\nbar 2\n", ":%s/foo/bar/g<CR>:wq<CR>"),
]


def fewshot_block():
    out = ["Examples:"]
    for instr, start, target, keys in FEWSHOT:
        out += [f"Instruction: {instr}", f"Start: {start!r} -> Target: {target!r}",
                f"Keystrokes: {keys}", ""]
    return "\n".join(out)


def extract_keys(text):
    """Pull the keystroke sequence out of a model response (tolerates fences)."""
    text = text.strip()
    if "```" in text:
        parts = text.split("```")
        # take the first fenced block (skip a language tag if present)
        block = parts[1].strip()
        if "\n" in block and not any(c in block.split("\n")[0] for c in "<:"):
            block = "\n".join(block.split("\n")[1:])
        text = block.strip()
    return text


class BaseProvider:
    name = "base"

    def __init__(self, **kw):
        pass

    def complete(self, task, prompt):
        raise NotImplementedError


class MockProvider(BaseProvider):
    """Pipeline validator: returns the task's reference solution."""
    name = "mock"

    def complete(self, task, prompt):
        return task["reference"]


class AnthropicProvider(BaseProvider):
    name = "anthropic"
    model = "claude-sonnet-4-6"

    def __init__(self, api_key=None, model=None):
        self.key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        if model:
            self.model = model

    def complete(self, task, prompt):
        body = json.dumps({
            "model": self.model, "max_tokens": 500,
            "system": SYSTEM + "\n\n" + fewshot_block(),
            "messages": [{"role": "user", "content": prompt}],
        }).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages", data=body,
            headers={"x-api-key": self.key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.load(r)
        return data["content"][0]["text"]


class OpenAIProvider(BaseProvider):
    name = "openai"
    model = "gpt-5"

    def __init__(self, api_key=None, model=None):
        self.key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self.key:
            raise RuntimeError("OPENAI_API_KEY not set")
        if model:
            self.model = model

    def complete(self, task, prompt):
        body = json.dumps({
            "model": self.model, "max_tokens": 500,
            "messages": [
                {"role": "system",
                 "content": SYSTEM + "\n\n" + fewshot_block()},
                {"role": "user", "content": prompt}],
        }).encode()
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions", data=body,
            headers={"authorization": f"Bearer {self.key}",
                     "content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.load(r)
        return data["choices"][0]["message"]["content"]


class OpenAICompatProvider(BaseProvider):
    """Local LLMs (LM Studio, Ollama, vLLM, llama.cpp server, ...) via an
    OpenAI-compatible /v1/chat/completions endpoint. No API key required."""
    name = "local"

    def __init__(self, base_url=None, model=None, api_key=None, timeout=120,
                 **kw):
        self.base_url = (base_url or os.environ.get("LOCAL_LLM_URL")
                         or "http://localhost:1234/v1").rstrip("/")
        self.model = model or os.environ.get("LOCAL_LLM_MODEL") or "local-model"
        self.key = api_key or os.environ.get("LOCAL_LLM_KEY") or "not-needed"
        self.timeout = timeout

    def complete(self, task, prompt):
        body = json.dumps({
            "model": self.model, "max_tokens": 500, "temperature": 0,
            "messages": [
                {"role": "system",
                 "content": SYSTEM + "\n\n" + fewshot_block()},
                {"role": "user", "content": prompt}],
        }).encode()
        req = urllib.request.Request(
            self.base_url + "/chat/completions", data=body,
            headers={"authorization": f"Bearer {self.key}",
                     "content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                data = json.load(r)
        except Exception as e:
            raise RuntimeError(
                f"could not reach a local LLM at {self.base_url} "
                f"(is LM Studio/Ollama running and serving? {e})")
        return data["choices"][0]["message"]["content"]


def make_provider(name, **kw):
    return {"mock": MockProvider,
            "anthropic": AnthropicProvider,
            "openai": OpenAIProvider,
            "local": OpenAICompatProvider}[name](**kw)


class ProviderAgent:
    """Adapts a provider to the multi-turn agent protocol."""

    def __init__(self, provider, task):
        self.provider = provider
        self.task = task

    def __call__(self, obs):
        text = self.provider.complete(
            self.task, build_prompt(self.task, buffer=obs["buffer"],
                                    turn=obs["turn"], history=obs["history"]))
        keys = extract_keys(text)
        if keys.strip() == "DONE":
            return {"done": True}
        return {"keys": keys}


def run_llm(tasks, provider, track="single", max_turns=8):
    results = []
    for t in tasks:
        if track == "multi":
            results.append(run_multiturn(t, ProviderAgent(provider, t),
                                         max_turns=max_turns))
        else:
            text = provider.complete(t, build_prompt(t))
            results.append(score_task(t, extract_keys(text)))
    return results


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="mock",
                    choices=["mock", "anthropic", "openai", "local"],
                    help="local = LM Studio / Ollama / any OpenAI-compatible server")
    ap.add_argument("--base-url", default=None,
                    help="base URL for --provider local "
                         "(default http://localhost:1234/v1 for LM Studio; "
                         "Ollama is http://localhost:11434/v1; "
                         "or set LOCAL_LLM_URL)")
    ap.add_argument("--model", default=None,
                    help="model name/ID for --provider local "
                         "(or set LOCAL_LLM_MODEL); also overrides the "
                         "default model for anthropic/openai")
    ap.add_argument("--timeout", type=int, default=120,
                    help="HTTP timeout in seconds per completion")
    ap.add_argument("--track", default="single", choices=["single", "multi"])
    ap.add_argument("--task-set", default="seed", choices=["seed", "synth", "all"])
    ap.add_argument("--max-tasks", type=int, default=10)
    ap.add_argument("--max-turns", type=int, default=8)
    ap.add_argument("--out", default="llm_results.json")
    args = ap.parse_args()

    from tasks import TASKS
    pool = list(TASKS)
    if args.task_set in ("synth", "all"):
        pool += json.load(open("/home/hatch/workspace/vimbench/tasks_synth.json"))
    tasks = pool[:args.max_tasks]

    provider = make_provider(args.provider, model=args.model,
                             base_url=args.base_url, timeout=args.timeout)
    print(f"provider={provider.name} track={args.track} tasks={len(tasks)}"
          + (f" base_url={provider.base_url} model={provider.model}"
             if args.provider == "local" else ""))
    results = run_llm(tasks, provider, track=args.track, max_turns=args.max_turns)
    summary = (summarize_multiturn(results) if args.track == "multi"
               else summarize(results))
    print(json.dumps(summary, indent=2))
    # strip bulky histories before saving
    for r in results:
        r.pop("history", None)
        r.pop("final_buffer", None)
    with open(args.out, "w") as f:
        json.dump({"summary": summary, "results": results}, f, indent=2)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
