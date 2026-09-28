"""`pretoken-v1`: a conservative token estimate (FR-003, specs/003-snapshot-index/research.md R2).

Measured against nomic-embed-text (WordPiece) and qwen3 (BPE) on real S-CORE paragraphs, it never
under-counted: ASCII letter runs cost ceil(len/2), every other non-space character costs one token
per UTF-8 byte, plus two special tokens. It can under-count adversarial gibberish, so the hard
guarantee is the embedding runtime's `truncate: false` (research R1), not this estimate.
"""

from __future__ import annotations

import re

TOKEN_COUNT_METHOD = "pretoken-v1"
_SPECIAL_TOKENS = 2
_PRETOKEN = re.compile(r"[A-Za-z]+|[^\sA-Za-z]")


def estimate_tokens(text: str) -> int:
    total = _SPECIAL_TOKENS
    for match in _PRETOKEN.finditer(text):
        piece = match.group()
        if piece.isascii() and piece.isalpha():
            total += (len(piece) + 1) // 2
        else:
            total += len(piece.encode("utf-8"))
    return total
