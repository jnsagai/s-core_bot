"""License allowlist evaluation against a fake pip-licenses inventory (FR-017)."""

from __future__ import annotations

from pathlib import Path

from scripts.check_licenses import (
    PackageLicense,
    evaluate,
    load_exceptions,
    npm_expression_allowed,
    parse_npm_inventory,
    render_notices,
)


def pkg(name: str, license_str: str, version: str = "1.0.0") -> PackageLicense:
    return PackageLicense(name=name, version=version, license=license_str)


def test_allowed_licenses_pass() -> None:
    inventory = [
        pkg("fastapi", "MIT License"),
        pkg("uvicorn", "BSD License"),
        pkg("some-pkg", "Apache Software License"),
        pkg("isc-pkg", "ISC License (ISCL)"),
        pkg("psf-pkg", "Python Software Foundation License"),
        pkg("mpl-pkg", "Mozilla Public License 2.0 (MPL 2.0)"),
        pkg("public-pkg", "The Unlicense (Unlicense)"),
    ]
    violations = evaluate(inventory, exceptions={})
    assert violations == []


def test_unknown_license_fails_naming_the_package() -> None:
    inventory = [pkg("mystery-pkg", "UNKNOWN")]
    violations = evaluate(inventory, exceptions={})
    assert len(violations) == 1
    assert violations[0].package == "mystery-pkg"
    assert "mystery-pkg" in violations[0].reason


def test_unlisted_license_fails_naming_the_package() -> None:
    inventory = [pkg("copyleft-pkg", "GNU General Public License v3 (GPLv3)")]
    violations = evaluate(inventory, exceptions={})
    assert len(violations) == 1
    assert violations[0].package == "copyleft-pkg"


def test_reviewed_exception_is_honoured() -> None:
    inventory = [pkg("copyleft-pkg", "GNU General Public License v3 (GPLv3)")]
    exceptions = {"copyleft-pkg": "Reviewed 2026-09-28: dev-only tool, not redistributed."}
    violations = evaluate(inventory, exceptions=exceptions)
    assert violations == []


def test_exception_for_a_different_package_does_not_apply() -> None:
    inventory = [pkg("copyleft-pkg", "GNU General Public License v3 (GPLv3)")]
    exceptions = {"other-pkg": "Reviewed."}
    violations = evaluate(inventory, exceptions=exceptions)
    assert len(violations) == 1
    assert violations[0].package == "copyleft-pkg"


def test_load_exceptions_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "license-exceptions.yaml"
    path.write_text("schema_version: 1\nexceptions: []\n")
    assert load_exceptions(path) == {}


def test_load_exceptions_missing_file_is_empty(tmp_path: Path) -> None:
    assert load_exceptions(tmp_path / "does-not-exist.yaml") == {}


def test_load_exceptions_populated(tmp_path: Path) -> None:
    path = tmp_path / "license-exceptions.yaml"
    path.write_text(
        "schema_version: 1\n"
        "exceptions:\n"
        "  - name: copyleft-pkg\n"
        "    license: GPLv3\n"
        "    reason: Reviewed 2026-09-28, dev-only.\n"
    )
    exceptions = load_exceptions(path)
    assert exceptions == {"copyleft-pkg": "Reviewed 2026-09-28, dev-only."}


def test_render_notices_includes_every_package_name_and_license() -> None:
    inventory = [pkg("fastapi", "MIT License"), pkg("httpx", "BSD License", version="0.28.1")]
    text = render_notices(inventory)
    assert "fastapi" in text
    assert "MIT License" in text
    assert "httpx" in text
    assert "0.28.1" in text


# F002 FR-025 / research R3: copyleft identifiers override permissive keywords.


def test_mixed_permissive_and_copyleft_string_fails_without_exception() -> None:
    # The exact string pip-licenses reports for docutils 0.23.
    inventory = [pkg("docutils", "BSD License; GNU General Public License (GPL); Public Domain")]
    violations = evaluate(inventory, exceptions={})
    assert [v.package for v in violations] == ["docutils"]
    assert "copyleft" in violations[0].reason


def test_mixed_string_passes_with_reviewed_exception() -> None:
    inventory = [pkg("docutils", "BSD License; GNU General Public License (GPL); Public Domain")]
    exceptions = {"docutils": "Reviewed: only GPL file (tools/editors/emacs/rst.el) not in wheel."}
    assert evaluate(inventory, exceptions=exceptions) == []


def test_dual_permissive_or_expression_still_passes() -> None:
    assert evaluate([pkg("packaging", "Apache-2.0 OR BSD-2-Clause")], exceptions={}) == []


def test_copyleft_variants_each_fail_even_alongside_permissive() -> None:
    for license_str in (
        "MIT; LGPL-3.0-or-later",
        "BSD License; GNU Lesser General Public License v3 (LGPLv3)",
        "Apache-2.0 AND AGPL-3.0-only",
        "MIT, CC-BY-SA-4.0",
        "BSD; Creative Commons Attribution-ShareAlike 4.0",
        "Apache-2.0; European Union Public Licence 1.2 (EUPL 1.2)",
        "MIT; Server Side Public License (SSPL)",
    ):
        violations = evaluate([pkg("x", license_str)], exceptions={})
        assert len(violations) == 1, license_str


def test_plain_word_containing_gpl_letters_is_not_misread() -> None:
    # "MIT License" must not trip on unrelated substrings; guards against over-broad matching.
    assert evaluate([pkg("a", "MIT License"), pkg("b", "ISC License (ISCL)")], exceptions={}) == []


# --- F006: npm inventory (FR-020) -------------------------------------------------------------


def test_unlicensed_is_not_the_unlicense() -> None:
    violations = evaluate([pkg("proprietary", "UNLICENSED")], exceptions={})
    assert [v.package for v in violations] == ["proprietary"]
    assert evaluate([pkg("public", "Unlicense")], exceptions={}) == []


def test_npm_expressions_are_strict() -> None:
    assert npm_expression_allowed("MIT")
    assert npm_expression_allowed("(MIT OR GPL-3.0)")
    assert npm_expression_allowed("Apache-2.0 AND MIT")
    assert npm_expression_allowed("BlueOak-1.0.0") and npm_expression_allowed("CC0-1.0")
    assert not npm_expression_allowed("(MIT AND CC-BY-3.0)")
    assert not npm_expression_allowed("MIT AND GPL-2.0")
    assert not npm_expression_allowed("UNLICENSED")


def test_npm_inventory_parsing_and_evaluation() -> None:
    raw = {
        "react@19.3.0": {"licenses": "MIT"},
        "@scope/tool@1.2.3": {"licenses": ["MIT", "ISC"]},
        "score-docs-assistant-frontend@0.1.0": {"licenses": "UNLICENSED", "private": True},
        "caniuse-lite@1.0.0": {"licenses": "CC-BY-4.0"},
        "left-pad@1.0.0": {"licenses": "GPL-3.0"},
    }
    inventory = parse_npm_inventory(raw)
    names = [p.name for p in inventory]
    assert "npm:@scope/tool" in names and "npm:score-docs-assistant-frontend" not in names
    assert next(p for p in inventory if p.name == "npm:@scope/tool").license == "MIT AND ISC"
    violations = {v.package for v in evaluate(inventory, exceptions={"npm:caniuse-lite": "ok"})}
    assert violations == {"npm:left-pad"}
