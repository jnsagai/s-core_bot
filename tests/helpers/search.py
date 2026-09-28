"""Fixture snapshots and a `SearchService` for F004 tests (mocked embedding provider).

Every source text carries a `SYNTHETIC — not S-CORE guidance` marker.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from score_docs_assistant.config.schema import AppConfig
from tests.helpers.build import build
from tests.helpers.fake_embedding import FakeEmbeddingProvider
from tests.helpers.lifecycle import activate
from tests.helpers.snapshot_env import SPDX_APACHE, SYNTHETIC_RST, SnapshotEnv, SourceSpec, make_env

if TYPE_CHECKING:
    from score_docs_assistant.retrieval.service import SearchService

REPEATED = "This synthetic paragraph about quorum voting appears twice in the guide."
SHARED = "Both fixture sources contain this identical synthetic sentence about telemetry."

REQS_RST = (
    SPDX_APACHE
    + SYNTHETIC_RST
    + "Requirements\n============\n\n"
    + ".. std_req:: Machine learning base practice\n   :id: MLE.3.BP1\n   :status: valid\n\n"
    + "   Define the machine learning data requirements.\n\n"
    + ".. feat_req:: Short requirement\n   :id: feat_req__alpha__short\n   :status: valid\n"
    + "   :satisfies: feat_req__alpha__long, feat_req__missing\n\n"
    + "   The short requirement explains the scheduler handshake.\n\n"
    + ".. feat_req:: Long requirement\n   :id: feat_req__alpha__long\n   :status: draft\n\n"
    + "   The long requirement describes persistence of configuration.\n\n"
    + ".. std_req:: Duplicate one\n   :id: std_req__dup__one\n\n"
    + "   Alpha variant of the duplicated requirement.\n"
)


def _guide_rst() -> str:
    sections = "".join(
        f"Topic {n}\n{'-' * (6 + len(str(n)))}\n\n"
        f"Section {n} explains how the watchdog supervises task {n} deadlines.\n\n"
        for n in range(1, 6)
    )
    return (
        SPDX_APACHE
        + SYNTHETIC_RST
        + "Guide\n=====\n\n"
        + sections
        + "Shared\n------\n\n"
        + SHARED
        + "\n\n"
        + "Repeat A\n--------\n\n"
        + REPEATED
        + "\n\n"
        + "Repeat B\n--------\n\n"
        + REPEATED
        + "\n"
    )


BUILD_MD = (
    "<!-- SPDX-License-Identifier: Apache-2.0 -->\n<!-- SYNTHETIC — not S-CORE guidance -->\n\n"
    "# Building the documentation\n\n"
    "Run the documentation build locally with bazel before opening a pull request.\n\n"
    "```sh\nbazel run //:docs\n```\n"
)

BETA_RST = (
    SPDX_APACHE
    + SYNTHETIC_RST
    + "Beta\n====\n\n"
    + "Shared\n------\n\n"
    + SHARED
    + "\n\n"
    + "Notes\n-----\n\n"
    + "The beta watchdog note mentions deadlines once.\n\n"
    + ".. std_req:: Duplicate one\n   :id: std_req__dup__one\n\n"
    + "   Beta variant of the duplicated requirement.\n"
)


def export_json() -> str:
    needs = {
        "feat_req__alpha__short": {
            "id": "feat_req__alpha__short",
            "type": "feat_req",
            "title": "Short requirement",
            "docname": "reqs",
            "satisfies": ["feat_req__alpha__long"],
        },
        "feat_req__alpha__long": {
            "id": "feat_req__alpha__long",
            "type": "feat_req",
            "title": "Long requirement",
            "docname": "reqs",
        },
        "feat_req__export_only": {
            "id": "feat_req__export_only",
            "type": "feat_req",
            "title": "Only in the export",
            "docname": "reqs",
        },
    }
    return json.dumps({"current_version": "1", "versions": {"1": {"needs": needs}}})


def search_sources() -> list[SourceSpec]:
    export = export_json()
    return [
        SourceSpec(
            "alpha",
            {"docs/reqs.rst": REQS_RST, "docs/guide.rst": _guide_rst(), "docs/build.md": BUILD_MD},
            revision="a" * 40,
        ),
        SourceSpec(
            "alpha-needs",
            {"needs.json": export},
            revision=hashlib.sha256(export.encode()).hexdigest(),
            kind="needs-export",
            required=False,
            associated_source="alpha",
            docs_root="docs",
        ),
        SourceSpec("beta", {"docs/beta.rst": BETA_RST}, revision="b" * 40),
    ]


@dataclass
class SearchFixture:
    env: SnapshotEnv
    provider: FakeEmbeddingProvider
    snapshot_id: str

    @property
    def data(self) -> Path:
        return self.env.data

    def config(self, **retrieval: Any) -> AppConfig:
        return AppConfig(data_dir=self.env.data, retrieval=retrieval or {})  # type: ignore[arg-type]

    def service(
        self, provider: FakeEmbeddingProvider | None = None, **retrieval: Any
    ) -> SearchService:
        from score_docs_assistant.retrieval.service import SearchService

        return SearchService(
            config=self.config(**retrieval),
            provider=provider if provider is not None else self.provider,
        )


def make_search_fixture(
    tmp_path: Path, sources: list[SourceSpec] | None = None, *, lexical_only: bool = False
) -> SearchFixture:
    env = make_env(tmp_path, sources if sources is not None else search_sources())
    provider = FakeEmbeddingProvider()
    snapshot_id = build(env, provider, lexical_only=lexical_only).snapshot_id
    activate(env, snapshot_id, runtime=provider)
    return SearchFixture(env=env, provider=provider, snapshot_id=snapshot_id)
