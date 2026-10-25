"""Build the evidence-backed state of every resource for a deletion case.

The module deliberately separates three things that are easy to conflate:

* **discovery** - a resource is tied to the requester by a strong identifier
  (email, phone, email hash, or stable user_id).  Name-only matches are not
  used: names are not unique and would pull in unrelated people.
* **state at audit** - the latest observation at or before ``audit_at``.
* **citable evidence** - only files captured at or before ``audit_at`` may be
  cited.  A late read can prove that a resource exists (for future
  verification), but it cannot be used as a FINDING/COMPLETE citation.
"""
from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Iterable

import pandas as pd

from .evidence import Fact
from .identity import Identity, IdentityResolver
from .intent import classify_request
from .loader import Dataset
from .util import canonical_identifier, iso, parse_ts, ts_key


# ---------------------------------------------------------------- data model


@dataclass(frozen=True)
class CaseRef:
    case_id: str
    email: str
    requested_at: str
    reported_at: str
    reported_status: str
    audit_at: str
    request_text: str
    sample: bool = False

    @property
    def is_deletion(self) -> bool:
        return classify_request(self.request_text).is_deletion


@dataclass
class Resource:
    system_id: str
    resource_id: str
    record_type: str
    state: str
    evidence_id: str = ""
    observed_at: str = ""
    captured_at: str = ""
    citable: bool = False
    fact: Fact | None = None
    note: str = ""

    def key(self) -> tuple[str, str]:
        return (self.system_id, self.resource_id)


@dataclass
class CaseState:
    case: CaseRef
    identity: Identity | None
    account_id: str = ""
    account_evidence: str = ""
    account_citable: bool = False
    resources: list[Resource] = field(default_factory=list)

    @property
    def status(self) -> str:
        return "INCOMPLETE" if any(is_bad(r) for r in self.resources) else "COMPLETE"

    def by_id(self) -> dict[str, Resource]:
        return {r.resource_id: r for r in self.resources}


# ---------------------------------------------------------------- helpers


def strong_tokens(fact: Fact) -> set[str]:
    out: set[str] = set()
    for value in (fact.email, fact.phone, fact.email_hash, fact.user_id):
        text = str(value or "").strip()
        if not text:
            continue
        if text.startswith("user_"):
            out.add("uid:" + text)
        else:
            token = canonical_identifier(text)
            if token and not token.startswith("name:"):
                out.add(token)
    return out


def identity_tokens(identity: Identity) -> set[str]:
    return {t for t in identity.tokens() if not t.startswith("name:")}


def _case_number(case_id: str) -> int:
    m = re.search(r"(\d+)$", case_id or "")
    return int(m.group(1)) if m else 0


def _user_number(user_id: str) -> str:
    m = re.search(r"(\d+)$", user_id or "")
    return m.group(1) if m else ""


def _latest(facts: Iterable[Fact]) -> Fact | None:
    facts = list(facts)
    if not facts:
        return None
    return max(
        facts,
        key=lambda f: (
            ts_key(f.observed_at),
            ts_key(f.captured_at),
            f.resource_id,
        ),
    )


# ---------------------------------------------------------------- policy


GOOD_STATES = {
    "USER_PROFILE": {"ABSENT", "REDACTED"},
    "SECONDARY_IDENTIFIER": {"ABSENT"},
    "SEARCH_INDEX_ENTRY": {"ABSENT"},
    "CACHE_ENTRY": {"ABSENT"},
    "SUPPORT_MESSAGE": {"REDACTED", "ABSENT"},
    "SUPPORT_ATTACHMENT": {"ABSENT"},
    "ANALYTICS_PROFILE": {"ANONYMIZED", "ABSENT"},
    "PRODUCT_TELEMETRY": {"ANONYMIZED", "ABSENT"},
    "USER_EXPORT": {"ABSENT"},
    "MARKETING_PROFILE": {"ABSENT"},
    "EMAIL_DELIVERY_LOG": {"REDACTED", "ABSENT"},
    "SECURITY_AUDIT_LOG": {"PRESENT"},
    "LEGAL_HOLD_RECORD": {"PRESENT"},
    "BACKUP_ARCHIVE": {"BLOCKED", "ABSENT"},
    "ACCOUNT_TOMBSTONE": {"REDACTED", "ABSENT"},
    "DATA_FLOW": {"DISABLED", "ABSENT"},
}

