#!/usr/bin/env python3
"""Fail CI on any locked dependency whose license is not on the allowlist (FR-017, OPS-005).

Usage:
    uv run python scripts/check_licenses.py                  # check only
    uv run python scripts/check_licenses.py --write-notices   # also (re)write notices file

Reviewed exceptions live in config/license-exceptions.yaml (research.md R13). Adding an entry
there is a human decision recording that the named package's actual license was checked and
accepted — never a way to silence a failure without reading the license.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EXCEPTIONS_PATH = REPO_ROOT / "config" / "license-exceptions.yaml"
DEFAULT_NOTICES_PATH = REPO_ROOT / "THIRD_PARTY_NOTICES.md"

# Substring match, case-insensitive, against pip-licenses' free-text `License` field. pip-licenses
# does not distinguish BSD-2-Clause from BSD-3-Clause (or, in principle, the rare 4-clause
# original BSD); every BSD license observed across this project's dependencies is 2- or 3-clause,
# so "BSD" is accepted as a group per research.md R13's "BSD-2/3-Clause" entry.
ALLOWED_LICENSE_KEYWORDS = (
    "MIT",
    "BSD",
    "APACHE",
    "ISC",
    "PYTHON SOFTWARE FOUNDATION",
    "PSF",
    "MOZILLA PUBLIC LICENSE",
    "MPL",
    # Added for the npm inventory (F006, docs/ASSUMPTIONS.md A-038): both are permissive and
    # OSI/FSF-recognized; CC0 is a public-domain dedication.
    "BLUEOAK",
    "CC0",
)
# "The Unlicense" is allowed, but npm's "UNLICENSED" means *no license granted* (proprietary).
# A plain substring test would accept the latter, so the Unlicense is matched as a whole word.
UNLICENSE_PATTERN = re.compile(r"\bUNLICENSE\b")
FRONTEND_DIR = REPO_ROOT / "frontend"


@dataclass(frozen=True)
class PackageLicense:
    name: str
    version: str
    license: str
    # "npm" licenses are SPDX expressions and are evaluated strictly (npm_expression_allowed).
    ecosystem: str = "python"


@dataclass(frozen=True)
class LicenseViolation:
    package: str
    reason: str


# A copyleft identifier anywhere in the string overrides any permissive keyword: pip-licenses joins
# a package's license classifiers with "; ", so "BSD License; GNU General Public License (GPL)"
# (docutils) names a mixed licence, not an either/or choice. Such packages pass only through a
# reviewed exception (F002 FR-025, research R3; docs/ASSUMPTIONS.md A-013).
COPYLEFT_PATTERN = re.compile(
    r"\b(?:A|L)?GPL|GENERAL PUBLIC LICEN[CS]E|\bEUPL\b|EUROPEAN UNION PUBLIC LICEN[CS]E|\bSSPL\b"
    r"|SERVER SIDE PUBLIC LICENSE|\bCC-BY-SA\b|SHARE-?ALIKE"
)


def is_copyleft(license_str: str) -> bool:
    return COPYLEFT_PATTERN.search(license_str.upper()) is not None


def is_allowed(license_str: str) -> bool:
    upper = license_str.upper()
    return any(keyword in upper for keyword in ALLOWED_LICENSE_KEYWORDS) or bool(
        UNLICENSE_PATTERN.search(upper)
    )


def npm_expression_allowed(expression: str) -> bool:
    """SPDX expression rule for npm: any one OR-alternative must be fully allowed, and every
    AND-part of that alternative must be allowed and not copyleft ("MIT AND CC-BY-3.0" fails)."""
    cleaned = expression.replace("(", " ").replace(")", " ")
    for alternative in re.split(r"\s+OR\s+", cleaned.strip(), flags=re.IGNORECASE):
        parts = [p.strip() for p in re.split(r"\s+AND\s+", alternative, flags=re.IGNORECASE)]
        if parts and all(p and is_allowed(p) and not is_copyleft(p) for p in parts):
            return True
    return False


def evaluate(inventory: list[PackageLicense], exceptions: dict[str, str]) -> list[LicenseViolation]:
    violations: list[LicenseViolation] = []
    for pkg in inventory:
        if pkg.name in exceptions:
            continue
        if is_copyleft(pkg.license):
            violations.append(
                LicenseViolation(
                    package=pkg.name,
                    reason=(
                        f"{pkg.name} {pkg.version}: license {pkg.license!r} names a copyleft "
                        f"license and needs a reviewed exception in {DEFAULT_EXCEPTIONS_PATH.name}."
                    ),
                )
            )
            continue
        if pkg.ecosystem == "npm":
            if npm_expression_allowed(pkg.license):
                continue
        elif is_allowed(pkg.license):
            continue
        violations.append(
            LicenseViolation(
                package=pkg.name,
                reason=(
                    f"{pkg.name} {pkg.version}: license {pkg.license!r} is not on the allowlist "
                    f"and has no reviewed exception in {DEFAULT_EXCEPTIONS_PATH.name}."
                ),
            )
        )
    return violations


def load_exceptions(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text()) or {}
    result: dict[str, str] = {}
    for entry in data.get("exceptions", []):
        result[entry["name"]] = entry["reason"]
    return result


def run_pip_licenses() -> list[PackageLicense]:
    """Run `pip-licenses --format=json` with PYTHONPATH cleared.

    A contaminated PYTHONPATH (e.g. a ROS environment sourced in the shell, see
    docs/ASSUMPTIONS.md A-009) makes Python's package discovery see distributions outside this
    project's uv-managed environment. Clearing it restores scanning to exactly the synced venv.
    """
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        ["pip-licenses", "--format=json"],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    raw = json.loads(result.stdout)
    return [PackageLicense(name=p["Name"], version=p["Version"], license=p["License"]) for p in raw]


def run_npm_licenses(frontend_dir: Path = FRONTEND_DIR) -> list[PackageLicense]:
    """Frontend inventory (F006 FR-020) from `license-checker-rseidelsohn`, run via the locked
    `npm run license-check` script. Covers production *and* dev dependencies, like the Python
    gate covers dev tools. The project's own private root package is excluded."""
    if not (frontend_dir / "package-lock.json").exists():
        return []
    if not (frontend_dir / "node_modules").is_dir():
        raise SystemExit(
            "frontend/node_modules is missing; run `npm ci` in frontend/ before the license check."
        )
    result = subprocess.run(
        ["npm", "run", "--silent", "license-check"],
        cwd=frontend_dir,
        capture_output=True,
        text=True,
        check=True,
    )
    return parse_npm_inventory(json.loads(result.stdout))


