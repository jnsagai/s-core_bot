"""Lock → verified, normalized documents and entities with resolved relationships
(FR-016–FR-021, FR-023; plan Key Design 4, 8, 9).

Order of operations per source: verify every acquired file against the lock (tampering fails the
source before anything is parsed) → decode strictly → license record → parse → classify. Links are
resolved only after every source is parsed, so resolution sees the complete entity index.
Everything is processed in a fixed order so two runs over the same lock are byte-identical.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from score_docs_assistant.domain.errors import ConfigError
from score_docs_assistant.domain.ingestion import (
    Block,
    CoverageReport,
    Diagnostic,
    DocumentStatus,
    Entity,
    LicenseRecord,
    LockedSource,
    NormalizedDocument,
    ParseResult,
    SourceLock,
)
from score_docs_assistant.ingestion.canonical import (
    canonical_hash,
    document_key,
    processing_hash,
    sha256_hex,
)
from score_docs_assistant.ingestion.decode import decode_document
from score_docs_assistant.ingestion.licenses import detect_license
from score_docs_assistant.ingestion.links import EntityIndex, resolve
from score_docs_assistant.ingestion.markdown import MarkdownParser
from score_docs_assistant.ingestion.needs_export import consistency, import_export
from score_docs_assistant.ingestion.report import SourceData, build_report
from score_docs_assistant.ingestion.rst.parser import IncludeContext, RstParser
from score_docs_assistant.sources.lock import source_root, verify_files
from score_docs_assistant.sources.paths import ensure_within, safe_relative_path
from score_docs_assistant.sources.profile import ParserProfile, load_profile, profile_hash

_SEVERITY_STATUS: dict[str, DocumentStatus] = {"error": "failed", "warning": "partial"}


@dataclass(frozen=True)
class NormalizationOutcome:
    documents: list[NormalizedDocument]
    entities: list[Entity]
    report: CoverageReport
    exit_code: int


def _status(diagnostics: list[Diagnostic]) -> DocumentStatus:
    severities = {d.severity for d in diagnostics}
    for severity in ("error", "warning"):
        if severity in severities:
            return _SEVERITY_STATUS[severity]
    return "included"


def _diag(source_id: str, path: str, code: str, severity: str, message: str) -> Diagnostic:
    return Diagnostic(
        code=code,
        severity=severity,  # type: ignore[arg-type]
        source_id=source_id,
        path=path,
        line=None,
        message=message,
    )


class NormalizationService:
    def __init__(
        self, lock: SourceLock, lock_sha256: str, data_dir: Path, profiles_dir: Path
    ) -> None:
        self._lock = lock
        self._lock_sha = lock_sha256
        self._data = data_dir
        self._profiles_dir = profiles_dir
        self._profiles: dict[str, ParserProfile] = {}
        self._allowed = set(lock.redistribution_allowed_licenses)

    def _profile(self, name: str | None) -> ParserProfile:
        if name is None:
            raise ConfigError([("parser_profile", "git source without a parser profile")])
        if name not in self._profiles:
            path = self._profiles_dir / f"{name}.yaml"
            if not path.is_file():
                raise ConfigError([(str(path), f"parser profile {name!r} not found")])
            self._profiles[name] = load_profile(path)
        return self._profiles[name]

    def run(self) -> NormalizationOutcome:
        sources = sorted(self._lock.sources, key=lambda s: s.source_id)
        by_id = {s.source_id: s for s in sources}
        data: dict[str, SourceData] = {}
        for locked in sources:
            data[locked.source_id] = self._source(locked, by_id)

        index = EntityIndex.build(
            {sid: [e.need_id for e in d.entities] for sid, d in data.items()},
            export_sources={s.source_id for s in sources if s.kind == "needs-export"},
        )
        for sid, source_data in data.items():
            source_data.entities = [
                e.model_copy(update={"links": [resolve(r, sid, index) for r in e.links]})
                for e in source_data.entities
            ]
            source_data.documents = [
                d.model_copy(
                    update={"blocks": [self._resolve_block(b, sid, index) for b in d.blocks]}
                )
                for d in source_data.documents
            ]
            self._add_consistency(by_id[sid], source_data, data)

        report = build_report(self._lock_sha, [data[s.source_id] for s in sources])
        failed_required = any(
            d.locked.required and d.coverage_failure is not None for d in data.values()
        )
        documents = [doc for s in sources for doc in data[s.source_id].documents]
        entities = sorted(
            (e for s in sources for e in data[s.source_id].entities), key=lambda e: e.key
        )
        return NormalizationOutcome(documents, entities, report, 1 if failed_required else 0)

    def _resolve_block(self, block: Block, source_id: str, index: EntityIndex) -> Block:
        return block.model_copy(
            update={
                "references": [resolve(r, source_id, index) for r in block.references],
                "children": [self._resolve_block(c, source_id, index) for c in block.children],
            }
        )

    def _source(self, locked: LockedSource, by_id: dict[str, LockedSource]) -> SourceData:
        source_data = SourceData(locked=locked)
        if locked.status == "failed" or locked.revision is None:
            source_data.coverage_failure = locked.failure or "failed during sync"
            return source_data
        root = source_root(self._data, locked.source_id, locked.revision)
        problems = verify_files(root, locked) if root.is_dir() else ["<revision directory>"]
        if problems:
            source_data.coverage_failure = (
                f"HASH_MISMATCH: {len(problems)} acquired file(s) missing or changed, e.g. "
                f"{problems[0]}"
            )
            return source_data
        if locked.kind == "needs-export":
            self._export(locked, root, by_id, source_data)
        else:
            self._git(locked, root, source_data)
        return source_data

    def _git(self, locked: LockedSource, root: Path, out: SourceData) -> None:
        profile = self._profile(locked.parser_profile)
        processing = processing_hash(profile_hash(profile))
        out.processing_hash = processing
        rst = RstParser(profile)
        markdown = MarkdownParser(profile)
        include = IncludeContext(root=root, selected={f.path for f in locked.files})
        id_counter: Counter[str] = Counter()
        for locked_file in sorted(locked.files, key=lambda f: f.path.encode("utf-8")):
            path = locked_file.path
            raw = ensure_within(root, safe_relative_path(path)).read_bytes()
            key = document_key(locked.source_id, path, locked_file.sha256, processing)
            decoded = decode_document(raw)
            diagnostics = [
                _diag(
                    locked.source_id,
                    path,
                    code,
                    "error" if code == "ENCODING_ERROR" else "info",
                    "file is not valid UTF-8" if code == "ENCODING_ERROR" else "document is empty",
                )
                for code in decoded.codes
            ]
            license_record = LicenseRecord(
                spdx=None, basis="unknown", redistribution="requires_review"
            )
            result = ParseResult(title=None, blocks=[], entities=[], diagnostics=[])
            suffix = PurePosixPath(path).suffix.lower()
            if decoded.text is not None:
                license_record, license_codes = detect_license(
                    decoded.text, locked.repository_license, self._allowed
                )
                diagnostics += [
                    _diag(
                        locked.source_id,
                        path,
                        c,
                        "warning",
                        "no SPDX header and no repository license",
                    )
                    for c in license_codes
                ]
                if suffix == ".rst":
                    result = rst.parse(
                        source_id=locked.source_id,
                        revision=locked.revision or "",
                        path=path,
                        text=decoded.text,
                        document_key=key,
                        include_context=include,
                        id_counter=id_counter,
                    )
                elif suffix == ".md":
                    result = markdown.parse(
                        source_id=locked.source_id,
                        revision=locked.revision or "",
                        path=path,
                        text=decoded.text,
                        document_key=key,
                        id_counter=id_counter,
                    )
                else:
                    diagnostics.append(
                        _diag(
                            locked.source_id,
                            path,
                            "UNSUPPORTED_FILE_TYPE",
                            "error",
                            f"no parser for {suffix or 'files without extension'}",
                        )
                    )
            diagnostics += result.diagnostics
            out.documents.append(
                NormalizedDocument(
                    document_key=key,
                    source_id=locked.source_id,
                    revision=locked.revision or "",
                    path=path,
                    format="markdown" if suffix == ".md" else "rst",
                    title=result.title,
                    license=license_record,
                    raw_sha256=locked_file.sha256,
                    normalized_sha256=canonical_hash(
                        [b.model_dump(mode="json") for b in result.blocks]
                    ),
                    processing_hash=processing,
                    blocks=result.blocks,
                    diagnostics=diagnostics,
                    status=_status(diagnostics),
                )
            )
            out.entities.extend(result.entities)

    def _export(
        self, locked: LockedSource, root: Path, by_id: dict[str, LockedSource], out: SourceData
    ) -> None:
        link_options: set[str] = set()
        associated = by_id.get(locked.associated_source or "")
        if associated is not None and associated.parser_profile is not None:
            link_options = set(self._profile(associated.parser_profile).link_options)
        processing = canonical_hash({"export_importer": 1, "link_options": sorted(link_options)})
        out.processing_hash = processing
        raw = (root / "needs.json").read_bytes()
        key = document_key(locked.source_id, "needs.json", sha256_hex(raw), processing)
        result = import_export(
            raw,
            source_id=locked.source_id,
            revision=locked.revision or "",
            document_key=key,
            link_options=link_options,
        )
        out.export_docnames = result.docnames
        record, _ = detect_license("", locked.repository_license, self._allowed)
        out.documents.append(
            NormalizedDocument(
                document_key=key,
                source_id=locked.source_id,
                revision=locked.revision or "",
                path="needs.json",
                format="needs-export",
                title=None,
                license=record,
                raw_sha256=sha256_hex(raw),
                normalized_sha256=canonical_hash(
                    [e.model_dump(mode="json") for e in result.entities]
                ),
                processing_hash=processing,
                blocks=[],
                diagnostics=result.diagnostics,
                status=_status(result.diagnostics),
            )
        )
        out.entities.extend(result.entities)

    @staticmethod
    def _add_consistency(
        locked: LockedSource, out: SourceData, data: dict[str, SourceData]
    ) -> None:
        if locked.kind != "needs-export" or locked.associated_source is None:
            return
        associated = data.get(locked.associated_source)
        if associated is None or not out.export_docnames or locked.docs_root is None:
            return
        paths: dict[str, list[str]] = {}
        for entity in associated.entities:
            paths.setdefault(entity.need_id, []).append(entity.path)
        out.consistency = consistency(
            out.export_docnames,
            paths,
            associated_source=locked.associated_source,
            docs_root=locked.docs_root,
        )
