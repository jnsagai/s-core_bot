"""Untrusted RST stays inert: no evaluation, no I/O, no leakage (FR-013, FR-014, SC-003)."""

from __future__ import annotations

import builtins
import socket
from pathlib import Path
from typing import Any

import pytest
from docutils.parsers.rst import directives, roles

from tests.helpers.parsing import codes, parse_rst, walk


def test_need_syntax_inside_code_block_is_inert() -> None:
    result = parse_rst(
        """
        .. code-block:: rst

           .. dd_sta:: <Title>
              :id: dd_sta__<Feature>__<Title>
        """
    )
    assert result.entities == []
    (code,) = [b for b in walk(result.blocks) if b.kind == "code"]
    assert code.attrs["language"] == "rst"
    assert ":id: dd_sta__<Feature>__<Title>" in code.text


def test_dynamic_directives_not_evaluated() -> None:
    expr = 'c.this_doc() and is_external == False and "feo/docs" in docname'
    result = parse_rst(
        f"""
        .. needextend:: {expr}
           :+tags: component_feo

        .. needtable::
           :filter: type == "feat_req" and status == "valid"
           :columns: id, title

        .. needpie:: Status
           :labels: open, closed
        """
    )
    views = [b for b in walk(result.blocks) if b.kind == "dynamic_view"]
    assert [v.attrs["directive"] for v in views] == ["needextend", "needtable", "needpie"]
    assert views[0].attrs["argument"] == expr
    assert views[1].attrs["options"] == {
        "filter": 'type == "feat_req" and status == "valid"',
        "columns": "id, title",
    }
    assert all(v.text == "" for v in views)
    assert codes(result).count("DYNAMIC_NOT_EVALUATED") == 3


def test_ndf_role_not_evaluated() -> None:
    result = parse_rst("Status: :ndf:`copy('status', need_id='gd_guidl__x')` here.\n")
    (para,) = [b for b in walk(result.blocks) if b.kind == "paragraph"]
    assert "copy(" not in para.text
    assert "DYNAMIC_NOT_EVALUATED" in codes(result)


def test_raw_html_excluded() -> None:
    result = parse_rst(".. raw:: html\n\n   <script>alert(1)</script>\n\nAfter.\n")
    raw = [b for b in walk(result.blocks) if b.kind == "raw_excluded"]
    assert len(raw) == 1 and raw[0].text == ""
    assert "<script>" not in " ".join(b.text for b in walk(result.blocks))
    assert "RAW_EXCLUDED" in codes(result)


def test_no_file_or_network_access(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    secret = tmp_path / "secret.csv"
    secret.write_text("leaked,value\n")
    real_open = builtins.open
    opened: list[str] = []

    def spy_open(file: Any, *args: Any, **kwargs: Any) -> Any:
        opened.append(str(file))
        return real_open(file, *args, **kwargs)

    def no_socket(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("no network access expected")

    monkeypatch.setattr(builtins, "open", spy_open)
    monkeypatch.setattr(socket.socket, "connect", no_socket)
    result = parse_rst(
        f"""
        .. image:: {secret}
           :scale: 50

        .. figure:: https://example.invalid/pic.png

           Caption text.

        .. csv-table:: Data
           :file: {secret}

        .. csv-table:: Remote
           :url: https://example.invalid/data.csv
        """
    )
    assert str(secret) not in opened
    assert not any(o.endswith(("conf.py", "docutils.conf")) for o in opened)
    assert "leaked" not in " ".join(b.text for b in walk(result.blocks))
    assert codes(result).count("EXTERNAL_RESOURCE_NOT_READ") == 4
    images = [b for b in walk(result.blocks) if b.kind == "image"]
    assert images[1].text == "Caption text."


def test_registries_restored_after_parse() -> None:
    before_directives = dict(directives._directives)
    before_roles = dict(roles._roles)
    parse_rst(".. somethingnew:: x\n\n:brandnewrole:`y`\n")
    assert dict(directives._directives) == before_directives
    assert dict(roles._roles) == before_roles
