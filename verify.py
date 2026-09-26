"""Verify every task is solvable by construction: the reference keystrokes,
replayed through the real harness, must produce the target buffer exactly."""
import sys
sys.path.insert(0, "/home/hatch/workspace/vimbench")
from harness import run_vim, keystroke_count
from tasks import TASKS

fails = 0
for t in TASKS:
    final, err = run_vim(t["start"], t["reference"])
    if err is None and final == t["target"]:
        print(f"OK   {t['id']:28s} tier{t['tier']}  {keystroke_count(t['reference']):3d} keys")
    else:
        fails += 1
        print(f"FAIL {t['id']:28s} err={err}")
        print(f"     want: {t['target']!r}")
        print(f"     got:  {final!r}")

print(f"\n{len(TASKS) - fails}/{len(TASKS)} tasks verified")
sys.exit(1 if fails else 0)
