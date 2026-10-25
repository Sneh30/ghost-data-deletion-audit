# Data Notes — Ghost Data Deletion Audit

Everything below was derived by opening every participant-facing file in `dataset/` (all CSVs, all 94 evidence files) and inspecting schemas, row counts, categorical values, and sample rows. `dataset/` is treated as read-only input.

## 1. File inventory

| File | Rows | Columns | Notes |
|---|---:|---|---|
| `deletion_requests.csv` | 518 | `case_id,email,requested_at,reported_status,reported_at,audit_at,request_text` | **Not sorted** in the raw file (first row `case_33`, last `case_550`). IDs are `case_33` … `case_550`, exactly 518 unique. |
| `sample_deletion_requests.csv` | 32 | same 7 columns | `case_01` … `case_32`; disjoint from the 518 evaluation cases. |
| `sample_output.csv` | 32 | `case_id,deletion_status,steps_json` | 10 COMPLETE, 22 INCOMPLETE, 0 NOT_APPLICABLE. |
| `user_identities.csv` | 850 | `user_id,name,email,phone,email_hash,updated_at` | One current snapshot per user; no duplicate emails; 3 duplicate names (different people). |
| `user_audit_log.csv` | 306 | `audit_id,user_id,event_time,field_name,old_value,new_value` | 196 users; 107 email changes, 107 email_hash changes, 92 phone changes. Audit IDs are `audit_01` … `audit_306`. |
| `system_activity.csv` | 4011 | `activity_id,event_time,event_type,source_system,target_system,resource_id,reported_result,details` | Global, noisy, interleaved across unrelated people. 3948 distinct resource IDs. |
| `deletion_rules.csv` | 15 | `rule_id,data_category,condition,required_action` | Decision table, see §5. |
| `evidence_files.csv` | 94 | `file_id,file_path,origin,captured_at` | IDs `evidence_01` … `evidence_94`. Captured 2026-01-29 … 2026-10-01. |
| `output.csv` | 0 | `case_id,deletion_status,steps_json` | Blank template. |

## 2. Categorical values

### Requests

- `reported_status` (518): `COMPLETE` 254, `PARTIALLY_COMPLETE` 152, `NOT_STARTED` 112.
- `reported_status` (sample 32): `COMPLETE` 17, `NOT_STARTED` 10, `PARTIALLY_COMPLETE` 5.
- `requested_at` range: 2026-01-05 … 2026-09-24.
- `audit_at` range: 2026-01-29 … 2026-10-01. All timestamps are UTC `...Z`, second precision.
- 29/32 sample request emails match a current identity; the remaining 3 match a historical email in `user_audit_log`.
- All 518 evaluation emails resolve to exactly **one** user via current email (418) or a historical email in the audit log (101); one email is both current for one user and historical for another but the two candidates are the same user (`user_18`, which has two cases: `case_33`, `case_52`). Normalized (case-folded, trimmed) matching is sufficient; no plus-addressing occurs.
- Request text is English, Spanish, French, Japanese, and Portuguese; lengths 86–252 chars. All request texts in the data are deletion/erasure requests. The evaluation set may include non-deletion texts and must be classified.

### Activity

`event_type` counts:

```
DELETE_RECORD 890, UPDATE_RECORD 672, SYNC_RECORD 447, INDEX_RECORD 400,
SEND_EMAIL 368, REFRESH_CACHE 284, RETAIN_RECORD 206, ANONYMIZE_RECORD 204,
REDACT_RECORD 173, CREATE_EXPORT 155, CHECK_DATA_FLOW 89,
DISABLE_DATA_FLOW 36, BLOCK_RESTORE 36, CHECK_RESTORE_ACCESS 28,
LINK_RESOURCE_IDENTITY 12, CLASSIFY_REQUEST 10, RESTORE_BACKUP 1
```

`reported_result` ∈ {`SUCCESS`, `FAILED`, `PARTIAL`}. Results are **claims**: many `DELETE_RECORD ... SUCCESS` rows are contradicted by evidence (replica/backup still has the row), and many `FAILED` rows are actually absent in evidence. `SYNC_RECORD` after a delete can recreate data. `CHECK_DATA_FLOW` says “remains enabled” (all reported SUCCESS), `CHECK_RESTORE_ACCESS` says “can still be restored” (all reported SUCCESS). `RESTORE_BACKUP` has one real row (`activity_3387`, 2026-08-22, backup_9287 → search_4882) which is the sample/global restore-risk example.

Resource ID prefixes: `account_`, `search_`, `analytics_`, `support_`, `email_delivery_`, `cache_`, `audit_record_`, `export_`, `data_flow_`, `backup_`, `tombstone_`, `legal_hold_`, `object_`, `marketing_`.

