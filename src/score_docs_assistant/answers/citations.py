"""Citations assembled only from stored provenance (FR-004, FR-005, research R6).

An immutable upstream link is built only for a git source on github.com whose lock entry has
exactly the revision the evidence came from. Everything else gets no link. No model output is used.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import quote, urlsplit

from score_docs_assistant.answers.prompt import EvidenceItem
from score_docs_assistant.domain.answers import Citation, Claim
from score_docs_assistant.sources.lock import LOCK_ARCHIVE_DIR

_ALLOWED_HOSTS = {"github.com"}


class SourceLinks:
    """Repository base URLs per (source ID, revision), read from the source lock."""

    def __init__(self, repositories: dict[tuple[str, str], str]) -> None:
        self._repositories = repositories

    @classmethod
    def from_lock(cls, lock_path: Path) -> SourceLinks:
        return cls(_repositories(lock_path))

    @classmethod
    def for_data_dir(cls, data_dir: Path) -> SourceLinks:
        """The current lock plus archived locks (F007 research R7), exact revisions only."""
        repositories: dict[tuple[str, str], str] = {}
        archive = data_dir / LOCK_ARCHIVE_DIR
        paths = sorted(archive.glob("*.json")) if archive.is_dir() else []
        for path in [*paths, data_dir / "source-lock.json"]:
            repositories.update(_repositories(path))
        return cls(repositories)

    def url(self, item: EvidenceItem) -> str | None:
        result = item.result
        if result.revision_status != "pinned":
            return None
        base = self._repositories.get((result.source_id, result.revision))
        if base is None:
            return None
        link = f"{base}/blob/{result.revision}/{quote(result.path)}"
        if result.line_start is not None:
            end = result.line_end if result.line_end is not None else result.line_start
            link += f"#L{result.line_start}-L{end}"
        return link


def _repositories(lock_path: Path) -> dict[tuple[str, str], str]:
    repositories: dict[tuple[str, str], str] = {}
    try:
        data = json.loads(lock_path.read_text())
    except (OSError, ValueError):
        return {}
    for source in data.get("sources", []):
        repo, revision = source.get("repository"), source.get("revision")
        if source.get("kind") != "git" or not repo or not revision:
            continue
        parts = urlsplit(str(repo))
        if parts.scheme != "https" or parts.hostname not in _ALLOWED_HOSTS:
            continue
        path = parts.path.removesuffix(".git").strip("/")
        if path.count("/") != 1:
            continue
        repositories[(str(source["source_id"]), str(revision))] = f"https://github.com/{path}"
    return repositories


def build_citations(
    claims: Sequence[Claim], evidence: dict[str, EvidenceItem], links: SourceLinks
) -> list[Citation]:
    """One citation per cited evidence ID, in first-use order."""
    order: list[str] = []
    for claim in claims:
        for evidence_id in claim.evidence_ids:
            if evidence_id not in order:
                order.append(evidence_id)
    return [citation_for(evidence_id, evidence[evidence_id], links) for evidence_id in order]


def citation_for(evidence_id: str, item: EvidenceItem, links: SourceLinks) -> Citation:
    """A citation built only from the stored provenance of one evidence item."""
    result = item.result
    url = links.url(item)
    if url is not None:
        match = "exact"
    elif result.revision_status != "pinned":
        match = "unverified"
    else:
        match = "none"
    return Citation(
        evidence_id=evidence_id,
        chunk_id=result.chunk_id,
        snapshot_id=result.snapshot_id,
        source_id=result.source_id,
        revision=result.revision,
        revision_status=result.revision_status,
        path=result.path,
        heading_path=list(result.heading_path),
        line_start=result.line_start,
        line_end=result.line_end,
        excerpt=result.excerpt,
        immutable_url=url,
        revision_match=match,  # type: ignore[arg-type]
    )
