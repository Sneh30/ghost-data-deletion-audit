"""Turn a case state into the exact ordered step list."""
from __future__ import annotations

from .rules import (
    finding_operation,
    is_compliant,
    remediation_operation,
    remediation_state,
    step_sort_key,
    verification_operation,
)
from .state import CaseState, RELEVANT_TYPES, Resource, is_bad


def _step(phase: str, operation: str, resource: Resource, state: str, evidence_id: str) -> dict:
    return {
        "step_no": 0,
        "phase": phase,
        "system_id": resource.system_id,
        "resource_id": resource.resource_id,
        "operation": operation,
        "state": state,
        "evidence_id": evidence_id,
    }


def _synthetic_account(cs: CaseState) -> Resource:
    return Resource(
        system_id="account_service",
        resource_id=cs.account_id,
        record_type="USER_PROFILE",
        state="ABSENT",
        evidence_id="",
        citable=False,
        note="account state synthesized from the intake record",
    )


def _ordered(resources: list[Resource]) -> list[Resource]:
    return sorted(resources, key=lambda r: (r.system_id, r.resource_id))


def plan_case(cs: CaseState) -> tuple[str, list[dict]]:
    """Return (deletion_status, ordered_steps) for one case."""
    if not cs.case.is_deletion:
        return "NOT_APPLICABLE", []

    resources = [r for r in cs.resources if r.record_type in RELEVANT_TYPES]
    # An account id is known but no account snapshot/row was found.  The
    # deletion workflow still needs an absent account verified; for an
    # incomplete case this is a future verification (empty evidence).
    if cs.account_id and not any(r.resource_id == cs.account_id for r in resources):
        resources.append(_synthetic_account(cs))
    resources = _ordered(resources)

    bads = [r for r in resources if is_bad(r)]
    # Only a resource proven non-compliant by evidence captured at or before
    # audit_at can make the case incomplete.  A late capture may reveal a
    # resource for future remediation, but it cannot establish the state at
    # audit_at on its own.  Keeping late-only bads in `bads` below is
    # intentional: when another citable bad already makes the case
    # incomplete, the late resource is still remediated and verified.
    citable_bads = [r for r in bads if r.citable and r.evidence_id]
    status = "INCOMPLETE" if citable_bads else "COMPLETE"

    if status == "COMPLETE":
        steps: list[dict] = []
        for r in resources:
            if not is_compliant(r) or not r.citable or not r.evidence_id:
                continue
            op = verification_operation(r.record_type, r.state)
            steps.append(_step("VERIFICATION", op, r, r.state, r.evidence_id))
        steps.sort(key=step_sort_key)
        for i, step in enumerate(steps, 1):
            step["step_no"] = i
        return status, steps

    steps = []
    # FINDINGS.  Every finding must cite participant-visible evidence.  A
    # late-only observation is still used for the future verification list,
    # but cannot be used as a finding.
    for r in bads:
        if not r.citable or not r.evidence_id:
            continue
        op = finding_operation(r.record_type)
        steps.append(_step("FINDING", op, r, r.state, r.evidence_id))

    # REMEDIATION.  Disable flows / block restores first (operation order),
    # then delete, redact, or anonymize every non-compliant record.
    for r in bads:
        target = remediation_state(r.record_type)
        op = remediation_operation(r.record_type)
        steps.append(_step("REMEDIATION", op, r, target, ""))

    # VERIFICATION.  Cover the account (if known) and every discovered
    # resource in its required final state.  These are future checks, so the
    # evidence id is always empty for an INCOMPLETE case.
    for r in resources:
        target = remediation_state(r.record_type) if is_bad(r) else r.state
        op = verification_operation(r.record_type, target)
        steps.append(_step("VERIFICATION", op, r, target, ""))

    steps.sort(key=step_sort_key)
    for i, step in enumerate(steps, 1):
        step["step_no"] = i
    return status, steps
