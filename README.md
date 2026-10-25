# Ghost Data Still Exists — Deletion Audit Agent

Deterministic, evidence-first solution for the HackerRank Orchestrate October 2026 challenge.

The agent answers one question for every deletion request:

> At `audit_at`, does any personal data or recreation path still exist, and what must be done next?

It ignores `reported_status` and `system_activity.reported_result` as claims. It reconstructs the state from participant-visible evidence, applies the policy table, and emits the required ordered step list.

## Public repository

<https://github.com/Sneh30/hackerrank-hackathon>

**Submission artifacts:** [`output.csv`](output.csv) · [`log.txt`](log.txt) · [`code.zip`](code.zip) · [`HIGHLIGHTS.txt`](HIGHLIGHTS.txt) · [`SUBMISSION.md`](SUBMISSION.md)

`log.txt` is the repository-root chat transcript required by the challenge. The longer
[`ai_chat_transcript.txt`](ai_chat_transcript.txt) is a supplementary full-session export
with a clearly labeled highlights cover page; its conversation body is unmodified.

## Why this submission stands out

- **Deterministic at inference.** Zero model calls, zero network calls, $0.00 API cost.
  The same 518-row CSV is reproducible from source.
- **Claims are not evidence.** `reported_status` and `system_activity.reported_result` are
  treated as assertions. State is reconstructed from logs, SQL snapshots, PDFs, OCR'd
  screenshots, and audit records.
- **Time-travel correct.** A fact is citable only when its evidence was captured at or
  before `audit_at`. Late facts become future work, never FINDING citations.
- **Evidence discipline.** Every `COMPLETE` verification cites real evidence. No evidence
  IDs are invented to chase a sample score.
- **Verified results.** 518/518 case IDs, 3,044 steps, validator 0 errors / 0 warnings,
  10/10 tests, 32/32 sample status, 30/32 exact-step, 98.96% field accuracy, 43.57 s
  runtime.
- **Honest about limits.** The two sample misses (`case_18`, `case_20`) are documented,
  and the B10.3 residual risk is quantified instead of hidden.

## Approach

The solution is intentionally deterministic. No model calls, no network calls, and no paid APIs are used at inference time.

1. **Request intent.** Multilingual rule patterns decide whether the text authorizes deletion. Non-deletion requests become `NOT_APPLICABLE` with `steps_json=[]`.
2. **Identity resolution.** The request email is resolved through the current identity snapshot and the historical audit log. Strong identifiers are email, phone, email hash, and stable `user_*` ID. Names are not used for matching.
3. **Evidence extraction.** Logs, JSON, SQL, PDF text, TXT handovers, and screenshots are normalized into `Fact` records. Local macOS Vision OCR is used for images and cached by file hash.
4. **State reconstruction.** For each resource, the latest fact observed at or before `audit_at` wins. A fact is citable only if its evidence file was captured at or before `audit_at`. Facts observed before audit but captured later are used for discovery and future verification, never as a FINDING citation.
5. **Policy.** The category state is compared with `deletion_rules.csv`. Non-compliant resources produce findings, remediation, and future verification. Compliant resources produce evidence-backed verification in a `COMPLETE` case.
6. **Account and analytics joins.** When the evidence does not name the account directly, a deterministic pairing uses `reported_status`, `requested_at`, `event_time`, and the intake batch. Identifier-free analytics rows are attached through `ANONYMIZE_RECORD` events and the following support/flow/backup block. The risk report is in [`docs/ambiguous_cases.md`](docs/ambiguous_cases.md).
7. **Serialization.** Steps use the exact seven-key schema, contiguous `step_no`, and deterministic phase/operation/system/resource ordering.

## Repository layout

```text
code/
  main.py          entry point
  run.py           end-to-end pipeline and fact cache
  loader.py        dataset loader
  intent.py        request classification
  identity.py      current + historical identity resolution
  evidence.py      fact extraction from every evidence format
  ocr.py           cached local OCR wrapper
  state.py         state reconstruction, account/analytics joins
  rules.py         policy mapping and step ordering
  planner.py       COMPLETE / INCOMPLETE / NOT_APPLICABLE step generation
  serialize.py     canonical JSON/CSV writer
  evaluate.py      sample scorer
  validate.py      hard output validator
  requirements.txt
  evaluation/
    evaluation_report.md
    usage_report.md
docs/
  data_notes.md
  ambiguous_cases.md
prompts/
  README.md
  deletion_audit_agent.md
tests/
  test_agent.py
tools/
  ocr.swift
output.csv
```

The `dataset/` directory is required at runtime but is **not** included in `code.zip`.

## Setup

