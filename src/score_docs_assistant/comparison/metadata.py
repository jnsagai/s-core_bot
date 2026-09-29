"""Snapshot metadata comparison (FR-009, FR-010, research R5a, R6).

Pure function of two manifests: per-source relations, processing identity differences and
warnings. A product release label is never inferred; per-source revisions are the identity.
"""

from __future__ import annotations

from score_docs_assistant.domain.comparison import (
    ProcessingDifference,
    SnapshotDiff,
    SourceRelation,
    SourceRelationKind,
)
from score_docs_assistant.domain.snapshots import ManifestSource, SnapshotManifest

IDENTICAL_REVISIONS = (
    "identical_revisions: every source revision is the same in both snapshots, so the "
    "documentation content is the same; differences can only come from processing or retrieval"
)


def _relation(left: ManifestSource | None, right: ManifestSource | None) -> SourceRelationKind:
    if left is None:
        return "right_only"
    if right is None:
        return "left_only"
    return "same" if left.revision == right.revision else "different"


def _processing(left: SnapshotManifest, right: SnapshotManifest) -> list[ProcessingDifference]:
    def embedding(manifest: SnapshotManifest) -> str | None:
        e = manifest.embedding
        return f"{e.model_tag}@{e.model_digest[:12]}" if e is not None else None

    pairs = [
        ("chunker_version", left.chunker_version, right.chunker_version),
        ("chunker_config_sha256", left.chunker_config_sha256, right.chunker_config_sha256),
        (
            "corpus_schema_version",
            str(left.corpus_schema_version),
            str(right.corpus_schema_version),
        ),
        ("semantic", left.semantic, right.semantic),
        ("embedding_model", embedding(left), embedding(right)),
        ("app_version", left.app_version, right.app_version),
    ]
    return [ProcessingDifference(field=f, left=a, right=b) for f, a, b in pairs if a != b]


def snapshot_diff(left: SnapshotManifest, right: SnapshotManifest) -> SnapshotDiff:
    left_sources = {s.source_id: s for s in left.sources}
    right_sources = {s.source_id: s for s in right.sources}
    rows: list[SourceRelation] = []
    warnings: list[str] = []
    for source_id in sorted(left_sources.keys() | right_sources.keys()):
        a, b = left_sources.get(source_id), right_sources.get(source_id)
        relation = _relation(a, b)
        rows.append(
            SourceRelation(
                source_id=source_id,
                relation=relation,
                left_revision=a.revision if a else None,
                right_revision=b.revision if b else None,
                left_revision_status=a.revision_status if a else None,
                right_revision_status=b.revision_status if b else None,
                left_status=a.status if a else None,
                right_status=b.status if b else None,
            )
        )
        if relation in ("left_only", "right_only"):
            side = "left" if relation == "left_only" else "right"
            warnings.append(
                f"source_only_on_one_side: {source_id} is only in the {side} snapshot; content "
                "from it cannot be compared"
            )
        for label, entry in (("left", a), ("right", b)):
            if entry is None:
                continue
            if entry.revision_status != "pinned":
                warnings.append(
                    f"unverified_revision: {source_id} in the {label} snapshot has an "
                    f"{entry.revision_status} revision (not tied to a commit)"
                )
            if entry.status != "ok":
                warnings.append(
                    f"source_not_ok: {source_id} is {entry.status} in the {label} snapshot"
                )
    shared = [r for r in rows if r.relation in ("same", "different")]
    if shared and all(r.relation == "same" for r in rows):
        warnings.insert(0, IDENTICAL_REVISIONS)
    return SnapshotDiff(
        left_snapshot_id=left.snapshot_id,
        right_snapshot_id=right.snapshot_id,
        left_created_at=left.created_at,
        right_created_at=right.created_at,
        sources=rows,
        processing=_processing(left, right),
        warnings=warnings,
    )
