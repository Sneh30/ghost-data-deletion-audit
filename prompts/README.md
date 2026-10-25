# Prompts

This solution is deterministic at inference time and makes **zero model calls**. The prompts below document the contract that the code implements and provide an optional review prompt for a human or an LLM reviewer.

Files:

- `deletion_audit_agent.md` — the full task/contract prompt used as the design reference for the deterministic agent.
- `evidence_reviewer.md` — an optional second-pass reviewer prompt for checking a single case without changing the deterministic output.

The production path does not read these files. They are included so the decision rules, evidence policy, and output schema are auditable.