Python 3.12+ is recommended. The reference environment used Python 3.14.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r code/requirements.txt
```

Local OCR on macOS uses the Vision framework through `tools/ocr.swift`. OCR results are cached in `.cache/ocr/`; delete that directory to force re-OCR. The pipeline still runs without OCR for non-image evidence, but image-backed cases need it.

## Run

Generate the 518-row submission from the repository root:

```bash
python -m code.main
```

Re-extract all evidence facts first (recommended after changing an extractor):

```bash
python -m code.main --refresh
```

Run the 32 public samples:

```bash
python -m code.main --samples --out /tmp/sample_pred.csv
```

Score the samples:

```bash
python -m code.evaluate --pred /tmp/sample_pred.csv
# or run the samples in memory:
python -m code.evaluate
```

Run the hard output validator:

```bash
python -m code.validate --output output.csv
```

Run the tests:

```bash
python -m unittest discover -s tests -v
```

## Output contract

```text
case_id,deletion_status,steps_json
```

- Exactly 518 data rows, sorted numerically by `case_id`.
- `deletion_status` is `COMPLETE`, `INCOMPLETE`, or `NOT_APPLICABLE`.
- `NOT_APPLICABLE` has `steps_json=[]`.
- `COMPLETE` contains only `VERIFICATION` steps, each with an evidence-backed `evidence_id`.
- `INCOMPLETE` contains `FINDING` steps with evidence, then the full `REMEDIATION` plan, then future `VERIFICATION` checks. All remediation and future verification steps use `evidence_id=""`.
- Each step has exactly these keys: `step_no`, `phase`, `system_id`, `resource_id`, `operation`, `state`, `evidence_id`.
- Phase order is `FINDING`, `REMEDIATION`, `VERIFICATION`; within a phase, operation order follows the challenge vocabulary, then `system_id`, then `resource_id` lexicographically.

## Evaluation summary

Public sample set:

| Metric | Result |
|---|---:|
| Status accuracy | 32 / 32 (100.00%) |
| Exact-step matches | 30 / 32 (93.75%) |
| Field accuracy (6 content fields) | 98.96% |
| Field accuracy including `step_no` | 98.67% |
| Step precision / recall / F1 | 100.00% / 98.96% / 99.48% |

Full submission:

| Status | Rows |
|---|---:|
| `COMPLETE` | 159 |
| `INCOMPLETE` | 349 |
| `NOT_APPLICABLE` | 10 |
| **Total** | **518** |

Hard validator: **0 errors, 0 warnings**. Tests: **10 passing**.

The only sample mismatches are `case_18` and `case_20`. Each is missing one `audit_record_*` verification step whose ID (`audit_record_6645`, `audit_record_5569`) does not appear anywhere in participant-visible evidence. Fabricating those IDs would be worse than the two known misses.

## Evidence rules and known risks

- **7-day window.** Citable evidence must be captured within the 7 days before `audit_at`. Late facts can add future verification IDs but cannot be cited.
- **Late-only PRESENT data.** `case_126` is now `COMPLETE` from its one citable audit-record verification. A late-captured `PRESENT` account cannot determine the status; late facts remain future work only when a citable finding already makes the case incomplete. This matches the sample-proven behavior for `case_09`.
- **Image subject filter.** A screenshot with an explicit `Subject filter: user_*` and no other visible user is treated as a scoped table, so every same-subject audit record in it is included. This is why `case_45` contains `audit_record_001`–`audit_record_006`.
- **Account heuristics.** 118 of 282 activity-paired accounts had multiple candidates. The deterministic batch/status/time ordering resolves them. Mutating workflow claims changes 18 (status) or 26 (result) account IDs but never the deletion status; a claim-free control would lose 6 sample exact-step matches, so this remains a documented residual risk. The full ambiguity list is in [`docs/ambiguous_cases.md`](docs/ambiguous_cases.md).
- **No audit step.** 92 of 508 deletion cases have no audit step after the extraction fix. Record-level review found no further same-user, in-window audit records; they are genuine no-audit-at-audit cases.
- **Unassigned accounts.** 10 image-only cases have no account event and no complete snapshot proving a conventional account ID. They are not forced onto a guessed account.

## Reports

- [`code/evaluation/evaluation_report.md`](code/evaluation/evaluation_report.md) — metrics, custom cases, failures, improvements, and risks.
- [`code/evaluation/usage_report.md`](code/evaluation/usage_report.md) — model/token/cost accounting (zero model calls).
- [`docs/ambiguous_cases.md`](docs/ambiguous_cases.md) — heuristic risk report.
- [`docs/data_notes.md`](docs/data_notes.md) — initial data exploration notes.

## Packaging

Create `code.zip` from the repository root without the dataset, virtual environment, caches, or secrets:

```bash
zip -r code.zip README.md code prompts docs tests tools \
  -x "*/__pycache__/*" "*/.venv/*" "*/.cache/*" "*.DS_Store"
```

Do not include `dataset/`, `.venv/`, `.cache/`, `__pycache__/`, or nested archives. The root `output.csv` and `log.txt` are submitted separately.
