# Evaluation Report

## Scope

This report evaluates the deterministic deletion-audit agent on the 32 public sample cases and profiles the 518-row full submission. The solution uses only participant-visible data under `dataset/`.

Reference environment:

- Python 3.14 virtual environment
- `pandas`, `pypdf`, `pillow`
- macOS Vision OCR through `tools/ocr.swift`
- warm fact cache for the timed full run

No model calls are used at inference time. See `usage_report.md` for token and cost accounting.

## 1. Public sample results

The scorer is `code/evaluate.py`. It compares status, exact step arrays, step signatures, and individual fields.

| Metric | Result |
|---|---:|
| Case/status accuracy | **32 / 32 (100.00%)** |
| Row accuracy (status + exact steps) | **30 / 32 (93.75%)** |
| Sequence accuracy (exact step array) | **30 / 32 (93.75%)** |
| Field accuracy (6 content fields) | **98.96%** |
| Field accuracy including `step_no` | **98.67%** |
| Step precision | **100.00%** |
| Step recall | **98.96%** |
| Step F1 | **99.48%** |
| Gold steps / predicted steps / matched | **193 / 191 / 191** |

Status confusion:

```text
COMPLETE   -> COMPLETE    10
INCOMPLETE -> INCOMPLETE  22
```

The two row/sequence misses are:

| Case | Gold status | Pred status | Difference |
|---|---|---|---|
| `case_18` | INCOMPLETE | INCOMPLETE | Missing `VERIFY_RECORD_PRESENT` for `audit_record_6645` |
| `case_20` | INCOMPLETE | INCOMPLETE | Missing `VERIFY_RECORD_PRESENT` for `audit_record_5569` |

Both audit IDs are absent from every participant-visible evidence file, `system_activity.csv` row, and OCR text. The agent does not fabricate IDs. These two misses are therefore retained and documented rather than patched with case-specific guesses.

## 2. Full submission profile

`output.csv`:

| Metric | Result |
|---|---:|
| Data rows | **518** |
| Total steps | **3,044** |
| `COMPLETE` | **159** |
| `INCOMPLETE` | **349** |
| `NOT_APPLICABLE` | **10** |
| Phase counts | FINDING 670 / REMEDIATION 670 / VERIFICATION 1,704 |
| Facts extracted | **2,917** |
| Evidence files parsed | **94** |
| Images OCR'd | **11** |
| Warm full-run time | **43.57 s** |

Hard validator (`code/validate.py`):

```text
rows: 518
steps: 3044
status_counts: {'INCOMPLETE': 349, 'COMPLETE': 159, 'NOT_APPLICABLE': 10}
errors: 0
warnings: 0
```

The validator checks row count, numeric ordering, exact header, seven-key schema, vocabulary, phase/operation/state compatibility, deterministic ordering, evidence existence, no post-audit citations, `NOT_APPLICABLE` emptiness, and the COMPLETE/INCOMPLETE evidence rules.

Tests:

```text
Ran 10 tests in 0.001s
OK
```

## 3. Custom evaluation cases

The custom cases are synthetic and live in `tests/test_agent.py`. They pin the contract independently of the private corpus.

| Case | Scenario | Expected | Result |
|---|---|---|---|
| `case_901` | Account, search entry, and audit log are compliant and citable | `COMPLETE`; only evidence-backed `VERIFICATION` steps | Pass |
| `case_902` | Support message, analytics profile, active flow, and active backup are non-compliant | `INCOMPLETE`; findings, full remediation, future verification with empty evidence | Pass |
| `case_903` | Request asks for a copy of data, not deletion | `NOT_APPLICABLE`; `steps_json=[]` | Pass |
| `case_904` | Account is `PRESENT` only in late-captured evidence | `COMPLETE`; late-only state cannot establish non-compliance; no steps without citable evidence | Pass |
| `case_905` | Account tombstone is `PRESENT` | `REPORT_EXPOSED_PII` → `REDACT_RECORD` → `VERIFY_RECORD_REDACTED` | Pass |
| `case_906` | Flow disabled, backup blocked, analytics anonymized | `COMPLETE`; three evidence-backed verification operations | Pass |
| `case_907` | Citable non-compliance plus a late-only bad account | `INCOMPLETE`; finding only for citable resource; late resource kept as future remediation/verification | Pass |

