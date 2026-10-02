"""Promotion gate: may a freshly built snapshot replace the active one unattended? (F011 FR-006)

Every check runs and is reported even after one fails, so the operator sees the whole picture.
The gate detects broken builds (parser regressions, truncated exports, lost embeddings, mass
deletion); it is not an engineering review of the content.
"""

from __future__ import annotations

from collections.abc import Callable

from score_docs_assistant.config.schema import AppConfig
from score_docs_assistant.domain.errors import SnapshotError
from score_docs_assistant.domain.ingestion import SourceLock
from score_docs_assistant.domain.snapshots import SnapshotManifest
from score_docs_assistant.refresh.models import GateCheck
from score_docs_assistant.retrieval.evaluation import ExactIdReport
from score_docs_assistant.storage.catalog import Catalog
from score_docs_assistant.storage.lifecycle import verify_for_activation
from score_docs_assistant.storage.manifest import read_snapshot_manifest

ExactIds = Callable[[str], ExactIdReport]


class PromotionGate:
    def __init__(self, config: AppConfig, *, exact_ids: ExactIds) -> None:
        self._config = config
        self._exact_ids = exact_ids

    def evaluate(
        self, candidate: str, active: SnapshotManifest | None, lock: SourceLock
    ) -> list[GateCheck]:
        manifest = read_snapshot_manifest(self._config.data_dir / "snapshots" / candidate)
        return [
            self._integrity(candidate),
            self._exact(candidate),
            self._coverage(manifest, active),
            self._semantic(manifest, active),
            self._required(manifest, lock),
        ]

    def _integrity(self, candidate: str) -> GateCheck:
        catalog = Catalog.open(self._config.data_dir, create=False)
        if catalog is None:
            return GateCheck(id="integrity", status="fail", detail="no snapshot catalog")
        with catalog:
            row = catalog.get(candidate)
        if row is None or row.state != "validated":
            state = "missing" if row is None else row.state
            return GateCheck(id="integrity", status="fail", detail=f"{candidate} is {state}")
        try:
            verify_for_activation(self._config, row)
        except SnapshotError as exc:
            return GateCheck(id="integrity", status="fail", detail=exc.message)
        return GateCheck(id="integrity", status="pass", detail="checksums and manifest verified")

    def _exact(self, candidate: str) -> GateCheck:
        try:
            report = self._exact_ids(candidate)
        except SnapshotError as exc:
            return GateCheck(id="exact_ids", status="fail", detail=exc.message)
        detail = f"{report.correct_first}/{report.ids_checked} found first"
        if report.failures:
            sample = ", ".join(f.need_id for f in report.failures[:5])
            return GateCheck(id="exact_ids", status="fail", detail=f"{detail}; e.g. {sample}")
        return GateCheck(id="exact_ids", status="pass", detail=detail)

    def _coverage(self, new: SnapshotManifest, active: SnapshotManifest | None) -> GateCheck:
        if active is None:
            return GateCheck(id="coverage_drop", status="pass", detail="no active snapshot")
        limit = self._config.refresh.max_count_drop
        parts: list[str] = []
        failed = False
        for name in ("documents", "chunks", "entities"):
            before = getattr(active.counts, name)
            after = getattr(new.counts, name)
            drop = (before - after) / before if before else 0.0
            if drop > limit:
                failed = True
            parts.append(f"{name} {before}→{after}")
        detail = ", ".join(parts) + f" (max drop {limit:.0%})"
        return GateCheck(id="coverage_drop", status="fail" if failed else "pass", detail=detail)

    @staticmethod
    def _semantic(new: SnapshotManifest, active: SnapshotManifest | None) -> GateCheck:
        if active is not None and active.semantic == "present" and new.semantic != "present":
            return GateCheck(
                id="semantic",
                status="fail",
                detail="active snapshot has semantic search; the candidate does not",
            )
        return GateCheck(id="semantic", status="pass", detail=f"semantic {new.semantic}")

    @staticmethod
    def _required(new: SnapshotManifest, lock: SourceLock) -> GateCheck:
        covered = {s.source_id: s.status for s in new.coverage.sources}
        missing = [
            s.source_id
            for s in lock.sources
            if s.required and covered.get(s.source_id) in (None, "failed")
        ]
        if missing:
            return GateCheck(
                id="required_sources", status="fail", detail=f"missing or failed: {missing}"
            )
        required = sum(1 for s in lock.sources if s.required)
        return GateCheck(
            id="required_sources", status="pass", detail=f"{required} required source(s) present"
        )
