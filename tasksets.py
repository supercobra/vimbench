"""Portable loading of seed and synthesized benchmark task sets."""
import json
from pathlib import Path

from tasks import TASKS

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_SYNTH_TASKS = PROJECT_ROOT / "tasks_synth.json"


def load_tasks(task_set="seed", synth_path=None):
    """Return tasks from the seed set, synthesized set, or both.

    ``synth_path`` defaults to the repository's ``tasks_synth.json`` regardless
    of the caller's current working directory.
    """
    if task_set not in {"seed", "synth", "all"}:
        raise ValueError(f"unknown task set: {task_set!r}")

    tasks = [] if task_set == "synth" else list(TASKS)
    if task_set in {"synth", "all"}:
        path = Path(synth_path) if synth_path is not None else DEFAULT_SYNTH_TASKS
        with path.open(encoding="utf-8") as f:
            tasks.extend(json.load(f))
    return tasks