Only 12 `LINK_RESOURCE_IDENTITY` rows explicitly link a resource to an email/user:
`account_5762→user_11`, `search_428→user_13`, `data_flow_1121→user_14`,
`analytics_7438→user_20`, `export_1260→user_18`, `support_1034→user_22`,
`backup_9287→user_16`, `object_19→user_07`, `marketing_001→user_09`,
`export_1842→user_18`, `audit_record_003→user_03`, `tombstone_17→user_17`.
Everything else must be connected through evidence contents.

### Rules

| rule_id | data_category | condition | action |
|---|---|---|---|
| rule_01 | USER_PROFILE | Always | DELETE |
| rule_02 | SECONDARY_IDENTIFIER | Always | DELETE |
| rule_03 | SEARCH_INDEX_ENTRY | Always | DELETE |
| rule_04 | CACHE_ENTRY | Always | DELETE |
| rule_05 | SUPPORT_MESSAGE | Conversation contains shared customer/agent/order context that must be retained | REDACT |
| rule_06 | SUPPORT_ATTACHMENT | Attachment belongs only to the deletion subject | DELETE |
| rule_07 | ANALYTICS_PROFILE | Record is still attributable to a user | ANONYMIZE |
| rule_08 | PRODUCT_TELEMETRY | Record is still attributable to a user | ANONYMIZE |
| rule_09 | USER_EXPORT | Always | DELETE |
| rule_10 | MARKETING_PROFILE | Always | DELETE |
| rule_11 | EMAIL_DELIVERY_LOG | Log contains a user email address | REDACT |
| rule_12 | SECURITY_AUDIT_LOG | Within retention period | RETAIN |
| rule_13 | LEGAL_HOLD_RECORD | Legal hold active | RETAIN |
| rule_14 | BACKUP_ARCHIVE | Restore access can be blocked | RETAIN |
| rule_15 | ACCOUNT_TOMBSTONE | Deleted account, stable user_id needed for retained references | REDACT |

The policy is a condition→action table, not a flat category map. `RETAIN` means the record must still exist; `BACKUP_ARCHIVE` is retained but its restore path must be blocked; `ACCOUNT_TOMBSTONE` keeps `user_id`/`customer_reference` and removes name/email/phone/email_hash.

## 3. Evidence formats (94 files)

| Format | Count | What it contains |
|---|---:|---|
| `.sql` | 24 | SQLite-compatible snapshots. Three families: (a) `customer_data_inventory_*` with 8 per-system tables + `snapshot_scope`; (b) `customer_data_read_replica_*` / `regional_replicas` / `reporting_replica` / `failover_replica` with `customer_data_primary` + one or more replica tables of `record_json`; (c) `customer_accounts_failover_replica_*` with full `customer_profiles_primary` / `_failover_replica` tables; (d) `customer_search_primary_*` with one search table. |
| `.json` | 28 | Four families: (a) `service_resource_export_*` with per-service arrays (`profile_lookups`, `profiles`, `restore_entries`, `exports`, `connectors`, `index_queries`, `audit_records`, `tickets`); (b) `customer_data_snapshot_bundle_*` with `snapshots[]` each having `data_store`, `collection`, `records[]`; (c) flat lookup manifests (`connector_configurations`, `customer_export_manifest`, `security_audit_ledger`) with `system,resource_id,record_type,result,subject_reference`; (d) `customer_analytics_report_*`, `customer_export_jobs_*`. |
| `.log` | 26 | Eight line dialects: `level=... service=... event=... k=v`, `[DEBUG] [service] [trace] event: k="v"`, `ts | LEVEL | service | trace | event | k="v"`, JSON-per-line, syslog `<15>1 node service trace - - k="v"`, CloudWatch `requestId=... message="... event=..."`, `record_lookup` lines, and `readback_collector` traces. All are parseable with a generic `k=v` tokenizer after unquoting/nesting. |
| `.txt` | 1 | `customer_account_handover_20261001.txt`: pipe-delimited lines `timestamp | system | resource_id | record_type | state | identifier`. Very high-signal, covers many users. |
| `.pdf` | 4 | `account_history_report_20260718` (customer statement, user_18), `delivery_correction_attachment` (support attachment `support_001`, user_07), `legal_retention_register_20260529` (retained disputed orders for user_08/12/17/21/24/29), `security_retention_extract` (retained `audit_record_003`, user_03). Text is extractable with `pypdf`; no OCR needed for PDFs. |
| `.png` | 11 | Admin consoles/screenshots: account admin, search inspector, connector management, analytics view, export console, support ticket, backup restore, security audit explorer, deleted-account reference, object storage, marketing profile. Facts are in the pixels; extracted with macOS Vision OCR (or a vision model) and cached. |

