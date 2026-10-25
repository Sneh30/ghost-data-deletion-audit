"""Policy rules and deterministic step ordering."""
from __future__ import annotations

from .state import GOOD_STATES, Resource, is_bad


PHASES = ("FINDING", "REMEDIATION", "VERIFICATION")

FINDING_OPERATIONS = {
    "REPORT_REMAINING_RECORD": 10,
    "REPORT_EXPOSED_PII": 20,
    "REPORT_ACTIVE_DATA_FLOW": 30,
    "REPORT_RESTORE_RISK": 40,
}
REMEDIATION_OPERATIONS = {
    "DISABLE_DATA_FLOW": 10,
    "BLOCK_RESTORE": 20,
    "DELETE_RECORD": 30,
    "REDACT_RECORD": 40,
    "ANONYMIZE_RECORD": 50,
}
VERIFICATION_OPERATIONS = {
    "VERIFY_RECORD_ABSENT": 10,
    "VERIFY_RECORD_PRESENT": 20,
    "VERIFY_RECORD_REDACTED": 30,
    "VERIFY_RECORD_ANONYMIZED": 40,
    "VERIFY_DATA_FLOW_DISABLED": 50,
    "VERIFY_RESTORE_BLOCKED": 60,
}

OPERATION_ORDER = {
    "FINDING": FINDING_OPERATIONS,
    "REMEDIATION": REMEDIATION_OPERATIONS,
    "VERIFICATION": VERIFICATION_OPERATIONS,
}


def is_compliant(resource: Resource) -> bool:
    return not is_bad(resource)


def finding_operation(record_type: str) -> str:
    if record_type == "DATA_FLOW":
        return "REPORT_ACTIVE_DATA_FLOW"
    if record_type == "BACKUP_ARCHIVE":
        return "REPORT_RESTORE_RISK"
    if record_type in {
        "ANALYTICS_PROFILE",
        "PRODUCT_TELEMETRY",
        "SUPPORT_MESSAGE",
        "ACCOUNT_TOMBSTONE",
    }:
        return "REPORT_EXPOSED_PII"
    return "REPORT_REMAINING_RECORD"


def remediation_operation(record_type: str) -> str:
    if record_type == "DATA_FLOW":
        return "DISABLE_DATA_FLOW"
    if record_type == "BACKUP_ARCHIVE":
        return "BLOCK_RESTORE"
    if record_type in {"SUPPORT_MESSAGE", "EMAIL_DELIVERY_LOG", "ACCOUNT_TOMBSTONE"}:
        return "REDACT_RECORD"
    if record_type in {"ANALYTICS_PROFILE", "PRODUCT_TELEMETRY"}:
        return "ANONYMIZE_RECORD"
    return "DELETE_RECORD"


def remediation_state(record_type: str) -> str:
    op = remediation_operation(record_type)
    return {
        "DISABLE_DATA_FLOW": "DISABLED",
        "BLOCK_RESTORE": "BLOCKED",
        "DELETE_RECORD": "ABSENT",
        "REDACT_RECORD": "REDACTED",
        "ANONYMIZE_RECORD": "ANONYMIZED",
    }[op]


def verification_operation(record_type: str, state: str) -> str:
    if record_type == "DATA_FLOW":
        return "VERIFY_DATA_FLOW_DISABLED"
    if record_type == "BACKUP_ARCHIVE":
        return "VERIFY_RESTORE_BLOCKED"
    return {
        "ABSENT": "VERIFY_RECORD_ABSENT",
        "PRESENT": "VERIFY_RECORD_PRESENT",
        "REDACTED": "VERIFY_RECORD_REDACTED",
        "ANONYMIZED": "VERIFY_RECORD_ANONYMIZED",
    }.get(state, "VERIFY_RECORD_PRESENT")


def step_sort_key(step: dict) -> tuple:
    phase = step["phase"]
    order = OPERATION_ORDER.get(phase, {})
    return (
        PHASES.index(phase),
        order.get(step["operation"], 999),
        step["system_id"],
        step["resource_id"],
    )
