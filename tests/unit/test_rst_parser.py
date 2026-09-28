"""RST structure and need entities (FR-010, FR-011, FR-012). Synthetic fixtures —
SYNTHETIC, not S-CORE guidance."""

from __future__ import annotations

from tests.helpers.parsing import codes, kinds, parse_rst, walk

NEED = """
Requirements
============

.. feat_req:: Async Runtime
   :id: feat_req__orch__Async-RT
   :status: valid
   :derived_from: stkh_req__exec__proc[version==1]
   :satisfied_by: feat__orch[version==1], feat__other
   :safety: QM

   The executor shall provide a runtime.

   .. note::

      Nested note inside the need.
"""


def test_need_entity_exact_fields() -> None:
    result = parse_rst(NEED)
    (entity,) = result.entities
    assert entity.need_id == "feat_req__orch__Async-RT"
    assert entity.key == "src:feat_req__orch__Async-RT"
    assert (entity.type, entity.title) == ("feat_req", "Async Runtime")
    assert entity.options["safety"] == "QM" and entity.options["status"] == "valid"
    links = [(ref.via, ref.target_id, ref.qualifier) for ref in entity.links]
    assert links == [
        ("derived_from", "stkh_req__exec__proc", "version==1"),
        ("satisfied_by", "feat__orch", "version==1"),
        ("satisfied_by", "feat__other", None),
    ]
    assert (entity.origin, entity.revision_status) == ("rst", "pinned")
    need_block = next(b for b in walk(result.blocks) if b.kind == "need")
    assert need_block.entity_key == entity.key
    assert need_block.heading_path == ["Requirements"]
    child_kinds = [b.kind for b in walk(need_block.children)]
    assert "admonition" in child_kinds
    assert "Nested note inside the need." in [b.text for b in walk(need_block.children)]


def test_sections_lists_tables_code_admonitions_toctree() -> None:
    result = parse_rst(
        """
        Top
        ===

        Intro paragraph.

        * one
        * two

        1. first
        2. second

        term
           definition text

        :owner: team

        .. list-table:: Caption
           :header-rows: 1

           * - H1
             - H2
           * - a
             - b

        +-----+-----+
        | G1  | G2  |
        +=====+=====+
        | x   | y   |
        +-----+-----+

        .. code-block:: python

           print("hi")

        .. warning:: Careful.

        .. toctree::
           :maxdepth: 1

           guide/setup
           other

        Sub
        ---

        Deep text.
        """
    )
    all_kinds = kinds(result)
    for expected in (
        "section",
        "paragraph",
        "list",
        "list_item",
        "definition_list",
        "field_list",
        "table",
        "code",
        "admonition",
        "toctree",
    ):
        assert expected in all_kinds, expected
    tables = [b for b in walk(result.blocks) if b.kind == "table"]
    assert tables[0].attrs["rows"] == [["H1", "H2"], ["a", "b"]]
    assert tables[0].attrs["header_rows"] == "1"
    assert tables[1].attrs["rows"] == [["G1", "G2"], ["x", "y"]]
    code = next(b for b in walk(result.blocks) if b.kind == "code")
    assert code.attrs["language"] == "python" and code.text == 'print("hi")'
    toc = next(b for b in walk(result.blocks) if b.kind == "toctree")
    assert toc.attrs["entries"] == ["guide/setup", "other"]
    deep = next(b for b in walk(result.blocks) if b.text == "Deep text.")
    assert deep.heading_path == ["Top", "Sub"]
    assert result.title == "Top"
    lists = [b for b in walk(result.blocks) if b.kind == "list"]
    assert [b.attrs["ordered"] for b in lists] == ["false", "true"]


def test_need_without_id_creates_no_entity() -> None:
    result = parse_rst(".. std_req:: No id\n   :status: valid\n\n   Body.\n")
    assert result.entities == []
    assert "NEED_WITHOUT_ID" in codes(result)