Additional tests cover compact JSON key order and the scorer’s handling of a missing step.

## 4. Failures found and improvements made

### 4.1 `case_45` and the image rule

**Failure.** The first implementation trusted only the single catalog link row in the security audit screenshot. The image showed six signed events for `user_03`, but only `audit_record_003` had a `LINK_RESOURCE_IDENTITY` row, so five same-subject audit records were omitted.

**Improvement.** Added a general subject-filter rule in `code/evidence.py`:

- It fires only when OCR contains an explicit `Subject filter: <subject>` line.
- It requires every visible `user_*` reference to match that filter subject.
- It includes every same-family resource shown in the scoped table, normalizing OCR variants such as `audit_record 004` → `audit_record_004`.
- It ignores screenshots without a subject filter and screens containing other users.

**Result.** Only `case_45` changed. Its output went from one verification step (`audit_record_003`) to six (`audit_record_001`–`audit_record_006`), all citing `evidence_37`. The other image-backed cases (`case_34`, `35`, `39`, `46`, `50`, `52`, `53`, `55`, `61`, `63`) were unchanged. Sample accuracy stayed at 32/32 status and 30/32 exact steps, so the change was kept.

### 4.2 The 113 full cases with no audit-record step

**Baseline.** 24/32 sample cases had an audit step (75.0%); 405/508 full deletion cases had one (79.7%), or 405/518 including `NOT_APPLICABLE` (78.2%). The sample rate was slightly lower than the full rate, so the 113 missing cases were not obviously anomalous.

**Audit sample.** Ten random non-image cases (`case_149`, `185`, `240`, `340`, `352`, `43`, `443`, `484`, `492`, `95`) plus five image-only cases (`case_35`, `39`, `50`, `52`, `53`) were checked.

| Classification | Count | Cases |
|---|---:|---|
| Genuine no audit resource at `audit_at` | 11 | `case_149`, `185`, `352`, `43`, `443`, `95`, `35`, `39`, `50`, `52`, `53` |
| Missed by extraction | 4 | `case_240`, `340`, `484`, `492` |

`case_53` does contain an audit record, but it was observed on 2026-09-15 for an audit on 2026-05-25, so it is not part of the audit-time state.

**Root cause.** JSON `operational_record_history` rows carry an explicit `record_type` and `lookup_value`. The extractor classified them as generic `SYSTEM_EVENT`s and ignored both fields, so audit rows were parsed but never tied to the user.

**General fix.** In `code/evidence.py`:

- An explicit JSON `record_type` is authoritative over the enclosing collection name.
- `lookup_value` is attached as the owner only when the lookup succeeded (`FOUND`, `PRESENT`, `IDENTIFIABLE`, etc.).
- `NOT_FOUND` rows are not treated as ownership evidence, avoiding invented account relationships.

**Result.** 21 cases changed, all gained one `VERIFICATION` / `security_service` / `VERIFY_RECORD_PRESENT` step. No status changed. Sample accuracy stayed 32/32 and 30/32.

Changed audit cases:

```text
case_234 audit_record_4438    case_333 audit_record_4647    case_340 audit_record_3872
case_236 audit_record_9285    case_334 audit_record_8558    case_341 audit_record_2862
case_237 audit_record_2859    case_337 audit_record_1961    case_342 audit_record_4058
case_240 audit_record_8918    case_338 audit_record_9226    case_483 audit_record_4738
case_241 audit_record_436     case_484 audit_record_5270    case_485 audit_record_4405
case_242 audit_record_3046    case_487 audit_record_1039    case_488 audit_record_6252
case_489 audit_record_1372    case_490 audit_record_5868    case_492 audit_record_9341
```

