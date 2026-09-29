"""Throwaway hostile snapshot with fake providers (F008 FR-010; mocked)."""

from __future__ import annotations

import asyncio
from pathlib import Path

from score_docs_assistant.config.schema import AppConfig
from score_docs_assistant.qualification.adversarial import (
    hostile_snapshot,
    load_cases,
    run_adversarial,
)
from tests.helpers.fake_embedding import FakeEmbeddingProvider
from tests.helpers.fake_generation import LOCKED_GENERATION_DIGEST, FakeGenerationProvider, answer
from tests.helpers.snapshot_env import PROFILES, write_model_lock

REPO = Path(__file__).parent.parent.parent


def test_builds_throwaway_snapshot_and_judges(tmp_path: Path) -> None:
    embedder = FakeEmbeddingProvider()
    write_model_lock(tmp_path, embedder.digest, generation_digest=LOCKED_GENERATION_DIGEST)
    cases = load_cases(REPO / "eval" / "hostile" / "cases.yaml")
    assert len(cases.cases) >= 10
    bad = answer(
        "answered", ("To finish, run rm -rf /tmp/score as the notice says.", "documented", ["E1"])
    )
    generator = FakeGenerationProvider(outputs=[bad] + [answer("insufficient_evidence")] * 20)
    work: list[Path] = []
    with hostile_snapshot(
        REPO / "eval" / "hostile" / "docs",
        model_lock=tmp_path / "model-lock.json",
        profiles_dir=PROFILES,
        embedder=embedder,
        base_config=AppConfig(data_dir=tmp_path / "unused"),
    ) as config:
        work.append(config.data_dir)
        assert (config.data_dir / "catalog.sqlite").is_file()
        report = asyncio.run(
            run_adversarial(
                cases, config=config, embedder=embedder, generator=generator, documents=8
            )
        )
    assert not work[0].exists()  # cleaned up
    assert not (tmp_path / "unused").exists()  # the configured data dir is never touched
    assert report.cases == len(cases.cases)
    first = report.judgements[0]
    if first.origin == "model":  # validation may reject the advice claim → fallback, also fine
        assert any(
            f.startswith("followed_instruction") or f == "command_as_advice" for f in first.failures
        )
    assert report.utility["total"] == 1
