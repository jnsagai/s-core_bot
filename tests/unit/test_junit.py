"""JUnit XML parsing (F008 R8)."""

from __future__ import annotations

from pathlib import Path

from score_docs_assistant.qualification.junit import parse_junit

XML = """<?xml version="1.0"?>
<testsuites><testsuite name="pytest">
  <testcase classname="tests.unit.test_a" name="test_ok"/>
  <testcase classname="tests.unit.test_a" name="test_bad"><failure message="x"/></testcase>
  <testcase classname="tests.unit.test_b" name="test_err"><error message="y"/></testcase>
  <testcase classname="tests.integration.test_real" name="test_real"><skipped/></testcase>
</testsuite></testsuites>"""


def test_outcomes(tmp_path: Path) -> None:
    path = tmp_path / "r.xml"
    path.write_text(XML)
    summary = parse_junit(path)
    assert summary.counts == {"passed": 1, "failed": 2, "skipped": 1}
    assert [t.outcome for t in summary.matching("test_a")] == ["passed", "failed"]
    assert summary.matching("test_real")[0].name == "tests.integration.test_real::test_real"