After the fix, 92 cases still have no audit step. A record-level sweep of all 92 found no further same-user, in-window audit records. The remaining raw hits were other users’ rows, outside the 7-day window, or observed after `audit_at`.

### 4.3 Heuristic risk review

Full-set usage (`case_33`–`case_550`, 508 deletion cases):

| Heuristic | Cases used | Ambiguous | Fallback |
|---|---:|---:|---:|
| Account — direct fact | 216 | 0 | 0 |
| Account — activity pairing | 282 | 118 | 0 |
| Account — synthetic fallback | 0 | 0 | 0 |
| Anonymous analytics | 92 cases / 155 rows | 87 | 59 |

- **Account activity pairing:** 118 of 282 cases had more than one candidate account event and/or more than one competing case. The deterministic tie-break is: match `reported_status`, order cases by `requested_at` descending with `case_id` ascending, and pair with events by `event_time` ascending. These are medium confidence.
- **Direct account facts:** no case had multiple candidate account resources.
- **Account fallback:** no full-set case uses the synthetic fallback. The only fallback is sample `case_04` → `account_004`, supported by `evidence_54` and `evidence_90`; the sample gold expects it.
- **Anonymous analytics:** 66 cases had multiple candidate rows/cases; 59 used a fallback method (`single` 51, `remainder` 8). The union is 87 cases. Block assignments with one row and one eligible case are high confidence; block assignments with multiple candidates are medium; single/remainder/unique-file assignments are low.
- **Unassigned accounts:** 10 image-only cases (`case_33`, `35`, `39`, `45`, `50`, `52`, `53`, `55`, `61`, `63`) have no account event and no complete snapshot proving a conventional account ID.

The full ambiguous-case list, candidate IDs, deciding signals, and confidence labels are in [`docs/ambiguous_cases.md`](../docs/ambiguous_cases.md). No output was changed for these heuristics because the deterministic ordering still reproduces the samples.

### 4.4 `case_126`: late-only PRESENT evidence (Pass 2 fix)

`case_126` has `account_8819` observed at `2026-08-11T10:00:00Z`, before the `2026-08-17T10:00:00Z` audit, but captured in `evidence_12` on `2026-08-19T10:00:00Z`, after the audit.

**Failure.** The planner derived the status from every bad resource, including non-citable late captures. `account_8819` was the only bad resource, so the case became `INCOMPLETE` with no `FINDING` and a validator warning. A post-audit capture cannot prove the state at `audit_at`; an `INCOMPLETE` case without a citable finding is also structurally invalid.

**General fix.** In `code/planner.py`, status now uses only citable non-compliance with a non-empty citation:

```python
citable_bads = [r for r in bads if r.citable and r.evidence_id]
status = "INCOMPLETE" if citable_bads else "COMPLETE"
```

Late-only bads remain in the remediation/verification lists only when a citable bad already makes the case incomplete. That preserves the sample-proven behavior for cases such as `case_09`, where late-captured `account_3960` and `audit_record_4902` are expected future checks, while preventing late evidence from creating an unsupported status.

**Result.** Only `case_126` changed:

| | Before | After |
|---|---|---|
| Status | `INCOMPLETE` | `COMPLETE` |
| Steps | 3 | 1 |
| FINDING | none | none |
| REMEDIATION | `DELETE_RECORD account_8819` | none |
| VERIFICATION | `VERIFY_RECORD_ABSENT account_8819`; `VERIFY_RECORD_PRESENT audit_record_6884` | `VERIFY_RECORD_PRESENT audit_record_6884` (`evidence_87`) |
| Validator | 1 warning | 0 warnings |

The late account remains in discovery state but is not emitted because a `COMPLETE` case may only contain citable verification.