def test_duplicate_id_in_source_keeps_both() -> None:
    result = parse_rst(
        ".. std_req:: A\n   :id: std_req__dup\n\n.. std_req:: B\n   :id: std_req__dup\n"
    )
    assert [e.key for e in result.entities] == ["src:std_req__dup", "src:std_req__dup#2"]
    assert "DUPLICATE_ID_IN_SOURCE" in codes(result)


def test_unknown_directive_kept_generic_and_unconfigured_need_flagged() -> None:
    result = parse_rst(
        """
        .. grid-item-card:: Card title
           :link: somewhere

           Card body text.

        .. weird_req:: Looks like a need
           :id: weird_req__x

           Weird body.
        """
    )
    generic = [b for b in walk(result.blocks) if b.kind == "generic_directive"]
    assert [b.attrs["directive"] for b in generic] == ["grid-item-card", "weird_req"]
    texts = [b.text for b in walk(result.blocks)]
    assert "Card body text." in texts and "Weird body." in texts
    assert result.entities == []
    assert codes(result).count("UNKNOWN_DIRECTIVE") == 2
    assert "POSSIBLE_UNCONFIGURED_NEED" in codes(result)


def test_unknown_role_text_kept() -> None:
    result = parse_rst("Press :kbd:`Ctrl+C` or :octicon:`book` now.\n")
    (para,) = [b for b in walk(result.blocks) if b.kind == "paragraph"]
    assert "Ctrl+C" in para.text
    assert "UNKNOWN_ROLE" in codes(result)


def test_need_role_reference_recorded() -> None:
    result = parse_rst("See :need:`feat_req__a__b` and :need:`Title <std_req__c>`.\n")
    (para,) = [b for b in walk(result.blocks) if b.kind == "paragraph"]
    assert [(r.via, r.target_id) for r in para.references] == [
        ("role:need", "feat_req__a__b"),
        ("role:need", "std_req__c"),
    ]


def test_role_directive_name_is_a_need_type() -> None:
    # `role` is both a docutils directive and an S-CORE need type; the need type wins.
    result = parse_rst(".. role:: Safety Manager\n   :id: rl__safety_manager\n")
    assert [e.type for e in result.entities] == ["role"]


def test_tab_indented_content() -> None:
    text = "Title\n=====\n\n* item\n\n\t- tab indented sub item\n"
    result = parse_rst(text, dedent=False)
    assert "tab indented sub item" in " ".join(b.text for b in walk(result.blocks))


def test_empty_document_has_no_blocks() -> None:
    result = parse_rst("..\n   just a comment\n")
    assert result.blocks == [] and result.entities == []


def test_card_heading_inside_unknown_directive_is_kept() -> None:
    # Mirrors docs/users_guide/index.rst upstream: a `=` title, then grid > card whose own
    # `^^^` heading docutils would reject as a title-level skip without a fresh title memo.
    result = parse_rst(
        """
        User's Guide
        ============

        .. grid:: 2

           .. grid-item-card::
              :link: project_basics/index

              Project Basics
              ^^^^^^^^^^^^^^
              Learn about the S-CORE module structure.
        """
    )
    texts = [b.text for b in walk(result.blocks)]
    assert "Project Basics" in texts
    assert "Learn about the S-CORE module structure." in texts
    assert "PARSE_ERROR" not in codes(result)


def test_directive_inside_grid_table_cell_is_registered() -> None:
    # `.. centered::` inside a grid-table cell (observed upstream in autosd.rst).
    result = parse_rst(
        """
        +----------------+-----------------------------+
        | .. centered:: Leonardo Rossetti              |
        +----------------+-----------------------------+
        | Github Handler | @odra                       |
        +----------------+-----------------------------+
        """
    )
    assert "PARSE_ERROR" not in codes(result)
    assert "UNKNOWN_DIRECTIVE" in codes(result)
    table = next(b for b in walk(result.blocks) if b.kind == "table")
    assert "@odra" in table.text
