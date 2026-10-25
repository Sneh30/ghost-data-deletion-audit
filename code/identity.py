"""Resolve a request email to a stable user_id and every identifier that could
still appear in historical copies (old emails, hashes, phones, names).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .loader import Dataset
from .util import canonical_identifier, norm_email, norm_phone, parse_ts, sha256_email


@dataclass
class Identity:
    user_id: str
    name: str = ""
    email: str = ""
    phone: str = ""
    email_hash: str = ""
    emails: set[str] = field(default_factory=set)
    phones: set[str] = field(default_factory=set)
    hashes: set[str] = field(default_factory=set)
    names: set[str] = field(default_factory=set)

    def tokens(self) -> set[str]:
        out: set[str] = set()
        for e in self.emails:
            out.add("email:" + norm_email(e))
            out.add("hash:" + sha256_email(e))
        for p in self.phones:
            digits = norm_phone(p)
            if digits:
                out.add("phone:" + digits)
        for h in self.hashes:
            if h:
                out.add("hash:" + h.lower())
        for n in self.names:
            tok = canonical_identifier(n)
            if tok:
                out.add(tok)
        if self.user_id:
            out.add("uid:" + self.user_id)
        return out


class IdentityResolver:
    def __init__(self, ds: Dataset):
        self.ds = ds
        self.ids = ds.identities.copy()
        self.ids["email_norm"] = self.ids["email"].map(norm_email)
        self.by_email: dict[str, list[str]] = {}
        for row in self.ids.to_dict("records"):
            self.by_email.setdefault(row["email_norm"], []).append(row["user_id"])
        self.history: dict[str, list[dict]] = {}
        for row in ds.audit_log.to_dict("records"):
            self.history.setdefault(row["user_id"], []).append(row)

    def resolve(self, email: str, audit_at: str = "") -> Identity | None:
        key = norm_email(email)
        candidates = list(self.by_email.get(key, []))
        if not candidates:
            for row in self.ds.audit_log.to_dict("records"):
                if row["field_name"] != "email":
                    continue
                if key in {norm_email(row["old_value"]), norm_email(row["new_value"])}:
                    candidates.append(row["user_id"])
        candidates = sorted(set(candidates))
        if not candidates:
            return None
        # The request email is the strongest key. If it is current for a user,
        # prefer that user; otherwise use the unique historical owner.
        current = [c for c in candidates if key in {norm_email(e) for e in self.ids[self.ids.user_id == c].email}]
        uid = (current or candidates)[0]
        return self.build(uid, audit_at)

    def build(self, user_id: str, audit_at: str) -> Identity:
        rows = self.ids[self.ids.user_id == user_id].to_dict("records")
        if not rows:
            return Identity(user_id=user_id)
        row = rows[0]
        ident = Identity(
            user_id=user_id,
            name=row["name"],
            email=row["email"],
            phone=row["phone"],
            email_hash=row["email_hash"],
        )
        ident.emails.add(row["email"])
        if row["phone"]:
            ident.phones.add(row["phone"])
        if row["email_hash"]:
            ident.hashes.add(row["email_hash"])
        if row["name"]:
            ident.names.add(row["name"])

        cutoff = parse_ts(audit_at)
        for event in self.history.get(user_id, []):
            changed = parse_ts(event["event_time"])
            after_cutoff = cutoff is not None and changed is not None and changed > cutoff
            field = event["field_name"]
            old, new = event["old_value"], event["new_value"]
            # The old value existed before the change, so it may remain in old
            # copies even if the change happened after audit_at.  The new value
            # only existed if the change happened on/before audit_at.
            if field == "email":
                if old:
                    ident.emails.add(old)
                if new and not after_cutoff:
                    ident.emails.add(new)
            elif field == "email_hash":
                if old:
                    ident.hashes.add(old)
                if new and not after_cutoff:
                    ident.hashes.add(new)
            elif field == "phone":
                if old:
                    ident.phones.add(old)
                if new and not after_cutoff:
                    ident.phones.add(new)
        return ident
