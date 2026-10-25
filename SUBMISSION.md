# Submission artifacts

Public repository: <https://github.com/Sneh30/hackerrank-hackathon>

Release with downloadable artifacts:
<https://github.com/Sneh30/hackerrank-hackathon/releases/tag/submission-v1>

| Artifact | Path | Details |
|---|---|---|
| Submission CSV | [`output.csv`](output.csv) | 518 rows, 3,044 steps, validator 0 errors / 0 warnings |
| Chat transcript | [`log.txt`](log.txt) | Repository-root log, plain text, 208 lines, 12,295 bytes — the challenge-required chat transcript |
| Submission highlights | [`HIGHLIGHTS.txt`](HIGHLIGHTS.txt) | Factual cover page: differentiators, verified metrics, reviewer's map |
| Supplementary transcript | [`ai_chat_transcript.txt`](ai_chat_transcript.txt) | 313-message session export plus highlights cover, 1,591,269 bytes |
| Unmodified transcript | [`agent-trace/opencode/ses_e8e4b25a2ffe7t9LnTN8HJYGRC.txt`](agent-trace/opencode/ses_e8e4b25a2ffe7t9LnTN8HJYGRC.txt) | Pure session export, 313 messages, 1,586,472 bytes |
| Raw session export | [`agent-trace/opencode/ses_e8e4b25a2ffe7t9LnTN8HJYGRC.json`](agent-trace/opencode/ses_e8e4b25a2ffe7t9LnTN8HJYGRC.json) | OpenCode structured export |
| Packaged code | [`code.zip`](code.zip) | 31 files, no dataset, includes evaluation reports |
| Trace archive | [release asset](https://github.com/Sneh30/hackerrank-hackathon/releases/download/submission-v1/agent-trace.zip) | ZIP of `agent-trace/` (readable transcript + raw JSON) |

## Chat transcript

The challenge contract (§6.9) requires the repository-root `log.txt`. That is the submitted
chat transcript: plain text, one file, no archive.

Direct download: <https://github.com/Sneh30/hackerrank-hackathon/releases/download/submission-v1/log.txt>

```text
sha256  490be67a6570df1d354136ecc703e99c7fd842be980d33f34a1bfa803a6d241f
bytes   12,295
lines   208
```

It summarizes the build, the Pass 2 audit, packaging, public-repo publishing, transcript
export, and the repository rename. `ai_chat_transcript.txt` is a supplementary full-session
export with a candidate-added highlights cover page; the conversation body from `[001]` is
the unmodified session export.

## Output CSV

Direct download: <https://github.com/Sneh30/hackerrank-hackathon/releases/download/submission-v1/output.csv>

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

## Supplementary full transcript

Direct download: <https://github.com/Sneh30/hackerrank-hackathon/releases/download/submission-v1/ai_chat_transcript.txt>

```text
session  ses_e8e4b25a2ffe7t9LnTN8HJYGRC
sha256   2797197967cc130215a17b073054b67fcfd72bca64124abb45e134348f6e98cc
bytes    1,591,269
messages 313
```

The file opens with a candidate-added "Submission Highlights" cover page (also available
as [`HIGHLIGHTS.txt`](HIGHLIGHTS.txt)), explicitly labeled as not part of the AI
conversation. The conversation body, from `[001]` onward, is the unmodified session export
and is byte-for-byte identical to the pure trace. The body records the repository under its
original name, `ghost-data-deletion-audit`; GitHub redirects that URL to
`hackerrank-hackathon`.

Unmodified trace:

```text
sha256  5b35568f40c58096648c7449f4893e5aa47e25a2dd6a0a68af6cdb9e1929289e
bytes   1,586,472
```

The `.txt` is a chronological rendering of the session: every user prompt, every assistant
response, reasoning traces, tool calls and outputs, system turns, and compaction summaries.
The raw JSON preserves the structured trace. Credentials were not captured; the only
token-shaped strings are the masked `gho_****` output from `gh auth status`.

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
