"""Prepared-package manifest and fresh-install report (F009 FR-005, FR-006).

python -m score_docs_assistant.qualification.package manifest PACKAGE_DIR [--meta KEY=VALUE ...]
python -m score_docs_assistant.qualification.package report STEPS.tsv --out REPORT
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from score_docs_assistant import __version__

MANIFEST = "package-manifest.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write_manifest(package: Path, meta: dict[str, str]) -> Path:
    items = [
        {"path": p.relative_to(package).as_posix(), "size": p.stat().st_size, "sha256": sha256(p)}
        for p in sorted(package.rglob("*"))
        if p.is_file() and p.name != MANIFEST
    ]
    manifest = {
        "created_at": datetime.now(UTC).isoformat(),
        "app_version": __version__,
        **meta,
        "items": items,
        "excluded": [
            {"what": "secrets, caches, logs, data/reports", "reason": "never packaged"},
            {
                "what": "model weights (unless --with-models)",
                "reason": "redistribution not reviewed",
            },
        ],
    }
    path = package / MANIFEST
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    return path


def verify_manifest(package: Path) -> list[str]:
    manifest = json.loads((package / MANIFEST).read_text())
    problems = []
    for item in manifest["items"]:
        path = package / item["path"]
        if not path.is_file():
            problems.append(f"missing {item['path']}")
        elif sha256(path) != item["sha256"]:
            problems.append(f"hash mismatch {item['path']}")
    return problems


def steps_report(steps_file: Path) -> dict[str, object]:
    steps = []
    for line in steps_file.read_text().splitlines():
        name, ok, detail = (line.split("\t", 2) + ["", ""])[:3]
        steps.append({"name": name, "ok": ok == "ok", "detail": detail})
    passed = bool(steps) and all(s["ok"] for s in steps)
    return {
        "created_at": datetime.now(UTC).isoformat(),
        "status": "pass" if passed else "fail",
        "reason": "all steps passed"
        if passed
        else "; ".join(str(s["name"]) for s in steps if not s["ok"]),
        "steps": steps,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    m = sub.add_parser("manifest")
    m.add_argument("package", type=Path)
    m.add_argument("--meta", action="append", default=[])
    v = sub.add_parser("verify")
    v.add_argument("package", type=Path)
    r = sub.add_parser("report")
    r.add_argument("steps", type=Path)
    r.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "manifest":
        meta = dict(item.split("=", 1) for item in args.meta)
        print(write_manifest(args.package, meta))
        return 0
    if args.command == "verify":
        problems = verify_manifest(args.package)
        for problem in problems:
            print(problem)
        print("package verified" if not problems else f"{len(problems)} problem(s)")
        return 1 if problems else 0
    report = steps_report(args.steps)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"fresh install: {report['status']} — {report['reason']}")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
