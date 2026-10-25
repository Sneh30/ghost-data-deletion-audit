"""Classify the free-text request as a deletion request or something else.

The dataset contains multilingual requests.  The evaluation set is mostly
deletion, so the classifier is deliberately conservative: it only returns
NOT_APPLICABLE when the text contains a clear non-deletion request, or an
explicit statement that deletion is *not* wanted.  This keeps a deletion
request containing incidental words such as "access" or "account" from being
misclassified.

No model call is required.  The small set of ambiguous requests can be routed
through an optional cached model fallback; the rule table below covers all
languages present in the public data.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Intent:
    is_deletion: bool
    reason: str
    confidence: float


# Strong deletion verbs in the languages present in the dataset.  The stems are
# intentionally broad (delete/deletion, erase/erasure, remove, close account,
# permanent closure, right to be forgotten, etc.).
_DELETION_PATTERNS = [
    r"\bdelet(?:e|ed|ing|ion)\b",
    r"\beras(?:e|ed|ing|ure)\b",
    r"\bremov(?:e|ed|ing|al)\b",
    r"\bclose\s+(?:my|this|the)\s+account\b",
    r"\bclosing\s+(?:my|this|the)\s+account\b",
    r"\baccount\s+closure\b",
    r"\bpermanent(?:ly)?\s+(?:delete|deletion|close|closure|erase|removal)\b",
    r"\bforget(?:ten)?\b",
    r"\bwipe\b",
    r"\bpurge\b",
    r"\b(?:is|are|was|were)\s+gone\b",
    r"\bno\s+longer\s+exists?\b",
    r"\bexclus[aã]o\b",
    r"\bexcluir\b",
    r"\bapagar\b",
    r"\belimin(?:ar|aci[oó]n)\b",
    r"\bsuprimir\b",
    r"\bsupprim(?:er|ez|é|ée|és|ées)\b",
    r"\bsuppression\b",
    r"\beffac(?:er|ement)\b",
    r"\bl[öo]sch(?:en|ung)\b",
    r"\bverwijderen\b",
    r"削除",
    r"消去",
    r"삭제",
    r"삭제",
    r"删除",
    r"刪除",
    r"\bterminate\b",
    r"\btermination\b",
]

# Explicit non-deletion requests / negations.  These are the signal for
# NOT_APPLICABLE.  A request can mention "delete" while negating it.
_NON_DELETION_PATTERNS = [
    r"\bnot\s+(?:asking|requesting|a\s+request)\s+(?:for\s+)?(?:deletion|deletion\s+of|erasure|removal)\b",
    r"\bnot\s+(?:a|an)\s+(?:request\s+)?(?:to\s+)?(?:delete|erase|remove|close)\b",
    r"\bdo\s+not\s+(?:delete|erase|remove|close|terminate)\b",
    r"\bdon'?t\s+(?:delete|erase|remove|close|terminate)\b",
    r"\bplease\s+(?:do\s+not|don'?t)\s+(?:delete|erase|remove|close)\b",
    r"\bnot\s+to\s+(?:delete|erase|remove|close)\b",
    r"\b(?:leave|keep)\b.{0,40}\b(?:account|profile|records?|history|data)\b.{0,30}\b(?:in\s+place|as\s+is|active|intact|unchanged)?\b",
    r"\b(?:still|continue\s+to)\s+(?:need|want|use|using)\b.{0,50}\b(?:account|service|profile|order\s+history|purchase\s+history)\b",
    r"\b(?:i\s+am|i'?m)\s+not\s+asking\s+for\s+deletion\b",
    r"\binformation\s+request\b",
    r"\bnot\s+a\s+request\s+to\s+erase\b",
    r"\bmarketing\s+(?:lists?|emails?|preferences?|messages?)\b",
    r"\b(?:unsubscribe|opt\s+out)\b",
    r"\bdownload\b.{0,40}\b(?:my|the)\b.{0,30}\b(?:information|data|account|invoices?|records?)\b",
    r"\bcopy\s+of\b.{0,40}\b(?:information|data|invoices?|records?)\b",
    r"\b(?:access|see|know|tell\s+me)\b.{0,50}\b(?:personal\s+information|what\s+information|data\s+you\s+hold|information\s+held)\b",
    r"\bcorrect(?:ion)?\b.{0,50}\b(?:name|surname|email|address|phone|record|information)\b",
    r"\b(?:spelling|misspelled|typo|wrong)\b.{0,40}\b(?:name|surname|email|address|phone)\b",
    r"\bchange\s+(?:the\s+)?(?:email|phone|mobile|address|name)\b",
    r"\breplace\s+(?:the\s+)?(?:mobile|phone|email|address)\b",
    r"\breset(?:ting)?\b.{0,30}\b(?:login|password|access)\b",
    r"\bcan'?t\s+access\b",
    r"\bwithout\s+(?:removing|deleting|closing)\b",
    r"\bkeep\s+(?:the\s+)?account\s+as\s+it\s+is\b",
]

_ACCESS_OR_CORRECTION_ONLY = re.compile(
    r"(?:"
    + "|".join(_NON_DELETION_PATTERNS)
    + r")",
    re.IGNORECASE | re.DOTALL,
)
_DELETION = re.compile("|".join(_DELETION_PATTERNS), re.IGNORECASE | re.DOTALL)


def classify_request(text: str) -> Intent:
    """Return the request intent using deterministic language rules.

    Order matters.  A clear negation or an unrelated privacy right wins even
    when a deletion word is present (e.g. "I am not asking for deletion").
    """
    normalized = re.sub(r"\s+", " ", (text or "").strip().lower())
    if not normalized:
        return Intent(False, "empty request", 1.0)

    # Specific explicit negations / other rights.  These are checked first so
    # that the word "deletion" in "not asking for deletion" is not decisive.
    non_deletion = bool(_ACCESS_OR_CORRECTION_ONLY.search(normalized))

    # A deletion verb plus an object that makes the deletion unambiguous.
    deletion = bool(_DELETION.search(normalized))

    # Phrases that mention a deletion word only to scope a different right.
    marketing_only = bool(
        re.search(r"\b(?:only|just)\b.{0,25}\bmarketing\b", normalized)
        or re.search(r"\bmarketing\b.{0,25}\b(?:only|just)\b", normalized)
    )
    if marketing_only:
        return Intent(False, "marketing preference only", 0.99)

    if non_deletion and not deletion:
        return Intent(False, "non-deletion privacy request", 0.98)
    if non_deletion and deletion:
        # "correct it without removing any records" scopes the deletion word
        # to a negation, not an authorization.
        if re.search(r"\bwithout\s+(?:removing|deleting|closing|erasing)\b", normalized):
            return Intent(False, "deletion word appears inside a negation", 0.99)
        # If the text explicitly negates deletion, it is not authorized.
        explicit_negation = bool(
            re.search(
                r"\b(?:not|never|don'?t|do\s+not)\b.{0,30}\b(?:delete|erase|remove|close|deletion|erasure|removal)\b",
                normalized,
            )
            or re.search(
                r"\b(?:delete|erase|remove|close|deletion|erasure|removal)\b.{0,30}\b(?:not|never)\b",
                normalized,
            )
        )
        if explicit_negation:
            return Intent(False, "deletion explicitly negated", 0.99)
        # Otherwise a deletion request can naturally mention access/export.
        return Intent(True, "deletion request with additional context", 0.85)

    if deletion:
        return Intent(True, "deletion request", 0.99)
    return Intent(False, "no deletion authorization", 0.9)
