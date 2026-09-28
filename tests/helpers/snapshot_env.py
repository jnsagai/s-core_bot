"""Synthetic source trees plus a source lock for F003 tests — no git, no network.

Every generated file starts with a `SYNTHETIC — not S-CORE guidance` comment. Content is generated
deterministically so long tables, code blocks and paragraphs need not be stored as fixtures.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from score_docs_assistant.domain.ingestion import LockedFile, LockedSource, SourceLock
from score_docs_assistant.sources.lock import write_lock

REPO_ROOT = Path(__file__).parent.parent.parent
PROFILES = REPO_ROOT / "config" / "parser-profiles"
SYNTHETIC_RST = ".. SYNTHETIC — not S-CORE guidance\n\n"
SPDX_APACHE = ".. SPDX-License-Identifier: Apache-2.0\n"
SHARED_PARAGRAPH = "Both sources repeat this exact synthetic paragraph about shared text."


def _sentences(count: int, topic: str) -> str:
    return " ".join(
        f"Sentence {i} explains how the {topic} behaves when the scheduler rotates its queue."
        for i in range(1, count + 1)
    )


def _table(rows: int) -> str:
    lines = [
        ".. list-table:: Synthetic signals",
        "   :header-rows: 1",
        "",
        "   * - Signal",
        "     - Description",
    ]
    for i in range(rows):
        lines += [f"   * - SIG_{i:03d}", f"     - Signal number {i} carries the wheel speed value."]
    return "\n".join(lines) + "\n"


def _code(lines: int) -> str:
    body = "\n".join(f"   int value_{i} = compute({i}); // step {i}" for i in range(lines))
    return ".. code-block:: cpp\n\n" + body + "\n"


def alpha_index_rst() -> str:
    long_need_body = "\n\n".join("   " + _sentences(6, f"component part {p}") for p in range(1, 9))
    return (
        SPDX_APACHE
        + SYNTHETIC_RST
        + "Alpha Platform\n==============\n\n"
        + "Intro paragraph for the alpha platform.\n\n"
        + ".. raw:: html\n\n   <script>alert('never')</script>\n\n"
        + ".. needtable::\n   :types: feat_req\n\n"
        + "Requirements\n------------\n\n"
        + ".. feat_req:: Short requirement\n   :id: feat_req__alpha__short\n"
        + "   :status: valid\n   :satisfies: feat_req__alpha__long\n\n"
        + "   The short requirement fits in one chunk.\n\n"
        + ".. feat_req:: Long requirement\n   :id: feat_req__alpha__long\n   :status: draft\n\n"
        + long_need_body
        + "\n\n"
        + "Small Section A\n---------------\n\nOnly a little text in section A.\n\n"
        + "Small Section B\n---------------\n\nOnly a little text in section B.\n\n"
        + "Shared\n------\n\n"
        + SHARED_PARAGRAPH
        + "\n\n"
        + "Data\n----\n\n"
        + _table(60)
        + "\n"
        + _code(200)
        + "\n"
        + ".. uml::\n\n   @startuml\n   A -> B: hello\n   @enduml\n\n"
        + "Long Prose\n----------\n\n"
        + _sentences(80, "watchdog")
        + "\n"
    )


def alpha_guide_md() -> str:
    return (
        "<!-- SPDX-License-Identifier: Apache-2.0 -->\n"
        "<!-- SYNTHETIC — not S-CORE guidance -->\n\n"
        "# Guide\n\nA markdown guide paragraph.\n\n## Usage\n\nRun the tool with care.\n"
    )


def alpha_sharealike_rst() -> str:
    return (
        ".. SPDX-License-Identifier: CC-BY-SA-4.0\n"
        + SYNTHETIC_RST
        + "Share Alike\n===========\n\nThis page requires license review before redistribution.\n"
    )


def beta_shared_rst() -> str:
    return (
        SPDX_APACHE
        + SYNTHETIC_RST
        + "Beta\n====\n\n"
        + SHARED_PARAGRAPH
        + "\n\n.. std_req:: Beta standard\n   :id: std_req__beta__one\n   :status: valid\n\n"
        + "   Beta requirement body.\n"
    )


@dataclass
class SourceSpec:
    source_id: str
    files: dict[str, str]
    revision: str
    required: bool = True
    kind: str = "git"
    status: str = "ok"
    associated_source: str | None = None
    docs_root: str | None = None


def default_sources() -> list[SourceSpec]:
    return [
        SourceSpec(
            "alpha",
            {
                "docs/index.rst": alpha_index_rst(),
                "docs/guide.md": alpha_guide_md(),
                "docs/sharealike.rst": alpha_sharealike_rst(),
            },
            revision="a" * 40,
        ),
        SourceSpec("beta", {"docs/shared.rst": beta_shared_rst()}, revision="b" * 40),
    ]


@dataclass
class SnapshotEnv:
    data: Path
    lock_path: Path
    sources: list[SourceSpec] = field(default_factory=list)

    def write(self, sources: list[SourceSpec] | None = None) -> Path:
        """(Re)write source trees and the lock; returns the lock path."""
        if sources is not None:
            self.sources = sources
        locked: list[LockedSource] = []
        for spec in sorted(self.sources, key=lambda s: s.source_id):
            root = self.data / "sources" / spec.source_id / spec.revision
            files: list[LockedFile] = []
            if spec.status == "ok":
                for path, text in sorted(spec.files.items()):
                    target = root / path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    raw = text.encode("utf-8")
                    target.write_bytes(raw)
                    files.append(
                        LockedFile(path=path, sha256=hashlib.sha256(raw).hexdigest(), size=len(raw))
                    )
            locked.append(
                LockedSource(
                    source_id=spec.source_id,
                    kind=spec.kind,  # type: ignore[arg-type]
                    status=spec.status,  # type: ignore[arg-type]
                    failure=None if spec.status == "ok" else "fixture failure",
                    required=spec.required,
                    repository=(
                        f"https://github.com/example/{spec.source_id}"
                        if spec.kind == "git"
                        else None
                    ),
                    url=(
                        f"https://example.github.io/{spec.source_id}/needs.json"
                        if spec.kind == "needs-export"
                        else None
                    ),
                    ref="main" if spec.kind == "git" else None,
                    authority="fixture",
                    repository_license="Apache-2.0",
                    parser_profile="s-core" if spec.kind == "git" else None,
                    associated_source=spec.associated_source,
                    docs_root=spec.docs_root,
                    revision=spec.revision if spec.status == "ok" else None,
                    revision_status="pinned" if spec.kind == "git" else "unverified",
                    fetched_at=datetime(2026, 9, 28, tzinfo=UTC),
                    selector_sha256="0" * 64 if spec.kind == "git" else None,
                    excluded_by_selector=0 if spec.kind == "git" else None,
                    files=files,
                )
            )
        lock = SourceLock(
            schema_version=1,
            generated_at=datetime(2026, 9, 28, tzinfo=UTC),
            registry_sha256="0" * 64,
            redistribution_allowed_licenses=["Apache-2.0"],
            sources=locked,
        )
        write_lock(self.lock_path, lock)
        return self.lock_path


def make_env(tmp_path: Path, sources: list[SourceSpec] | None = None) -> SnapshotEnv:
    data = tmp_path / "data"
    data.mkdir(parents=True, exist_ok=True)
    env = SnapshotEnv(data=data, lock_path=data / "source-lock.json")
    env.write(sources if sources is not None else default_sources())
    return env


def write_model_lock(
    data: Path,
    digest: str,
    tag: str = "nomic-embed-text:latest",
    generation_digest: str | None = None,
) -> None:
    (data / "model-lock.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "profile": "local-small",
                "runtime": {"provider": "ollama", "version": "0.34.0"},
                "models": [
                    {
                        "role": "embedding",
                        "tag": tag,
                        "digest": digest,
                        "size_bytes": 1,
                        "acquired_at": "2026-09-28T00:00:00Z",
                    },
                    *(
                        [
                            {
                                "role": "generation",
                                "tag": "qwen3:4b-instruct",
                                "digest": generation_digest,
                                "size_bytes": 1,
                                "acquired_at": "2026-09-28T00:00:00Z",
                            }
                        ]
                        if generation_digest
                        else []
                    ),
                ],
            }
        )
    )
