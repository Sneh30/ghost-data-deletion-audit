"""Score an output CSV against a gold CSV.

The public sample set is the only labelled data, so this is the primary
regression gate.  The scorer deliberately reports several views of the same
prediction:

* status accuracy - the headline contract;
* exact-step matches - whole arrays equal;
* step precision/recall/F1 - exact 6-field step signatures;
* field accuracy - individual fields on aligned steps;
* a status confusion matrix and per-case missing/extra steps.

Run it without ``--pred`` to execute the 32 public samples in memory:

    python -m code.evaluate

Or score a file that was already generated:

    python -m code.evaluate --pred /tmp/sample_pred.csv
"""
from __future__ import annotations

import argparse
import collections
import csv
import difflib
import json
import sys
from pathlib import Path
from typing import Iterable

from .serialize import STEP_KEYS, steps_json

ROOT = Path(__file__).resolve().parent.parent
CONTENT_KEYS = tuple(key for key in STEP_KEYS if key != "step_no")
ALLOWED_STATUSES = ("COMPLETE", "INCOMPLETE", "NOT_APPLICABLE")


def load_output(path: str | Path) -> list[dict]:
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _steps(row: dict) -> list[dict]:
    if "steps" in row:
        return list(row["steps"])
    raw = row.get("steps_json", "[]")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{row.get('case_id')}: invalid steps_json: {exc}") from exc
    if not isinstance(value, list):
        raise ValueError(f"{row.get('case_id')}: steps_json is not a list")
    return value


def _signature(step: dict) -> tuple:
    return tuple(step.get(key, "") for key in CONTENT_KEYS)


def _as_output_rows(rows: Iterable[dict]) -> list[dict]:
    out = []
    for row in rows:
        if "steps_json" not in row:
            row = dict(row)
            row["steps_json"] = steps_json(row.get("steps", []))
        out.append(row)
    return out


def score(gold_rows: Iterable[dict], pred_rows: Iterable[dict]) -> dict:
    """Return a JSON-serialisable score report."""
    gold = {row["case_id"]: row for row in _as_output_rows(gold_rows)}
    pred = {row["case_id"]: row for row in _as_output_rows(pred_rows)}

    all_ids = sorted(set(gold) | set(pred))
    common_ids = sorted(set(gold) & set(pred))
    missing_cases = sorted(set(gold) - set(pred))
    extra_cases = sorted(set(pred) - set(gold))

    status_ok = 0
    exact_cases = 0
    confusion: collections.Counter = collections.Counter()

    gold_steps = 0
    pred_steps = 0
    matched_steps = 0
    field_matches = 0
    full_field_matches = 0
    aligned_pairs = 0
    per_case: list[dict] = []

    for case_id in all_ids:
        g_row = gold.get(case_id)
        p_row = pred.get(case_id)
        g_status = g_row["deletion_status"] if g_row else "(missing)"
        p_status = p_row["deletion_status"] if p_row else "(missing)"
        confusion[(g_status, p_status)] += 1

        if g_row and p_row and g_status == p_status:
            status_ok += 1

        g_steps = _steps(g_row) if g_row else []
        p_steps = _steps(p_row) if p_row else []
        gold_steps += len(g_steps)
        pred_steps += len(p_steps)

        if g_row and p_row and g_steps == p_steps:
            exact_cases += 1

        g_sigs = [_signature(step) for step in g_steps]
        p_sigs = [_signature(step) for step in p_steps]
        g_counter = collections.Counter(g_sigs)
        p_counter = collections.Counter(p_sigs)
        matched = 0
        for signature, count in g_counter.items():
            matched += min(count, p_counter.get(signature, 0))
        matched_steps += matched

        # Field accuracy is measured on sequence-aligned steps.  A missing
        # gold step contributes zero matches; an extra prediction step does
        # not inflate the denominator.  This keeps the metric interpretable
        # as "how much of the gold answer did we recover?".
        matcher = difflib.SequenceMatcher(a=g_sigs, b=p_sigs, autojunk=False)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag != "equal":
                continue
            for gi, pi in zip(range(i1, i2), range(j1, j2)):
                aligned_pairs += 1
                field_matches += sum(
                    g_steps[gi].get(key, "") == p_steps[pi].get(key, "")
                    for key in CONTENT_KEYS
                )
                full_field_matches += sum(
                    g_steps[gi].get(key, "") == p_steps[pi].get(key, "")
                    for key in STEP_KEYS
                )

        if g_row and p_row and g_steps != p_steps:
            missing = list((g_counter - p_counter).elements())
            extra = list((p_counter - g_counter).elements())
            per_case.append(
                {
                    "case_id": case_id,
                    "gold_status": g_status,
                    "pred_status": p_status,
                    "gold_steps": len(g_steps),
                    "pred_steps": len(p_steps),
                    "missing_steps": [dict(zip(CONTENT_KEYS, sig)) for sig in missing],
                    "extra_steps": [dict(zip(CONTENT_KEYS, sig)) for sig in extra],
                }
            )
        elif not g_row or not p_row:
            per_case.append(
                {
                    "case_id": case_id,
                    "gold_status": g_status,
                    "pred_status": p_status,
                    "gold_steps": len(g_steps),
                    "pred_steps": len(p_steps),
                    "missing_steps": [],
                    "extra_steps": [],
                }
            )

    precision = matched_steps / pred_steps if pred_steps else 0.0
    recall = matched_steps / gold_steps if gold_steps else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    field_accuracy = field_matches / (len(CONTENT_KEYS) * gold_steps) if gold_steps else 0.0
    full_field_accuracy = full_field_matches / (len(STEP_KEYS) * gold_steps) if gold_steps else 0.0

    return {
        "gold_cases": len(gold),
        "pred_cases": len(pred),
        "common_cases": len(common_ids),
        "missing_cases": missing_cases,
        "extra_cases": extra_cases,
        "status_correct": status_ok,
        "status_accuracy": status_ok / len(gold) if gold else 0.0,
        "exact_cases": exact_cases,
        "exact_step_accuracy": exact_cases / len(gold) if gold else 0.0,
        "gold_steps": gold_steps,
        "pred_steps": pred_steps,
        "matched_steps": matched_steps,
        "step_precision": precision,
        "step_recall": recall,
        "step_f1": f1,
        "field_accuracy": field_accuracy,
        "full_field_accuracy": full_field_accuracy,
        "aligned_step_pairs": aligned_pairs,
        "status_confusion": {
            f"{gold_status}->{pred_status}": count
            for (gold_status, pred_status), count in sorted(confusion.items())
        },
        "pred_status_counts": dict(
            collections.Counter(row["deletion_status"] for row in pred.values())
        ),
        "per_case_diffs": per_case,
    }


