"""AnswerService over F004 fixture snapshots with fake providers (mocked)."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from score_docs_assistant.answers.service import AnswerService
from score_docs_assistant.config.schema import AppConfig
from score_docs_assistant.domain.answers import AnswerEnvelope, ChatRequest
from tests.helpers.fake_embedding import FakeEmbeddingProvider
from tests.helpers.fake_generation import LOCKED_GENERATION_DIGEST, FakeGenerationProvider
from tests.helpers.hostile_sources import hostile_sources
from tests.helpers.search import SearchFixture, make_search_fixture
from tests.helpers.snapshot_env import SourceSpec, write_model_lock


@dataclass
class AnswerFixture:
    search: SearchFixture
    generator: FakeGenerationProvider

    @property
    def data(self) -> Path:
        return self.search.data

    def config(self, **sections: Any) -> AppConfig:
        return AppConfig(data_dir=self.data, **sections)

    def service(
        self,
        generator: FakeGenerationProvider | None = None,
        embedder: FakeEmbeddingProvider | None = None,
        **sections: Any,
    ) -> AnswerService:
        from score_docs_assistant.retrieval.service import SearchService

        config = self.config(**sections)
        return AnswerService(
            config=config,
            search=SearchService(config=config, provider=embedder or self.search.provider),
            provider=generator if generator is not None else self.generator,
        )

    def ask(
        self, question: str, *scripts: Any, service: AnswerService | None = None, **kw: Any
    ) -> AnswerEnvelope:
        if scripts:
            self.generator.outputs.extend(scripts)
        service = service or self.service()
        return asyncio.run(service.answer(ChatRequest(question=question, **kw), request_id="t"))


def make_answer_fixture(tmp_path: Path, sources: list[SourceSpec] | None = None) -> AnswerFixture:
    search = make_search_fixture(tmp_path, sources)
    write_model_lock(
        search.data, search.provider.digest, generation_digest=LOCKED_GENERATION_DIGEST
    )
    return AnswerFixture(search=search, generator=FakeGenerationProvider())


def make_hostile_fixture(tmp_path: Path) -> AnswerFixture:
    return make_answer_fixture(tmp_path, hostile_sources())


def evidence_ids(messages: list[dict[str, str]]) -> dict[str, str]:
    """E# → excerpt text as shown in the prompt (for scripting realistic outputs)."""
    import re

    user = messages[-1]["content"] if messages[-1]["role"] == "user" else messages[1]["content"]
    return {
        m.group(1): m.group(2).strip()
        for m in re.finditer(r'<excerpt id="(E\d+)"[^>]*>\n(.*?)\n</excerpt>', user, re.S)
    }


def dumps(value: Any) -> str:
    return json.dumps(value)
