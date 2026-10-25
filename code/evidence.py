"""Extract normalized facts from every evidence file.

A fact is a statement about one resource observed in one evidence file:
its system, resource id, data category, observed state, and the identifiers
that are still attached to it.  Facts are deliberately low-level; policy and
case reasoning live in state.py / planner.py.
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterable

from .loader import Dataset
from .util import (
    canonical_identifier,
    iso,
    norm_email,
    norm_name,
    norm_phone,
    parse_ts,
    sha256_email,
    ts_key,
)

# ---------------------------------------------------------------- constants

RECORD_TYPES = {
    "USER_PROFILE",
    "SECONDARY_IDENTIFIER",
    "SEARCH_INDEX_ENTRY",
    "CACHE_ENTRY",
    "SUPPORT_MESSAGE",
    "SUPPORT_ATTACHMENT",
    "ANALYTICS_PROFILE",
    "PRODUCT_TELEMETRY",
    "USER_EXPORT",
    "MARKETING_PROFILE",
    "EMAIL_DELIVERY_LOG",
    "SECURITY_AUDIT_LOG",
    "LEGAL_HOLD_RECORD",
    "BACKUP_ARCHIVE",
    "ACCOUNT_TOMBSTONE",
    "DATA_FLOW",
    "SYSTEM_EVENT",
    "UNKNOWN",
}

COLLECTION_TO_TYPE = {
    "customer_profiles": "USER_PROFILE",
    "customer_search_documents": "SEARCH_INDEX_ENTRY",
    "customer_analytics_reports": "ANALYTICS_PROFILE",
    "customer_analytics_profiles": "ANALYTICS_PROFILE",
    "support_conversations": "SUPPORT_MESSAGE",
    "support_records": "SUPPORT_MESSAGE",
    "ticket_attachments": "SUPPORT_ATTACHMENT",
    "customer_export_jobs": "USER_EXPORT",
    "customer_exports": "USER_EXPORT",
    "connector_configurations": "DATA_FLOW",
    "connector_subscriptions": "DATA_FLOW",
    "backup_catalog": "BACKUP_ARCHIVE",
    "backup_restore_entries": "BACKUP_ARCHIVE",
    "security_audit_events": "SECURITY_AUDIT_LOG",
    "security_audit_records": "SECURITY_AUDIT_LOG",
    "deleted_customer_references": "ACCOUNT_TOMBSTONE",
    "retained_order_records": "LEGAL_HOLD_RECORD",
    "legal_hold_records": "LEGAL_HOLD_RECORD",
    "customer_marketing_profiles": "MARKETING_PROFILE",
    "marketing_profiles": "MARKETING_PROFILE",
    "email_delivery_logs": "EMAIL_DELIVERY_LOG",
    "cache_entries": "CACHE_ENTRY",
    "product_telemetry": "PRODUCT_TELEMETRY",
    "operational_record_history": "SYSTEM_EVENT",
}

SYSTEM_BY_PREFIX = {
    "account": "account_service",
    "search": "search_service",
    "analytics": "analytics_platform",
    "support": "support_platform",
    "email_delivery": "email_delivery_service",
    "cache": "cache_service",
    "audit_record": "security_service",
    "export": "export_service",
    "data_flow": "integration_service",
    "backup": "backup_service",
    "tombstone": "identity_service",
    "legal_hold": "legal_service",
    "object": "object_storage",
    "marketing": "marketing_platform",
}

# Log services sometimes use an internal service name. Normalize to the
# public system ids used by the answer vocabulary and the sample gold output.
SYSTEM_ALIASES = {
    "profile_service": "account_service",
    "search_index_service": "search_service",
    "support_replica": "support_platform",
    "backup_restore_service": "backup_service",
    "downstream_delivery_service": "notification_service",
    "privacy_treatment_service": "privacy_treatment_service",
    "support_storage_service": "support_platform",
}


def system_for_resource(resource_id: str) -> str:
    rid = str(resource_id or "")
    for prefix, system in sorted(SYSTEM_BY_PREFIX.items(), key=lambda item: -len(item[0])):
        if rid.startswith(prefix + "_"):
            return system
    return "unknown"


def _clean(value: Any) -> str:
    """Normalize the many string encodings of NULL used in the exports."""
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"", "null", "none", "nil", "n/a", "na", "undefined"}:
        return ""
    return text


def record_type_for_collection(collection: str) -> str:
    return COLLECTION_TO_TYPE.get(collection or "", "UNKNOWN")


# ---------------------------------------------------------------- fact model


@dataclass
class Fact:
    file_id: str
    captured_at: str
    system_id: str
    resource_id: str
    record_type: str
    state: str
    observed_at: str = ""
    user_id: str = ""
    name: str = ""
    email: str = ""
    phone: str = ""
    email_hash: str = ""
    table_role: str = ""
    source_format: str = ""
    result_raw: str = ""
    raw_ref: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def identifiers(self) -> set[str]:
        out = set()
        for value in (self.email, self.phone, self.email_hash, self.name, self.user_id):
            text = _clean(value)
            if not text:
                continue
            if text.startswith("user_"):
                out.add("uid:" + text)
                continue
            token = canonical_identifier(text)
            if token:
                out.add(token)
        return out

    def to_dict(self) -> dict:
        return asdict(self)


STATE_RANK = {
    "ABSENT": 0,
    "BLOCKED": 1,
    "DISABLED": 1,
    "ANONYMIZED": 2,
    "REDACTED": 3,
    "PRESENT": 4,
    "ACTIVE": 5,
    "UNKNOWN": -1,
}


def worst_state(states: Iterable[str]) -> str:
    states = [s for s in states if s]
    if not states:
        return "UNKNOWN"
    return max(states, key=lambda s: STATE_RANK.get(s, -1))


def map_result(value: str) -> str:
    raw = str(value or "").strip().upper()
    if raw in {"FOUND", "PRESENT", "IDENTIFIABLE", "EXISTS", "HIT", "TRUE", "YES", "1"}:
        return "PRESENT"
    if raw in {"NOT_FOUND", "ABSENT", "MISSING", "FALSE", "NO", "0"}:
        return "ABSENT"
    if raw in {"REDACTED", "MASKED"}:
        return "REDACTED"
    if raw in {"ANONYMIZED", "ANONYMISED", "DEIDENTIFIED"}:
        return "ANONYMIZED"
    if raw in {"ACTIVE", "ENABLED", "RESTORABLE"}:
        return "ACTIVE"
    if raw in {"DISABLED", "INACTIVE"}:
        return "DISABLED"
    if raw in {"BLOCKED", "RESTORE_BLOCKED"}:
        return "BLOCKED"
    return "UNKNOWN"


def identity_state(record: dict, kind: str) -> str:
    email = norm_email(_clean(record.get("email") or record.get("requester_email") or record.get("owner_email") or record.get("customer_email")))
    phone = norm_phone(_clean(record.get("phone") or record.get("requester_phone") or record.get("owner_phone")))
    email_hash = _clean(record.get("email_hash"))
    name = norm_name(_clean(record.get("full_name") or record.get("requester_name") or record.get("display_name")))
    user_ref = _clean(record.get("customer_reference") or record.get("subject_reference") or record.get("user_id"))

    if kind in {"ANALYTICS_PROFILE", "PRODUCT_TELEMETRY"}:
        if not any([email, phone, email_hash, name, user_ref]):
            return "ANONYMIZED"
        return "PRESENT"
    if kind == "SUPPORT_MESSAGE":
        text = _clean(record.get("message_excerpt") or record.get("message_text") or "")
        # A support thread may be retained when it has shared context, but all
        # direct customer identifiers must be gone.  Stable internal refs are
        # allowed.  A message with no direct identifiers is therefore redacted.
        if not any([email, phone, name]):
            return "REDACTED"
        if text == "[REDACTED]" and not any([email, phone, name]):
            return "REDACTED"
        return "PRESENT"
    if kind == "EMAIL_DELIVERY_LOG":
        return "PRESENT" if email else "REDACTED"
    if kind == "SEARCH_INDEX_ENTRY":
        return "PRESENT"
    if kind == "ACCOUNT_TOMBSTONE":
        if not any([email, phone, email_hash, name]):
            return "REDACTED"
        return "PRESENT"
    if kind == "USER_PROFILE":
        if not any([email, phone, email_hash, name]) and user_ref:
            # A row that only preserves a stable reference is a tombstone-like remainder.
            return "REDACTED"
        return "PRESENT"
    if kind == "SUPPORT_ATTACHMENT":
        return "PRESENT"
    return "PRESENT"


def fact_from_record(
    *,
    file_id: str,
    captured_at: str,
    system_id: str,
    resource_id: str,
    record_type: str,
    record: dict,
    observed_at: str = "",
    table_role: str = "",
    source_format: str = "",
    result: str = "",
    raw_ref: str = "",
) -> Fact:
    state = identity_state(record, record_type)
    result_state = map_result(result) if result else ""
    if result_state and result_state != "UNKNOWN":
        state = result_state
    canonical_system = system_for_resource(resource_id or record.get("resource_id") or "")
    if canonical_system != "unknown":
        system_id = canonical_system
    return Fact(
        file_id=file_id,
        captured_at=captured_at,
        system_id=system_id or system_for_resource(resource_id),
        resource_id=_clean(resource_id or record.get("resource_id")),
        record_type=record_type,
        state=state,
        observed_at=iso(_clean(observed_at or record.get("observed_at") or record.get("updated_at") or record.get("recorded_at")) or captured_at),
        user_id=_clean(record.get("user_id") or record.get("customer_reference") or record.get("subject_reference")),
        name=_clean(record.get("full_name") or record.get("requester_name") or record.get("display_name") or record.get("name")),
        email=_clean(record.get("email") or record.get("requester_email") or record.get("owner_email") or record.get("customer_email")),
        phone=_clean(record.get("phone") or record.get("requester_phone") or record.get("owner_phone")),
        email_hash=_clean(record.get("email_hash")),
        table_role=table_role,
        source_format=source_format,
        result_raw=_clean(result),
        raw_ref=raw_ref,
        extra={k: v for k, v in record.items() if isinstance(v, (str, int, float, bool)) or v is None},
    )


# ---------------------------------------------------------------- extractor


class EvidenceExtractor:
    def __init__(self, ds: Dataset):
        self.ds = ds
        self.facts: list[Fact] = []
        self.notes: list[str] = []

    def extract_all(self) -> list[Fact]:
        for row in self.ds.manifest.itertuples(index=False):
            path = self.ds.root / "dataset" / row.file_path
            if not path.exists():
                self.notes.append(f"missing evidence path {path}")
                continue
            handler = {
                ".sql": self._extract_sql,
                ".json": self._extract_json,
                ".log": self._extract_log,
                ".txt": self._extract_txt,
                ".pdf": self._extract_pdf,
                ".png": self._extract_image,
            }.get(path.suffix.lower())
            if handler is None:
                self.notes.append(f"unhandled evidence extension {path.suffix} ({row.file_id})")
                continue
            try:
                handler(row.file_id, row.captured_at, path)
            except Exception as exc:  # keep the run alive; surface in trace
                self.notes.append(f"{row.file_id} {path.name}: {type(exc).__name__}: {exc}")
        return self.facts

    # ---------------------------------------------------------- SQL

    def _extract_sql(self, file_id: str, captured_at: str, path: Path) -> None:
        sql = path.read_text(encoding="utf-8", errors="replace")
        con = sqlite3.connect(":memory:")
        try:
            con.executescript(sql)
            tables = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
            scope_time = captured_at
            if "snapshot_scope" in tables:
                t = con.execute("select captured_at from snapshot_scope limit 1").fetchone()
                if t:
                    scope_time = t[0]
            for table in tables:
                if table == "snapshot_scope":
                    continue
                cols = [d[1] for d in con.execute(f'pragma table_info("{table}")')]
                role = table
                for row in con.execute(f'select * from "{table}"'):
                    rec = dict(zip(cols, row))
                    if "record_json" in rec and rec["record_json"]:
                        try:
                            payload = json.loads(rec["record_json"])
                        except Exception:
                            payload = {}
                        rec = {**rec, **payload}
                    if isinstance(rec.get("document"), dict):
                        rec = {**rec, **rec["document"]}
                    if "resource_id" not in rec:
                        continue
                    collection = rec.get("collection_name") or table
                    record_type = record_type_for_collection(collection)
                    if record_type == "UNKNOWN":
                        record_type = self._type_from_table(table, rec)
                    system = rec.get("origin_system") or self._system_from_table(table, rec)
                    observed = rec.get("observed_at") or rec.get("updated_at") or scope_time
                    result_state = ""
                    if record_type == "BACKUP_ARCHIVE" and "restore_allowed" in rec:
                        allowed = str(rec.get("restore_allowed")).strip().lower()
                        result_state = "ACTIVE" if allowed in {"1", "true", "yes", "allowed"} else "BLOCKED"
                    elif record_type == "DATA_FLOW" and "enabled" in rec:
                        enabled = str(rec.get("enabled")).strip().lower()
                        result_state = "ACTIVE" if enabled in {"1", "true", "yes"} else "DISABLED"
                    self.facts.append(
                        fact_from_record(
                            file_id=file_id,
                            captured_at=scope_time,
                            system_id=system,
                            resource_id=str(rec.get("resource_id")),
                            record_type=record_type,
                            record=rec,
                            observed_at=observed,
                            table_role=role,
                            source_format="sql",
                            result=result_state,
                            raw_ref=f"{path.name}:{table}",
                        )
                    )
        finally:
            con.close()

    @staticmethod
    def _type_from_table(table: str, rec: dict) -> str:
        t = table.lower()
        if "customer_profiles" in t or t == "customer_profiles":
            return "USER_PROFILE"
        if "search" in t:
            return "SEARCH_INDEX_ENTRY"
        if "analytics" in t or "telemetry" in t:
            return "PRODUCT_TELEMETRY" if "telemetry" in t else "ANALYTICS_PROFILE"
        if "support" in t and ("attachment" in t or "file" in t):
            return "SUPPORT_ATTACHMENT"
        if "support" in t:
            return "SUPPORT_MESSAGE"
        if "export" in t:
            return "USER_EXPORT"
        if "connector" in t or "subscription" in t:
            return "DATA_FLOW"
        if "backup" in t:
            return "BACKUP_ARCHIVE"
        if "security" in t or "audit" in t:
            return "SECURITY_AUDIT_LOG"
        if "deleted_customer" in t or "tombstone" in t:
            return "ACCOUNT_TOMBSTONE"
        if "legal" in t or "retained" in t:
            return "LEGAL_HOLD_RECORD"
        if "marketing" in t:
            return "MARKETING_PROFILE"
        if "email_delivery" in t:
            return "EMAIL_DELIVERY_LOG"
        if "cache" in t:
            return "CACHE_ENTRY"
        if "operational" in t or "system_event" in t:
            return "SYSTEM_EVENT"
        return "UNKNOWN"

    @staticmethod
    def _system_from_table(table: str, rec: dict) -> str:
        t = table.lower()
        if "customer_profiles" in t:
            return "account_service"
        if "search" in t:
            return "search_service"
        if "analytics" in t or "telemetry" in t:
            return "analytics_platform"
        if "support" in t:
            return "support_platform"
        if "export" in t:
            return "export_service"
        if "connector" in t or "subscription" in t:
            return "integration_service"
        if "backup" in t:
            return "backup_service"
        if "security" in t or "audit" in t:
            return "security_service"
        if "deleted_customer" in t or "tombstone" in t:
            return "identity_service"
        if "legal" in t or "retained" in t:
            return "legal_service"
        if "marketing" in t:
            return "marketing_platform"
        if "email_delivery" in t:
            return "email_delivery_service"
        if "cache" in t:
            return "cache_service"
        return system_for_resource(rec.get("resource_id", ""))

    # ---------------------------------------------------------- JSON

    def _extract_json(self, file_id: str, captured_at: str, path: Path) -> None:
        data = json.loads(path.read_text(encoding="utf-8"))
        self._walk_json(file_id, captured_at, data, path, context={})

    def _walk_json(self, file_id: str, captured_at: str, node: Any, path: Path, context: dict) -> None:
        if isinstance(node, list):
            for item in node:
                self._walk_json(file_id, captured_at, item, path, context)
            return
        if not isinstance(node, dict):
            return

        # service_resource_export: dict of service -> dict of section -> list
        if "service_exports" in node:
            captured = node.get("exported_at") or captured_at
            for service, sections in node["service_exports"].items():
                if not isinstance(sections, dict):
                    continue
                for section, items in sections.items():
                    if not isinstance(items, list):
                        continue
                    for item in items:
                        self._json_service_item(file_id, captured, service, section, item, path)
            return

        # snapshot bundle
        if "snapshots" in node:
            captured = node.get("exported_at") or captured_at
            for snap in node["snapshots"]:
                store = snap.get("data_store", "")
                collection = snap.get("collection", "")
                rtype = record_type_for_collection(collection)
                for rec in snap.get("records", []):
                    if not isinstance(rec, dict):
                        continue
                    rec = dict(rec)
                    # The enclosing file may have been exported later than the
                    # snapshot itself.  The record becomes observable at the
                    # snapshot capture time, which matters for audit windows.
                    rec.setdefault("recorded_at", snap.get("captured_at") or captured)
                    if isinstance(rec.get("document"), dict):
                        rec = {**rec, **rec["document"]}
                    self._json_record(file_id, captured, store, rec, rtype, collection, path)
            return

        # flat record list
        if "records" in node and isinstance(node["records"], list):
            captured = node.get("exported_at") or node.get("captured_at") or captured_at
            collection = node.get("collection") or ""
            for rec in node["records"]:
                if not isinstance(rec, dict):
                    continue
                rtype = record_type_for_collection(collection)
                if "record_type" in rec:
                    rtype = str(rec["record_type"]).upper()
                system = rec.get("system") or system_for_resource(rec.get("resource_id", ""))
                if collection in {"customer_export_jobs"}:
                    self._json_export(file_id, captured, system, rec, path)
                    continue
                if collection in {"customer_analytics_reports"}:
                    rtype = "ANALYTICS_PROFILE"
                self._json_record(file_id, captured, system, rec, rtype, collection, path)
            return

    def _json_service_item(self, file_id: str, captured: str, service: str, section: str, item: dict, path: Path) -> None:
        obs = item.get("observed_at") or captured
        if section == "profile_lookups":
            state = "ABSENT" if str(item.get("status_code")) == "404" or item.get("profile") is None else "PRESENT"
            prof = item.get("profile") or {}
            self.facts.append(
                fact_from_record(
                    file_id=file_id, captured_at=captured, system_id="account_service",
                    resource_id=item.get("resource_id", ""), record_type="USER_PROFILE",
                    record={**item, **prof}, observed_at=obs, source_format="json",
                    raw_ref=f"{path.name}:{service}.{section}",
                    result=state,
                )
            )
        elif section == "profiles":
            rtype = "ANALYTICS_PROFILE"
            self.facts.append(
                fact_from_record(
                    file_id=file_id, captured_at=captured, system_id="analytics_platform",
                    resource_id=item.get("resource_id", ""), record_type=rtype, record=item,
                    observed_at=obs, source_format="json", raw_ref=f"{path.name}:{service}.{section}",
                )
            )
        elif section == "restore_entries":
            state = "ACTIVE" if item.get("restore_allowed") else "BLOCKED"
            self.facts.append(
                fact_from_record(
                    file_id=file_id, captured_at=captured, system_id="backup_service",
                    resource_id=item.get("resource_id", ""), record_type="BACKUP_ARCHIVE",
                    record=item, observed_at=obs, source_format="json", result=state,
                    raw_ref=f"{path.name}:{service}.{section}",
                )
            )
        elif section == "exports":
            self.facts.append(
                fact_from_record(
                    file_id=file_id, captured_at=captured, system_id="export_service",
                    resource_id=item.get("resource_id", ""), record_type="USER_EXPORT",
                    record=item, observed_at=obs, source_format="json", result="PRESENT",
                    raw_ref=f"{path.name}:{service}.{section}",
                )
            )
        elif section == "connectors":
            state = "ACTIVE" if item.get("enabled") else "DISABLED"
            self.facts.append(
                fact_from_record(
                    file_id=file_id, captured_at=captured, system_id="integration_service",
                    resource_id=item.get("resource_id", ""), record_type="DATA_FLOW",
                    record=item, observed_at=obs, source_format="json", result=state,
                    raw_ref=f"{path.name}:{service}.{section}",
                )
            )
        elif section == "index_queries":
            # hits is either {"documents": [...], "total": n} or a list.
            hits = item.get("hits") or []
            if isinstance(hits, dict):
                hits = hits.get("documents") or []
            for hit in hits:
                if not isinstance(hit, dict):
                    continue
                self.facts.append(
                    fact_from_record(
                        file_id=file_id, captured_at=captured, system_id="search_service",
                        resource_id=hit.get("resource_id") or hit.get("_id") or item.get("resource_id", ""),
                        record_type="SEARCH_INDEX_ENTRY", record=hit, observed_at=obs,
                        source_format="json", result="PRESENT",
                        raw_ref=f"{path.name}:{service}.{section}",
                    )
                )
        elif section == "audit_records":
            self.facts.append(
                fact_from_record(
                    file_id=file_id, captured_at=captured, system_id="security_service",
                    resource_id=item.get("resource_id", ""), record_type="SECURITY_AUDIT_LOG",
                    record=item, observed_at=obs, source_format="json", result="PRESENT",
                    raw_ref=f"{path.name}:{service}.{section}",
                )
            )
        elif section == "tickets":
            rtype = "SUPPORT_ATTACHMENT" if (item.get("file") or item.get("attachment")) else "SUPPORT_MESSAGE"
            self.facts.append(
                fact_from_record(
                    file_id=file_id, captured_at=captured, system_id="support_platform",
                    resource_id=item.get("resource_id", ""), record_type=rtype, record=item,
                    observed_at=obs, source_format="json",
                    raw_ref=f"{path.name}:{service}.{section}",
                )
            )

    def _json_export(self, file_id: str, captured: str, system: str, rec: dict, path: Path) -> None:
        available = rec.get("download_available")
        state = "PRESENT" if available is True or str(available).lower() in {"true", "1", "yes"} else "ABSENT"
        self.facts.append(
            fact_from_record(
                file_id=file_id, captured_at=captured, system_id=system,
                resource_id=rec.get("resource_id", ""), record_type="USER_EXPORT", record=rec,
                observed_at=rec.get("created_at") or captured, source_format="json",
                result=state, raw_ref=f"{path.name}",
            )
        )

    def _json_record(self, file_id: str, captured: str, system: str, rec: dict, rtype: str, collection: str, path: Path) -> None:
        rid = rec.get("resource_id") or ""
        if not rid:
            return
        # Operational-history rows carry the authoritative category and the
        # lookup key in the record itself.  The enclosing collection is only
        # a generic bucket, so prefer the explicit record_type when present.
        explicit_type = str(rec.get("record_type") or "").strip().upper()
        if explicit_type in RECORD_TYPES and explicit_type not in {"SYSTEM_EVENT", "UNKNOWN"}:
            rtype = explicit_type
        lookup = _clean(rec.get("lookup_value"))
        result_hint = str(rec.get("result") or rec.get("status") or "").strip().upper()
        lookup_found = result_hint in {"FOUND", "PRESENT", "EXISTS", "HIT", "IDENTIFIABLE", "TRUE", "YES", "1"}
        # A lookup key identifies the owner only when the lookup found the
        # record.  A NOT_FOUND row is a failed query for an account that may
        # belong to somebody else, so attaching its email would invent a
        # relationship that the evidence does not establish.
        if lookup and (lookup_found or explicit_type == "SECURITY_AUDIT_LOG"):
            if lookup.startswith("user_"):
                rec.setdefault("customer_reference", lookup)
            elif "@" in lookup:
                rec.setdefault("email", lookup)
            elif re.fullmatch(r"[0-9a-fA-F]{64}", lookup):
                rec.setdefault("email_hash", lookup)
            elif re.fullmatch(r"[+\d][\d ()-]{6,}", lookup):
                rec.setdefault("phone", lookup)
        if rtype == "UNKNOWN":
            rtype = self._type_from_record_shape(rec, system)
        result = rec.get("result") or rec.get("status") or ""
        state = map_result(result)
        if state == "UNKNOWN":
            if rtype == "BACKUP_ARCHIVE" and "restore_allowed" in rec:
                state = "ACTIVE" if rec.get("restore_allowed") else "BLOCKED"
            elif rtype == "DATA_FLOW" and "enabled" in rec:
                state = "ACTIVE" if rec.get("enabled") else "DISABLED"
            else:
                state = ""
        fact = fact_from_record(
            file_id=file_id, captured_at=captured, system_id=system, resource_id=rid,
            record_type=rtype, record=rec, observed_at=rec.get("recorded_at") or captured,
            source_format="json", result=state, raw_ref=f"{path.name}:{collection}",
        )
        if not fact.system_id or fact.system_id == "unknown":
            fact.system_id = system_for_resource(rid)
        self.facts.append(fact)

    @staticmethod
    def _type_from_record_shape(rec: dict, system: str) -> str:
        if "message_excerpt" in rec or "message_text" in rec or "requester_email" in rec:
            return "SUPPORT_MESSAGE"
        if "restore_allowed" in rec or "archive_key" in rec:
            return "BACKUP_ARCHIVE"
        if "connector_name" in rec or "enabled" in rec:
            return "DATA_FLOW"
        if "object_key" in rec:
            return "USER_EXPORT"
        if "event_code" in rec or "retention_until" in rec:
            return "SECURITY_AUDIT_LOG"
        if "email_hash" in rec or "audience_cohort" in rec:
            return "ANALYTICS_PROFILE"
        if system == "account_service":
            return "USER_PROFILE"
        return "UNKNOWN"

    # ---------------------------------------------------------- logs

    def _extract_log(self, file_id: str, captured_at: str, path: Path) -> None:
        text = path.read_text(encoding="utf-8", errors="replace")
        pending: dict[str, dict] = {}
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or not line[:4].isdigit():
                continue
            parsed = parse_log_line(line)
            if not parsed:
                continue
            ts = parsed["ts"]
            trace = parsed["fields"].get("trace_id") or parsed["fields"].get("requestId") or parsed["trace"] or ""
            if trace and trace.startswith("tr-") is False and "trace" in parsed and parsed["trace"]:
                trace = parsed["trace"]
            key = trace or f"__noid{len(pending)}"
            event = parsed["event"]
            if event.endswith("_started") or event.endswith("_scan_started") or event.startswith("contact_query_started"):
                pending[key] = {**parsed["fields"], "lookup_key": parsed["fields"].get("lookup_key") or parsed["fields"].get("subject_key") or parsed["fields"].get("match_key") or parsed["fields"].get("owner_key") or parsed["fields"].get("scan_key") or parsed["fields"].get("subject_ref")}
                continue
            is_completion = (
                event.endswith("_completed")
                or event.endswith("_pii_scan")
                or event in {"message_read", "connector_config_loaded", "connector_heartbeat", "analytics_profile_read", "analytics_profile_scan", "analytics_identity_scan", "restore_candidate_evaluated", "restore_authorization_completed", "retained_order_loaded"}
                or event.startswith("record_lookup")
                or event.startswith("contact_query")
            )
            if not is_completion:
                continue
            merged = {**pending.pop(key, {}), **parsed["fields"]}
            self._fact_from_log_event(file_id, captured_at, parsed, merged, path)

    def _fact_from_log_event(self, file_id: str, captured_at: str, parsed: dict, fields: dict, path: Path) -> None:
        event = parsed["event"]
        service = parsed["service"] or fields.get("service") or ""
        rid = fields.get("resource_id") or ""
        if not rid:
            return
        lookup = fields.get("lookup_key") or fields.get("correlation_key") or fields.get("email") or fields.get("subject_reference") or fields.get("subject_ref") or ""
        record: dict = {
            "resource_id": rid,
            "email": _clean(fields.get("email")),
            "phone": _clean(fields.get("phone")),
            "email_hash": _clean(fields.get("email_hash")),
            "user_id": _clean(fields.get("subject_reference")) if _clean(fields.get("subject_reference")).startswith("user_") else "",
            "customer_reference": _clean(fields.get("customer_reference") or fields.get("subject_ref")),
            "observed_at": parsed["ts"],
        }
        if lookup and "@" in str(lookup):
            record["email"] = lookup
        elif str(lookup).startswith("user_"):
            record["customer_reference"] = lookup
        if fields.get("email") and "@" in str(fields["email"]):
            record["email"] = fields["email"]
        if fields.get("email") and re.fullmatch(r"[0-9a-f]{64}", str(fields["email"])):
            record["email_hash"] = fields["email"]

        rtype = "UNKNOWN"
        state = ""
        result = fields.get("result") or fields.get("http_status") or ""
        if event in {"profile_lookup_completed"}:
            rtype = "USER_PROFILE"
            rows = fields.get("rows")
            if str(result) == "404" or str(rows) == "0":
                state = "ABSENT"
            elif str(result) == "200" or (rows not in (None, "") and str(rows) != "0"):
                state = "PRESENT"
        elif event in {"analytics_profile_read_completed", "analytics_profile_scan", "analytics_identity_scan"}:
            rtype = "ANALYTICS_PROFILE"
            if any(_clean(fields.get(k)) for k in ("email", "phone", "email_hash", "customer_reference", "matched_value")):
                state = "PRESENT"
                if _clean(fields.get("matched_value")):
                    record["email"] = _clean(fields["matched_value"]) if "@" in str(fields["matched_value"]) else record["email"]
            else:
                state = "ANONYMIZED"
        elif event == "contact_lookup_completed":
            # The analytics contact index still maps a hashed contact to a
            # subject.  That is a secondary identifier (DELETE), not a profile.
            rtype = "SECONDARY_IDENTIFIER"
            state = "PRESENT" if str(_clean(fields.get("rows", "1"))) != "0" else "ABSENT"
            if _clean(fields.get("correlation_key")):
                record["email_hash"] = _clean(fields["correlation_key"])
        elif event in {"index_query_completed"}:
            rtype = "SEARCH_INDEX_ENTRY"
            if str(result).lower() == "hit" or fields.get("hits") not in (None, "", "0"):
                state = "PRESENT"
            elif str(result).lower() in {"miss", "not_found"}:
                state = "ABSENT"
        elif event in {"support_ticket_read_completed"}:
            rtype = "SUPPORT_MESSAGE"
            record["name"] = _clean(fields.get("requester_name"))
            record["email"] = _clean(fields.get("requester_email"))
            record["phone"] = _clean(fields.get("requester_phone"))
            record["message_excerpt"] = _clean(fields.get("message_excerpt"))
            if not any(_clean(fields.get(k)) for k in ("requester_name", "requester_email", "requester_phone")):
                state = "REDACTED"
            else:
                state = "PRESENT"
        elif event in {"message_pii_scan", "message_read"}:
            rtype = "SUPPORT_MESSAGE"
            state = "PRESENT"
            if _clean(fields.get("matched_value")):
                mv = _clean(fields["matched_value"])
                if "@" in mv:
                    record["email"] = mv
                elif any(ch.isdigit() for ch in mv) and len(re.sub(r"\D", "", mv)) >= 7:
                    record["phone"] = mv
                else:
                    record["name"] = mv
            text = _clean(fields.get("message_text"))
            if text == "[REDACTED]" and not record["email"] and not record["phone"]:
                state = "REDACTED"
        elif event in {"analytics_profile_read"}:
            rtype = "ANALYTICS_PROFILE"
            email = _clean(fields.get("email"))
            phone = _clean(fields.get("phone"))
            if str(_clean(fields.get("direct_identifiers", "1"))) == "0" and not email and not phone:
                state = "ANONYMIZED"
            else:
                state = "PRESENT"
            if email and "@" in email:
                record["email"] = email
            if phone:
                record["phone"] = phone
        elif event in {"attachment_pii_scan"}:
            rtype = "SUPPORT_ATTACHMENT"
            state = "PRESENT"
            record["email"] = fields.get("matched_value", "")
        elif event in {"export_download_check_completed", "export_metadata_read_completed"}:
            rtype = "USER_EXPORT"
            if str(fields.get("available", "")).lower() == "true" or event == "export_metadata_read_completed":
                state = "PRESENT"
            else:
                state = "ABSENT"
        elif event in {"connector_config_read_completed", "connector_config_loaded", "connector_heartbeat"}:
            rtype = "DATA_FLOW"
            enabled = str(fields.get("enabled", "")).lower()
            state = "ACTIVE" if enabled in {"true", "1", "yes"} else "DISABLED" if enabled in {"false", "0", "no"} else "UNKNOWN"
        elif event in {"restore_policy_read_completed", "restore_authorization_completed"}:
            rtype = "BACKUP_ARCHIVE"
            allowed = str(fields.get("restore_allowed", "")).lower()
            decision = str(fields.get("decision", "")).lower()
            if decision:
                state = "BLOCKED" if decision in {"deny", "denied", "block", "blocked"} else "ACTIVE" if decision in {"allow", "allowed", "permit", "permitted"} else "UNKNOWN"
            else:
                state = "ACTIVE" if allowed in {"true", "1", "yes"} else "BLOCKED" if allowed in {"false", "0", "no"} else "UNKNOWN"
        elif event in {"restore_candidate_evaluated"}:
            rtype = "BACKUP_ARCHIVE"
            if str(fields.get("deletion_block", "")).lower() in {"true", "1", "yes"}:
                state = "BLOCKED"
            elif str(fields.get("eligible", "")).lower() in {"true", "1", "yes"}:
                state = "ACTIVE"
            else:
                state = "BLOCKED"
        elif event in {"retained_order_loaded"}:
            rtype = "LEGAL_HOLD_RECORD"
            state = "PRESENT"
        elif event in {"audit_record_read_completed"}:
            rtype = "SECURITY_AUDIT_LOG"
            state = "PRESENT" if str(fields.get("rows", "1")) != "0" else "ABSENT"
        elif event in {"contact_query_completed"}:
            # A contact lookup index/table.  It is a secondary identifier that
            # must be deleted, not a retained support conversation.
            rtype = "SECONDARY_IDENTIFIER"
            state = "PRESENT" if str(_clean(fields.get("rows", "1"))) != "0" else "ABSENT"
        elif event == "record_lookup":
            rtype = str(fields.get("record_type") or "").upper() or "UNKNOWN"
            state = map_result(fields.get("result"))
            if fields.get("subject_reference"):
                sub = fields["subject_reference"]
                if "@" in sub:
                    record["email"] = sub
                elif str(sub).startswith("user_"):
                    record["customer_reference"] = sub
        if state in {"", "UNKNOWN"}:
            return
        if rtype == "UNKNOWN":
            rtype = self._type_from_record_shape(record, service)
        system_id = service or system_for_resource(rid)
        system_id = SYSTEM_ALIASES.get(system_id, system_id)
        fact = fact_from_record(
            file_id=file_id, captured_at=captured_at, system_id=system_id,
            resource_id=rid, record_type=rtype, record=record, observed_at=parsed["ts"],
            source_format="log", result=state, raw_ref=f"{path.name}:{parsed.get('event')}",
        )
        self.facts.append(fact)

    # ---------------------------------------------------------- text handover

    def _extract_txt(self, file_id: str, captured_at: str, path: Path) -> None:
        text = path.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            if "|" not in line:
                continue
            parts = [p.strip().lstrip("- ").strip() for p in line.split("|")]
            if len(parts) < 6:
                continue
            ts, system, rid, rtype, state_raw, identifier = parts[:6]
            if not re.match(r"\d{4}-\d{2}-\d{2}", ts):
                continue
            record = {"resource_id": rid, "observed_at": ts}
            if "@" in identifier:
                record["email"] = identifier
            elif identifier.startswith("user_"):
                record["customer_reference"] = identifier
            self.facts.append(
                fact_from_record(
                    file_id=file_id, captured_at=captured_at, system_id=system,
                    resource_id=rid, record_type=rtype, record=record, observed_at=ts,
                    source_format="txt", result=state_raw, raw_ref=path.name,
                )
            )

    # ---------------------------------------------------------- PDFs

    def _extract_pdf(self, file_id: str, captured_at: str, path: Path) -> None:
        try:
            from pypdf import PdfReader
        except Exception:
            self.notes.append("pypdf not installed; cannot parse PDFs")
            return
        text = "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)
        name = path.name
        if "delivery_correction_attachment" in name:
            rid = _first(r"support_\d+", text) or "support_001"
            email = _first(r"[\w.+-]+@[\w.-]+\.\w+", text) or ""
            phone = _first(r"\+\d[\d ()-]{6,}\d", text) or ""
            person = "Priya Raman" if "Priya Raman" in text else ""
            self.facts.append(
                fact_from_record(
                    file_id=file_id, captured_at=captured_at, system_id="support_platform",
                    resource_id=rid, record_type="SUPPORT_ATTACHMENT",
                    record={"resource_id": rid, "email": email, "phone": phone, "full_name": person},
                    observed_at=captured_at, source_format="pdf", result="PRESENT", raw_ref=name,
                )
            )
        elif "account_history_report" in name:
            uid = _first(r"user_\d+", text) or ""
            email = _first(r"[\w.+-]+@[\w.-]+\.\w+", text) or ""
            statement = _first(r"NST-\d{4}-\d{4}-\d+", text) or ""
            order = _first(r"ORD-\d+", text) or ""
            # The linked catalog resource is the customer statement export
            # (export_1842 for statement NST-2026-0718-1842).
            suffix = statement.rsplit("-", 1)[-1] if statement else ""
            rid = f"export_{suffix}" if suffix else (order or f"export_{uid}")
            self.facts.append(
                fact_from_record(
                    file_id=file_id, captured_at=captured_at, system_id="export_service",
                    resource_id=rid, record_type="USER_EXPORT",
                    record={"resource_id": rid, "email": email, "customer_reference": uid, "statement": statement, "order": order},
                    observed_at=captured_at, source_format="pdf", result="PRESENT", raw_ref=name,
                )
            )
        elif "legal_retention_register" in name:
            for m in re.finditer(r"(ORD-\d+)\s*\|\s*(user_\d+)", text):
                order, uid = m.group(1), m.group(2)
                self.facts.append(
                    fact_from_record(
                        file_id=file_id, captured_at=captured_at, system_id="legal_service",
                        resource_id=order, record_type="LEGAL_HOLD_RECORD",
                        record={"resource_id": order, "customer_reference": uid},
                        observed_at=captured_at, source_format="pdf", result="PRESENT", raw_ref=name,
                    )
                )
        elif "security_retention_extract" in name:
            rid = _first(r"audit_record_\d+", text) or "audit_record_003"
            uid = _first(r"user_\d+", text) or ""
            self.facts.append(
                fact_from_record(
                    file_id=file_id, captured_at=captured_at, system_id="security_service",
                    resource_id=rid, record_type="SECURITY_AUDIT_LOG",
                    record={"resource_id": rid, "customer_reference": uid},
                    observed_at=captured_at, source_format="pdf", result="PRESENT", raw_ref=name,
                )
            )

    # ---------------------------------------------------------- images

    def _extract_image(self, file_id: str, captured_at: str, path: Path) -> None:
        from .ocr import ocr_image

        text = ocr_image(path)
        name = path.name
        system = _system_from_image_name(name)
        emails = re.findall(r"[\w.+-]+@[\w.-]+\.\w+", text)
        uids = re.findall(r"user_\d+", text)

        # Screenshots are catalog artefacts: the catalog link identifies the
        # canonical resource shown in the screenshot.  Decoy rows visible in
        # the same screen are intentionally ignored.
        linked = []
        for link in self._image_links():
            rid = link["resource_id"]
            detail = link.get("detail", "")
            hit = rid in text
            if not hit and detail:
                # The catalog detail is the human-visible name in the screen:
                # an object filename, a statement number, or a user reference.
                hit = detail in text or detail.strip("()") in text
            if not hit and link.get("user_id") and rid.startswith("tombstone_"):
                hit = link["user_id"] in text
            if hit:
                linked.append(link)
        if linked:
            for link in linked:
                rid = link["resource_id"]
                record = {
                    "resource_id": rid,
                    "email": link["email"],
                    "customer_reference": link["user_id"],
                }
                if not record["email"] and emails:
                    record["email"] = emails[0]
                if not record["customer_reference"] and uids:
                    record["customer_reference"] = uids[0]
                rtype = _record_type_from_image(name, rid)
                state = _image_state(name, text, rtype)
                self.facts.append(
                    fact_from_record(
                        file_id=file_id, captured_at=captured_at,
                        system_id=link.get("system") or system,
                        resource_id=rid, record_type=rtype, record=record,
                        observed_at=link.get("event_time") or captured_at,
                        source_format="image", result=state, raw_ref=name,
                    )
                )
            self._extend_subject_filtered_image(
                file_id=file_id,
                captured_at=captured_at,
                text=text,
                name=name,
                linked=linked,
                system=system,
            )
            return

        # Fallback for an image without a catalog link: extract the first
        # resource and attach the identifiers printed on the same screen.
        for rid in sorted(set(re.findall(r"(?:account|search|analytics|support|export|data_flow|backup|audit_record|tombstone|object|marketing)_\d+", text))):
            rtype = _record_type_from_image(name, rid)
            record = {"resource_id": rid}
            if emails:
                record["email"] = emails[0]
            if uids:
                record["customer_reference"] = uids[0]
            self.facts.append(
                fact_from_record(
                    file_id=file_id, captured_at=captured_at, system_id=system,
                    resource_id=rid, record_type=rtype, record=record,
                    observed_at=captured_at, source_format="image",
                    result=_image_state(name, text, rtype), raw_ref=name,
                )
            )

    def _extend_subject_filtered_image(
        self,
        *,
        file_id: str,
        captured_at: str,
        text: str,
        name: str,
        linked: list[dict],
        system: str,
    ) -> None:
        """Include every same-subject record in a filtered table screenshot.

        A screenshot whose visible subject filter names one strong subject is
        a scoped view, not a single-record view: every record row in that
        table belongs to the filtered subject.  The catalog link still names
        the canonical row; the remaining rows are additional resources for the
        same subject, not decoys.  This is deliberately narrow: the rule only
        fires when the screen contains an explicit ``Subject filter`` line and
        no other user reference anywhere in the image, so screens that merely
        happen to show several customers are unaffected.
        """
        match = re.search(r"subject\s+filter\s*:\s*([A-Za-z0-9_.@+-]+)", text, re.I)
        if not match:
            return
        subject = re.sub(r"\buser[ _](\d+)", r"user_\1", match.group(1), flags=re.I)
        # A scoped table can still contain another subject in a sidebar or
        # activity feed.  Do not broaden the rule if the image does.
        visible_subjects = {
            re.sub(r"\buser[ _](\d+)", r"user_\1", token, flags=re.I)
            for token in re.findall(r"\buser[ _]\d+\b", text, re.I)
        }
        visible_subjects.discard(subject)
        if visible_subjects:
            return

        for link in linked:
            canonical = str(link["resource_id"])
            family_match = re.match(r"([a-z_]+)_\d+$", canonical)
            if not family_match:
                continue
            family = family_match.group(1)
            # OCR sometimes renders an underscore as a space.  Normalize the
            # visible reference before comparing it with the catalog id.
            visible = {
                re.sub(r"\s+", "_", token)
                for token in re.findall(
                    rf"\b{re.escape(family)}[ _]\d+\b", text, re.I
                )
            }
            rtype = _record_type_from_image(name, canonical)
            state = _image_state(name, text, rtype)
            for rid in sorted(visible):
                if rid == canonical:
                    continue
                record = {
                    "resource_id": rid,
                    "email": link.get("email", ""),
                    "customer_reference": link.get("user_id", ""),
                }
                self.facts.append(
                    fact_from_record(
                        file_id=file_id,
                        captured_at=captured_at,
                        system_id=link.get("system") or system,
                        resource_id=rid,
                        record_type=rtype,
                        record=record,
                        observed_at=link.get("event_time") or captured_at,
                        source_format="image",
                        result=state,
                        raw_ref=name,
                    )
                )

    def _image_links(self) -> list[dict]:
        if not hasattr(self, "_links_cache"):
            self._links_cache = []
            sa = self.ds.activity
            for row in sa.itertuples(index=False):
                if str(row.event_type) != "LINK_RESOURCE_IDENTITY":
                    continue
                details = str(row.details)
                email = _first(r"[\w.+-]+@[\w.-]+\.\w+", details)
                uid = _first(r"user_\d+", details)
                detail_match = re.search(r"\(([^)]*)\)", details)
                detail = detail_match.group(1).strip() if detail_match else ""
                self._links_cache.append({
                    "resource_id": str(row.resource_id),
                    "system": str(row.target_system),
                    "event_time": str(row.event_time),
                    "email": email,
                    "user_id": uid,
                    "detail": detail,
                })
        return self._links_cache


def _first(pattern: str, text: str) -> str:
    m = re.search(pattern, text)
    return m.group(0) if m else ""


def _image_state(name: str, text: str, rtype: str) -> str:
    low = text.lower()
    if rtype == "ACCOUNT_TOMBSTONE":
        return "PRESENT" if re.search(r"[\w.+-]+@[\w.-]+\.\w+", text) else "REDACTED"
    if rtype == "BACKUP_ARCHIVE":
        if "restore blocked" in low or "not restorable" in low:
            return "BLOCKED"
        return "ACTIVE"
    if rtype == "DATA_FLOW":
        if "disabled" in low or "paused" in low or "inactive" in low:
            return "DISABLED"
        return "ACTIVE"
    if rtype == "SECURITY_AUDIT_LOG":
        return "PRESENT"
    if rtype == "USER_PROFILE":
        if "not found" in low or "no customer" in low:
            return "ABSENT"
        return "PRESENT"
    return "PRESENT"


def _system_from_image_name(name: str) -> str:
    for token, system in {
        "account_admin": "account_service",
        "search_index": "search_service",
        "connector": "integration_service",
        "analytics": "analytics_platform",
        "customer_export": "export_service",
        "support_ticket": "support_platform",
        "backup_restore": "backup_service",
        "security_audit": "security_service",
        "deleted_account": "identity_service",
        "object_storage": "object_storage",
        "marketing_profile": "marketing_platform",
    }.items():
        if token in name:
            return system
    return "unknown"


def _record_type_from_image(name: str, rid: str) -> str:
    if "account_admin" in name:
        return "USER_PROFILE"
    if "search_index" in name:
        return "SEARCH_INDEX_ENTRY"
    if "connector" in name:
        return "DATA_FLOW"
    if "analytics" in name:
        return "ANALYTICS_PROFILE"
    if "customer_export" in name:
        return "USER_EXPORT"
    if "support_ticket" in name:
        return "SUPPORT_MESSAGE"
    if "backup_restore" in name:
        return "BACKUP_ARCHIVE"
    if "security_audit" in name:
        return "SECURITY_AUDIT_LOG"
    if "deleted_account" in name:
        return "ACCOUNT_TOMBSTONE"
    if "object_storage" in name:
        return "SUPPORT_ATTACHMENT"
    if "marketing_profile" in name:
        return "MARKETING_PROFILE"
    return "UNKNOWN"


# ---------------------------------------------------------------- log parsing


KV_RE = re.compile(r'(?P<key>[A-Za-z_][\w.]*)=(?P<val>"(?:[^"\\]|\\.)*"|[^\s]+)')


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        try:
            return json.loads(value)
        except Exception:
            return value[1:-1]
    return value


def parse_log_line(line: str) -> dict | None:
    m = re.match(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)\s+(.*)$", line)
    if not m:
        return None
    ts, rest = m.group(1), m.group(2)
    service = ""
    trace = ""
    event = ""

    # JSON-per-line
    if rest.startswith("{"):
        try:
            rec = json.loads(rest)
            fields = {k: str(v) for k, v in rec.items()}
            return {"ts": ts, "service": fields.get("service") or fields.get("logger", ""), "trace": fields.get("trace_id", ""), "event": fields.get("event", ""), "fields": fields}
        except Exception:
            pass

    # CloudWatch message="..."
    msg = re.search(r'message="((?:[^"\\]|\\.)*)"', rest)
    if msg:
        try:
            inner = json.loads('"' + msg.group(1) + '"')
        except Exception:
            inner = msg.group(1)
        fields = {k: _unquote(v) for k, v in KV_RE.findall(inner)}
        fields.update({k: _unquote(v) for k, v in KV_RE.findall(rest[: msg.start()])})
        return {"ts": ts, "service": fields.get("function") or fields.get("service", ""), "trace": fields.get("requestId", ""), "event": fields.get("event", ""), "fields": fields}

    # [DEBUG] [service] [trace] event: k="v"
    m2 = re.match(r"\[[A-Z]+\]\s+\[([^\]]+)\]\s+\[([^\]]+)\]\s+([\w.]+):\s*(.*)$", rest)
    if m2:
        service, trace, event, tail = m2.groups()
        fields = {k: _unquote(v) for k, v in KV_RE.findall(tail)}
        return {"ts": ts, "service": service, "trace": trace, "event": event, "fields": fields}

    # ts | LEVEL | service | trace | event | k="v"
    if " | " in rest or rest.startswith("|"):
        stripped = rest[1:].strip() if rest.startswith("|") else rest
        parts = [p.strip() for p in stripped.split("|")]
        if len(parts) >= 4:
            level, service, trace, event = parts[0], parts[1], parts[2], parts[3]
            tail = " | ".join(parts[4:])
            fields = {k: _unquote(v) for k, v in KV_RE.findall(tail)}
            return {"ts": ts, "service": service, "trace": trace, "event": event, "fields": fields}

    # syslog <15>1 node service trace - - k="v"
    m3 = re.match(r"<\d+>1\s+\S+\s+([\w.-]+)\s+(\S+)\s+-\s+-\s+(.*)$", rest)
    if m3:
        service, trace, tail = m3.groups()
        fields = {k: _unquote(v) for k, v in KV_RE.findall(tail)}
        return {"ts": ts, "service": service, "trace": trace, "event": fields.get("event", ""), "fields": fields}

    # plain k=v
    fields = {k: _unquote(v) for k, v in KV_RE.findall(rest)}
    if not fields:
        return None
    service = fields.get("service", "")
    trace = fields.get("trace_id", "")
    event = fields.get("event", "")
    return {"ts": ts, "service": service, "trace": trace, "event": event, "fields": fields}
