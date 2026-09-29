"""Release assembly (F009 FR-011, master §18.1).

Copies the release contents into `data/releases/<version>-<utc>/` with a SHA-256 manifest:
- the locks, SBOM and license notices;
- the model record and the corpus manifest;
- the evaluation, deployment and release reports;
- the hardware matrix and known limitations.

Model weights and corpus bundles are never included: their redistribution conditions have not been
reviewed.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from score_docs_assistant import __version__
from score_docs_assistant.qualification.package import sha256


@dataclass(frozen=True)
class Item:
    kind: str
    source: str  # repository-relative path, or a glob under the reports directory (latest wins)
    in_reports: bool = False
    required: bool = True


ITEMS = (
    Item("lock", "uv.lock"),
    Item("lock", "frontend/package-lock.json"),
    Item("notices", "THIRD_PARTY_NOTICES.md"),
    Item("hardware", "docs/quality/hardware-matrix.md"),
    Item("limitations", "docs/KNOWN_LIMITATIONS.md"),
    Item("sbom", "sbom-*.cdx.json", in_reports=True),
    Item("models", "models-*.json", in_reports=True),
    Item("evaluation", "suite-heldout-*-combined.json", in_reports=True),
    Item("evaluation", "adversarial-*.json", in_reports=True),
    Item("evaluation", "performance-*.json", in_reports=True),
    Item("deployment", "offline-2*.json", in_reports=True),
    Item("deployment", "container-2*.json", in_reports=True),
    Item("deployment", "fresh-install-*.json", in_reports=True),
    Item("deployment", "restore-*.json", in_reports=True),
    Item("deployment", "contract-2*.json", in_reports=True),
    Item("release-report", "release-*/report.md", in_reports=True),
)
EXCLUDED = [
    {"what": "model weights", "reason": "redistribution conditions not reviewed"},
    {
        "what": "corpus bundles",
        "reason": "redistribution conditions not reviewed (license review items)",
    },
]


def assemble(root: Path, reports: Path, snapshot_manifest: Path | None, out_base: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = out_base / f"{__version__}-{stamp}"
    out.mkdir(parents=True)
    entries: list[dict[str, object]] = []
    missing: list[str] = []
    for item in ITEMS:
        if item.in_reports:
            matches = sorted(reports.glob(item.source))
            source = matches[-1] if matches else None
        else:
            candidate = root / item.source
            source = candidate if candidate.is_file() else None
        if source is None:
            if item.required:
                missing.append(item.source)
            continue
        target_name = source.name if item.kind != "release-report" else "release-report.md"
        target = out / item.kind / target_name
        target.parent.mkdir(exist_ok=True)
        shutil.copy2(source, target)
        entries.append(
            {
                "kind": item.kind,
                "path": target.relative_to(out).as_posix(),
                "from": item.source,
                "size": target.stat().st_size,
                "sha256": sha256(target),
            }
        )
    if snapshot_manifest is not None and snapshot_manifest.is_file():
        target = out / "corpus" / "snapshot-manifest.json"
        target.parent.mkdir(exist_ok=True)
        shutil.copy2(snapshot_manifest, target)
        entries.append(
            {
                "kind": "corpus",
                "path": "corpus/snapshot-manifest.json",
                "from": "active snapshot",
                "size": target.stat().st_size,
                "sha256": sha256(target),
            }
        )
    else:
        missing.append("active snapshot manifest")
    manifest = {
        "version": __version__,
        "created_at": datetime.now(UTC).isoformat(),
        "items": entries,
        "missing": missing,
        "excluded": EXCLUDED,
        "complete": not missing,
    }
    (out / "release-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return out
