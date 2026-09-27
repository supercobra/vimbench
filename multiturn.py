"""Multi-turn track: the agent sees the buffer after each batch of keystrokes
and can adapt, like a real editing session. Each turn replays one keystroke
batch into a fresh headless vim (state persists via the safety :wq! suffix),
and the updated buffer is returned to the agent.

Persistence rule: ONLY the buffer persists between turns. Each turn starts a
fresh vim process, so registers, marks, undo history, and :set options are
reset (this vim-tiny build has -viminfo, so register persistence is not even
possible). Agents must re-issue :set or re-record macros within a single turn.

Agent protocol: agent(obs) -> {"keys": notation} | {"done": True}
  obs = {"id", "instruction", "start", "buffer", "turn", "max_turns", "history"}
"""
from difflib import SequenceMatcher

from harness import run_vim, keystroke_count, tokenize
from scorer import summarize
from telemetry import aggregate_usage


def run_multiturn(task, agent, max_turns=8):
    buf = task["start"]
    history = []
    total_keys = 0
    ref_keys = keystroke_count(task["reference"])
    turns_used = 0
    request_latencies = []
    request_usages = []
    for turn in range(1, max_turns + 1):
        obs = {"id": task["id"], "instruction": task["instruction"],
               "start": task["start"], "buffer": buf, "turn": turn,
               "max_turns": max_turns, "history": history}
        action = agent(obs)
        telemetry = action.get("telemetry") or {}
        latency = telemetry.get("latency_seconds")
        usage = telemetry.get("usage")
        if latency is not None:
            request_latencies.append(latency)
        if usage:
            request_usages.append(usage)
        if action.get("done"):
            break
        keys = action.get("keys", "")
        turns_used = turn
        try:
            n_keys = keystroke_count(keys)
        except ValueError as e:
            history.append({"turn": turn, "keys": keys, "error": str(e), "buffer": buf})
            break
        buf, err = run_vim(buf, keys)
        total_keys += n_keys
        history.append({"turn": turn, "keys": keys, "error": err, "buffer": buf})
        if err is not None or buf == task["target"]:
            break
    passed = buf == task["target"]
    partial = (1.0 if passed else
               SequenceMatcher(None, buf, task["target"]).ratio())
    efficiency = min(1.0, ref_keys / total_keys) if (passed and total_keys) else 0.0
    return {"id": task["id"], "tier": task["tier"], "passed": passed,
            "turns_used": turns_used, "keystrokes": total_keys,
            "ref_keystrokes": ref_keys, "efficiency": round(efficiency, 3),
            "partial": round(partial, 3),
            "latency_seconds": round(sum(request_latencies), 6),
            "request_latencies": request_latencies,
            "usage": aggregate_usage(request_usages),
            "final_buffer": buf, "history": history}


def summarize_multiturn(results):
    s = summarize(results)
    s["avg_turns"] = (round(sum(r["turns_used"] for r in results) / len(results), 2)
                      if results else 0.0)
    return s


class ChunkedReferenceAgent:
    """Mechanics demo: knows the reference, sends it in `chunks` batches split
    at safe boundaries (after <CR>/<Esc>), then signals done. Validates the
    loop, not a real strategy."""

    def __init__(self, task, chunks=2):
        ref = task["reference"]
        quit_cmd = ":wq<CR>"
        body = ref[:-len(quit_cmd)] if ref.endswith(quit_cmd) else ref
        units = tokenize(body)
        bounds, chunk, safe = [], [], True
        # split only after <CR> or <Esc>
        per = max(1, len(units) // chunks)
        for u in units:
            chunk.append(u)
            if u in ("<CR>", "<Esc>") and len(chunk) >= per:
                bounds.append("".join(chunk))
                chunk = []
        if chunk:
            bounds.append("".join(chunk))
        self.batches = bounds + [quit_cmd]

    def __call__(self, obs):
        if obs["turn"] > len(self.batches):
            return {"done": True}
        return {"keys": self.batches[obs["turn"] - 1]}


class FlailAgent:
    """Mechanics demo: tries something wrong, sees it fail, gives up."""

    def __call__(self, obs):
        if obs["turn"] == 1:
            return {"keys": "ggdG"}  # delete everything — wrong
        return {"done": True}


class RecoverAgent:
    """Demo of the track's value: hard-coded for t1-delete-second-line.
    Turn 1 deletes the WRONG line; turn 2 compares start vs buffer, restores
    the lost line; turn 3 does it right. Single-shot would score this 0."""

    def __call__(self, obs):
        if obs["turn"] == 1:
            return {"keys": "dd"}            # oops: deleted line 1, not line 2
        if obs["turn"] == 2:
            return {"keys": "ggOalpha<Esc>"}  # restore the lost line from start
        if obs["turn"] == 3:
            return {"keys": "jdd"}            # now delete line 2 correctly
        return {"done": True}


def demo():
    from tasks import TASKS
    by_id = {t["id"]: t for t in TASKS}
    chunked_sample = [by_id[i] for i in
                      ["t2-quote-first-word", "t3-delete-matching-lines",
                       "t4-dedent-and-strip", "t2-change-inside-quotes"]]
    for name, mk_agent, sample in [
        ("chunked-reference", lambda t: ChunkedReferenceAgent(t), chunked_sample),
        ("flail", lambda t: FlailAgent(), chunked_sample),
        ("recover", lambda t: RecoverAgent(), [by_id["t1-delete-second-line"]]),
    ]:
        results = [run_multiturn(t, mk_agent(t)) for t in sample]
        s = summarize_multiturn(results)
        print(f"\n=== multi-turn: {name} ===")
        print(f"pass {s['passed']}/{s['tasks']}  efficiency {s['avg_efficiency']}  "
              f"avg turns {s['avg_turns']}")
        for r in results:
            print(f"  {r['id']:28s} {'ok' if r['passed'] else 'miss':4s} "
                  f"turns={r['turns_used']} keys={r['keystrokes']} eff={r['efficiency']}")


if __name__ == "__main__":
    demo()
