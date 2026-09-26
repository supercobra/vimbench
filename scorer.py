"""Scoring for the vim benchmark.

Per task:
  passed      exact byte-level match of final buffer vs target
  partial     difflib similarity ratio (0..1) when not passed
  keystrokes  number of real keystrokes the model's notation expands to
  efficiency  min(1, reference_keys / model_keys) when passed, else 0 —
              the "golf" dimension: how close to optimal was the solution?
"""
from difflib import SequenceMatcher

from harness import run_vim, keystroke_count


def score_task(task, notation):
    final, err = run_vim(task["start"], notation)
    ref_keys = keystroke_count(task["reference"])
    if err is not None:
        return {
            "id": task["id"], "tier": task["tier"], "passed": False,
            "error": err, "partial": 0.0, "keystrokes": 0,
            "ref_keystrokes": ref_keys, "efficiency": 0.0,
        }
    model_keys = keystroke_count(notation)
    passed = final == task["target"]
    partial = 1.0 if passed else SequenceMatcher(None, final, task["target"]).ratio()
    efficiency = min(1.0, ref_keys / model_keys) if (passed and model_keys) else 0.0
    return {
        "id": task["id"], "tier": task["tier"], "passed": passed,
        "error": None, "partial": round(partial, 3),
        "keystrokes": model_keys, "ref_keystrokes": ref_keys,
        "efficiency": round(efficiency, 3),
    }


def summarize(results):
    n = len(results)
    passed = [r for r in results if r["passed"]]
    eff = [r["efficiency"] for r in passed]
    return {
        "tasks": n,
        "passed": len(passed),
        "pass_rate": round(len(passed) / n, 3) if n else 0.0,
        "avg_efficiency": round(sum(eff) / len(eff), 3) if eff else 0.0,
        "avg_partial": round(sum(r["partial"] for r in results) / n, 3) if n else 0.0,
    }
