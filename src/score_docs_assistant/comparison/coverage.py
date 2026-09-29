"""Coverage reasons for `not_established` differences (FR-005, research R4).

Derived only from the snapshot manifests and the record lookup, never from model output. The
reason explains why a comparison cannot say more; it never claims that content was removed.
"""

from __future__ import annotations

from score_docs_assistant.domain.comparison import CoverageReason
from score_docs_assistant.domain.snapshots import SnapshotManifest


def source_reason(manifest: SnapshotManifest, source_id: str) -> CoverageReason | None:
    """Why `source_id` may be incompletely covered in `manifest`; None when fully covered."""
    entry = next((s for s in manifest.sources if s.source_id == source_id), None)
    if entry is None:
        return "source_absent"
    if entry.status != "ok":
        return "source_failed"
    summary = next((s for s in manifest.coverage.sources if s.source_id == source_id), None)
    if summary is not None and (summary.partial or summary.failed):
        return "source_partial"
    return None


def missing_reason(
    manifest: SnapshotManifest, source_ids: list[str], default: CoverageReason
) -> CoverageReason:
    """The strongest coverage reason over the sources the other side's evidence came from."""
    strongest: tuple[CoverageReason, ...] = ("source_absent", "source_failed", "source_partial")
    for reason in strongest:
        if any(source_reason(manifest, s) == reason for s in source_ids):
            return reason
    return default


REASON_TEXT: dict[CoverageReason, str] = {
    "source_absent": "the source is not in the {side} snapshot",
    "source_failed": "the source failed to sync in the {side} snapshot",
    "source_partial": "the source is only partly covered in the {side} snapshot",
    "record_not_found": "the record was not found in the {side} snapshot's records",
    "record_without_excerpt": "the record has no excerpt in the {side} snapshot",
    "not_retrieved": "it was not found in the {side} snapshot's retrieved evidence",
    "no_evidence": "the {side} snapshot returned no evidence for this question",
}


def reason_text(reason: CoverageReason, side: str) -> str:
    return REASON_TEXT[reason].format(side=side)
