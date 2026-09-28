"""ReadinessService: cached, bounded-probe capability computation (FR-009, data-model.md).

Uses `OllamaRuntime`, `CorpusProbe`, and `lock.py` directly — it does not import
`diagnostics/checks.py` (tasks.md Phase Dependencies note).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime

from score_docs_assistant.config.schema import AppConfig
from score_docs_assistant.domain.errors import (
    RuntimeIncompatible,
    RuntimeTimeout,
    RuntimeUnreachable,
)
from score_docs_assistant.domain.models import ModelProfile
from score_docs_assistant.domain.readiness import Capability, CapabilityState, Readiness, ReasonCode
from score_docs_assistant.models.lock import compare_role, read_lock
from score_docs_assistant.models.runtime import ModelRuntime, normalize_tag
from score_docs_assistant.storage.corpus_probe import CorpusProbe, CorpusState


def _state(reasons: list[ReasonCode]) -> CapabilityState:
    return CapabilityState(available=not reasons, reasons=reasons)


class ReadinessService:
    def __init__(
        self,
        *,
        config: AppConfig,
        runtime: ModelRuntime,
        corpus_probe: CorpusProbe,
        profile: ModelProfile,
        cache_seconds: float | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = config
        self._runtime = runtime
        self._corpus_probe = corpus_probe
        self._profile = profile
        self._cache_seconds = (
            cache_seconds
            if cache_seconds is not None
            else config.diagnostics.readiness_cache_seconds
        )
        self._clock = clock
        self._cached: Readiness | None = None
        self._cached_at: float | None = None

    def get(self) -> Readiness:
        now = self._clock()
        if (
            self._cached is not None
            and self._cached_at is not None
            and (now - self._cached_at) < self._cache_seconds
        ):
            return self._cached
        readiness = self._compute()
        self._cached = readiness
        self._cached_at = now
        return readiness

    def _compute(self) -> Readiness:
        corpus_state = self._corpus_probe.probe()
        corpus_reasons: list[ReasonCode] = []
        if corpus_state == CorpusState.ABSENT:
            corpus_reasons.append(ReasonCode.CORPUS_MISSING)
        elif corpus_state == CorpusState.INCOMPATIBLE:
            corpus_reasons.append(ReasonCode.CORPUS_INCOMPATIBLE)

        search_state = _state(corpus_reasons)

        chat_reasons: list[ReasonCode] = list(corpus_reasons)
        try:
            installed = self._runtime.list_models()
        except RuntimeUnreachable:
            installed = []
            chat_reasons.append(ReasonCode.RUNTIME_UNREACHABLE)
        except RuntimeTimeout:
            installed = []
            chat_reasons.append(ReasonCode.RUNTIME_UNREACHABLE)
        except RuntimeIncompatible:
            installed = []
            chat_reasons.append(ReasonCode.RUNTIME_INCOMPATIBLE)
        else:
            lock = read_lock(self._config.data_dir / "model-lock.json")
            generation_model = self._profile.model_for_role("generation")
            tag = normalize_tag(generation_model.tag)
            match = next((m for m in installed if m.tag == tag), None)
            if match is None:
                chat_reasons.append(ReasonCode.GENERATION_MODEL_MISSING)
            elif compare_role(lock, "generation", installed) == "mismatch":
                chat_reasons.append(ReasonCode.MODEL_IDENTITY_MISMATCH)

        if corpus_state == CorpusState.COMPATIBLE:
            # Search arrives in F004 and answers in F005; a compatible corpus alone must not make
            # either capability look available (research R11, docs/ASSUMPTIONS.md A-022).
            search_state = _state([ReasonCode.NOT_IMPLEMENTED])
            chat_reasons.append(ReasonCode.NOT_IMPLEMENTED)
        chat_state = _state(chat_reasons)
        compare_state = _state([ReasonCode.NOT_IMPLEMENTED])

        return Readiness(
            capabilities={
                Capability.SEARCH: search_state,
                Capability.CHAT: chat_state,
                Capability.COMPARE: compare_state,
            },
            checked_at=datetime.now(UTC),
        )
