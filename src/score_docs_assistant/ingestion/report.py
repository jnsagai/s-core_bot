"""Coverage report, human summary, and deterministic JSON Lines output (FR-023, FR-024;
contracts/normalized-output.md)."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from score_docs_assistant.domain.ingestion import (
    AmbiguousItem,
    Block,
    CoverageReport,
    Diagnostic,
    Entity,
    ExportConsistency,
    FailedFile,
    LinkRef,
    LinkSummary,
    LockedSource,
    NormalizedDocument,
    PartialFile,
    SourceCoverage,
    UnresolvedItem,
)
from score_docs_assistant.ingestion.canonical import (
    CANONICAL_VERSION,
    canonical_hash,
    canonical_json,
)

if TYPE_CHECKING:
    from score_docs_assistant.ingestion.normalize import NormalizationOutcome


@dataclass
class SourceData:
    """Everything normalization learned about one locked source."""

    locked: LockedSource
    documents: list[NormalizedDocument] = field(default_factory=list)
    entities: list[Entity] = field(default_factory=list)
    coverage_failure: str | None = None
    integrity_diagnostics: list[Diagnostic] = field(default_factory=list)
    processing_hash: str | None = None
    export_docnames: dict[str, str] = field(default_factory=dict)
    consistency: ExportConsistency | None = None


def _walk(blocks: list[Block]) -> list[Block]:
    out: list[Block] = []
    for block in blocks:
        out.append(block)
        out.extend(_walk(block.children))
    return out


def _link_summary(data: SourceData) -> LinkSummary:
    refs: list[tuple[str, LinkRef]] = [(e.key, r) for e in data.entities for r in e.links]
    for doc in data.documents:
        refs += [(doc.path, r) for b in _walk(doc.blocks) for r in b.references]
    counts = Counter(r.resolution for _, r in refs)
    return LinkSummary(
        resolved=counts["resolved"],
        ambiguous=counts["ambiguous"],
        unresolved=counts["unresolved"],
        malformed=counts["malformed"],
        ambiguous_items=[
            AmbiguousItem(from_key=k, via=r.via, target_id=r.target_id, candidates=r.resolved_keys)
            for k, r in refs
            if r.resolution == "ambiguous"
        ],
        unresolved_items=[
            UnresolvedItem(from_key=k, via=r.via, target_id=r.target_id)
            for k, r in refs
            if r.resolution == "unresolved"
        ],
    )


def _coverage(data: SourceData) -> SourceCoverage:
    locked = data.locked
    statuses = Counter(d.status for d in data.documents)
    failed = [
        FailedFile(
            path=d.path,
            reason=next((x.code for x in d.diagnostics if x.severity == "error"), "FAILED"),
        )
        for d in data.documents
        if d.status == "failed"
    ] + [FailedFile(path=x.path, reason=x.code) for x in data.integrity_diagnostics]
    partial_files = [
        PartialFile(
            path=d.path, codes=sorted({x.code for x in d.diagnostics if x.severity == "warning"})
        )
        for d in data.documents
        if d.status == "partial"
    ]
    all_diagnostics = [x for d in data.documents for x in d.diagnostics]
    all_diagnostics += data.integrity_diagnostics
    git_docs = [d for d in data.documents if d.format != "needs-export"]
    return SourceCoverage(
        source_id=locked.source_id,
        kind=locked.kind,
        revision=locked.revision,
        status="failed" if data.coverage_failure else "ok",
        failure=data.coverage_failure,
        selected=len(locked.files),
        included=statuses["included"],
        partial=statuses["partial"],
        partial_files=partial_files,
        failed=failed,
        skipped=list(locked.skipped),
        excluded_by_selector=locked.excluded_by_selector,
        entities=len(data.entities),
        links=_link_summary(data),
        diagnostics_by_code=dict(sorted(Counter(x.code for x in all_diagnostics).items())),
        licenses=dict(sorted(Counter(d.license.spdx or "unknown" for d in git_docs).items())),
        requires_review=sorted(
            d.path for d in git_docs if d.license.redistribution == "requires_review"
        ),
        export_consistency=data.consistency,
    )


def build_report(lock_sha256: str, sources: list[SourceData]) -> CoverageReport:
    coverage = [_coverage(s) for s in sources]
    return CoverageReport(
        lock_sha256=lock_sha256,
        processing_hash=canonical_hash(
            {s.locked.source_id: s.processing_hash for s in sources if s.processing_hash}
        ),
        sources=coverage,
        totals={
            "documents": sum(len(s.documents) for s in sources),
            "entities": sum(c.entities for c in coverage),
            "diagnostics": sum(sum(c.diagnostics_by_code.values()) for c in coverage),
            "sources_failed": sum(1 for c in coverage if c.status == "failed"),
        },
    )


def render_text(report: CoverageReport) -> str:
    lines: list[str] = []
    for c in report.sources:
        revision = (c.revision or "-")[:7]
        if c.status == "failed":
            lines.append(f"{c.source_id} @ {revision}  FAILED  {c.failure}")
            continue
        lines.append(
            f"{c.source_id} @ {revision}  selected {c.selected}  included {c.included}  "
            f"partial {c.partial}  failed {len(c.failed)}  entities {c.entities}"
        )
        links = c.links
        lines.append(
            f"  links: resolved {links.resolved}  ambiguous {links.ambiguous}  "
            f"unresolved {links.unresolved}  malformed {links.malformed}"
        )
        top = sorted(c.diagnostics_by_code.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
        diagnostics = ", ".join(f"{code} {count}" for code, count in top) or "none"
        lines.append(
            f"  requires review: {len(c.requires_review)} files   top diagnostics: {diagnostics}"
        )
        if c.partial_files:
            shown = ", ".join(f"{p.path} ({'/'.join(p.codes)})" for p in c.partial_files[:5])
            more = f" … +{len(c.partial_files) - 5} more" if len(c.partial_files) > 5 else ""
            lines.append(f"  partial: {shown}{more}")
        if c.export_consistency is not None:
            s = c.export_consistency
            lines.append(
                f"  export consistency vs {s.associated_source}: matched {s.matched}  "
                f"id-only {s.id_only_matched}  missing in source {s.missing_in_source}  "
                f"missing in export {s.missing_in_export}  (statistic only; unverified)"
            )
    return "\n".join(lines)


def write_report(report: CoverageReport, reports_dir: Path) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"coverage-{report.lock_sha256[:12]}.json"
    path.write_text(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n")
    return path


def _jsonl(records: list[dict[str, object]]) -> str:
    return "".join(
        canonical_json({**r, "canonical_version": CANONICAL_VERSION}).decode("utf-8") + "\n"
        for r in records
    )


def write_outputs(outcome: NormalizationOutcome, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "documents.jsonl").write_text(
        _jsonl([d.model_dump(mode="json") for d in outcome.documents]), encoding="utf-8"
    )
    (output_dir / "entities.jsonl").write_text(
        _jsonl([e.model_dump(mode="json") for e in outcome.entities]), encoding="utf-8"
    )
