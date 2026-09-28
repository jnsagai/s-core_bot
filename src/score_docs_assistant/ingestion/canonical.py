"""Canonical serialization, hashes and document keys (FR-017, research.md R9).

Hashes are SHA-256 over canonical JSON: sorted keys, compact separators, UTF-8, no floats.
`CANONICAL_VERSION` versions this serialization; `PARSER_VERSION` versions our normalization
logic. Both feed `processing_hash`, so changing either changes every document key.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import docutils
import markdown_it

CANONICAL_VERSION = 1
PARSER_VERSION = "1"


def _reject_floats(value: Any) -> None:
    if isinstance(value, float):
        raise TypeError("floats are not allowed in canonical records")
    if isinstance(value, dict):
        for item in value.values():
            _reject_floats(item)
    elif isinstance(value, list | tuple):
        for item in value:
            _reject_floats(item)


def canonical_json(obj: Any) -> bytes:
    _reject_floats(obj)
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_hash(obj: Any) -> str:
    return sha256_hex(canonical_json(obj))


def library_versions() -> dict[str, str]:
    return {"docutils": docutils.__version__, "markdown-it-py": markdown_it.__version__}


def processing_hash(profile_hash: str, versions: dict[str, str] | None = None) -> str:
    return canonical_hash(
        {
            "canonical_version": CANONICAL_VERSION,
            "parser_version": PARSER_VERSION,
            "profile_hash": profile_hash,
            "libraries": versions if versions is not None else library_versions(),
        }
    )


def document_key(source_id: str, path: str, raw_sha256: str, processing: str) -> str:
    """Stable for identical bytes + configuration regardless of revision (enables F003 reuse)."""
    return canonical_hash(
        {
            "canonical_version": CANONICAL_VERSION,
            "source_id": source_id,
            "path": path,
            "raw_sha256": raw_sha256,
            "processing_hash": processing,
        }
    )
