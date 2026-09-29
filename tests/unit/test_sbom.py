"""SBOM completeness against the locks (F009 FR-010, SC-005)."""

from __future__ import annotations

import importlib.util
import json
import tomllib
from pathlib import Path

REPO = Path(__file__).parent.parent.parent
spec = importlib.util.spec_from_file_location("sbom", REPO / "scripts" / "sbom.py")
assert spec and spec.loader
sbom = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sbom)


def test_every_locked_package_is_listed() -> None:
    bom = sbom.build(REPO)
    assert bom["bomFormat"] == "CycloneDX" and bom["specVersion"] == "1.5"
    purls = {c["purl"] for c in bom["components"]}
    uv_lock = tomllib.loads((REPO / "uv.lock").read_text())["package"]
    for package in uv_lock:
        if package["name"] != "s-core-docs-assistant":
            assert f"pkg:pypi/{sbom._norm(package['name'])}@{package['version']}" in purls
    npm = json.loads((REPO / "frontend" / "package-lock.json").read_text())["packages"]
    # Nested node_modules may repeat the same name@version; the SBOM lists each distinct one.
    distinct = {
        (path.split("node_modules/")[-1], meta.get("version"))
        for path, meta in npm.items()
        if path.startswith("node_modules/")
    }
    assert sum(1 for p in purls if p.startswith("pkg:npm/")) == len(distinct)
    assert len(purls) == len(bom["components"])  # no duplicate components


def test_runtime_and_dev_scopes() -> None:
    components = {c["name"]: c for c in sbom.build(REPO)["components"]}
    assert components["fastapi"]["scope"] == "required"
    assert components["pytest"]["scope"] == "optional"
    assert (
        components["react"]["scope"] == "required" and components["vitest"]["scope"] == "optional"
    )
    assert components["fastapi"]["licenses"]
