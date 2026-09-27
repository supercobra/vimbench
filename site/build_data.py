#!/usr/bin/env python3
"""Build the compact public leaderboard payload used by the Pages site."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REQUIRED_FIELDS = {
    "model",
    "tasks",
    "passed",
    "pass_rate",
    "avg_efficiency",
    "avg_partial",
    "seconds",
}
OPTIONAL_FIELDS = {
    "p95_latency_seconds",
    "tokens_per_pass",
    "cost_per_pass_usd",
}


def build(source: Path, destination: Path) -> None:
    payload = json.loads(source.read_text(encoding="utf-8"))
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"{source} does not contain a non-empty rows list")

    public_rows = []
    for index, row in enumerate(rows):
        missing = REQUIRED_FIELDS.difference(row)
        if missing:
            raise ValueError(f"row {index} is missing: {', '.join(sorted(missing))}")
        if row.get("error"):
            continue
        public_row = {field: row[field] for field in sorted(REQUIRED_FIELDS)}
        public_row.update({field: row.get(field) for field in sorted(OPTIONAL_FIELDS)})
        public_rows.append(public_row)

    public_rows.sort(
        key=lambda row: (row["pass_rate"], row["avg_efficiency"], -row["seconds"]),
        reverse=True,
    )
    output = {
        "track": payload.get("track", "single"),
        "task_set": payload.get("task_set", "seed"),
        "generated_from": source.name,
        "rows": public_rows,
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    build(args.source, args.destination)


if __name__ == "__main__":
    main()
