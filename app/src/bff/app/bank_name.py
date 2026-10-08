"""Normalize the canonical firm label in complete prose, not source identities.

Brand selection belongs to the frontend. This module does not translate real
institution names or schema fields; sources and agent instructions must already
use the bank-neutral contract.
"""

from __future__ import annotations

import re
from typing import Any

_BANK = re.compile(r"(?<![\w/-])(?:the[ \t]+)+bank(?![\w/-])", re.I)
_SENTENCE_START = re.compile(
    r"(?:^|[.!?]\s+|\n|\|)[ \t]*(?:(?:[-*+>#]+|\d+\.)[ \t]*)?[\"'“‘(\[]*$"
)
_PROTECTED = re.compile(
    r"^[ \t]*(?P<fence>`{3,}|~{3,})[^\n]*\n[\s\S]*?"
    r"(?:^[ \t]*(?P=fence)[`~]*[ \t]*(?:\n|\Z)|\Z)"
    r"|(?<!`)(?P<ticks>`+)(?!`)[\s\S]*?(?<!`)(?P=ticks)(?!`)"
    r"|^(?: {4}|\t)[^\n]*(?:\n|\Z)"
    r"|\]\((?:[^()\n]|\([^()\n]*\))*\)"
    r"|(?:https?://|urn:)[^\s<>]+"
    r"|^[ \t]*\[[^\]\n]+\]:[^\n]*"
    r"|【[^】]*】|\[[^\]\n]*\](?![\[(])"
    r"|\b(?:href|src|id)\s*=\s*(?:\"[^\"]*\"|'[^']*')",
    re.I | re.M,
)


def normalize_bank_text(text: str) -> str:
    """Canonicalize articles/case without altering code, links or citation IDs."""
    protected = [(m.start(), m.end()) for m in _PROTECTED.finditer(text)]

    def replace(match: re.Match[str]) -> str:
        if any(start < match.end() and match.start() < end for start, end in protected):
            return match.group()
        return "The Bank" if _SENTENCE_START.search(text[:match.start()]) else "the Bank"

    return _BANK.sub(replace, text)


def normalize_citations(citations: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Copy citations, normalizing display prose only; metadata stays untouched."""
    out = []
    for c in citations or []:
        c = dict(c)
        for key in ("title", "snippet", "text"):
            if isinstance(c.get(key), str):
                c[key] = normalize_bank_text(c[key])
        out.append(c)
    return out
