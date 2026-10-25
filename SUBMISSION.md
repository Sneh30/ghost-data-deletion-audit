# Submission artifacts

Public repository: <https://github.com/Sneh30/ghost-data-deletion-audit>

Release with downloadable artifacts:
<https://github.com/Sneh30/ghost-data-deletion-audit/releases/tag/submission-v1>

| Artifact | Path | Details |
|---|---|---|
| Submission CSV | [`output.csv`](output.csv) | 518 rows, 3,044 steps, validator 0 errors / 0 warnings |
| Submission highlights | [`HIGHLIGHTS.txt`](HIGHLIGHTS.txt) | Factual cover page: differentiators, verified metrics, reviewer's map |
| AI chat transcript | [`ai_chat_transcript.txt`](ai_chat_transcript.txt) | Full transcript plus highlights cover, 313 messages, 1,590,284 bytes |
| Unmodified transcript | [`agent-trace/opencode/ses_e8e4b25a2ffe7t9LnTN8HJYGRC.txt`](agent-trace/opencode/ses_e8e4b25a2ffe7t9LnTN8HJYGRC.txt) | Pure session export, 313 messages, 1,586,472 bytes |
| Raw session export | [`agent-trace/opencode/ses_e8e4b25a2ffe7t9LnTN8HJYGRC.json`](agent-trace/opencode/ses_e8e4b25a2ffe7t9LnTN8HJYGRC.json) | OpenCode structured export |
| Packaged code | [`code.zip`](code.zip) | 37 files, no dataset, includes evaluation reports |
| Trace archive | [release asset](https://github.com/Sneh30/ghost-data-deletion-audit/releases/download/submission-v1/agent-trace.zip) | ZIP of `agent-trace/` (readable transcript + raw JSON) |

## Output CSV

Direct download: <https://github.com/Sneh30/ghost-data-deletion-audit/releases/download/submission-v1/output.csv>

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

Direct download: <https://github.com/Sneh30/ghost-data-deletion-audit/releases/download/submission-v1/ai_chat_transcript.txt>

Presentation copy:

```text
session  ses_e8e4b25a2ffe7t9LnTN8HJYGRC
sha256   709cf86e4e2c95a8be3e662aa4a66797b45c9eb8f6288ff2e2625ca92308c82a
bytes    1,590,284
messages 313
```

The file opens with a candidate-added "Submission Highlights" cover page (also available
as [`HIGHLIGHTS.txt`](HIGHLIGHTS.txt)). The cover is explicitly labeled as not part of the
AI conversation. The conversation body, from `[001]` onward, is the unmodified session
export and is byte-for-byte identical to the pure trace.

Unmodified trace:

```text
sha256  5b35568f40c58096648c7449f4893e5aa47e25a2dd6a0a68af6cdb9e1929289e
bytes   1,586,472
```

The `.txt` is a chronological rendering of the full session: every user prompt, every
assistant response, reasoning traces, tool calls and outputs, system turns, and compaction
summaries. The raw JSON preserves the structured trace. Credentials were not captured; the
only token-shaped strings are the masked `gho_****` output from `gh auth status`.

The session read the provided synthetic dataset while debugging, so the transcript contains
incidental excerpts such as case IDs, synthetic identities, and evidence snippets. The
`dataset/` tree itself is deliberately not published in this repository.

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
