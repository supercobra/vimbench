"""Runner CLI.

Usage:
    python3 run.py --verify            # check all reference solutions (task validation)
    python3 run.py --demo [--task-set seed|synth|all]
                                      # score three synthetic models, print leaderboard
    python3 run.py --solutions sol.json [--task-set ...] --out results.json
                                      # score a model's solutions: {task_id: notation}
    python3 multiturn.py               # multi-turn track demo (chunked / flail / recover agents)
    python3 synthesize.py --count N    # generate N verified tasks per template
    python3 llm_runner.py --provider mock|anthropic|openai --track single|multi ...
                                      # run a real (or mock) LLM over the tasks
"""
import argparse
import json
import sys

from harness import run_vim
from scorer import score_task, summarize
from tasksets import load_tasks
from tasks import TASKS

BY_ID = {t["id"]: t for t in TASKS}

# Correct but wasteful solutions — should pass with efficiency < 1.
VERBOSE = {
    "t1-delete-second-line": ":2d<CR>:wq<CR>",
    "t1-swap-first-two": "yyddp:wq<CR>",
    "t1-join-three": ":%j<CR>:wq<CR>",
    "t1-reverse-lines": "GddggPGddP:wq<CR>",
    "t2-swap-chars": "dlp:wq<CR>",
    "t2-duplicate-word": "ywwP:wq<CR>",
}

# Wrong solutions — should fail, some with high partial credit.
SLOPPY = {
    "t1-delete-second-line": "dd:wq<CR>",
    "t1-join-three": "J:wq<CR>",
    "t2-semicolons-macro": ":%s/$/,/<CR>:wq<CR>",
    "t2-change-inside-quotes": 'f"ci(goodbye<Esc>:wq<CR>',
    "t3-substitute-all": ":%s/foo/baz/g<CR>:wq<CR>",
    "t4-swap-csv-columns": ":%s/,/;/g<CR>:wq<CR>",
}


def run_all(tasks, solutions):
    results = []
    for t in tasks:
        notation = solutions.get(t["id"], "")
        results.append(score_task(t, notation))
    return results


def print_report(name, results):
    s = summarize(results)
    print(f"\n=== {name} ===")
    print(f"pass rate: {s['passed']}/{s['tasks']} ({s['pass_rate']:.0%})   "
          f"avg efficiency (passed): {s['avg_efficiency']}   "
          f"avg partial: {s['avg_partial']}")
    print(f"{'task':28s} {'tier':4s} {'pass':4s} {'keys':>4s} {'ref':>3s} {'eff':>5s} {'partial':>7s}")
    for r in results:
        flag = "FAIL " if r["error"] else ("ok  " if r["passed"] else "miss")
        print(f"{r['id']:28s} {r['tier']:<4d} {flag:4s} {r['keystrokes']:>4d} "
              f"{r['ref_keystrokes']:>3d} {r['efficiency']:>5.2f} {r['partial']:>7.2f}")


def demo(task_set="seed", synth_path=None, out="demo_results.json"):
    tasks = load_tasks(task_set, synth_path)
    reference = {t["id"]: t["reference"] for t in tasks}
    verbose = {**reference, **VERBOSE}
    sloppy = {**reference, **SLOPPY}
    # verbose/sloppy overrides only exist for seed tasks; synth tasks fall
    # back to the reference in those models
    all_results = {}
    for name, sols in [("reference", reference), ("verbose", verbose), ("sloppy", sloppy)]:
        results = run_all(tasks, sols)
        all_results[name] = {"summary": summarize(results), "results": results}
        print_report(name, results)
    print("\n--- leaderboard (pass rate, then efficiency) ---")
    rows = sorted(all_results.items(),
                  key=lambda kv: (kv[1]["summary"]["pass_rate"],
                                  kv[1]["summary"]["avg_efficiency"]), reverse=True)
    for name, data in rows:
        s = data["summary"]
        print(f"{name:10s} pass {s['passed']}/{s['tasks']}  efficiency {s['avg_efficiency']}")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nwrote {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--solutions")
    ap.add_argument("--out", default=None,
                    help="result file (default: demo_results.json for --demo, "
                         "results.json for --solutions)")
    ap.add_argument("--task-set", default="seed", choices=["seed", "synth", "all"])
    ap.add_argument("--synth-tasks", default=None,
                    help="synthesized task JSON (default: tasks_synth.json next to this script)")
    args = ap.parse_args()

    if args.verify:
        fails = 0
        for t in TASKS:
            final, err = run_vim(t["start"], t["reference"])
            ok = err is None and final == t["target"]
            fails += not ok
            print(("OK  " if ok else "FAIL"), t["id"])
        print(f"{len(TASKS) - fails}/{len(TASKS)} verified")
        sys.exit(1 if fails else 0)
    elif args.demo:
        demo(args.task_set, args.synth_tasks, args.out or "demo_results.json")
    elif args.solutions:
        tasks = load_tasks(args.task_set, args.synth_tasks)
        with open(args.solutions, encoding="utf-8") as f:
            solutions = json.load(f)
        results = run_all(tasks, solutions)
        print_report(args.solutions, results)
        out = args.out or "results.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump({"summary": summarize(results), "results": results}, f, indent=2)
        print(f"\nwrote {out}")
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
