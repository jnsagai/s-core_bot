"""Source spans (FR-016). Rules verified against docutils 0.23 by prototype (research R2):
paragraph/list-item lines exact; section lines corrected from docutils' underline line; needs
end at their last option or body line."""

from __future__ import annotations

import hashlib

from tests.helpers.parsing import parse_rst, walk

TEXT = """Title Here
==========

First paragraph line one
continues on line five
and ends on line six.

* item one
* item two
  wraps

.. std_req:: Only options
   :id: std_req__opts
   :status: valid

.. feat_req:: With body
   :id: feat_req__body

   Body line 18.
   Body line 19.

========
Overline
========

After overline.

.. code-block:: python

   x = 1
   y = 2
"""


def _by_text(text: str) -> object:
    return next(b for b in walk(parse_rst(TEXT, dedent=False).blocks) if b.text == text)


def _span(block: object) -> tuple[int | None, int | None]:
    return block.line_start, block.line_end  # type: ignore[attr-defined]


def test_section_spans_use_title_line() -> None:
    result = parse_rst(TEXT, dedent=False)
    sections = [b for b in walk(result.blocks) if b.kind == "section"]
    assert [(s.text, s.line_start) for s in sections] == [("Title Here", 1), ("Overline", 22)]


def test_paragraph_spans_exact() -> None:
    para = next(b for b in walk(parse_rst(TEXT, dedent=False).blocks) if b.text.startswith("First"))
    assert _span(para) == (4, 6)


def test_list_item_spans() -> None:
    items = [b for b in walk(parse_rst(TEXT, dedent=False).blocks) if b.kind == "list_item"]
    assert [b.line_start for b in items] == [8, 9]
    assert items[1].line_end == 10


def test_need_spans_with_and_without_body() -> None:
    result = parse_rst(TEXT, dedent=False)
    spans = {e.need_id: (e.line_start, e.line_end) for e in result.entities}
    assert spans == {"std_req__opts": (12, 14), "feat_req__body": (16, 20)}


def test_code_block_span_and_hashes() -> None:
    result = parse_rst(TEXT, dedent=False)
    code = next(b for b in walk(result.blocks) if b.kind == "code")
    assert _span(code) == (28, 31)
    lines = TEXT.splitlines()
    expected = hashlib.sha256("\n".join(lines[27:31]).encode()).hexdigest()
    assert code.raw_sha256 == expected
    for block in walk(result.blocks):
        assert len(block.raw_sha256) == 64
        assert block.origin_path == "docs/test.rst"