### 4.5 Pass 2 adversarial review: B7–B10

Pass 2 checked intent, identity, time cutoff, and claim independence. Each defect was reproduced with a mutation or counterexample, then the full pipeline was rerun.

| Sub-check | Result | Proof |
|---|---|---|
| B7.1 request-intent classification | PASS | 508/518 eval requests authorize deletion; the 10 non-deletion texts (`case_533`–`case_542`) are genuine correction/access/export/marketing/negation requests; all 10 become `NOT_APPLICABLE`; no deletion text is rejected |
| B7.2 intent independent of activity claims | PASS | Removing all 10 `CLASSIFY_REQUEST` rows produced **0 output diffs**; the classifier reads `request_text` only |
| B7.3 `NOT_APPLICABLE` serialization | PASS | 10/10 NA rows have `steps_json=[]`; the 10 activity claims agree one-for-one; no sample case is non-deletion |
| B8.1 current + historical identifier resolution | PASS | 550/550 cases resolved (518 eval + 32 sample); 3 sample historical emails (`case_10`, `case_29`, `case_30`) resolve to the correct user; 189/189 audited eval cases contain every expected current/audit identifier with 0 omissions |
| B8.2 strong-token matching, no name joins | PASS | 0 resources matched without an email/phone/hash/`user_*` token; 0 same-name/different-user resources; renaming all 850 identity names to one decoy produced **0 output diffs** |
| B8.3 ambiguity and reuse | PASS | 0 ambiguous email→user resolutions; 0 emails shared across users; 0 identity snapshots updated after `audit_at`; 0 post-cutoff identifiers included; `user_18` cases `case_33`/`case_52` use their own audit windows |
| B9.1 no observations after the cutoff | PASS | 0 resources with `observed_at > audit_at`; all 670 findings have a non-empty evidence ID; 0 findings cite late evidence |
| B9.2 citable seven-day window | PASS | 1,418 citable resources; 0 captured before `audit_at − 7d` or after `audit_at`; 0 accounts whose latest pre-audit fact predates the window |
| B9.3 late-only evidence handling | PASS after fix | 193 late-only resources in 141 cases; 0 cited; 167 future-verification steps in 116 already-incomplete eval cases; sample `case_09` confirms late discovery is expected future work; the one late-only bad (`case_126`) no longer determines status |
| B10.1 status is not copied from claims | PASS | Sample status accuracy 32/32 while 11 of 17 `COMPLETE` claims are truly `INCOMPLETE` and 3 of 10 `NOT_STARTED` claims are truly `COMPLETE` |
| B10.2 status mutation independence | PASS | Flipping 50 `reported_status` values (10 NA + 40 stratified) changed **0** deletion statuses |
| B10.3 full step-list mutation independence | **FAIL** | Flipping those 50 statuses changed 18 step lists (16 account-ID swaps, 2 account-step drops); flipping 50 `DELETE_RECORD` results changed 26 step lists (24 swaps, 2 drops). All differences are confined to `account_service` verification; no phase, finding, evidence, operation, or status change. A claim-free control drops sample exact-step from **30/32 to 24/32** (field 98.96% → 94.82%), below the required sample floor, so it was not adopted. |

**Metrics before and after the implemented fix:**

| Metric | Before | After |
|---|---:|---:|
| Rows | 518 | 518 |
| Status `INCOMPLETE` / `COMPLETE` / `NOT_APPLICABLE` | 350 / 158 / 10 | 349 / 159 / 10 |
| Total steps | 3,046 | 3,044 |
| FINDING / REMEDIATION / VERIFICATION | 670 / 671 / 1,705 | 670 / 670 / 1,704 |
| Validator | 0 errors, 1 warning | 0 errors, 0 warnings |
| Tests | 9/9 | 10/10 |
| Sample status accuracy | 32/32 | 32/32 |
| Sample exact-step accuracy | 30/32 | 30/32 |
| Sample field accuracy | 98.96% | 98.96% |
| Determinism | two runs byte-identical | two runs byte-identical |