def _pct(value: float) -> str:
    return f"{100.0 * value:.2f}%"


def print_report(report: dict) -> None:
    print("Sample evaluation")
    print("-----------------")
    print(
        f"status accuracy:    {report['status_correct']}/{report['gold_cases']} "
        f"({_pct(report['status_accuracy'])})"
    )
    print(
        f"exact-step matches: {report['exact_cases']}/{report['gold_cases']} "
        f"({_pct(report['exact_step_accuracy'])})"
    )
    print(
        f"field accuracy:     {_pct(report['field_accuracy'])} "
        f"(6 content fields; {_pct(report['full_field_accuracy'])} incl. step_no)"
    )
    print(
        "step P/R/F1:        "
        f"{_pct(report['step_precision'])} / "
        f"{_pct(report['step_recall'])} / "
        f"{_pct(report['step_f1'])}"
    )
    print(
        f"steps:              gold={report['gold_steps']} "
        f"pred={report['pred_steps']} matched={report['matched_steps']}"
    )
    print("status confusion:")
    for key, count in report["status_confusion"].items():
        print(f"  {key:36} {count}")
    print("predicted status counts:", report["pred_status_counts"])
    if report["missing_cases"]:
        print("missing cases:", ", ".join(report["missing_cases"]))
    if report["extra_cases"]:
        print("extra cases:", ", ".join(report["extra_cases"]))
    if report["per_case_diffs"]:
        print("case diffs:")
        for diff in report["per_case_diffs"]:
            print(
                f"  {diff['case_id']}: gold={diff['gold_status']} "
                f"pred={diff['pred_status']} steps {diff['gold_steps']}->{diff['pred_steps']}"
            )
            for step in diff["missing_steps"]:
                print("    missing:", step)
            for step in diff["extra_steps"]:
                print("    extra:  ", step)
    else:
        print("case diffs: none")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score deletion-audit output")
    parser.add_argument("--gold", default=str(ROOT / "dataset" / "sample_output.csv"))
    parser.add_argument("--pred", default="", help="prediction CSV; omit to run samples")
    parser.add_argument("--json", action="store_true", help="emit the full report as JSON")
    args = parser.parse_args(argv)

    gold_rows = load_output(args.gold)
    if args.pred:
        pred_rows = load_output(args.pred)
    else:
        # Import lazily so scoring a file does not require rebuilding facts.
        from .run import build_rows, extract_facts

        facts = extract_facts(ROOT)
        pred_rows = build_rows(ROOT, facts, mode="sample")

    report = score(gold_rows, pred_rows)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_report(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
