"""Contact parser for the conversational ticket flow.

When a COMPLAINT lands without a contact record on the session, the
graph asks the user for their name, phone, and email. The next user
message is parsed by this module — anything we can lift (phone, email,
remaining text → name) becomes a `Contact`. The ticket is filed once
we have at least a phone OR an email so a human agent can call/write
back.

The phone and email regexes are reused from `src/pii.py` so the parser
agrees with the redactor about what counts as PII.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from src.pii import _RECOGNISERS  # noqa: SLF001 — reuse compiled patterns

_PHONE_RE = next(p for k, p in _RECOGNISERS if k == "EG_PHONE")
_EMAIL_RE = next(p for k, p in _RECOGNISERS if k == "EMAIL")

# Strip common label prefixes ("name:", "اسمي", "I'm", "أنا") so what's
# left is closer to the actual name.
_NAME_LABEL_RE = re.compile(
    r"^\s*(?:name|الاسم|اسمي|انا|أنا|i'?m|my\s+name\s+is)\s*[:،-]?\s*",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Contact:
    name: str | None = None
    phone: str | None = None
    email: str | None = None

    def is_actionable(self) -> bool:
        """At minimum we need a way to reach the customer back."""
        return bool(self.phone or self.email)

    def as_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v}


def parse_contact(text: str) -> Contact:
    """Extract a `Contact` from a free-form user message.

    Examples:
        "Ahmed Mohamed, 01012345678, ahmed@gmail.com"
        "اسمي محمد، الهاتف 01098765432"
        "0100 123 4567"          → phone-only is fine
        "ahmed@niletel.com"      → email-only is fine
    """
    if not text:
        return Contact()

    phone_match = _PHONE_RE.search(text)
    email_match = _EMAIL_RE.search(text)
    phone = phone_match.group(0).strip() if phone_match else None
    email = email_match.group(0).strip() if email_match else None

    # Whatever remains after removing phone + email becomes the name
    # candidate. We also drop common label words and stray punctuation.
    leftover = text
    if phone:
        leftover = leftover.replace(phone, " ")
    if email:
        leftover = leftover.replace(email, " ")
    leftover = _NAME_LABEL_RE.sub("", leftover)
    leftover = re.sub(r"[,،.\-:|\n]+", " ", leftover)
    leftover = re.sub(r"\s{2,}", " ", leftover).strip()

    name: str | None = None
    if leftover:
        # Cap to a reasonable length so we don't store entire sentences
        # as "names" if the user typed a paragraph.
        candidate = leftover[:60].strip()
        # Reject if the leftover is just filler ("the", "yes", etc.).
        if len(candidate) >= 2 and any(ch.isalpha() for ch in candidate):
            name = candidate

    return Contact(name=name, phone=phone, email=email)


def format_missing(contact: Contact) -> str:
    """Human-readable list of what we still need."""
    missing = []
    if not contact.name:
        missing.append("name")
    if not contact.phone and not contact.email:
        missing.append("phone or email")
    return ", ".join(missing)
