"""Shared utilities: timestamps, identifier normalization, hashing."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime, timezone


def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    value = str(value).strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def ts_key(value: str | None) -> float:
    dt = parse_ts(value)
    return dt.timestamp() if dt else 0.0


def iso(value: str | None) -> str:
    dt = parse_ts(value)
    if not dt:
        return ""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def norm_email(value: str | None) -> str:
    return str(value or "").strip().lower()


def norm_phone(value: str | None) -> str:
    return re.sub(r"\D", "", str(value or ""))


def norm_name(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text.strip().lower())


def sha256_email(value: str | None) -> str:
    return hashlib.sha256(norm_email(value).encode("utf-8")).hexdigest()


def canonical_identifier(value: str | None) -> str:
    """Return a stable comparison form for an email/phone/name/hash token."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    if "@" in raw:
        return "email:" + norm_email(raw)
    if re.fullmatch(r"[0-9a-fA-F]{64}", raw):
        return "hash:" + raw.lower()
    digits = norm_phone(raw)
    if len(digits) >= 7 and re.fullmatch(r"[+()\-\s\d.]+", raw):
        return "phone:" + digits
    return "name:" + norm_name(raw)


def safe_slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", value)[:120]


def resource_sort_key(resource_id: str) -> str:
    return "" if resource_id is None else str(resource_id)
