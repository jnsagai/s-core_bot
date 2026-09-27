"""ReadinessService: capability derivation table, cache TTL, and runtime stop/start reflection
(data-model.md, SC-007)."""

from __future__ import annotations

from datetime import datetime

from score_docs_assistant.config.schema import AppConfig
from score_docs_assistant.domain.errors import RuntimeUnreachable
from score_docs_assistant.domain.models import InstalledModel, ModelProfile, ProfileModel
from score_docs_assistant.domain.readiness import Capability, ReasonCode
from score_docs_assistant.readiness import ReadinessService
from score_docs_assistant.storage.corpus_probe import CorpusState


class _FakeProbe:
    def __init__(self, state: CorpusState) -> None:
        self.state = state

    def probe(self) -> CorpusState:
        return self.state


class _FakeRuntime:
    def __init__(self, models: list[InstalledModel] | None, exc: Exception | None = None) -> None:
        self._models = models
        self._exc = exc

    def version(self) -> object:
        raise NotImplementedError

    def list_models(self) -> list[InstalledModel]:
        if self._exc is not None:
            raise self._exc
        assert self._models is not None
        return self._models


def _profile() -> ModelProfile:
    return ModelProfile(
        name="local-small",
        models=[
            ProfileModel(role="generation", tag="gen:latest", size_source="t"),
            ProfileModel(role="embedding", tag="emb:latest", size_source="t"),
        ],
    )


def test_search_unavailable_when_corpus_absent() -> None:
    service = ReadinessService(
        config=AppConfig(),
        runtime=_FakeRuntime([]),
        corpus_probe=_FakeProbe(CorpusState.ABSENT),
        profile=_profile(),
        cache_seconds=0,
    )
    readiness = service.get()
    search = readiness.capabilities[Capability.SEARCH]
    assert search.available is False
    assert search.reasons == [ReasonCode.CORPUS_MISSING]
    assert readiness.ready is False


def test_chat_reasons_combine_corpus_and_model_missing() -> None:
    service = ReadinessService(
        config=AppConfig(),
        runtime=_FakeRuntime([]),
        corpus_probe=_FakeProbe(CorpusState.ABSENT),
        profile=_profile(),
        cache_seconds=0,
    )
    chat = service.get().capabilities[Capability.CHAT]
    assert chat.available is False
    assert ReasonCode.CORPUS_MISSING in chat.reasons
    assert ReasonCode.GENERATION_MODEL_MISSING in chat.reasons


def test_chat_reasons_runtime_unreachable() -> None:
    service = ReadinessService(
        config=AppConfig(),
        runtime=_FakeRuntime(None, exc=RuntimeUnreachable("http://x", "down")),
        corpus_probe=_FakeProbe(CorpusState.ABSENT),
        profile=_profile(),
        cache_seconds=0,
    )
    chat = service.get().capabilities[Capability.CHAT]
    assert ReasonCode.RUNTIME_UNREACHABLE in chat.reasons


def test_compare_always_not_implemented() -> None:
    service = ReadinessService(
        config=AppConfig(),
        runtime=_FakeRuntime([]),
        corpus_probe=_FakeProbe(CorpusState.ABSENT),
        profile=_profile(),
        cache_seconds=0,
    )
    compare = service.get().capabilities[Capability.COMPARE]
    assert compare.available is False
    assert compare.reasons == [ReasonCode.NOT_IMPLEMENTED]


def test_cache_ttl_honoured_and_runtime_change_reflected_after_expiry() -> None:
    runtime = _FakeRuntime([])
    probe = _FakeProbe(CorpusState.ABSENT)
    clock_value = {"t": 0.0}
    service = ReadinessService(
        config=AppConfig(),
        runtime=runtime,
        corpus_probe=probe,
        profile=_profile(),
        cache_seconds=2.0,
        clock=lambda: clock_value["t"],
    )
    first = service.get()

    runtime._exc = RuntimeUnreachable("http://x", "now down")
    clock_value["t"] = 1.0  # still within the 2s cache window
    cached = service.get()
    assert cached is first

    clock_value["t"] = 3.0  # cache expired; must reflect the new runtime state
    fresh = service.get()
    assert ReasonCode.RUNTIME_UNREACHABLE in fresh.capabilities[Capability.CHAT].reasons
    assert isinstance(fresh.checked_at, datetime)
