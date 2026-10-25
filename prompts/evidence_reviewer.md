# Optional Evidence Reviewer Prompt

This prompt is for a second-pass review of one case. It is not used by the production pipeline. The deterministic output remains authoritative; a reviewer may only flag a case for human inspection.

## Task

Review one deletion case against the participant-visible evidence.

Return:

1. the identity tokens you used;
2. each resource found, its system, category, state at `audit_at`, and the supporting file;
3. whether the file was captured at or before `audit_at`;
4. any resource that is present only in late-captured evidence;
5. any account or analytics join that required a heuristic;
6. whether the deterministic output should be kept, or flagged with a concrete reason.

## Rules

- Do not use names alone to match a person.
- Do not trust `reported_status` or `system_activity.reported_result`.
- Do not cite evidence captured after `audit_at`.
- Do not invent IDs.
- If the evidence is insufficient, say so and keep the deterministic result.
- If a screenshot has an explicit subject filter, treat every row in that scoped table as belonging to the filtered subject unless another user is visible.
- If a heuristic had multiple candidates, state the candidates and the signal that resolved them.

## Output

Use a compact table:

| Resource | System | State at audit | Evidence | Citable | Note |
|---|---|---|---|---|---|

Then add:

```text
Decision: KEEP | FLAG
Reason:
Confidence: high | medium | low
```
