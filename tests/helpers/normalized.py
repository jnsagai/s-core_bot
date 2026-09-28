"""Normalize a `SnapshotEnv` and build blocks by hand for chunker unit tests."""

from __future__ import annotations

import hashlib

from score_docs_assistant.domain.ingestion import Block, LicenseRecord, NormalizedDocument
from score_docs_assistant.ingestion.normalize import NormalizationOutcome, NormalizationService
from score_docs_assistant.sources.lock import read_lock
from tests.helpers.snapshot_env import PROFILES, SnapshotEnv


def normalize_env(env: SnapshotEnv) -> NormalizationOutcome:
    lock_sha = hashlib.sha256(env.lock_path.read_bytes()).hexdigest()
    return NormalizationService(read_lock(env.lock_path), lock_sha, env.data, PROFILES).run()


def block(kind: str, text: str, heading: list[str] | None = None, **extra: object) -> Block:
    return Block.model_validate(
        {
            "kind": kind,
            "text": text,
            "heading_path": heading or ["H"],
            "line_start": 1,
            "line_end": 2,
            "origin_path": "docs/x.rst",
            "raw_sha256": "0" * 64,
            **extra,
        }
    )


def document(blocks: list[Block], key: str = "doc-key", source: str = "s") -> NormalizedDocument:
    return NormalizedDocument(
        document_key=key,
        source_id=source,
        revision="r" * 40,
        path="docs/x.rst",
        format="rst",
        title="Doc",
        license=LicenseRecord(spdx="Apache-2.0", basis="declared", redistribution="allowed"),
        raw_sha256="0" * 64,
        normalized_sha256="0" * 64,
        processing_hash="0" * 64,
        blocks=blocks,
        diagnostics=[],
        status="included",
    )
