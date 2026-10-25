"""Regression tests for the deterministic planner and scorer.

The tests use synthetic ``CaseState`` objects rather than the private dataset
so they run anywhere and pin down the contract independently of the evidence
corpus.  The public sample scorer and the hard output validator are run as
separate CLI gates.
"""
from __future__ import annotations

import json
import unittest

from code.evaluate import score
from code.intent import classify_request
from code.planner import plan_case
from code.serialize import STEP_KEYS, canonical_steps, steps_json
from code.state import CaseRef, CaseState, Resource


def _case(case_id: str, text: str = "Please delete my account and all related data.") -> CaseRef:
    return CaseRef(
        case_id=case_id,
        email="synthetic@example.com",
        requested_at="2026-01-01T10:00:00Z",
        reported_at="2026-01-02T10:00:00Z",
        reported_status="COMPLETE",
        audit_at="2026-01-10T10:00:00Z",
        request_text=text,
        sample=True,
    )


def _resource(
    system_id: str,
    resource_id: str,
    record_type: str,
    state: str,
    evidence_id: str = "",
    *,
    citable: bool = True,
    captured_at: str = "2026-01-05T10:00:00Z",
    observed_at: str = "2026-01-05T10:00:00Z",
) -> Resource:
    return Resource(
        system_id=system_id,
        resource_id=resource_id,
        record_type=record_type,
        state=state,
        evidence_id=evidence_id,
        observed_at=observed_at,
        captured_at=captured_at,
        citable=citable,
    )


