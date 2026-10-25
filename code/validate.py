"""Hard validation of the submitted ``output.csv``.

This validator is intentionally stricter than the sample scorer.  It checks the
submission contract itself, not agreement with the gold answer:

* exactly the 518 evaluation cases, in numeric order;
* the three required columns;
* the seven-key step schema and allowed vocabulary;
* phase/operation/state compatibility;
* deterministic phase, operation, system and resource ordering;
* evidence rules for COMPLETE and INCOMPLETE;
* no post-audit citations;
* NOT_APPLICABLE only for non-deletion requests.

Usage:

    python -m code.validate --output output.csv
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import re
import sys
from pathlib import Path

from .evidence import system_for_resource
from .intent import classify_request
from .loader import load_dataset
from .rules import (
    OPERATION_ORDER,
    PHASES,
    REMEDIATION_OPERATIONS,
    VERIFICATION_OPERATIONS,
    step_sort_key,
)
from .serialize import STEP_KEYS
from .util import ts_key

ROOT = Path(__file__).resolve().parent.parent
STATUSES = {"COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"}
STEP_STATES = {"PRESENT", "ABSENT", "REDACTED", "ANONYMIZED", "DISABLED", "BLOCKED", "ACTIVE"}
FINDING_STATES = {
    "REPORT_REMAINING_RECORD": {"PRESENT"},
    "REPORT_EXPOSED_PII": {"PRESENT"},
    "REPORT_ACTIVE_DATA_FLOW": {"ACTIVE"},
    "REPORT_RESTORE_RISK": {"ACTIVE"},
}
REMEDIATION_STATES = {
    "DISABLE_DATA_FLOW": "DISABLED",
    "BLOCK_RESTORE": "BLOCKED",
    "DELETE_RECORD": "ABSENT",
    "REDACT_RECORD": "REDACTED",
    "ANONYMIZE_RECORD": "ANONYMIZED",
}
VERIFICATION_STATES = {
    "VERIFY_RECORD_ABSENT": "ABSENT",
    "VERIFY_RECORD_PRESENT": "PRESENT",
    "VERIFY_RECORD_REDACTED": "REDACTED",
    "VERIFY_RECORD_ANONYMIZED": "ANONYMIZED",
    "VERIFY_DATA_FLOW_DISABLED": "DISABLED",
    "VERIFY_RESTORE_BLOCKED": "BLOCKED",
}


def _case_number(case_id: str) -> int:
    match = re.search(r"(\d+)$", case_id or "")
    return int(match.group(1)) if match else 0


def _expected_cases(ds) -> list[str]:
    return sorted(ds.requests["case_id"].tolist(), key=_case_number)


def validate(output_path: str | Path, root: str | Path = ROOT) -> tuple[list[str], list[str], dict]:
    """Return ``(errors, warnings, stats)`` for one output file."""
    root = Path(root)
    ds = load_dataset(root)
    errors: list[str] = []
    warnings: list[str] = []

    expected = _expected_cases(ds)
    expected_set = set(expected)
    request_by_case = {row["case_id"]: row for row in ds.requests.to_dict("records")}
    manifest = {row["file_id"]: row for row in ds.manifest.to_dict("records")}

    with Path(output_path).open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration:
            return ["output file is empty"], warnings, {}
        if header != ["case_id", "deletion_status", "steps_json"]:
            errors.append(
                "header must be exactly case_id,deletion_status,steps_json; "
                f"found {header!r}"
            )
        rows = list(reader)

    if len(rows) != len(expected):
        errors.append(f"expected {len(expected)} rows, found {len(rows)}")

    seen: set[str] = set()
    status_counts: collections.Counter = collections.Counter()
    phase_counts: collections.Counter = collections.Counter()
    step_count = 0

    for row_no, row in enumerate(rows, start=2):
        if len(row) != 3:
            errors.append(f"row {row_no}: expected 3 columns, found {len(row)}")
            continue
        case_id, status, raw_steps = row
        if case_id in seen:
            errors.append(f"row {row_no}: duplicate case_id {case_id}")
        seen.add(case_id)
        if case_id not in expected_set:
            errors.append(f"row {row_no}: unexpected case_id {case_id}")
            continue
        status_counts[status] += 1
        if status not in STATUSES:
            errors.append(f"{case_id}: invalid deletion_status {status!r}")
            continue

        try:
            steps = json.loads(raw_steps)
        except json.JSONDecodeError as exc:
            errors.append(f"{case_id}: invalid steps_json: {exc}")
            continue
        if not isinstance(steps, list):
            errors.append(f"{case_id}: steps_json must be a list")
            continue
        step_count += len(steps)

        request = request_by_case[case_id]
        is_deletion = classify_request(request["request_text"]).is_deletion
        if is_deletion and status == "NOT_APPLICABLE":
            errors.append(f"{case_id}: deletion request marked NOT_APPLICABLE")
        if not is_deletion and status != "NOT_APPLICABLE":
            errors.append(f"{case_id}: non-deletion request marked {status}")

        if status == "NOT_APPLICABLE":
            if steps:
                errors.append(f"{case_id}: NOT_APPLICABLE must have steps_json=[]")
            if raw_steps != "[]":
                errors.append(f"{case_id}: NOT_APPLICABLE steps_json should be the empty list")
            continue
        if not steps:
            errors.append(f"{case_id}: {status} case has no steps")
            continue

        finding_count = 0
        remediation_count = 0
        verification_count = 0
        signatures: set[tuple] = set()
        previous_sort: tuple | None = None

        for index, step in enumerate(steps, start=1):
            where = f"{case_id} step {index}"
            if not isinstance(step, dict):
                errors.append(f"{where}: step is not an object")
                continue
            if list(step.keys()) != list(STEP_KEYS):
                errors.append(f"{where}: keys must be exactly {list(STEP_KEYS)}; found {list(step.keys())}")
                continue
            if not isinstance(step["step_no"], int) or step["step_no"] != index:
                errors.append(f"{where}: step_no must be {index}, found {step['step_no']!r}")
            for key in STEP_KEYS[1:]:
                if not isinstance(step[key], str):
                    errors.append(f"{where}: {key} must be a string")
            phase = step["phase"]
            operation = step["operation"]
            state = step["state"]
            phase_counts[phase] += 1
            if phase not in PHASES:
                errors.append(f"{where}: invalid phase {phase!r}")
                continue
            if operation not in OPERATION_ORDER[phase]:
                errors.append(f"{where}: operation {operation!r} is not allowed in {phase}")
                continue
            if state not in STEP_STATES:
                errors.append(f"{where}: invalid state {state!r}")
            if phase == "FINDING":
                finding_count += 1
                if state not in FINDING_STATES.get(operation, set()):
                    errors.append(f"{where}: state {state!r} invalid for {operation}")
            elif phase == "REMEDIATION":
                remediation_count += 1
                expected_state = REMEDIATION_STATES.get(operation)
                if expected_state and state != expected_state:
                    errors.append(
                        f"{where}: {operation} requires state {expected_state}, found {state}"
                    )
            else:
                verification_count += 1
                expected_state = VERIFICATION_STATES.get(operation)
                if expected_state and state != expected_state:
                    errors.append(
                        f"{where}: {operation} requires state {expected_state}, found {state}"
                    )

            canonical_system = system_for_resource(step["resource_id"])
            if canonical_system != "unknown" and canonical_system != step["system_id"]:
                errors.append(
                    f"{where}: system_id {step['system_id']} does not match resource prefix "
                    f"({canonical_system})"
                )
            if not step["system_id"] or not step["resource_id"]:
                errors.append(f"{where}: system_id and resource_id must be non-empty")

            signature = (
                step["phase"],
                step["system_id"],
                step["resource_id"],
                step["operation"],
                step["state"],
                step["evidence_id"],
            )
            if signature in signatures:
                errors.append(f"{where}: duplicate step")
            signatures.add(signature)

            if previous_sort is not None and step_sort_key(step) < previous_sort:
                errors.append(f"{where}: steps are not in deterministic order")
            previous_sort = step_sort_key(step)

            evidence_id = step["evidence_id"]
            if status == "COMPLETE":
                if phase != "VERIFICATION":
                    errors.append(f"{where}: COMPLETE may contain only VERIFICATION steps")
                if not evidence_id:
                    errors.append(f"{where}: COMPLETE verification must cite evidence")
            elif status == "INCOMPLETE":
                if phase == "FINDING":
                    if not evidence_id:
                        errors.append(f"{where}: FINDING must cite evidence")
                elif evidence_id:
                    errors.append(f"{where}: {phase} steps must have evidence_id=''")

            if evidence_id:
                evidence = manifest.get(evidence_id)
                if evidence is None:
                    errors.append(f"{where}: unknown evidence_id {evidence_id!r}")
                else:
                    captured = ts_key(evidence.get("captured_at", ""))
                    audit = ts_key(request.get("audit_at", ""))
                    if captured and audit and captured > audit:
                        errors.append(
                            f"{where}: evidence {evidence_id} was captured after audit_at"
                        )

        if status == "COMPLETE":
            if finding_count or remediation_count:
                errors.append(f"{case_id}: COMPLETE must not contain FINDING or REMEDIATION")
            if not verification_count:
                errors.append(f"{case_id}: COMPLETE must contain at least one VERIFICATION")
        elif status == "INCOMPLETE":
            if not remediation_count:
                errors.append(f"{case_id}: INCOMPLETE must contain REMEDIATION steps")
            if not verification_count:
                errors.append(f"{case_id}: INCOMPLETE must contain VERIFICATION steps")
            if not finding_count:
                warnings.append(
                    f"{case_id}: INCOMPLETE has no FINDING (late-only evidence case?)"
                )

    missing = sorted(expected_set - seen, key=_case_number)
    extra = sorted(seen - expected_set, key=_case_number)
    if missing:
        errors.append(f"missing case_ids: {', '.join(missing)}")
    if extra:
        errors.append(f"unexpected case_ids: {', '.join(extra)}")
    if [row[0] for row in rows if row] != expected:
        errors.append("rows are not in numeric case_id order")

    stats = {
        "rows": len(rows),
        "steps": step_count,
        "status_counts": dict(status_counts),
        "phase_counts": dict(phase_counts),
        "errors": len(errors),
        "warnings": len(warnings),
    }
    return errors, warnings, stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate deletion-audit output.csv")
    parser.add_argument("--output", default=str(ROOT / "output.csv"))
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--limit", type=int, default=50, help="maximum errors to print")
    args = parser.parse_args(argv)

    errors, warnings, stats = validate(args.output, args.root)
    print("Validation")
    print("----------")
    for key in ("rows", "steps", "status_counts", "phase_counts"):
        print(f"{key}: {stats.get(key)}")
    print(f"errors: {len(errors)}")
    print(f"warnings: {len(warnings)}")
    for warning in warnings:
        print("WARNING:", warning)
    for error in errors[: args.limit]:
        print("ERROR:", error)
    if len(errors) > args.limit:
        print(f"... {len(errors) - args.limit} more errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