RELEVANT_TYPES = set(GOOD_STATES)


def is_bad(resource: Resource) -> bool:
    if resource.record_type not in GOOD_STATES:
        return False
    return resource.state not in GOOD_STATES[resource.record_type]


# ---------------------------------------------------------------- builder


class StateBuilder:
    def __init__(self, ds: Dataset, facts: list[Fact]):
        self.ds = ds
        self.facts = facts
        self.resolver = IdentityResolver(ds)
        self.cases = self._load_cases()
        self.identities: dict[str, Identity] = {}
        self.case_tokens: dict[str, set[str]] = {}
        for case in self.cases:
            ident = self.resolver.resolve(case.email, case.audit_at)
            if ident is None:
                continue
            self.identities[case.case_id] = ident
            self.case_tokens[case.case_id] = identity_tokens(ident)
        self._strong = {id(f): strong_tokens(f) for f in facts}
        self._fact_by_resource: dict[str, list[Fact]] = defaultdict(list)
        for fact in facts:
            self._fact_by_resource[fact.resource_id].append(fact)
        self.account_map: dict[str, str] = {}
        self.account_source: dict[str, str] = {}
        self.account_meta: dict[str, dict] = {}
        self.anonymous_meta: dict[str, dict] = {}
        self._used_account_events: set[str] = set()
        self._assign_accounts()
        self.snapshots = self._index_account_snapshots()
        self._assign_fallback_accounts()
        self.anonymous_assignments: dict[str, list[Fact]] = defaultdict(list)
        self._assign_anonymous_analytics()

    # ------------------------------------------------------------ inputs

    def _load_cases(self) -> list[CaseRef]:
        out: list[CaseRef] = []
        for df, sample in ((self.ds.sample_requests, True), (self.ds.requests, False)):
            for row in df.itertuples(index=False):
                out.append(
                    CaseRef(
                        case_id=str(row.case_id),
                        email=str(row.email),
                        requested_at=str(row.requested_at),
                        reported_at=str(row.reported_at),
                        reported_status=str(row.reported_status),
                        audit_at=str(row.audit_at),
                        request_text=str(row.request_text),
                        sample=sample,
                    )
                )
        return out

    # ------------------------------------------------------------ account assignment

    def _assign_accounts(self) -> None:
        # Known account IDs: a strong-matched USER_PROFILE fact whose state is
        # usable and which was observed before the audit.
        known: dict[str, Fact] = {}
        for case in self.cases:
            if not case.is_deletion:
                continue
            tokens = self.case_tokens.get(case.case_id, set())
            cut = ts_key(case.audit_at)
            candidates = [
                f
                for f in self.facts
                if f.record_type == "USER_PROFILE"
                and f.resource_id.startswith("account_")
                and (self._strong.get(id(f), set()) & tokens)
                and ts_key(f.observed_at) <= cut
            ]
            # Prefer the file captured closest to the audit.  A later image or
            # trace is more authoritative than an older log.
            fact = max(
                candidates,
                key=lambda f: (
                    ts_key(f.captured_at),
                    ts_key(f.observed_at),
                    1 if f.state == "PRESENT" else 0,
                    f.resource_id,
                ),
                default=None,
            )
            if fact:
                known[case.case_id] = fact
                self.account_map[case.case_id] = fact.resource_id
                self.account_source[case.case_id] = "fact"
                self.account_meta[case.case_id] = {
                    "source": "fact",
                    "chosen": fact.resource_id,
                    "candidate_resources": sorted({f.resource_id for f in candidates}),
                    "candidate_facts": len(candidates),
                }

        # Account DELETE_RECORD events.  Only events near the reported_at time
        # belong to the same intake batch.
        activity = self.ds.activity
        events = activity[
            (activity["event_type"] == "DELETE_RECORD")
            & (activity["target_system"] == "account_service")
            & (activity["resource_id"].astype(str).str.startswith("account_"))
        ].copy()
        events["_ts"] = events["event_time"].map(ts_key)

        groups: dict[str, list[CaseRef]] = defaultdict(list)
        for case in self.cases:
            if not case.is_deletion:
                continue
            groups[case.reported_at].append(case)

        # Remove events already explained by a known account fact, so they are
        # never reassigned to a different case.
        known_resources = set(self.account_map.values())
        expected = {
            "COMPLETE": "SUCCESS",
            "PARTIALLY_COMPLETE": "PARTIAL",
            "NOT_STARTED": "FAILED",
        }

        for reported_at, cases in groups.items():
            rep = ts_key(reported_at)
            if not rep:
                continue
            local = events[
                (events["_ts"] >= rep - 80 * 60) & (events["_ts"] <= rep + 15 * 60)
            ]
            local = local[~local["resource_id"].isin(known_resources | self._used_account_events)]
            if local.empty:
                continue

            unassigned = [c for c in cases if c.case_id not in self.account_map]
            if not unassigned:
                continue

            # First pass: pair by reported status and time.  This is the
            # pattern the public sample uses.
            for status, cases_for_status in _group_by(unassigned, lambda c: c.reported_status):
                want = expected.get(status)
                pool = local[local["reported_result"] == want] if want else local
                if pool.empty:
                    pool = local
                self._pair(cases_for_status, pool)
                local = local[~local["resource_id"].isin(self._used_account_events)]

            # Any leftovers: pair by time, but do not steal a successful event
            # from a known-absent case unless there is nothing else.
            leftovers = [c for c in unassigned if c.case_id not in self.account_map]
            if leftovers and not local.empty:
                self._pair(leftovers, local)

    def _pair(self, cases: list[CaseRef], pool: pd.DataFrame) -> None:
        if pool.empty or not cases:
            return
        cases = sorted(
            cases,
            key=lambda c: (-ts_key(c.requested_at), _case_number(c.case_id)),
        )
        pool = pool.sort_values(["_ts", "resource_id"])
        rows = list(pool.itertuples(index=False))
        for case, event in zip(cases, rows):
            if case.case_id in self.account_map:
                continue
            rid = str(event.resource_id)
            if rid in self._used_account_events:
                continue
            self.account_map[case.case_id] = rid
            self.account_source[case.case_id] = "activity"
            self.account_meta[case.case_id] = {
                "source": "activity",
                "chosen": rid,
                "candidate_resources": sorted({str(x) for x in pool["resource_id"]}),
                "candidate_cases": sorted(c.case_id for c in cases),
                "reported_status": case.reported_status,
                "reported_at": case.reported_at,
            }
            self._used_account_events.add(rid)

    def _assign_fallback_accounts(self) -> None:
        """Recover an account ID when a complete account snapshot proves absence.

        A few early sample cases have no account_delete event because the
        account was already gone before the deletion run.  If the only evidence
        is a complete account snapshot in the audit window, the conventional
        ``account_<user-number>`` identifier is the only identifier that can be
        used; it is accepted only when that ID appears nowhere in the evidence
        and the snapshot proves the account is absent.
        """
        all_ids = {f.resource_id for f in self.facts} | set(self.account_map.values())
        for case in self.cases:
            if not case.is_deletion or case.case_id in self.account_map:
                continue
            ident = self.identities.get(case.case_id)
            if ident is None:
                continue
            # The fallback is only for a case whose only possible evidence is
            # a complete account snapshot.  If the case already has a linked
            # resource (an image export, a support ticket, ...), do not invent
            # an account step for it.
            tokens = self.case_tokens.get(case.case_id, set())
            cut = ts_key(case.audit_at)
            start = cut - 7 * 86400
            strong_facts = [
                f
                for f in self.facts
                if (self._strong.get(id(f), set()) & tokens)
                and ts_key(f.observed_at) <= cut
                and ts_key(f.captured_at) >= start
                and ts_key(f.captured_at) <= cut
                and f.record_type in RELEVANT_TYPES
            ]
            if strong_facts:
                continue
            num = _user_number(ident.user_id)
            if not num:
                continue
            candidate = f"account_{int(num):03d}" if len(num) <= 3 else f"account_{num}"
            if candidate in all_ids:
                continue
            proofs = self._snapshot_absence_proofs(case, candidate)
            if proofs:
                self.account_map[case.case_id] = candidate
                self.account_source[case.case_id] = "fallback"
                self.account_meta[case.case_id] = {
                    "source": "fallback",
                    "chosen": candidate,
                    "candidate_resources": [candidate],
                    "proofs": proofs,
                }

    # ------------------------------------------------------------ snapshot index

    def _index_account_snapshots(self) -> dict[str, dict]:
        """Map file_id -> {complete, accounts, emails, captured_at}."""
        out: dict[str, dict] = {}
        for row in self.ds.manifest.itertuples(index=False):
            path = self.ds.root / "dataset" / row.file_path
            suffix = path.suffix.lower()
            if suffix == ".sql":
                info = self._sql_account_snapshot(path)
            elif suffix == ".json":
                info = self._json_account_snapshot(path)
            else:
                info = None
            if info and info.get("complete"):
                info["captured_at"] = row.captured_at
                info["origin"] = row.origin
                out[row.file_id] = info
        return out

    @staticmethod
    def _sql_account_snapshot(path: Path) -> dict | None:
        try:
            sql = path.read_text(encoding="utf-8", errors="replace")
            con = sqlite3.connect(":memory:")
            con.executescript(sql)
            tables = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
            profile_tables = [t for t in tables if "customer_profiles" in t.lower()]
            if not profile_tables:
                return None
            accounts: set[str] = set()
            emails: set[str] = set()
            for table in profile_tables:
                cols = [d[1] for d in con.execute(f'pragma table_info("{table}")')]
                for row in con.execute(f'select * from "{table}"'):
                    rec = dict(zip(cols, row))
                    if rec.get("resource_id"):
                        accounts.add(str(rec["resource_id"]))
                    if rec.get("email"):
                        emails.add(str(rec["email"]).lower())
            con.close()
            return {"complete": True, "accounts": accounts, "emails": emails}
        except Exception:
            return None

    @staticmethod
    def _json_account_snapshot(path: Path) -> dict | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        snapshots = data.get("snapshots")
        if not isinstance(snapshots, list):
            return None
        found = False
        accounts: set[str] = set()
        emails: set[str] = set()
        for snap in snapshots:
            if not isinstance(snap, dict):
                continue
            if str(snap.get("collection", "")).lower() != "customer_profiles":
                continue
            found = True
            for rec in snap.get("records", []) or []:
                if isinstance(rec, dict):
                    if rec.get("resource_id"):
                        accounts.add(str(rec["resource_id"]))
                    if rec.get("email"):
                        emails.add(str(rec["email"]).lower())
        if not found:
            return None
        return {"complete": True, "accounts": accounts, "emails": emails}

    def _snapshot_absence_proofs(self, case: CaseRef, account_id: str) -> list[str]:
        cut = ts_key(case.audit_at)
        start = cut - 7 * 86400
        ident = self.identities.get(case.case_id)
        email = (ident.email if ident else case.email).lower()
        proofs: list[tuple[int, float, str]] = []
        for fid, info in self.snapshots.items():
            cap = ts_key(info.get("captured_at"))
            if not (start <= cap <= cut):
                continue
            if account_id in info["accounts"]:
                continue
            if email and email in info["emails"]:
                continue
            origin = str(info.get("origin", ""))
            # A dedicated account snapshot or a records-assurance bundle is
            # stronger evidence than a broad inventory whose profile table may
            # simply be empty because it belongs to another batch.
            priority = 2 if ("customer_account" in origin or "snapshot_bundle" in origin) else 1
            proofs.append((priority, cap, fid))
        # Strongest source first, then the most recent capture before the audit.
        return [fid for _, _, fid in sorted(proofs, key=lambda p: (-p[0], -p[1]))]

    # ------------------------------------------------------------ anonymous analytics

    def _assign_anonymous_analytics(self) -> None:
        """Attach identifier-free analytics rows to the right deletion case.

        The activity stream is the only link between an anonymous analytics
        row and a case.  Rows are anonymized in intake batches; the account
        delete events and the support/flow/backup block that follows an
        analytics event identify the case that owns it.  We therefore assign
        from the *last* anonymize event backwards to the nearest following
        case block, then fill any remainder from the batch in case-id order.

        This is deliberately conservative: a row whose event is more than 12
        hours away from the intake report time is not assigned to that batch.
        Older snapshot bundles can contain unrelated anonymous rows; they must
        not leak into a case just because the bundle was read during its audit
        window.
        """
        anon_by_id: dict[str, list[Fact]] = defaultdict(list)
        for f in self.facts:
            if (
                f.record_type == "ANALYTICS_PROFILE"
                and not self._strong.get(id(f), set())
                and not f.email
                and not f.phone
                and not f.email_hash
                and not f.user_id
            ):
                anon_by_id[f.resource_id].append(f)
        if not anon_by_id:
            return

        # Resource -> case mapping through strong facts and account delete
        # events.  This is used to recognise the known blocks in the activity
        # stream that follow the anonymize events.
        resource_cases: dict[str, set[str]] = defaultdict(set)
        for f in self.facts:
            tokens = self._strong.get(id(f), set())
            if not tokens:
                continue
            for case in self.cases:
                if not case.is_deletion:
                    continue
                if tokens & self.case_tokens.get(case.case_id, set()):
                    resource_cases[f.resource_id].add(case.case_id)
        for cid, aid in self.account_map.items():
            resource_cases[aid].add(cid)

        # Identity-linked analytics by case (eligibility).
        identified: dict[str, set[str]] = defaultdict(set)
        for case in self.cases:
            if not case.is_deletion:
                continue
            tokens = self.case_tokens.get(case.case_id, set())
            for f in self.facts:
                if f.record_type == "ANALYTICS_PROFILE" and (
                    self._strong.get(id(f), set()) & tokens
                ):
                    if ts_key(f.observed_at) <= ts_key(case.audit_at):
                        identified[case.case_id].add(f.resource_id)

        account_present = {
            cid for cid, aid in self.account_map.items()
            if self._account_present(cid, aid)
        }

        activity = self.ds.activity.copy()
        activity["_ts"] = activity["event_time"].map(ts_key)
        event_time: dict[str, float] = {}
        for _, row in activity[
            (activity["event_type"] == "ANONYMIZE_RECORD")
            & (activity["target_system"] == "analytics_platform")
        ].iterrows():
            rid = str(row["resource_id"])
            if rid in anon_by_id:
                event_time[rid] = min(event_time.get(rid, float("inf")), float(row["_ts"]))

        groups: dict[str, list[CaseRef]] = defaultdict(list)
        for case in self.cases:
            if case.is_deletion:
                groups[case.reported_at].append(case)

        # Place anonymize events in the closest intake batch (±12h).
        batch_rows: dict[str, list[tuple[float, str]]] = defaultdict(list)
        no_event: list[str] = []
        for rid in anon_by_id:
            t = event_time.get(rid)
            if t is None:
                no_event.append(rid)
                continue
            if not groups:
                continue
            rep, dist = min(
                ((r, abs(ts_key(r) - t)) for r in groups),
                key=lambda pair: pair[1],
            )
            if dist <= 12 * 3600:
                batch_rows[rep].append((t, rid))

        for rep, rows in batch_rows.items():
            rows.sort()
            if not rows:
                continue
            last_t = rows[-1][0]
            following: list[str] = []
            # The block immediately after the last anonymize event names the
            # case that owns the trailing row.  Keep first-seen order.
            for _, event in activity[
                (activity["_ts"] > last_t)
                & (activity["_ts"] <= last_t + 30 * 60)
            ].sort_values(["_ts", "resource_id"]).iterrows():
                # Only the support/flow/backup block is a reliable owner
                # marker.  A lone tombstone redaction can belong to another
                # case in the same batch and would steal the analytics row.
                if str(event["event_type"]) not in {
                    "REDACT_RECORD",
                    "DISABLE_DATA_FLOW",
                    "BLOCK_RESTORE",
                }:
                    continue
                if str(event["target_system"]) in {"identity_service", "account_service"}:
                    continue
                for cid in sorted(resource_cases.get(str(event["resource_id"]), set())):
                    if cid not in following:
                        following.append(cid)

            eligible = [
                c
                for c in groups[rep]
                if c.case_id not in identified
                and c.case_id not in account_present
            ]
            eligible.sort(key=lambda c: _case_number(c.case_id))
            used_cases: set[str] = set()

            # Assign from the last anonymize event backwards.  The first
            # following case owns the last row, the next case the one before
            # it, and so on.
            assigned_from_block = False
            for event_ts, rid in reversed(rows):
                target = None
                for cid in following:
                    if cid not in used_cases and any(c.case_id == cid for c in eligible):
                        target = cid
                        break
                if target is not None:
                    assigned_from_block = True
                elif len(rows) == 1:
                    # No following block.  The row belongs to the case that
                    # has no other discovered non-audit resource: the
                    # analytics profile is its only remaining record.  If
                    # several cases tie, leave the row unassigned rather than
                    # guess.
                    candidates = [c.case_id for c in eligible if c.case_id not in used_cases]
                    scores: dict[str, int] = {}
                    for cid in candidates:
                        case = next(c for c in self.cases if c.case_id == cid)
                        cs = self.build(case)
                        scores[cid] = sum(
                            1
                            for r in (cs.resources if cs else [])
                            if r.record_type
                            not in {
                                "SECURITY_AUDIT_LOG",
                                "USER_PROFILE",
                                "ANALYTICS_PROFILE",
                            }
                        )
                    if scores:
                        best = min(scores.values())
                        winners = [cid for cid, score in scores.items() if score == best]
                        if len(winners) == 1:
                            target = winners[0]
                elif assigned_from_block:
                    for c in eligible:
                        if c.case_id not in used_cases:
                            target = c.case_id
                            break
                if target is None:
                    break
                used_cases.add(target)
                method = "block" if target in following else ("single" if len(rows) == 1 else "remainder")
                meta = self.anonymous_meta.setdefault(
                    target,
                    {
                        "source": "activity",
                        "method": method,
                        "candidate_resources": [],
                        "batch_rows": len(rows),
                        "eligible_cases": [c.case_id for c in eligible],
                        "following_cases": list(following),
                    },
                )
                meta["candidate_resources"] = sorted(
                    set(meta["candidate_resources"]) | {rid}
                )
                self.anonymous_assignments[target].extend(anon_by_id[rid])

        # Rows with no activity event can only be assigned when exactly one
        # eligible case has the containing file in its audit window.
        for rid in no_event:
            facts = anon_by_id[rid]
            files = {f.file_id for f in facts}
            candidates: list[str] = []
            for case in self.cases:
                if not case.is_deletion or case.case_id in identified:
                    continue
                if case.case_id in account_present:
                    continue
                cut = ts_key(case.audit_at)
                start = cut - 7 * 86400
                for f in facts:
                    cap = ts_key(f.captured_at)
                    if f.file_id in files and start <= cap <= cut:
                        candidates.append(case.case_id)
                        break
            candidates = sorted(set(candidates), key=_case_number)
            if len(candidates) == 1 and candidates[0] not in self.anonymous_assignments:
                self.anonymous_assignments[candidates[0]].extend(facts)
                self.anonymous_meta[candidates[0]] = {
                    "source": "file",
                    "method": "unique-file",
                    "candidate_resources": [rid],
                    "batch_rows": 1,
                    "eligible_cases": candidates,
                    "following_cases": [],
                }

    def _account_present(self, case_id: str, account_id: str) -> bool:
        cut = ts_key(self._audit_for(case_id))
        facts = [
            f
            for f in self._fact_by_resource.get(account_id, [])
            if ts_key(f.observed_at) <= cut
        ]
        if not facts:
            return False
        latest = max(
            facts,
            key=lambda f: (ts_key(f.observed_at), ts_key(f.captured_at)),
        )
        return latest.state == "PRESENT"

    def _audit_for(self, case_id: str) -> str:
        for c in self.cases:
            if c.case_id == case_id:
                return c.audit_at
        return ""

    # ------------------------------------------------------------ state

    def build(self, case: CaseRef) -> CaseState | None:
        ident = self.identities.get(case.case_id)
        if ident is None:
            return None
        tokens = self.case_tokens[case.case_id]
        cut = ts_key(case.audit_at)
        start = cut - 7 * 86400

        # Facts tied to the requester by a strong identifier.
        matched = [
            f
            for f in self.facts
            if (self._strong.get(id(f), set()) & tokens)
            and ts_key(f.observed_at) <= cut
            and f.record_type in RELEVANT_TYPES
        ]

        citable: dict[str, Fact] = {}
        late: dict[str, Fact] = {}
        for f in matched:
            cap = ts_key(f.captured_at)
            if cap <= cut and cap >= start:
                old = citable.get(f.resource_id)
                if old is None or (
                    ts_key(f.observed_at),
                    ts_key(f.captured_at),
                ) > (
                    ts_key(old.observed_at),
                    ts_key(old.captured_at),
                ):
                    citable[f.resource_id] = f
            elif cap > cut:
                old = late.get(f.resource_id)
                if old is None or ts_key(f.observed_at) > ts_key(old.observed_at):
                    late[f.resource_id] = f

        resources: dict[str, Resource] = {}

        def add_fact(f: Fact, is_citable: bool) -> None:
            resources[f.resource_id] = Resource(
                system_id=f.system_id,
                resource_id=f.resource_id,
                record_type=f.record_type,
                state=f.state,
                evidence_id=f.file_id if is_citable else "",
                observed_at=f.observed_at,
                captured_at=f.captured_at,
                citable=is_citable,
                fact=f,
            )

        for f in citable.values():
            add_fact(f, True)
        for rid, f in late.items():
            if rid not in resources:
                add_fact(f, False)

        # Anonymous analytics assigned to this case.
        for f in self.anonymous_assignments.get(case.case_id, []):
            cap = ts_key(f.captured_at)
            if cap <= cut:
                add_fact(f, cap >= start)

        # Account resource.  Use a strong-matched fact if one exists; otherwise
        # look for a 404 fact by resource id, then a complete snapshot.
        account = self.account_map.get(case.case_id, "")
        account_evidence = ""
        account_citable = False
        if account:
            acc_fact = None
            for f in self._fact_by_resource.get(account, []):
                if ts_key(f.observed_at) > cut:
                    continue
                if f.record_type not in {"USER_PROFILE", "ACCOUNT_TOMBSTONE"}:
                    continue
                if acc_fact is None or (
                    ts_key(f.observed_at),
                    ts_key(f.captured_at),
                ) > (
                    ts_key(acc_fact.observed_at),
                    ts_key(acc_fact.captured_at),
                ):
                    acc_fact = f
            if acc_fact is not None:
                cap = ts_key(acc_fact.captured_at)
                is_cit = cap <= cut and cap >= start
                # Prefer an earlier citable fact if the newer one is a late read.
                if not is_cit and account in resources and resources[account].citable:
                    is_cit = True
                    acc_fact = resources[account].fact
                if account not in resources or is_cit:
                    resources[account] = Resource(
                        system_id="account_service",
                        resource_id=account,
                        record_type="USER_PROFILE",
                        state=acc_fact.state,
                        evidence_id=acc_fact.file_id if is_cit else "",
                        observed_at=acc_fact.observed_at,
                        captured_at=acc_fact.captured_at,
                        citable=is_cit,
                        fact=acc_fact,
                    )
                account_evidence = acc_fact.file_id if is_cit else ""
                account_citable = is_cit
            else:
                # Explicit absence proof for this resource id.
                absence = [
                    f
                    for f in self._fact_by_resource.get(account, [])
                    if f.state == "ABSENT" and ts_key(f.observed_at) <= cut
                ]
                if absence:
                    f = max(absence, key=lambda f: (ts_key(f.observed_at), ts_key(f.captured_at)))
                    cap = ts_key(f.captured_at)
                    is_cit = cap <= cut and cap >= start
                    resources[account] = Resource(
                        system_id="account_service",
                        resource_id=account,
                        record_type="USER_PROFILE",
                        state="ABSENT",
                        evidence_id=f.file_id if is_cit else "",
                        observed_at=f.observed_at,
                        captured_at=f.captured_at,
                        citable=is_cit,
                        fact=f,
                    )
                    account_evidence = f.file_id if is_cit else ""
                    account_citable = is_cit
                else:
                    proofs = self._snapshot_absence_proofs(case, account)
                    if proofs:
                        fid = proofs[0]
                        cap = ts_key(self.snapshots[fid]["captured_at"])
                        resources[account] = Resource(
                            system_id="account_service",
                            resource_id=account,
                            record_type="USER_PROFILE",
                            state="ABSENT",
                            evidence_id=fid,
                            observed_at=iso(self.snapshots[fid]["captured_at"]),
                            captured_at=iso(self.snapshots[fid]["captured_at"]),
                            citable=cap <= cut,
                            note="complete account snapshot",
                        )
                        account_evidence = fid
                        account_citable = True

        # Sort resources deterministically (planner imposes operation order).
        ordered = sorted(resources.values(), key=lambda r: (r.system_id, r.resource_id))
        return CaseState(
            case=case,
            identity=ident,
            account_id=account,
            account_evidence=account_evidence,
            account_citable=account_citable,
            resources=ordered,
        )


def _group_by(items: Iterable, key) -> list[tuple]:
    out: dict = defaultdict(list)
    for item in items:
        out[key(item)].append(item)
    return list(out.items())