**Defect fixed.** B9 late-only status inflation (`case_126`). Root cause and general rule are in §4.4. Only one case changed; no sample regression.

**Defect not fixed.** B10.3 account disambiguation inside a multi-case intake batch uses the claim signals `reported_status`/`reported_result`. The activity stream has no case/user foreign key, so when several account events fall in one batch, the claim-to-result correlation is the only signal that reproduces the sample mapping. Removing it is a measured sample regression, not a safe general fix. This remains a documented low/medium-confidence heuristic; the final `deletion_status` is still derived only from citable evidence and never from claims.

**Pass 2 verdict: Pass 3 needed.** B11–B15 were not run in this pass.

### 4.6 Earlier extraction hardening

The following general fixes were made before the four checks above:

- TXT handover field 4 is authoritative for `record_type`; state and identifier are merged from fields 5 and 6.
- `contact_lookup_completed` and `contact_query_completed` map to `SECONDARY_IDENTIFIER` / `DELETE`.
- Support attachments delete; support messages redact direct PII; support messages with only a stable user reference are treated as already redacted.
- SQL `backup_archives` and `data_flow` honor `restore_allowed` / `enabled`.
- Nested JSON `record_json` and `document` fields are flattened.
- Snapshot records use their own `captured_at` as `observed_at`.
- System IDs are normalized by the longest resource prefix rather than trusting the evidence file’s origin service.
- Account mapping uses direct evidence first, then batch/status/time pairing, then the absence-proof fallback.
- Anonymous analytics rows use `ANONYMIZE_RECORD` activity events, the following support/flow/backup block, and last-to-first assignment.
- Snapshot absence proofs prefer dedicated account snapshots / records-assurance bundles over broad inventories, then the latest capture before audit.

## 5. Known limitations and risks

1. **Two sample rows are not exactly reproducible.** `case_18` and `case_20` reference audit IDs that do not exist in participant-visible evidence. The current result is 30/32 exact.
2. **92 full cases have no audit step.** Record-level review found no further in-window same-user audit records, but hidden truth may include IDs that are not participant-visible.
3. **Ten image-only cases have no account mapping.** They are not forced onto a guessed account ID.
4. **Heuristic ambiguity.** 118 account activity assignments and 87 analytics assignments had multiple candidates or used a fallback. The full list and confidence labels are in `docs/ambiguous_cases.md`.
5. **Late-only evidence.** `case_126` is now `COMPLETE` from its one citable audit-record verification. The late-captured `account_8819` is retained only as discovery state. Hidden gold could instead treat that late `PRESENT` account as a finding, but that would require a finding without a citable evidence ID and is not adopted.
6. **Per-case account artifacts.** Account IDs are per-case artifacts in the synthetic data, not stable per-user IDs. The account mapping heuristic is therefore case-level, not identity-level.
7. **Deterministic-only.** No LLM is used, so the agent cannot reason about an unforeseen evidence format. The extractor covers every format present in the participant corpus.
8. **Claim-based batch disambiguation.** For 18/518 status mutations and 26/518 result mutations, the account ID chosen inside a multi-case batch changes. The final status, findings, and evidence are unchanged. The alternative claim-free pairing loses 6 sample exact-step matches, so this is a documented residual risk rather than a code defect that can be fixed without regression.

## 6. Reproducibility

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r code/requirements.txt

python -m code.main --refresh
python -m code.main
python -m code.main --samples --out /tmp/sample_pred.csv
python -m code.evaluate --pred /tmp/sample_pred.csv
python -m code.validate --output output.csv
python -m unittest discover -s tests -v
```

Expected sample result: 32/32 status, 30/32 exact steps, 98.96% field accuracy. Expected validation: 518 rows, 3,044 steps, 0 errors, 0 warnings. Expected tests: 10/10 passing.