Manifest `origin` values describe the exporting tool (e.g. `records_assurance_snapshot_bundle`, `customer_data_read_replica_capture`, `central_observability_export`), not the case. The manifest never identifies the case/user; linkage is by contents.

## 4. Identity resolution

- Match request email after `strip().lower()` against current identities.
- Else search `user_audit_log` where `field_name='email'`, matching `old_value` or `new_value`; recover **all** historical emails, email hashes, and phones for that `user_id` effective at or before `audit_at`.
- Email hash is `sha256(lowercased, trimmed email)` — verified for all 850 identities.
- Phone matching should normalize to digits (formats vary: `+1 (202) 555-0103`, `+33 6 24 34 80 16`, `+55 11 96954-2024`).
- Name variants occur in evidence (e.g. `Mateo Ríos` vs `Mateo Rios Gil`, `Priya Raman` vs `Priya Ramanathan`); name alone is not a safe join key. Use email/hash/phone/user_id; names are supporting identifiers only.
- 29/32 sample emails are current; 3 are historical. All 518 evaluation emails resolve.

## 5. Sample-output reverse engineering (summary; full detail in `docs/rules_learned.md`)

- Gold output selects **one evidence file per case**, the latest captured-at ≤ `audit_at` that contains any direct fact for the case’s user/resources. That same `evidence_id` is cited on every step of the case, including account-absent steps whose account_* ID is not literally present in the file.
- COMPLETE cases list only VERIFICATION steps. INCOMPLETE cases list FINDING(s), then REMEDIATION, then VERIFICATION. NOT_APPLICABLE would be `[]`.
- Verification for INCOMPLETE covers the **entire known resource set** (both already-compliant copies and remediated copies), plus retained audit records and flow/restore checks. It is not just one check per remediation.
- Retained `SECURITY_AUDIT_LOG` is verified PRESENT in almost every case that has one; it is never deleted.
- `ANALYTICS_PROFILE` is verified ANONYMIZED; `SUPPORT_MESSAGE` REDACTED; `SUPPORT_ATTACHMENT` and `SEARCH_INDEX_ENTRY`/`USER_EXPORT`/`USER_PROFILE` ABSENT.
- `ACCOUNT_TOMBSTONE` is verified REDACTED (compliant) or found PRESENT and remediated with REDACT.
- `DATA_FLOW` active → finding + DISABLE + VERIFY DISABLED; `BACKUP_ARCHIVE` restorable → finding + BLOCK + VERIFY BLOCKED.
- Evidence IDs in sample are all `evidence_01/02/03/05/06/10/.../94`; the special end-of-run snapshots `evidence_51`–`evidence_94` cover the sample families.

## 6. Ordering

Confirmed against every sample row:

1. Phase order `FINDING` → `REMEDIATION` → `VERIFICATION`.
2. Within a phase, operation order is exactly the table order in the problem statement (not alphabetical).
3. Then `system_id` ascending, then `resource_id` ascending. Plain lexicographic string order matches all sample ties; no sample has a numeric-ID tie that distinguishes natural vs lexicographic sort. We implement plain string ascending (`sorted()`), which is the literal reading of “ascending”.
4. `step_no` is 1-based, consecutive across the whole array.
5. No duplicate `(phase, operation, system_id, resource_id)` tuples.

## 7. Data quality / traps observed

- `reported_status` is deliberately misleading: `COMPLETE` sample cases include 15 INCOMPLETE; `NOT_STARTED` sample cases include 4 COMPLETE.
- `system_activity.reported_result` is also misleading in both directions.
- Replication drift: `customer_data_read_replica` / `regional_replicas` / `reporting_replica` can contain rows absent from primary (sample case_05: account_005 only in failover replica; case_16: account_994 in both).
- Backup restore: `restore_allowed=1` / `restore_allowed=true` is an active risk even when the account itself is gone. `CHECK_RESTORE_ACCESS` SUCCESS means “can still be restored”.
- Active connector: `enabled=1` / `enabled=true` is an active data flow; `CHECK_DATA_FLOW` SUCCESS means “remains enabled”.
- Tombstones: `identity_service.deleted_customer_references` rows with only `subject_reference` are compliant; rows with name/email/phone/hash are exposed PII.
- Some evidence files are decoys/noise for unrelated users (`operational_record_history` with 39–43 system events, generic service logs with cache/DNS/webhook errors).
- Some evidence files are captured **after** `audit_at` for a case and must be ignored for that case.
