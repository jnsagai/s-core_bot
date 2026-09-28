"""Import a published Sphinx-Needs `needs.json` as a separately identified, unverified artifact
(FR-019, FR-020; research R1, R7).

The export carries no commit identity (verified for both S-CORE exports), so its entities are
always `unverified` and live in their own namespace. Validation is strict and all-or-nothing:
one malformed need rejects the whole export rather than silently importing a partial one.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from score_docs_assistant.domain.ingestion import Diagnostic, Entity, ExportConsistency, LinkRef
from score_docs_assistant.ingestion.links import parse_link_value

MAX_NEEDS = 200_000
MAX_FIELD_BYTES = 1024 * 1024
_REQUIRED = ("id", "type", "title", "docname")


class _Invalid(ValueError):
    pass


@dataclass(frozen=True)
class ExportResult:
    entities: list[Entity]
    diagnostics: list[Diagnostic]
    docnames: dict[str, str] = field(default_factory=dict)


def _json_safe(value: Any) -> Any:
    """Stringify floats (canonical hashing forbids them); enforce the per-string size limit."""
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        if len(value.encode("utf-8")) > MAX_FIELD_BYTES:
            raise _Invalid(f"a string field exceeds {MAX_FIELD_BYTES} bytes")
        return value
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    return value


def _needs(data: bytes) -> dict[str, Any]:
    try:
        document = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _Invalid(f"not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise _Invalid("top level is not an object")
    current = document.get("current_version")
    versions = document.get("versions")
    if not isinstance(current, str) or not isinstance(versions, dict) or current not in versions:
        raise _Invalid("current_version missing or not present in versions")
    block = versions[current]
    needs = block.get("needs") if isinstance(block, dict) else None
    if not isinstance(needs, dict):
        raise _Invalid(f"versions[{current!r}].needs is not an object")
    if len(needs) > MAX_NEEDS:
        raise _Invalid(f"more than {MAX_NEEDS} needs")
    return needs


def _links(need: Mapping[str, Any], link_options: set[str]) -> list[LinkRef]:
    refs: list[LinkRef] = []
    for name, value in need.items():
        if name not in link_options:
            continue
        items = value if isinstance(value, list) else [value]
        for item in items:
            if isinstance(item, str):
                refs.extend(parse_link_value(name, item))
    return refs


def import_export(
    data: bytes, *, source_id: str, revision: str, document_key: str, link_options: set[str]
) -> ExportResult:
    try:
        needs = _needs(data)
        entities: list[Entity] = []
        docnames: dict[str, str] = {}
        for key in sorted(needs):
            raw = needs[key]
            if not isinstance(raw, dict):
                raise _Invalid(f"need {key!r} is not an object")
            missing = [f for f in _REQUIRED if not isinstance(raw.get(f), str) or not raw.get(f)]
            if missing:
                raise _Invalid(f"need {key!r} lacks required field(s): {', '.join(missing)}")
            if raw["id"] != key:
                raise _Invalid(f"need key {key!r} does not match its id {raw['id']!r}")
            fields = _json_safe(raw)
            options = {
                k: str(v)
                for k, v in fields.items()
                if isinstance(v, str | int | bool) and k not in ("id", "type", "title", "content")
            }
            docnames[key] = fields["docname"]
            entities.append(
                Entity(
                    key=f"{source_id}:{key}",
                    need_id=key,
                    type=fields["type"],
                    title=fields["title"],
                    options=options,
                    links=_links(fields, link_options),
                    source_id=source_id,
                    document_key=document_key,
                    path="needs.json",
                    line_start=None,
                    line_end=None,
                    origin="needs-export",
                    revision_status="unverified",
                    export_fields=fields,
                )
            )
    except _Invalid as exc:
        diagnostic = Diagnostic(
            code="EXPORT_INVALID",
            severity="error",
            source_id=source_id,
            path="needs.json",
            line=None,
            message=f"export rejected: {exc}",
        )
        return ExportResult(entities=[], diagnostics=[diagnostic])
    return ExportResult(entities=entities, diagnostics=[], docnames=docnames)


def consistency(
    export_docnames: Mapping[str, str],
    source_paths: Mapping[str, list[str]],
    *,
    associated_source: str,
    docs_root: str,
) -> ExportConsistency:
    """How well the export matches the parsed associated source. A statistic only: it never
    changes the export's revision status (FR-020)."""
    matched = id_only = missing_in_source = 0
    for need_id, docname in export_docnames.items():
        paths = source_paths.get(need_id)
        if not paths:
            missing_in_source += 1
            continue
        expected = {f"{docs_root}/{docname}.rst", f"{docs_root}/{docname}.md"}
        if expected & set(paths):
            matched += 1
        else:
            id_only += 1
    missing_in_export = sum(1 for need_id in source_paths if need_id not in export_docnames)
    return ExportConsistency(
        associated_source=associated_source,
        docs_root=docs_root,
        matched=matched,
        id_only_matched=id_only,
        missing_in_source=missing_in_source,
        missing_in_export=missing_in_export,
    )
