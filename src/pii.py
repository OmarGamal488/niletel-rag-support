"""PII redaction layer (Tier 3 #11).

Strips Egyptian-context PII out of queries before they reach the LLM and
restores it in the answer so the user still sees their own data. This is
a regex-based subset of what Microsoft Presidio's `AnalyzerEngine` does;
the public API (`redact` / `restore`) mirrors Presidio's pattern so a
production deployment can swap this module out for the real library.

Recognised entity types:
  * EG_PHONE       — Egyptian mobile (e.g. 01012345678, +20 1012345678)
  * EG_NATIONAL_ID — 14-digit Egyptian national ID
  * EMAIL          — anything@anything.tld
  * IBAN           — Egyptian IBAN (EG + 27 digits)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

# Order matters: more specific patterns first. Each entry is
# (entity_kind, compiled_regex).
_RECOGNISERS: list[tuple[str, re.Pattern[str]]] = [
    (
        "EG_NATIONAL_ID",
        # 14 digits, century-leading 2 or 3, sandwiched in non-digit
        # boundaries so it doesn't eat phone-number prefixes.
        re.compile(r"(?<!\d)([23]\d{13})(?!\d)"),
    ),
    (
        "IBAN",
        re.compile(r"\bEG\d{27}\b"),
    ),
    (
        "EG_PHONE",
        # Either:
        #   +20[ ]1XXXXXXXXX | 0020[ ]1XXXXXXXXX  (12-digit international)
        #   01XXXXXXXXX                            (11-digit local)
        # The lookarounds prevent the regex from eating leading
        # whitespace, which would otherwise contaminate the redaction map.
        re.compile(
            r"(?<!\d)(?:(?:\+20|0020)\s?1[0125]\d{8}|01[0125]\d{8})(?!\d)"
        ),
    ),
    (
        "EMAIL",
        re.compile(
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
        ),
    ),
]


@dataclass(frozen=True)
class PIIMatch:
    kind: str
    original: str
    placeholder: str


def _make_placeholder(kind: str, idx: int) -> str:
    return f"<{kind}_{idx}>"


def redact(text: str) -> tuple[str, dict[str, str]]:
    """Replace each PII span with a typed placeholder.

    Returns the redacted text and a `{placeholder: original}` mapping so
    callers can `restore()` later. Idempotent on plain text (no PII →
    text + {}).
    """
    if not text:
        return text, {}

    mapping: dict[str, str] = {}
    counters: dict[str, int] = {}

    def _sub(kind: str, match: re.Match[str]) -> str:
        original = match.group(0)
        # Already-allocated? Re-use the same placeholder for stable maps.
        for ph, orig in mapping.items():
            if orig == original:
                return ph
        counters[kind] = counters.get(kind, 0) + 1
        ph = _make_placeholder(kind, counters[kind])
        mapping[ph] = original
        return ph

    out = text
    for kind, pat in _RECOGNISERS:
        out = pat.sub(lambda m, k=kind: _sub(k, m), out)
    return out, mapping


def restore(text: str, mapping: dict[str, str]) -> str:
    """Replace any placeholders in `text` with their original values."""
    if not text or not mapping:
        return text
    out = text
    # Sort longest-first so `<EG_PHONE_10>` doesn't get partially matched by
    # `<EG_PHONE_1>`.
    for ph in sorted(mapping.keys(), key=len, reverse=True):
        out = out.replace(ph, mapping[ph])
    return out


def found_kinds(mapping: dict[str, str]) -> list[str]:
    """Distinct entity kinds present in a redaction map (for metrics / UI)."""
    return sorted({ph.strip("<>").rsplit("_", 1)[0] for ph in mapping})


__all__ = ["redact", "restore", "PIIMatch", "found_kinds"]
