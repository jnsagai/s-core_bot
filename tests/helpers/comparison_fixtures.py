"""Two fixture snapshots with controlled differences for F007 tests (mocked providers).

Every source text carries a `SYNTHETIC — not S-CORE guidance` marker. The left snapshot is the
"older" one; the right snapshot is active. Differences, by design:

- docs/inspection.rst: changed (two reviewers → three reviewers)
- docs/stable.rst: unchanged
- docs/policy.rst: conflicting guidance (release manager writes notes → must not write them)
- docs/checklist.rst: only on the right (same source present on both sides)
- source `platform`: only on the right
- requirements: feat_req__cmp__same unchanged, feat_req__cmp__edit changed, feat_req__cmp__new
  right-only, feat_req__cmp__plat right-only in a right-only source
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from score_docs_assistant.config.schema import AppConfig
from tests.helpers.build import build
from tests.helpers.fake_embedding import FakeEmbeddingProvider
from tests.helpers.fake_generation import LOCKED_GENERATION_DIGEST, FakeGenerationProvider
from tests.helpers.lifecycle import activate
from tests.helpers.snapshot_env import (
    SPDX_APACHE,
    SYNTHETIC_RST,
    SourceSpec,
    make_env,
    write_model_lock,
)

if TYPE_CHECKING:
    from score_docs_assistant.comparison.service import ComparisonService
    from score_docs_assistant.domain.comparison import ComparisonResult

LEFT_REV, RIGHT_REV, PLATFORM_REV = "1" * 40, "2" * 40, "3" * 40

STABLE = "The documentation build runs with bazel and publishes the generated site locally."
INSPECTION_LEFT = "Inspections of work products shall be performed by two independent reviewers."
INSPECTION_RIGHT = "Inspections of work products shall be performed by three independent reviewers."
POLICY_LEFT = "Release notes shall be written by the release manager before each release."
POLICY_RIGHT = "Release notes shall not be written by the release manager; the team writes them."
CHECKLIST = "The inspection checklist lists the entry criteria that each review must confirm."
PLATFORM = "The platform overview describes how the orchestrator schedules the gateway."


def _doc(title: str, body: str) -> str:
    return SPDX_APACHE + SYNTHETIC_RST + f"{title}\n{'=' * len(title)}\n\n{body}\n"


def _reqs(edit_title: str, edit_body: str, *, new: bool) -> str:
    text = (
        SPDX_APACHE
        + SYNTHETIC_RST
        + "Requirements\n============\n\n"
        + ".. feat_req:: Stable requirement\n   :id: feat_req__cmp__same\n   :status: valid\n\n"
        + "   The stable requirement defines the supervision interval.\n\n"
        + f".. feat_req:: {edit_title}\n   :id: feat_req__cmp__edit\n   :status: valid\n\n"
        + f"   {edit_body}\n"
    )
    if new:
        text += (
            "\n.. feat_req:: New requirement\n   :id: feat_req__cmp__new\n   :status: draft\n\n"
            "   The new requirement introduces the heartbeat check.\n"
        )
    return text


def left_sources() -> list[SourceSpec]:
    return [
        SourceSpec(
            "proc",
            {
                "docs/inspection.rst": _doc("Inspection", INSPECTION_LEFT),
                "docs/stable.rst": _doc("Build", STABLE),
                "docs/policy.rst": _doc("Release notes", POLICY_LEFT),
                "docs/reqs.rst": _reqs(
                    "Edited requirement", "The edited requirement allows 10 retries.", new=False
                ),
            },
            revision=LEFT_REV,
        )
    ]


def right_sources() -> list[SourceSpec]:
    return [
        SourceSpec(
            "proc",
            {
                "docs/inspection.rst": _doc("Inspection", INSPECTION_RIGHT),
                "docs/stable.rst": _doc("Build", STABLE),
                "docs/policy.rst": _doc("Release notes", POLICY_RIGHT),
                "docs/checklist.rst": _doc("Checklist", CHECKLIST),
                "docs/reqs.rst": _reqs(
                    "Edited requirement v2", "The edited requirement allows 3 retries.", new=True
                ),
            },
            revision=RIGHT_REV,
        ),
        SourceSpec(
            "platform",
            {
                "docs/overview.rst": _doc("Overview", PLATFORM)
                + "\n.. feat_req:: Platform requirement\n   :id: feat_req__cmp__plat\n"
                "   :status: valid\n\n   The platform requirement covers scheduling.\n"
            },
            revision=PLATFORM_REV,
        ),
    ]


@dataclass
class ComparisonFixture:
    data: Path
    left_id: str
    right_id: str
    provider: FakeEmbeddingProvider
    generator: FakeGenerationProvider = field(default_factory=FakeGenerationProvider)

    def config(self, **sections: Any) -> AppConfig:
        return AppConfig(data_dir=self.data, **sections)

    def service(
        self, generator: FakeGenerationProvider | None = None, **sections: Any
    ) -> ComparisonService:
        from score_docs_assistant.answers.service import AnswerService
        from score_docs_assistant.comparison.service import ComparisonService
        from score_docs_assistant.retrieval.service import SearchService

        config = self.config(**sections)
        search = SearchService(config=config, provider=self.provider)
        provider = generator if generator is not None else self.generator
        answers = AnswerService(config=config, search=search, provider=provider)
        return ComparisonService(config=config, search=search, answers=answers)

    def compare(
        self,
        question: str,
        *scripts: Any,
        service: ComparisonService | None = None,
        left: str | None = None,
        right: str | None = None,
    ) -> ComparisonResult:
        from score_docs_assistant.domain.comparison import ComparisonRequest

        if scripts:
            self.generator.outputs.extend(scripts)
        service = service or self.service()
        request = ComparisonRequest(
            question=question,
            left_snapshot_id=left or self.left_id,
            right_snapshot_id=right or self.right_id,
        )
        return asyncio.run(service.compare(request, request_id="t"))


def make_comparison_fixture(tmp_path: Path) -> ComparisonFixture:
    env = make_env(tmp_path, left_sources())
    provider = FakeEmbeddingProvider()
    left_id = build(env, provider).snapshot_id
    archive = env.data / "source-locks"
    archive.mkdir(exist_ok=True)
    shutil.copy(env.lock_path, archive / "left.json")
    env.write(right_sources())
    right_id = build(env, provider).snapshot_id
    activate(env, right_id, runtime=provider)
    write_model_lock(env.data, provider.digest, generation_digest=LOCKED_GENERATION_DIGEST)
    return ComparisonFixture(data=env.data, left_id=left_id, right_id=right_id, provider=provider)


# --- scripting helpers ---------------------------------------------------------------------------


def answer_citing_all(messages: list[dict[str, str]]) -> str:
    """A valid single-snapshot answer that cites every supplied excerpt (E1…)."""
    # At most 4 claims, like a real model held to the comparison side budget's schema.
    ids = re.findall(r'<excerpt id="(E\d+)"', messages[1]["content"])[:4]
    if not ids:
        return json.dumps({"status": "insufficient_evidence", "claims": []})
    return json.dumps(
        {
            "status": "answered",
            "claims": [
                {
                    "text": f"The excerpt {i} documents this.",
                    "kind": "documented",
                    "evidence_ids": [i],
                }
                for i in ids
            ],
        }
    )


def side_evidence(messages: list[dict[str, str]]) -> dict[str, str]:
    """L#/R# → excerpt text as shown in the comparison prompt."""
    user = messages[1]["content"]
    return {
        m.group(1): m.group(2).strip()
        for m in re.finditer(r'<excerpt id="([LR]\d+)"[^>]*>\n(.*?)\n</excerpt>', user, re.S)
    }


def find(evidence: dict[str, str], prefix: str, needle: str) -> str:
    for key, text in evidence.items():
        if key.startswith(prefix) and needle in text:
            return key
    raise AssertionError(f"no {prefix} excerpt containing {needle!r}: {evidence}")


def differences(*items: tuple[str, str, list[str], list[str]]) -> dict[str, Any]:
    return {
        "differences": [
            {"type": t, "statement": s, "left_evidence_ids": left, "right_evidence_ids": right}
            for t, s, left, right in items
        ]
    }
