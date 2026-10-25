# Submission artifacts

Public repository: <https://github.com/Sneh30/ghost-data-deletion-audit>

| Artifact | Path | Details |
|---|---|---|
| Submission CSV | [`output.csv`](output.csv) | 518 rows, 3,044 steps, validator 0 errors / 0 warnings |
| AI chat transcript | [`ai_chat_transcript.txt`](ai_chat_transcript.txt) | Full readable transcript, 313 messages, 1,586,472 bytes |
| Raw session export | [`agent-trace/opencode/ses_e8e4b25a2ffe7t9LnTN8HJYGRC.json`](agent-trace/opencode/ses_e8e4b25a2ffe7t9LnTN8HJYGRC.json) | OpenCode structured export |
| Packaged code | [`code.zip`](code.zip) | 37 files, no dataset, includes evaluation reports |

## Output CSV

```text
sha256  f6f1cbe1953ee5e4624d2a8f8dedac3ca472f121c0290ad95f7f280bb730e10b
bytes   608,214
rows    518
columns case_id,deletion_status,steps_json
```

Status counts: **349 INCOMPLETE**, **159 COMPLETE**, **10 NOT_APPLICABLE**.

Validation:

```text
steps: 3044
phase_counts: {'FINDING': 670, 'REMEDIATION': 670, 'VERIFICATION': 1704}
errors: 0
warnings: 0
```

## Transcript

```text
session ses_e8e4b25a2ffe7t9LnTN8HJYGRC
sha256  5b35568f40c58096648c7449f4893e5aa47e25a2dd6a0a68af6cdb9e1929289e
```

The `.txt` is a chronological rendering of the full session: every user prompt, every
assistant response, reasoning traces, tool calls and outputs, system turns, and compaction
summaries. The raw JSON preserves the structured trace. Credentials were not captured; the
only token-shaped strings are the masked `gho_****` output from `gh auth status`.

## Reproducing

The `dataset/` directory is intentionally excluded from this public repository because the
challenge data is supplied separately by HackerRank. Place the provided `dataset/` at the
repository root, install `code/requirements.txt`, then run:

```bash
python -m code.main
python -m code.validate --output output.csv
python -m unittest discover -s tests -v
```

The reference run is deterministic and uses zero model calls.