class PlannerSyntheticTests(unittest.TestCase):
    def test_complete_case_is_all_evidence_backed_verification(self) -> None:
        state = CaseState(
            case=_case("case_901"),
            identity=None,
            resources=[
                _resource("security_service", "audit_record_1", "SECURITY_AUDIT_LOG", "PRESENT", "evidence_1"),
                _resource("search_service", "search_1", "SEARCH_INDEX_ENTRY", "ABSENT", "evidence_1"),
                _resource("account_service", "account_1", "USER_PROFILE", "ABSENT", "evidence_1"),
            ],
        )

        status, steps = plan_case(state)

        self.assertEqual(status, "COMPLETE")
        self.assertTrue(steps)
        self.assertTrue(all(step["phase"] == "VERIFICATION" for step in steps))
        self.assertTrue(all(step["evidence_id"] == "evidence_1" for step in steps))
        self.assertEqual([step["step_no"] for step in steps], [1, 2, 3])
        self.assertEqual(
            [step["resource_id"] for step in steps],
            ["account_1", "search_1", "audit_record_1"],
        )

    def test_incomplete_case_has_findings_then_full_remediation_and_future_checks(self) -> None:
        state = CaseState(
            case=_case("case_902"),
            identity=None,
            account_id="account_2",
            resources=[
                _resource("account_service", "account_2", "USER_PROFILE", "ABSENT", "evidence_2"),
                _resource("support_platform", "support_2", "SUPPORT_MESSAGE", "PRESENT", "evidence_2"),
                _resource("analytics_platform", "analytics_2", "ANALYTICS_PROFILE", "PRESENT", "evidence_2"),
                _resource("integration_service", "data_flow_2", "DATA_FLOW", "ACTIVE", "evidence_2"),
                _resource("backup_service", "backup_2", "BACKUP_ARCHIVE", "ACTIVE", "evidence_2"),
            ],
        )

        status, steps = plan_case(state)

        self.assertEqual(status, "INCOMPLETE")
        findings = [step for step in steps if step["phase"] == "FINDING"]
        remediation = [step for step in steps if step["phase"] == "REMEDIATION"]
        verification = [step for step in steps if step["phase"] == "VERIFICATION"]

        self.assertEqual(
            [step["operation"] for step in findings],
            [
                "REPORT_EXPOSED_PII",      # analytics_platform sorts before support_platform
                "REPORT_EXPOSED_PII",
                "REPORT_ACTIVE_DATA_FLOW",
                "REPORT_RESTORE_RISK",
            ],
        )
        self.assertTrue(all(step["evidence_id"] == "evidence_2" for step in findings))
        self.assertEqual(
            [step["operation"] for step in remediation],
            [
                "DISABLE_DATA_FLOW",
                "BLOCK_RESTORE",
                "REDACT_RECORD",
                "ANONYMIZE_RECORD",
            ],
        )
        self.assertTrue(all(step["evidence_id"] == "" for step in remediation))
        self.assertTrue(all(step["evidence_id"] == "" for step in verification))
        self.assertIn("VERIFY_RECORD_ABSENT", [step["operation"] for step in verification])

    def test_not_applicable_request_has_no_steps(self) -> None:
        state = CaseState(
            case=_case(
                "case_903",
                "Please send me a copy of the personal information you hold about me.",
            ),
            identity=None,
            resources=[_resource("account_service", "account_3", "USER_PROFILE", "PRESENT", "evidence_3")],
        )

        status, steps = plan_case(state)

        self.assertEqual(status, "NOT_APPLICABLE")
        self.assertEqual(steps, [])

    def test_late_only_present_account_cannot_make_case_incomplete(self) -> None:
        state = CaseState(
            case=_case("case_904"),
            identity=None,
            account_id="account_4",
            resources=[
                _resource(
                    "account_service",
                    "account_4",
                    "USER_PROFILE",
                    "PRESENT",
                    "",
                    citable=False,
                    captured_at="2026-01-12T10:00:00Z",
                    observed_at="2026-01-08T10:00:00Z",
                )
            ],
        )

        status, steps = plan_case(state)

        # A post-audit capture cannot establish the state at audit_at.  With no
        # citable non-compliance the case is complete, and the unverifiable
        # late-only resource is not emitted.
        self.assertEqual(status, "COMPLETE")
        self.assertEqual(steps, [])

    def test_late_only_resource_is_future_work_when_citable_bad_exists(self) -> None:
        state = CaseState(
            case=_case("case_907"),
            identity=None,
            account_id="account_6",
            resources=[
                _resource(
                    "support_platform",
                    "support_6",
                    "SUPPORT_MESSAGE",
                    "PRESENT",
                    "evidence_6",
                ),
                _resource(
                    "account_service",
                    "account_6",
                    "USER_PROFILE",
                    "PRESENT",
                    "",
                    citable=False,
                    captured_at="2026-01-12T10:00:00Z",
                    observed_at="2026-01-08T10:00:00Z",
                ),
            ],
        )

        status, steps = plan_case(state)

        self.assertEqual(status, "INCOMPLETE")
        findings = [step for step in steps if step["phase"] == "FINDING"]
        self.assertEqual([step["resource_id"] for step in findings], ["support_6"])
        self.assertEqual(
            [step["resource_id"] for step in steps if step["phase"] == "REMEDIATION"],
            ["account_6", "support_6"],
        )
        self.assertEqual(
            [step["resource_id"] for step in steps if step["phase"] == "VERIFICATION"],
            ["account_6", "support_6"],
        )
        self.assertIn(
            ("VERIFICATION", "VERIFY_RECORD_ABSENT", "account_6"),
            [(s["phase"], s["operation"], s["resource_id"]) for s in steps],
        )

    def test_tombstone_is_redacted_not_deleted(self) -> None:
        state = CaseState(
            case=_case("case_905"),
            identity=None,
            resources=[
                _resource("identity_service", "tombstone_5", "ACCOUNT_TOMBSTONE", "PRESENT", "evidence_5")
            ],
        )

        status, steps = plan_case(state)

        self.assertEqual(status, "INCOMPLETE")
        self.assertEqual(
            [(step["phase"], step["operation"], step["state"]) for step in steps],
            [
                ("FINDING", "REPORT_EXPOSED_PII", "PRESENT"),
                ("REMEDIATION", "REDACT_RECORD", "REDACTED"),
                ("VERIFICATION", "VERIFY_RECORD_REDACTED", "REDACTED"),
            ],
        )

    def test_compliant_flow_backup_and_analytics_are_complete(self) -> None:
        state = CaseState(
            case=_case("case_906"),
            identity=None,
            resources=[
                _resource("integration_service", "data_flow_6", "DATA_FLOW", "DISABLED", "evidence_6"),
                _resource("backup_service", "backup_6", "BACKUP_ARCHIVE", "BLOCKED", "evidence_6"),
                _resource("analytics_platform", "analytics_6", "ANALYTICS_PROFILE", "ANONYMIZED", "evidence_6"),
            ],
        )

        status, steps = plan_case(state)

        self.assertEqual(status, "COMPLETE")
        self.assertEqual(
            [step["operation"] for step in steps],
            [
                "VERIFY_RECORD_ANONYMIZED",
                "VERIFY_DATA_FLOW_DISABLED",
                "VERIFY_RESTORE_BLOCKED",
            ],
        )


