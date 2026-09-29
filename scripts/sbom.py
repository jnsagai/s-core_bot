#!/usr/bin/env python3
"""CycloneDX 1.5 SBOM from the locks (F009 FR-010, OPS-005). Offline; stdlib only.

Python components come from uv.lock (runtime scope = the closure of the project's dependencies,
optional = dev-only), with licenses from installed package metadata when available. npm components
come from frontend/package-lock.json (dev packages are optional scope).

    uv run python scripts/sbom.py --out data/reports/sbom-<utc>.cdx.json
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
import uuid
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
PROJECT = "s-core-docs-assistant"


def _norm(name: str) -> str:
    return name.lower().replace("_", "-").replace(".", "-")


def python_license(name: str) -> str | None:
    try:
        meta = metadata.metadata(name)
    except metadata.PackageNotFoundError:
        return None
    expression = meta.get("License-Expression")
    if expression:
        return str(expression)
    classifiers = [
        c.split("::")[-1].strip()
        for c in meta.get_all("Classifier") or []
        if c.startswith("License ::")
    ]
    if classifiers:
        return " OR ".join(sorted(set(classifiers)))
    raw = meta.get("License")
    return raw.splitlines()[0][:80] if raw else None


def python_components(lock_path: Path) -> list[dict[str, Any]]:
    lock = tomllib.loads(lock_path.read_text())
    packages = {_norm(p["name"]): p for p in lock["package"]}
    runtime: set[str] = set()
    stack = [d["name"] for d in packages[_norm(PROJECT)].get("dependencies", [])]
    while stack:
        name = _norm(stack.pop())
        if name in runtime or name not in packages:
            continue
        runtime.add(name)
        stack.extend(d["name"] for d in packages[name].get("dependencies", []))
    components = []
    for key, package in sorted(packages.items()):
        if key == _norm(PROJECT):
            continue
        component: dict[str, Any] = {
            "type": "library",
            "name": package["name"],
            "version": package["version"],
            "purl": f"pkg:pypi/{key}@{package['version']}",
            "scope": "required" if key in runtime else "optional",
        }
        license_id = python_license(package["name"])
        if license_id:
            component["licenses"] = [{"expression": license_id}]
        components.append(component)
    return components


def npm_components(lock_path: Path) -> list[dict[str, Any]]:
    lock = json.loads(lock_path.read_text())
    components = []
    seen: set[str] = set()
    for path, package in sorted(lock.get("packages", {}).items()):
        if not path.startswith("node_modules/"):
            continue
        name = path.split("node_modules/")[-1]
        version = package.get("version", "")
        encoded = name.replace("@", "%40", 1) if name.startswith("@") else name
        component: dict[str, Any] = {
            "type": "library",
            "name": name,
            "version": version,
            "purl": f"pkg:npm/{encoded}@{version}",
            "scope": "optional" if package.get("dev") else "required",
        }
        if component["purl"] in seen:  # nested node_modules may repeat name@version
            continue
        seen.add(component["purl"])
        if package.get("license"):
            component["licenses"] = [{"expression": str(package["license"])}]
        components.append(component)
    return components


def build(root: Path = ROOT) -> dict[str, Any]:
    project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    components = python_components(root / "uv.lock") + npm_components(
        root / "frontend" / "package-lock.json"
    )
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{uuid.uuid4()}",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(UTC).isoformat(),
            "component": {
                "type": "application",
                "name": project["name"],
                "version": project["version"],
                "licenses": [{"expression": project.get("license", "Apache-2.0")}],
            },
            "tools": [{"name": "scripts/sbom.py"}],
        },
        "components": components,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    bom = build()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(bom, indent=2) + "\n")
    comps = bom["components"]
    python = sum(1 for c in comps if c["purl"].startswith("pkg:pypi/"))
    unlicensed = sum(1 for c in comps if "licenses" not in c)
    print(
        f"SBOM: {len(comps)} components ({python} Python, {len(comps) - python} npm); "
        f"{unlicensed} without license data → {args.out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
