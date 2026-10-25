"""Deterministic CSV/JSON serialization for the submission."""
from __future__ import annotations

import csv
import json
from pathlib import Path

STEP_KEYS = (
    "step_no",
    "phase",
    "system_id",
    "resource_id",
    "operation",
    "state",
    "evidence_id",
)


def canonical_steps(steps: list[dict]) -> list[dict]:
    return [{key: step[key] for key in STEP_KEYS} for step in steps]


def steps_json(steps: list[dict]) -> str:
    return json.dumps(
        canonical_steps(steps),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def write_output(rows: list[dict], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["case_id", "deletion_status", "steps_json"])
        for row in rows:
            writer.writerow(
                [
                    row["case_id"],
                    row["deletion_status"],
                    steps_json(row["steps"]),
                ]
            )
