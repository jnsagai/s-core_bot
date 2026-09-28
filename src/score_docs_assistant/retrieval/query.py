"""Query handling shared by all retrieval paths (specs/004-hybrid-search/research.md R1, R2, R9).

User text is never passed to FTS5 as an expression: each token becomes a quoted string literal and
tokens are OR-ed, so operators such as `AND`, `NEAR(`, `*` or `col:` are matched as plain words.
"""

from __future__ import annotations

import re

MAX_QUERY_TERMS = 64
_TRAILING = ".,;:!?)]\"'"
_LEADING = "([\"'"
_ALIAS_SEPARATORS = re.compile(r"[-._\s]+")
_HAS_WORD = re.compile(r"\w")
_SNAPSHOT_ID = re.compile(r"^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$")
_CHUNK_ID = re.compile(r"^[0-9a-f]{64}$")


def tokenize(query: str) -> list[str]:
    return query.split()


def id_tokens(query: str) -> list[str]:
    """Candidate IDs: tokens with surrounding sentence punctuation removed, in query order."""
    tokens: list[str] = []
    for token in tokenize(query):
        stripped = token.rstrip(_TRAILING).lstrip(_LEADING)
        if stripped:
            tokens.append(stripped)
    return tokens


def alias(identifier: str) -> str:
    """Normalized alias (FR-002): case-folded, separator runs collapsed to `_`, trimmed."""
    return _ALIAS_SEPARATORS.sub("_", identifier.casefold()).strip("_")


def fts_expression(query: str) -> tuple[str | None, bool]:
    """(expression, truncated). None when no token carries a letter or digit."""
    terms: list[str] = []
    seen: set[str] = set()
    truncated = False
    for token in tokenize(query):
        if not _HAS_WORD.search(token) or token in seen:
            continue
        if len(terms) == MAX_QUERY_TERMS:
            truncated = True
            break
        seen.add(token)
        terms.append('"' + token.replace('"', '""') + '"')
    return (" OR ".join(terms) if terms else None), truncated


def excerpt(text: str, limit: int) -> tuple[str, bool]:
    """Stored display text bounded to `limit` characters, cut at whitespace when possible."""
    if len(text) <= limit:
        return text, False
    cut = text[:limit]
    space = max(cut.rfind(" "), cut.rfind("\n"))
    if space > 0:
        cut = cut[:space]
    return cut.rstrip(), True


def valid_snapshot_id(value: str) -> bool:
    return bool(_SNAPSHOT_ID.match(value))


def valid_chunk_id(value: str) -> bool:
    return bool(_CHUNK_ID.match(value))
