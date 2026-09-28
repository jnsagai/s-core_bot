"""Golden test over verbatim upstream S-CORE files (SC-001, SC-007; FR-011, FR-014, FR-018).

tests/fixtures/upstream/NOTICE records provenance (score@e2373d8, process_description@66321fe).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from score_docs_assistant.domain.ingestion import Block, Entity
from tests.helpers.git_repos import make_plain_repo, make_repo_from_tree
from tests.helpers.parsing import walk
from tests.helpers.pipeline import normalize, sync
from tests.helpers.registries import git_source

UPSTREAM = Path(__file__).parent.parent / "fixtures" / "upstream"


@pytest.fixture(scope="module")
def outcome(tmp_path_factory: pytest.TempPathFactory):  # type: ignore[no-untyped-def]
    tmp = tmp_path_factory.mktemp("golden")
    score = make_repo_from_tree(tmp / "score", UPSTREAM / "score")
    process = make_repo_from_tree(tmp / "process", UPSTREAM / "process_description")
    # SYNTHETIC: a third source redefining a score ID and a fourth referencing it.
    dup = make_plain_repo(
        tmp / "dup",
        {"docs/d.rst": ".. document:: Dup\n   :id: doc__platform_mgt_plan\n", "LICENSE": "x\n"},
    )
    ref = make_plain_repo(
        tmp / "ref", {"docs/r.rst": "See :need:`doc__platform_mgt_plan`.\n", "LICENSE": "x\n"}
    )
    data = tmp / "data"
    sources = [
        git_source("score-platform", score.url, include=["docs/**/*.rst", "docs/**/*.md"]),
        git_source("score-process", process.url, include=["process/**/*.rst"]),
        git_source("syn-dup", dup.url, include=["docs/**/*.rst"]),
        git_source("syn-ref", ref.url, include=["docs/**/*.rst"]),
    ]
    assert sync(data, sources) == 0
    return normalize(data)


def _entities(outcome) -> dict[str, Entity]:  # type: ignore[no-untyped-def]
    return {e.key: e for e in outcome.entities}


def _blocks(outcome, path: str) -> list[Block]:  # type: ignore[no-untyped-def]
    (doc,) = [d for d in outcome.documents if d.path == path]
    return list(walk(doc.blocks))


def test_feat_req_exact_fields(outcome) -> None:  # type: ignore[no-untyped-def]
    entity = _entities(outcome)["score-platform:feat_req__gen_ai__workloads_execution"]
    assert (entity.type, entity.title) == ("feat_req", "GenAI Execution")
    assert entity.options["safety"] == "QM" and entity.options["valid_from"] == "v2.0.0"
    assert [(r.via, r.target_id, r.qualifier) for r in entity.links] == [
        ("derived_from", "stkh_req__gen_ai__enablement", "version==1"),
        ("satisfied_by", "feat__gen_ai", "version==1"),
    ]
    assert (entity.line_start, entity.revision_status) == (20, "pinned")
    gen_ai = [k for k in _entities(outcome) if k.startswith("score-platform:feat_req__gen_ai__")]
    assert len(gen_ai) == 4


def test_std_req_ids_case_and_nested_note(outcome) -> None:  # type: ignore[no-untyped-def]
    entities = _entities(outcome)
    for n in range(1, 8):
        assert f"score-process:std_req__aspice_40__MAN-5-BP{n}" in entities
    bp1 = entities["score-process:std_req__aspice_40__MAN-5-BP1"]
    assert [r.target_id for r in bp1.links] == [
        "std_req__aspice_40__iic-15-09",
        "std_req__aspice_40__iic-15-51",
    ]
    blocks = _blocks(outcome, "process/standards/aspice_40/man/man.5.rst")
    need = next(b for b in blocks if b.entity_key == bp1.key)
    assert any(b.kind == "admonition" for b in walk(need.children))


def test_multiline_link_value_and_quoted_pseudo_directive(outcome) -> None:  # type: ignore[no-untyped-def]
    entities = _entities(outcome)
    template = entities["score-process:gd_temp__platform_mgmt_plan"]
    complies = [r.target_id for r in template.links if r.via == "complies"]
    assert len(complies) == 9
    assert complies.count("std_req__aspice_40__iic-08-56") == 2
    assert "score-process:doc__platform_mgt_plan" not in entities
    assert "score-platform:doc__platform_mgt_plan" in entities


def test_code_block_templates_never_entities(outcome) -> None:  # type: ignore[no-untyped-def]
    assert not any("<" in e.need_id for e in outcome.entities)
    blocks = _blocks(
        outcome, "docs/modules/feo/feo/docs/detailed_design/component_detailed_design.rst"
    )
    codes = [b for b in blocks if b.kind == "code"]
    assert any("dd_sta__<Feature>__<Title>" in b.text for b in codes)
    assert "score-platform:doc__component_feo_detailed_design" in _entities(outcome)


def test_dynamic_raw_toctree_table(outcome) -> None:  # type: ignore[no-untyped-def]
    tools = _blocks(outcome, "docs/score_tools/tools_compiler/index.rst")
    assert any(b.kind == "dynamic_view" and b.attrs["directive"] == "needtable" for b in tools)
    release = _blocks(outcome, "process/process_areas/release_management/guidance/index.rst")
    extend = [b for b in release if b.kind == "dynamic_view"]
    assert extend and extend[0].attrs["directive"] == "needextend"
    intro = _blocks(outcome, "docs/introduction/index.rst")
    assert any(b.kind == "raw_excluded" for b in intro)
    ci = _blocks(outcome, "docs/contribute/ci/index.rst")
    assert next(b for b in ci if b.kind == "toctree").attrs["entries"] == ["publishing-gh-pages"]
    checklist = _blocks(
        outcome,
        "process/process_areas/documentation_management/guidance/documentation_checklist.rst",
    )
    table = next(b for b in checklist if b.kind == "table")
    assert table.attrs["rows"][0] == ["Id", "Topic", "Status [FAIL|PASS]"]  # type: ignore[index]
    feo = _blocks(outcome, "docs/features/frameworks/feo/safety_planning/index.rst")
    assert not any("copy(" in b.text for b in feo)


def test_markdown_decision_record(outcome) -> None:  # type: ignore[no-untyped-def]
    (doc,) = [d for d in outcome.documents if d.path.endswith("DR-006-infra.md")]
    assert doc.format == "markdown" and doc.license.spdx == "Apache-2.0"
    assert doc.license.basis == "declared"
    # MyST backtick directive in Markdown (found by comparing against the published export).
    entity = _entities(outcome)["score-platform:dec_rec__infra__clippy_rules_lint"]
    assert (entity.type, entity.origin) == ("dec_rec", "markdown")
    assert entity.options["status"] == "accepted"


def test_cross_source_ambiguity(outcome) -> None:  # type: ignore[no-untyped-def]
    (doc,) = [d for d in outcome.documents if d.source_id == "syn-ref"]
    (ref,) = [r for b in walk(doc.blocks) for r in b.references]
    assert ref.resolution == "ambiguous"
    assert ref.resolved_keys == [
        "score-platform:doc__platform_mgt_plan",
        "syn-dup:doc__platform_mgt_plan",
    ]
