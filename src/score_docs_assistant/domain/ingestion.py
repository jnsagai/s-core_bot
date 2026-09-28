"""Records produced by F002 (lock, normalized documents, entities, coverage) and consumed by F003.

specs/002-source-ingestion/data-model.md. All records are frozen; none contains floats, so their
canonical JSON form (ingestion/canonical.py) is stable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict

Severity = Literal["info", "warning", "error"]
SourceKind = Literal["git", "needs-export"]
RevisionStatus = Literal["pinned", "unverified"]
LinkResolution = Literal["resolved", "ambiguous", "unresolved", "malformed"]
DocumentStatus = Literal["included", "partial", "failed"]
BlockKind = Literal[
    "section",
    "paragraph",
    "list",
    "list_item",
    "table",
    "code",
    "literal",
    "diagram",
    "admonition",
    "field_list",
    "definition_list",
    "block_quote",
    "toctree",
    "need",
    "dynamic_view",
    "raw_excluded",
    "generic_directive",
    "image",
]
AttrValue = str | list[str] | list[list[str]] | dict[str, str]

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class Diagnostic(BaseModel):
    model_config = _FROZEN

    code: str
    severity: Severity
    source_id: str
    path: str
    line: int | None = None
    message: str


class LicenseRecord(BaseModel):
    model_config = _FROZEN

    spdx: str | None
    basis: Literal["declared", "inherited", "unknown"]
    redistribution: Literal["allowed", "requires_review"]


class LinkRef(BaseModel):
    model_config = _FROZEN

    via: str
    target_id: str
    qualifier: str | None = None
    raw: str
    resolution: LinkResolution = "unresolved"
    resolved_keys: list[str] = []


class Block(BaseModel):
    model_config = _FROZEN

    kind: BlockKind
    text: str
    heading_path: list[str]
    line_start: int | None
    line_end: int | None
    origin_path: str
    raw_sha256: str
    attrs: dict[str, AttrValue] = {}
    references: list[LinkRef] = []
    children: list[Block] = []
    entity_key: str | None = None


class Entity(BaseModel):
    model_config = _FROZEN

    key: str
    need_id: str
    type: str
    title: str
    options: dict[str, str]
    links: list[LinkRef]
    source_id: str
    document_key: str
    path: str
    line_start: int | None
    line_end: int | None
    origin: Literal["rst", "markdown", "needs-export"]
    revision_status: RevisionStatus
    # Raw export fields (exports only). Values are JSON-compatible without floats: the export
    # mapper stringifies any float so canonical hashing stays stable.
    export_fields: dict[str, Any] | None = None


class NormalizedDocument(BaseModel):
    model_config = _FROZEN

    document_key: str
    source_id: str
    revision: str
    path: str
    format: Literal["rst", "markdown", "needs-export"]
    title: str | None
    license: LicenseRecord
    raw_sha256: str
    normalized_sha256: str
    processing_hash: str
    blocks: list[Block]
    diagnostics: list[Diagnostic]
    status: DocumentStatus


# --- Source lock (contracts/lock.md) -------------------------------------------------------


class LockedFile(BaseModel):
    model_config = _FROZEN

    path: str
    sha256: str
    size: int


class SkippedEntry(BaseModel):
    model_config = _FROZEN

    path: str
    reason: Literal["symlink", "submodule", "oversize", "unsafe_path"]


class LockedSource(BaseModel):
    model_config = _FROZEN

    source_id: str
    kind: SourceKind
    status: Literal["ok", "failed"]
    failure: str | None = None
    required: bool = True
    repository: str | None = None
    url: str | None = None
    ref: str | None = None
    authority: str
    repository_license: str | None = None
    parser_profile: str | None = None
    associated_source: str | None = None
    docs_root: str | None = None
    revision: str | None = None
    revision_status: RevisionStatus
    release_mapping: None = None
    fetched_at: datetime
    selector_sha256: str | None = None
    excluded_by_selector: int | None = None
    files: list[LockedFile] = []
    notice_files: list[LockedFile] = []
    skipped: list[SkippedEntry] = []


class SourceLock(BaseModel):
    model_config = _FROZEN

    schema_version: Literal[1]
    generated_at: datetime
    registry_sha256: str
    redistribution_allowed_licenses: list[str]
    sources: list[LockedSource]


# --- Coverage report (contracts/normalized-output.md) --------------------------------------


class FailedFile(BaseModel):
    model_config = _FROZEN

    path: str
    reason: str


class PartialFile(BaseModel):
    model_config = _FROZEN

    path: str
    codes: list[str]


class AmbiguousItem(BaseModel):
    model_config = _FROZEN

    from_key: str
    via: str
    target_id: str
    candidates: list[str]


class UnresolvedItem(BaseModel):
    model_config = _FROZEN

    from_key: str
    via: str
    target_id: str


class LinkSummary(BaseModel):
    model_config = _FROZEN

    resolved: int = 0
    ambiguous: int = 0
    unresolved: int = 0
    malformed: int = 0
    ambiguous_items: list[AmbiguousItem] = []
    unresolved_items: list[UnresolvedItem] = []


class ExportConsistency(BaseModel):
    model_config = _FROZEN

    associated_source: str
    docs_root: str
    matched: int
    id_only_matched: int
    missing_in_source: int
    missing_in_export: int
    note: str = "statistic only; does not verify revision"


class SourceCoverage(BaseModel):
    model_config = _FROZEN

    source_id: str
    kind: SourceKind
    revision: str | None
    status: Literal["ok", "failed"]
    failure: str | None = None
    selected: int = 0
    included: int = 0
    partial: int = 0
    partial_files: list[PartialFile] = []
    failed: list[FailedFile] = []
    skipped: list[SkippedEntry] = []
    excluded_by_selector: int | None = None
    entities: int = 0
    links: LinkSummary = LinkSummary()
    diagnostics_by_code: dict[str, int] = {}
    licenses: dict[str, int] = {}
    requires_review: list[str] = []
    export_consistency: ExportConsistency | None = None


class CoverageReport(BaseModel):
    model_config = _FROZEN

    schema_version: Literal[1] = 1
    lock_sha256: str
    processing_hash: str
    sources: list[SourceCoverage]
    totals: dict[str, int]


# --- Protocols (master spec §5.1) ---------------------------------------------------------


@dataclass(frozen=True)
class ParseResult:
    """What a `DocumentParser` returns for one file; entities reference the document key."""

    title: str | None
    blocks: list[Block]
    entities: list[Entity]
    diagnostics: list[Diagnostic]
    extra: dict[str, Any] = field(default_factory=dict)


class DocumentParser(Protocol):
    def parse(
        self, *, source_id: str, revision: str, path: str, text: str, document_key: str
    ) -> ParseResult: ...


class SourceAdapter(Protocol):
    """Acquires one registry source into a staging directory and describes it for the lock."""

    @property
    def kind(self) -> SourceKind: ...

    def acquire(self, staging_root: Path) -> LockedSource: ...
