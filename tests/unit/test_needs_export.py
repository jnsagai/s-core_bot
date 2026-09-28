"""Sphinx-Needs export import: strict validation, own namespace, always `unverified`
(FR-019, FR-020, SC-006). Shape mirrors the real exports inspected in research R1."""

from __future__ import annotations

import json
from typing import Any

import pytest

from score_docs_assistant.ingestion.needs_export import (
    MAX_FIELD_BYTES,
    consistency,
    import_export,
)

LINKS = {"derived_from", "satisfied_by", "complies"}


def _export(needs: dict[str, Any], **top: Any) -> bytes:
    doc: dict[str, Any] = {
        "current_version": "0.1",
        "project": "S-CORE",
        "versions": {
            "0.1": {"creator": {"program": "sphinx_needs", "version": "8.3.1"}, "needs": needs}
        },
    }
    doc.update(top)
    return json.dumps(doc).encode()


def _need(need_id: str, **extra: Any) -> dict[str, Any]:
    return {
        "id": need_id,
        "type": "feat_req",
        "title": f"Title {need_id}",
        "docname": "features/x/requirements/index",
        "lineno": 35,
        "content": "The executor shall …",
        "status": "valid",
        "tags": ["component_feo"],
        "derived_from": ["stkh_req__a[version==1]"],
        "fulfils_back": ["feat__x"],
        "score": 0.5,
        **extra,
    }


def _import(data: bytes) -> Any:
    return import_export(
        data, source_id="exp", revision="e" * 64, document_key="d" * 64, link_options=LINKS
    )


def test_valid_export_entities() -> None:
    result = _import(_export({"feat_req__x__1": _need("feat_req__x__1")}))
    (entity,) = result.entities
    assert entity.key == "exp:feat_req__x__1" and entity.origin == "needs-export"
    assert entity.revision_status == "unverified"
    assert entity.export_fields is not None
    assert entity.export_fields["tags"] == ["component_feo"]
    assert entity.export_fields["fulfils_back"] == ["feat__x"]
    assert entity.export_fields["score"] == "0.5"  # floats stringified for stable hashing
    assert [(r.via, r.target_id, r.qualifier) for r in entity.links] == [
        ("derived_from", "stkh_req__a", "version==1")
    ]
    assert result.diagnostics == []
    assert result.docnames == {"feat_req__x__1": "features/x/requirements/index"}


@pytest.mark.parametrize(
    "data",
    [
        b"not json",
        json.dumps({"versions": {}}).encode(),
        json.dumps({"current_version": "0.2", "versions": {"0.1": {"needs": {}}}}).encode(),
        _export({"a__1": {k: v for k, v in _need("a__1").items() if k != "docname"}}),
        _export({"a__1": {k: v for k, v in _need("a__1").items() if k != "id"}}),
        _export({"a__1": _need("a__2")}),  # key/id mismatch
        _export({"a__1": _need("a__1", content="x" * (MAX_FIELD_BYTES + 1))}),
    ],
)
def test_invalid_exports_rejected_whole(data: bytes) -> None:
    result = _import(data)
    assert result.entities == []
    assert [d.code for d in result.diagnostics] == ["EXPORT_INVALID"]
    assert result.diagnostics[0].severity == "error"


def test_too_many_needs(monkeypatch: pytest.MonkeyPatch) -> None:
    import score_docs_assistant.ingestion.needs_export as module

    monkeypatch.setattr(module, "MAX_NEEDS", 2)
    result = _import(_export({f"a__{i}": _need(f"a__{i}") for i in range(3)}))
    assert result.entities == [] and result.diagnostics[0].code == "EXPORT_INVALID"


def test_consistency_statistic() -> None:
    export_docnames = {
        "a__1": "features/x/index",  # same id, same path  → matched
        "a__2": "features/y/index",  # same id, other path → id_only_matched
        "a__3": "features/z/index",  # not in source       → missing_in_source
    }
    source_paths = {
        "a__1": ["docs/features/x/index.rst"],
        "a__2": ["docs/features/other.rst"],
        "a__4": ["docs/features/w.md"],  # not in export → missing_in_export
    }
    stat = consistency(export_docnames, source_paths, associated_source="git-src", docs_root="docs")
    assert (stat.matched, stat.id_only_matched, stat.missing_in_source, stat.missing_in_export) == (
        1,
        1,
        1,
        1,
    )
    assert "does not verify" in stat.note
