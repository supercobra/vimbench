"""Leaderboard: run several models back-to-back on the same task set and compare.

Each model gets the identical tasks, track, and limits, so the table is an
apples-to-apples comparison. A failing model (server down, bad key) is
reported as an error row instead of aborting the whole run.

Usage:
    # models.json lists the contenders:
    python3 leaderboard.py --models-file models.json --track single --max-tasks 30

    # ...or pass them inline (repeatable): name,base_url,model-id
    python3 leaderboard.py --track single --max-tasks 30 \\
        --model "qwen2.5-coder,http://localhost:11434/v1,qwen2.5-coder:7b" \\
        --model "llama3.1,http://localhost:11434/v1,llama3.1:8b" \\
        --model "claude,anthropic:,claude-sonnet-4-6"

    # cloud entries use provider name as base_url, with the key in the env
    # (e.g. "anthropic:" or "openai:"); local entries use a URL.

models.json format:
    [{"name": "qwen2.5-coder", "base_url": "http://localhost:11434/v1",
      "model": "qwen2.5-coder:7b"},
     {"name": "claude", "provider": "anthropic", "model": "claude-sonnet-4-6",
      "pricing": {"input_per_million": 3, "output_per_million": 15}}]

Pricing is optional and expressed in USD per million tokens. When supplied, the
leaderboard reports estimated total cost and cost per successful task.
"""
import argparse
import json
import time

from llm_runner import make_provider, run_llm, summarize_run
from tasksets import load_tasks


def parse_inline(spec):
    """name,base_url,model-id  (provider name as base_url for cloud entries)."""
    parts = spec.split(",", 2)
    if len(parts) != 3:
        raise ValueError(f"--model expects name,base_url,model-id, got {spec!r}")
    name, base_url, model = (p.strip() for p in parts)
    entry = {"name": name, "model": model}
    if base_url.rstrip(":") in ("anthropic", "openai", "mock"):
        entry["provider"] = base_url.rstrip(":")
    else:
        entry["base_url"] = base_url
    return entry


def build_provider(entry, timeout):
    if entry.get("provider", "local") == "local":
        return make_provider("local", base_url=entry.get("base_url"),
                             model=entry.get("model"), timeout=timeout)
    return make_provider(entry["provider"], model=entry.get("model"),
                         timeout=timeout)


def fmt_time(s):
    m, s = divmod(int(s), 60)
    return f"{m}m{s:02d}s" if m else f"{s}s"


def run_leaderboard(entries, tasks, track="single", max_turns=8, timeout=120):
    rows, details = [], {}
    for entry in entries:
        name = entry["name"]
        print(f"\n>>> {name} ({track}, {len(tasks)} tasks) ...", flush=True)
        t0 = time.time()
        try:
            pricing = entry.get("pricing")
            if pricing and (pricing.get("input_per_million") is None
                            or pricing.get("output_per_million") is None):
                raise ValueError("pricing requires input_per_million and output_per_million")
            provider = build_provider(entry, timeout)
            results = run_llm(tasks, provider, track=track,
                              max_turns=max_turns,
                              pricing=pricing)
            summary = summarize_run(results, track)
            for r in results:  # keep the file small
                r.pop("history", None)
                r.pop("final_buffer", None)
            row = {"model": name, "track": track, "error": None,
                   "seconds": round(time.time() - t0, 1), **summary}
            details[name] = {"entry": entry, "summary": summary,
                             "results": results}
        except Exception as e:  # one bad model must not kill the run
            row = {"model": name, "track": track, "error": str(e),
                   "seconds": round(time.time() - t0, 1)}
            details[name] = {"entry": entry, "error": str(e)}
        rows.append(row)
        print(("error: " + row["error"]) if row["error"]
              else f"pass {summary['passed']}/{summary['tasks']}  "
                   f"eff {summary['avg_efficiency']}  "
                   f"p95 {summary['p95_latency_seconds'] or 0:.2f}s  "
                   f"({fmt_time(row['seconds'])})")
    return rows, details


