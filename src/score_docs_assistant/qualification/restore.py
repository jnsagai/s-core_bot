"""Restore check: a restored corpus keeps its citations (F009 FR-007, SC-003, AT-16).

Compares an original and a restored data directory:
- the active snapshot ID;
- a deterministic sample of chunks (text, source, revision, path, lines);
- the keyword-search citations of fixed questions.

Keyword search keeps the comparison deterministic and independent of any model.

    python -m score_docs_assistant.qualification.restore \
        --original DATA --restored DATA --out REPORT
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from score_docs_assistant.config.schema import AppConfig
from score_docs_assistant.domain.errors import SearchError
from score_docs_assistant.domain.retrieval import SearchRequest
from score_docs_assistant.retrieval.service import SearchService

QUESTIONS = (
    "What is the recommended way to set up the development environment?",
    "How are inspections performed?",
    "feat_req__com__interfaces",
)
_FORBID = ConfigDict(extra="forbid", frozen=True)


class RestoreReport(BaseModel):
    model_config = _FORBID

    created_at: datetime
    status: str
    original_snapshot: str | None
    restored_snapshot: str | None
    chunks_compared: int
    chunk_mismatches: list[str]
    citations_compared: int
    citation_mismatches: list[str]


def _service(data_dir: Path) -> SearchService:
    return SearchService(config=AppConfig(data_dir=data_dir), provider=None)


def _sample(service: SearchService, count: int) -> list[str]:
    with service.pinned(None) as handle:
        rows = handle.corpus().execute("SELECT chunk_id FROM chunks ORDER BY rowid").fetchall()
    step = max(1, len(rows) // count)
    return [str(r[0]) for r in rows[::step][:count]]


def compare(original: Path, restored: Path, *, sample: int = 50) -> RestoreReport:
    a, b = _service(original), _service(restored)
    snap_a = a.snapshots().active
    snap_b = b.snapshots().active
    chunk_problems: list[str] = []
    citation_problems: list[str] = []
    if snap_a is None or snap_b is None:
        return RestoreReport(
            created_at=datetime.now(UTC),
            status="fail",
            original_snapshot=snap_a,
            restored_snapshot=snap_b,
            chunks_compared=0,
            chunk_mismatches=["no active snapshot on one side"],
            citations_compared=0,
            citation_mismatches=[],
        )
    ids = _sample(a, sample)
    for chunk_id in ids:
        try:
            x = a.citation(snap_a, chunk_id)
            y = b.citation(snap_b, chunk_id)
        except SearchError as exc:
            chunk_problems.append(f"{chunk_id[:12]}: {exc.code}")
            continue
        fields = ("text", "source_id", "revision", "path", "line_start", "line_end", "heading_path")
        diffs = [f for f in fields if getattr(x, f) != getattr(y, f)]
        if diffs:
            chunk_problems.append(f"{chunk_id[:12]}: {diffs}")
    compared = 0
    for question in QUESTIONS:
        ra = a.search(SearchRequest(query=question, snapshot_id=snap_a), force_lexical=True)
        rb = b.search(SearchRequest(query=question, snapshot_id=snap_b), force_lexical=True)
        sig_a = [(r.chunk_id, r.excerpt, r.revision) for r in ra.results]
        sig_b = [(r.chunk_id, r.excerpt, r.revision) for r in rb.results]
        compared += len(sig_a)
        if sig_a != sig_b:
            citation_problems.append(f"{question!r}: results differ")
    ok = snap_a == snap_b and not chunk_problems and not citation_problems and bool(ids)
    return RestoreReport(
        created_at=datetime.now(UTC),
        status="pass" if ok else "fail",
        original_snapshot=snap_a,
        restored_snapshot=snap_b,
        chunks_compared=len(ids),
        chunk_mismatches=chunk_problems,
        citations_compared=compared,
        citation_mismatches=citation_problems,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--restored", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    report = compare(args.original, args.restored)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report.model_dump_json(indent=2) + "\n")
    print(
        f"restore check: {report.status} — snapshot {report.original_snapshot} → "
        f"{report.restored_snapshot}; chunks {report.chunks_compared} "
        f"({len(report.chunk_mismatches)} mismatches); citations {report.citations_compared} "
        f"({len(report.citation_mismatches)} mismatches)"
    )
    return 0 if report.status == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