class SerializationTests(unittest.TestCase):
    def test_key_order_and_compact_json(self) -> None:
        steps = [
            {
                "step_no": 1,
                "phase": "FINDING",
                "system_id": "support_platform",
                "resource_id": "support_1",
                "operation": "REPORT_EXPOSED_PII",
                "state": "PRESENT",
                "evidence_id": "evidence_1",
            }
        ]
        raw = steps_json(steps)
        self.assertEqual(raw, '[{"step_no":1,"phase":"FINDING","system_id":"support_platform","resource_id":"support_1","operation":"REPORT_EXPOSED_PII","state":"PRESENT","evidence_id":"evidence_1"}]')
        self.assertEqual(list(json.loads(raw)[0].keys()), list(STEP_KEYS))
        self.assertEqual(canonical_steps(steps)[0], steps[0])


class IntentTests(unittest.TestCase):
    def test_deletion_and_non_deletion(self) -> None:
        self.assertTrue(classify_request("Please delete my account permanently.").is_deletion)
        self.assertFalse(classify_request("I am not asking for deletion; keep my account.").is_deletion)
        self.assertFalse(classify_request("Please send me a copy of my data.").is_deletion)
        self.assertTrue(classify_request("Löschen Sie bitte mein Konto.").is_deletion)


class ScorerTests(unittest.TestCase):
    def test_scores_status_exact_steps_and_missing_step(self) -> None:
        gold = [
            {
                "case_id": "case_1",
                "deletion_status": "COMPLETE",
                "steps_json": steps_json(
                    [
                        {
                            "step_no": 1,
                            "phase": "VERIFICATION",
                            "system_id": "account_service",
                            "resource_id": "account_1",
                            "operation": "VERIFY_RECORD_ABSENT",
                            "state": "ABSENT",
                            "evidence_id": "evidence_1",
                        }
                    ]
                ),
            },
            {
                "case_id": "case_2",
                "deletion_status": "INCOMPLETE",
                "steps_json": steps_json(
                    [
                        {
                            "step_no": 1,
                            "phase": "FINDING",
                            "system_id": "support_platform",
                            "resource_id": "support_1",
                            "operation": "REPORT_EXPOSED_PII",
                            "state": "PRESENT",
                            "evidence_id": "evidence_2",
                        },
                        {
                            "step_no": 2,
                            "phase": "REMEDIATION",
                            "system_id": "support_platform",
                            "resource_id": "support_1",
                            "operation": "REDACT_RECORD",
                            "state": "REDACTED",
                            "evidence_id": "",
                        },
                    ]
                ),
            },
        ]
        pred = [
            gold[0],
            {
                "case_id": "case_2",
                "deletion_status": "INCOMPLETE",
                "steps_json": steps_json(json.loads(gold[1]["steps_json"])[:1]),
            },
        ]

        report = score(gold, pred)

        self.assertEqual(report["status_correct"], 2)
        self.assertEqual(report["exact_cases"], 1)
        self.assertEqual(report["matched_steps"], 2)
        self.assertEqual(len(report["per_case_diffs"]), 1)
        self.assertEqual(report["per_case_diffs"][0]["case_id"], "case_2")
        self.assertEqual(len(report["per_case_diffs"][0]["missing_steps"]), 1)


if __name__ == "__main__":
    unittest.main()
