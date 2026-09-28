"""Markdown normalization (FR-010, FR-013, FR-016). SYNTHETIC — not S-CORE guidance."""

from __future__ import annotations

from score_docs_assistant.ingestion.markdown import MarkdownParser
from tests.helpers.parsing import walk

DOC = """# Design Record

Intro paragraph
over two lines.

## Context

- one
- two

1. first
2. second

```python
print("x")
```

    indented code

| Col A | Col B |
| ----- | ----- |
| a1    | b1    |

> quoted text

<div onclick="evil()">html block</div>

Inline <b>html</b> here and a [link](https://example.invalid).
"""


def _parse(text: str = DOC):  # type: ignore[no-untyped-def]
    return MarkdownParser().parse(
        source_id="src", revision="r" * 40, path="docs/dr.md", text=text, document_key="k" * 64
    )


def test_structure_and_heading_paths() -> None:
    result = _parse()
    assert result.title == "Design Record"
    sections = [b for b in walk(result.blocks) if b.kind == "section"]
    assert [(s.text, s.heading_path) for s in sections] == [
        ("Design Record", []),
        ("Context", ["Design Record"]),
    ]
    items = [b for b in walk(result.blocks) if b.kind == "list_item"]
    assert [b.heading_path for b in items][0] == ["Design Record", "Context"]
    lists = [b for b in walk(result.blocks) if b.kind == "list"]
    assert [b.attrs["ordered"] for b in lists] == ["false", "true"]


def test_code_table_quote() -> None:
    blocks = list(walk(_parse().blocks))
    codes = [b for b in blocks if b.kind == "code"]
    assert [(c.attrs["language"], c.text) for c in codes] == [
        ("python", 'print("x")'),
        ("", "indented code"),
    ]
    (table,) = [b for b in blocks if b.kind == "table"]
    assert table.attrs["rows"] == [["Col A", "Col B"], ["a1", "b1"]]
    assert table.attrs["header_rows"] == "1"
    assert any(b.kind == "block_quote" for b in blocks)


def test_html_excluded_with_diagnostics() -> None:
    result = _parse()
    blocks = list(walk(result.blocks))
    assert [b.kind for b in blocks].count("raw_excluded") == 1
    all_text = " ".join(b.text for b in blocks)
    assert "evil" not in all_text and "<b>" not in all_text
    para = next(b for b in blocks if b.text.startswith("Inline"))
    assert para.text == "Inline html here and a link."
    assert [d.code for d in result.diagnostics].count("RAW_EXCLUDED") == 3


def test_spans_one_based() -> None:
    blocks = list(walk(_parse().blocks))
    intro = next(b for b in blocks if b.text.startswith("Intro"))
    assert (intro.line_start, intro.line_end) == (3, 4)
    title = next(b for b in blocks if b.kind == "section")
    assert title.line_start == 1
    assert all(len(b.raw_sha256) == 64 and b.origin_path == "docs/dr.md" for b in blocks)


def test_no_entities_from_markdown() -> None:
    assert _parse().entities == []


# MyST backtick-fenced directives (observed upstream in DR-*.md; SRC-005).

MYST = """# DR-006: Decision

```{dec_rec} Clippy Integration
:id: dec_rec__infra__clippy
:status: accepted
:derived_from: stkh_req__a[version==1], stkh_req__b

The body is **Markdown** with a [link](https://example.invalid).
```

```{mermaid}
flowchart TB
  a --> b
```

```{toctree}
:maxdepth: 1

DR-006/considerations
DR-006/details
```

```{grid-item-card} Unknown
:id: looks__like_a_need

Card body.
```

```{needtable}
:filter: type == "dec_rec"
```

```python
print("plain fence stays code")
```
"""


def _parse_myst():  # type: ignore[no-untyped-def]
    from tests.helpers.parsing import profile

    return MarkdownParser(profile()).parse(
        source_id="src", revision="r" * 40, path="docs/dr.md", text=MYST, document_key="k" * 64
    )


def test_myst_need_becomes_entity() -> None:
    result = _parse_myst()
    (entity,) = result.entities
    assert (entity.key, entity.type, entity.title) == (
        "src:dec_rec__infra__clippy",
        "dec_rec",
        "Clippy Integration",
    )
    assert entity.options["status"] == "accepted"
    assert [(r.target_id, r.qualifier) for r in entity.links] == [
        ("stkh_req__a", "version==1"),
        ("stkh_req__b", None),
    ]
    assert (entity.line_start, entity.line_end) == (3, 9)
    need = next(b for b in walk(result.blocks) if b.kind == "need")
    body = [b for b in walk(need.children) if b.kind == "paragraph"]
    assert body[0].text == "The body is Markdown with a link."
    assert body[0].line_start == 8


def test_myst_other_directive_kinds() -> None:
    result = _parse_myst()
    blocks = list(walk(result.blocks))
    diagram = next(b for b in blocks if b.kind == "diagram")
    assert diagram.attrs["language"] == "mermaid" and diagram.text.startswith("flowchart TB")
    toc = next(b for b in blocks if b.kind == "toctree")
    assert toc.attrs["entries"] == ["DR-006/considerations", "DR-006/details"]
    generic = next(b for b in blocks if b.kind == "generic_directive")
    assert generic.attrs["directive"] == "grid-item-card"
    assert any(b.text == "Card body." for b in walk(generic.children))
    view = next(b for b in blocks if b.kind == "dynamic_view")
    assert view.attrs["options"] == {"filter": 'type == "dec_rec"'}
    code = next(b for b in blocks if b.kind == "code")
    assert code.attrs["language"] == "python"
    codes = [d.code for d in result.diagnostics]
    for expected in ("UNKNOWN_DIRECTIVE", "POSSIBLE_UNCONFIGURED_NEED", "DYNAMIC_NOT_EVALUATED"):
        assert expected in codes, expected


def test_without_profile_fences_stay_code() -> None:
    result = _parse(MYST)
    assert result.entities == []
    assert not any(b.kind == "need" for b in walk(result.blocks))