def parse_npm_inventory(raw: dict[str, dict[str, object]]) -> list[PackageLicense]:
    inventory: list[PackageLicense] = []
    for key, info in sorted(raw.items()):
        if info.get("private"):
            continue
        name, _, version = key.rpartition("@")
        licenses = info.get("licenses", "UNKNOWN")
        if isinstance(licenses, list):
            licenses = " AND ".join(str(item) for item in licenses)
        inventory.append(
            PackageLicense(
                name=f"npm:{name}", version=version, license=str(licenses), ecosystem="npm"
            )
        )
    return inventory


def render_notices(inventory: list[PackageLicense]) -> str:
    lines = [
        "# Third-party notices",
        "",
        "Locked dependencies of this project and their reported licenses, generated by",
        "`scripts/check_licenses.py --write-notices` from `pip-licenses --format=json`. This file",
        "records attribution; it is not a substitute for reading each package's own license file.",
        "",
    ]
    for pkg in sorted(inventory, key=lambda p: p.name.lower()):
        lines.append(f"- **{pkg.name}** {pkg.version} — {pkg.license}")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write-notices",
        action="store_true",
        help=f"Also (re)write {DEFAULT_NOTICES_PATH.name} from the current inventory.",
    )
    parser.add_argument("--exceptions", type=Path, default=DEFAULT_EXCEPTIONS_PATH)
    parser.add_argument("--notices-path", type=Path, default=DEFAULT_NOTICES_PATH)
    args = parser.parse_args(argv)

    inventory = run_pip_licenses() + run_npm_licenses()
    exceptions = load_exceptions(args.exceptions)
    violations = evaluate(inventory, exceptions)

    if args.write_notices:
        args.notices_path.write_text(render_notices(inventory))
        print(f"Wrote {args.notices_path} ({len(inventory)} packages).")

    if violations:
        print(f"License check FAILED: {len(violations)} package(s) not on the allowlist.")
        for v in violations:
            print(f"  - {v.reason}")
        return 1

    print(f"License check passed: {len(inventory)} packages, all allowed or reviewed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
