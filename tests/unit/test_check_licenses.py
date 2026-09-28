"""License allowlist evaluation against a fake pip-licenses inventory (FR-017)."""

from __future__ import annotations

from pathlib import Path

from scripts.check_licenses import (
    PackageLicense,
    evaluate,
    load_exceptions,
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
