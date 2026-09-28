"""Strict decoding and per-document license records (FR-021; research R1 SPDX observations)."""

from __future__ import annotations

from score_docs_assistant.ingestion.decode import decode_document
from score_docs_assistant.ingestion.licenses import detect_license

ALLOWED = {"Apache-2.0", "MIT", "CC0-1.0"}


def test_valid_utf8() -> None:
    result = decode_document("Überblick\n".encode())
    assert result.text == "Überblick\n" and result.codes == []


def test_bom_stripped() -> None:
    assert decode_document(b"\xef\xbb\xbfTitle\n").text == "Title\n"


def test_invalid_bytes_fail_without_replacement() -> None:
    result = decode_document(b"ok\xff\xfe")
    assert result.text is None and result.codes == ["ENCODING_ERROR"]


def test_empty_and_blank_documents() -> None:
    assert decode_document(b"").codes == ["EMPTY_DOCUMENT"]
    assert decode_document(b"  \n\t\n").codes == ["EMPTY_DOCUMENT"]


RST_HEADER = """..
   # *******************************************************************************
   # Copyright (c) 2025 Contributors to the Eclipse Foundation
   # SPDX-License-Identifier: {spdx}
   # *******************************************************************************

Title
=====
"""


def test_declared_in_rst_comment() -> None:
    record, codes = detect_license(RST_HEADER.format(spdx="Apache-2.0"), "Apache-2.0", ALLOWED)
    assert (record.spdx, record.basis, record.redistribution) == (
        "Apache-2.0",
        "declared",
        "allowed",
    )
    assert codes == []


def test_declared_cc_by_sa_requires_review() -> None:
    record, _ = detect_license(RST_HEADER.format(spdx="CC-BY-SA-4.0"), "Apache-2.0", ALLOWED)
    assert (record.spdx, record.basis, record.redistribution) == (
        "CC-BY-SA-4.0",
        "declared",
        "requires_review",
    )


def test_declared_in_markdown_html_comment() -> None:
    text = "<!--\nSPDX-License-Identifier: Apache-2.0\n-->\n# DR\n"
    record, _ = detect_license(text, None, ALLOWED)
    assert (record.spdx, record.basis) == ("Apache-2.0", "declared")


def test_single_line_html_comment_trailing_marker_removed() -> None:
    record, _ = detect_license("<!-- SPDX-License-Identifier: MIT -->\n", None, ALLOWED)
    assert record.spdx == "MIT"


def test_absent_header_inherits_repository_license() -> None:
    record, codes = detect_license("Title\n=====\n", "Apache-2.0", ALLOWED)
    assert (record.spdx, record.basis, record.redistribution) == (
        "Apache-2.0",
        "inherited",
        "allowed",
    )
    assert codes == []


def test_absent_everything_is_unknown() -> None:
    record, codes = detect_license("Title\n", None, ALLOWED)
    assert (record.spdx, record.basis, record.redistribution) == (
        None,
        "unknown",
        "requires_review",
    )
    assert codes == ["LICENSE_UNKNOWN"]


def test_compound_expression_requires_review() -> None:
    record, _ = detect_license("SPDX-License-Identifier: MIT OR GPL-2.0-only\n", None, ALLOWED)
    assert record.spdx == "MIT OR GPL-2.0-only"
    assert record.redistribution == "requires_review"


def test_header_beyond_first_20_lines_ignored() -> None:
    text = "\n" * 25 + "SPDX-License-Identifier: MIT\n"
    record, _ = detect_license(text, None, ALLOWED)
    assert record.basis == "unknown"