def print_table(rows, track):
    cols = ["model", "pass", "pass%", "efficiency", "partial", "p95",
            "tok/pass", "$/pass", "time"]
    if track == "multi":
        cols.insert(5, "turns")
    header = {"model": "model", "pass": "pass", "pass%": "pass%",
              "efficiency": "eff", "partial": "part", "turns": "turns",
              "p95": "p95", "tok/pass": "tok/pass", "$/pass": "$/pass",
              "time": "time"}
    lines = []
    for r in sorted(rows, key=lambda r: (r.get("pass_rate") or -1,
                                         r.get("avg_efficiency") or -1),
                    reverse=True):
        if r.get("error"):
            lines.append((r["model"], "ERROR", r["error"][:60]))
            continue
        s = r
        p95 = s.get("p95_latency_seconds")
        tokens_per_pass = s.get("tokens_per_pass")
        cost_per_pass = s.get("cost_per_pass_usd")
        line = {"model": r["model"],
                "pass": f"{s['passed']}/{s['tasks']}",
                "pass%": f"{s['pass_rate']:.0%}",
                "efficiency": f"{s['avg_efficiency']:.3f}",
                "partial": f"{s['avg_partial']:.3f}",
                "p95": f"{p95:.2f}s" if p95 is not None else "-",
                "tok/pass": (f"{tokens_per_pass:.0f}"
                             if tokens_per_pass is not None else "-"),
                "$/pass": (f"${cost_per_pass:.4f}"
                           if cost_per_pass is not None else "-"),
                "time": fmt_time(r["seconds"])}
        if track == "multi":
            line["turns"] = f"{s['avg_turns']:.1f}"
        lines.append(tuple(line[c] for c in cols))
    widths = [max([len(header[c])] + [len(l[i]) for l in lines
                                      if isinstance(l, tuple) and len(l) == len(cols)])
              for i, c in enumerate(cols)]
    print("\n" + "  ".join(h.ljust(w) for h, w in zip(
        [header[c] for c in cols], widths)))
    print("  ".join("-" * w for w in widths))
    for l in lines:
        if len(l) != len(cols):  # error row
            print(f"{l[0]:{widths[0]}s}  ERROR: {l[2]}")
        else:
            print("  ".join(v.ljust(w) for v, w in zip(l, widths)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models-file", default=None,
                    help="JSON list of {name, base_url|provider, model}")
    ap.add_argument("--model", action="append", default=[],
                    help="repeatable: name,base_url,model-id "
                         "(provider name as base_url for cloud)")
    ap.add_argument("--track", default="single", choices=["single", "multi"])
    ap.add_argument("--task-set", default="seed", choices=["seed", "synth", "all"])
    ap.add_argument("--synth-tasks", default=None,
                    help="synthesized task JSON (default: tasks_synth.json next to this script)")
    ap.add_argument("--max-tasks", type=int, default=30)
    ap.add_argument("--max-turns", type=int, default=8)
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--out", default="leaderboard.json")
    args = ap.parse_args()

    entries = []
    if args.models_file:
        with open(args.models_file, encoding="utf-8") as f:
            entries += json.load(f)
    entries += [parse_inline(m) for m in args.model]
    if not entries:
        ap.error("no models: pass --models-file or at least one --model")

    tasks = load_tasks(args.task_set, args.synth_tasks)[:args.max_tasks]
    print(f"leaderboard: {len(entries)} models x {len(tasks)} tasks "
          f"(task-set={args.task_set}, track={args.track})")

    rows, details = run_leaderboard(entries, tasks, track=args.track,
                                    max_turns=args.max_turns,
                                    timeout=args.timeout)
    print_table(rows, args.track)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"track": args.track, "task_set": args.task_set,
                   "rows": rows, "details": details}, f, indent=2)
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
