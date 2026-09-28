"""AnswerService: question → validated, cited answer envelope (FR-001–FR-021, research R1–R8).

Flow per request, under one deadline: validate the request → admission (one active generation,
bounded waiters) → retrieval on one pinned snapshot (F004) → model identity check → budgeted
prompt → generation → validation → at most one repair → otherwise extractive fallback. The unchecked
draft never leaves this module, and nothing here logs question, history or answer text.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any

from score_docs_assistant.answers.citations import SourceLinks, build_citations
from score_docs_assistant.answers.fallback import extractive_fallback
from score_docs_assistant.answers.policy import POLICY_VERSION, answer_schema
from score_docs_assistant.answers.prompt import (
    Prompt,
    build_prompt,
    retrieval_query,
    select_history,
)
from score_docs_assistant.answers.queue import GenerationQueue
from score_docs_assistant.answers.validate import ValidationOutcome, validate_draft
from score_docs_assistant.config.schema import AppConfig
from score_docs_assistant.domain.answers import (
    AnswerEnvelope,
    AnswerOrigin,
    AnswerStatus,
    ChatRequest,
    Claim,
    GenerationIdentity,
    RetrievalSummary,
)
from score_docs_assistant.domain.errors import GenerationError
from score_docs_assistant.domain.retrieval import SearchRequest, SearchResponse
from score_docs_assistant.models.lock import read_lock
from score_docs_assistant.models.runtime import GenerationProvider, normalize_tag
from score_docs_assistant.retrieval.query import valid_snapshot_id
from score_docs_assistant.retrieval.service import SearchService

Progress = Callable[[dict[str, Any]], Awaitable[None]]
MAX_REPAIR_ECHO = 4000
NO_ANSWER_LIMITATION = "The supplied evidence does not answer this question."


async def _no_progress(_event: dict[str, Any]) -> None:
    return None


class AnswerService:
    def __init__(
        self,
        *,
        config: AppConfig,
        search: SearchService,
        provider: GenerationProvider | None,
        queue: GenerationQueue | None = None,
    ) -> None:
        self._config = config
        self._search = search
        self._provider = provider
        self._queue = queue or GenerationQueue(config.limits.queued_generations)
        # Test seam: awaited after retrieval, before generation (snapshot-activation tests).
        self.after_retrieval: Callable[[], Awaitable[None]] | None = None

    @property
    def queue(self) -> GenerationQueue:
        return self._queue

    # --- request validation ------------------------------------------------------------------

    def _check_request(self, request: ChatRequest) -> None:
        limits = self._config.limits
        if request.response_language != "en":
            raise GenerationError(
                "UNSUPPORTED_LANGUAGE", "only response_language 'en' is supported"
            )
        question = request.question.strip()
        if not question or len(question) > limits.question_characters:
            raise GenerationError(
                "REQUEST_INVALID", f"question must be 1..{limits.question_characters} characters"
            )
        if len(request.history) > self._config.generation.history_turns:
            raise GenerationError(
                "REQUEST_INVALID",
                f"history is limited to {self._config.generation.history_turns} turns",
            )
        if sum(len(t.content) for t in request.history) > limits.history_characters:
            raise GenerationError(
                "REQUEST_INVALID", f"history exceeds {limits.history_characters} characters"
            )
        if request.snapshot_id is not None and not valid_snapshot_id(request.snapshot_id):
            raise GenerationError("REQUEST_INVALID", "snapshot_id has an invalid format")

    # --- identity --------------------------------------------------------------------------------

    async def _identity(self) -> GenerationIdentity:
        if self._provider is None:
            raise GenerationError(
                "GENERATION_UNAVAILABLE",
                "no generation runtime configured",
                reason="runtime_unreachable",
            )
        identity = await self._provider.identity()
        lock = read_lock(self._config.data_dir / "model-lock.json")
        entry = lock.entry_for_role("generation") if lock is not None else None
        if entry is None:
            raise GenerationError(
                "GENERATION_UNAVAILABLE",
                "the model lock has no generation model; run `score-assistant models pull`",
                reason="model_not_locked",
            )
        if (
            normalize_tag(entry.tag) != identity.name
            or entry.digest.removeprefix("sha256:") != identity.digest
        ):
            raise GenerationError(
                "GENERATION_UNAVAILABLE",
                f"installed {identity.name} ({identity.digest[:12]}…) differs from the model lock "
                f"({entry.digest.removeprefix('sha256:')[:12]}…); run `models pull` to requalify",
                reason="model_identity_mismatch",
            )
        return identity

    async def generation_available(self) -> tuple[bool, str | None]:
        """For readiness: (available, reason). Never generates."""
        try:
            await self._identity()
        except GenerationError as exc:
            return False, exc.reason
        return True, None

    # --- main flow -------------------------------------------------------------------------------

    async def answer(
        self,
        request: ChatRequest,
        *,
        request_id: str,
        progress: Progress | None = None,
    ) -> AnswerEnvelope:
        self._check_request(request)
        emit = progress or _no_progress
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._config.limits.request_deadline_seconds
        try:
            async with asyncio.timeout_at(deadline):
                return await self._answer(request, request_id, emit, deadline)
        except TimeoutError:
            raise GenerationError(
                "DEADLINE_EXCEEDED", "the answer did not finish within the request deadline"
            ) from None

    async def _answer(
        self, request: ChatRequest, request_id: str, emit: Progress, deadline: float
    ) -> AnswerEnvelope:
        timings: dict[str, float] = {}
        started = time.monotonic()

        async def on_queued(position: int) -> None:
            await emit({"stage": "queued", "position": position})

        async with self._queue.slot(on_queued):
            timings["queue"] = _ms(started)
            await emit({"stage": "searching"})
            mark = time.monotonic()
            question = request.question.strip()
            query = retrieval_query(
                question, request.history, self._config.limits.question_characters
            )
            search = await asyncio.to_thread(
                self._search.search,
                SearchRequest(
                    query=query,
                    snapshot_id=request.snapshot_id,
                    limit=self._config.generation.evidence_items,
                ),
            )
            timings["retrieval"] = _ms(mark)
            warnings = list(search.warnings)
            if self.after_retrieval is not None:
                await self.after_retrieval()

            if not search.results:
                return self._envelope(
                    request_id=request_id,
                    request=request,
                    search=search,
                    status="insufficient_evidence",
                    origin="no_evidence",
                    claims=[
                        Claim(
                            text="The selected snapshot contains no evidence for this question.",
                            kind="limitation",
                        )
                    ],
                    prompt=None,
                    identity=None,
                    warnings=warnings,
                    timings=timings,
                    started=started,
                )

            identity = await self._identity()
            history, history_warnings = select_history(
                request.history,
                search.snapshot_id,
                max_turns=self._config.generation.history_turns,
            )
            prompt = build_prompt(
                question,
                history,
                search.results,
                self._config.generation,
                self._config.runtime.context_tokens,
                self._config.runtime.output_tokens,
            )
            warnings += history_warnings + prompt.warnings
            if not prompt.evidence:
                warnings.append("evidence_budget: no excerpt fits the evidence budget")
                return self._envelope(
                    request_id=request_id,
                    request=request,
                    search=search,
                    status="insufficient_evidence",
                    origin="no_evidence",
                    claims=[
                        Claim(
                            text="No evidence excerpt fits the configured context budget.",
                            kind="limitation",
                        )
                    ],
                    prompt=None,
                    identity=None,
                    warnings=warnings,
                    timings=timings,
                    started=started,
                )

            await emit({"stage": "generating"})
            outcome, generation_ms, repair_ms, repaired = await self._generate_validated(
                prompt, deadline, emit
            )
            timings["generation"] = generation_ms
            timings["repair"] = repair_ms
            if outcome.ok:
                assert outcome.status is not None
                if repaired:
                    warnings.append("repaired: the first model output failed validation")
                status: AnswerStatus = outcome.status
                origin: AnswerOrigin = "model"
                claims = outcome.claims
                if status == "insufficient_evidence" and not any(
                    c.kind == "limitation" for c in claims
                ):
                    # A server-authored gap statement: it asserts nothing about S-CORE.
                    claims = [*claims, Claim(text=NO_ANSWER_LIMITATION, kind="limitation")]
            else:
                codes = sorted({e.split(":")[0] for e in outcome.errors})
                warnings.append(
                    "model_output_invalid: the model output failed validation "
                    f"({', '.join(codes)}); showing extractive excerpts"
                )
                status, origin = "partial", "extractive_fallback"
                claims = extractive_fallback(
                    prompt.evidence, self._config.generation.fallback_excerpts
                )
            return self._envelope(
                request_id=request_id,
                request=request,
                search=search,
                status=status,
                origin=origin,
                claims=claims,
                prompt=prompt,
                identity=identity,
                warnings=warnings,
                timings=timings,
                started=started,
            )

    async def _generate_validated(
        self, prompt: Prompt, deadline: float, emit: Progress
    ) -> tuple[ValidationOutcome, float, float, bool]:
        assert self._provider is not None
        generation = self._config.generation
        schema = answer_schema(generation.max_claims, generation.max_claim_characters)
        evidence = prompt.evidence_map()

        async def call(messages: list[dict[str, str]]) -> tuple[ValidationOutcome, str]:
            assert self._provider is not None
            result = await self._provider.generate(
                messages,
                schema=schema,
                temperature=generation.temperature,
                context_tokens=self._config.runtime.context_tokens,
                output_tokens=self._config.runtime.output_tokens,
            )
            await emit({"stage": "validating"})
            outcome = validate_draft(
                result.text,
                truncated=result.truncated,
                evidence=evidence,
                max_claims=generation.max_claims,
                max_claim_characters=generation.max_claim_characters,
            )
            return outcome, result.text

        mark = time.monotonic()
        outcome, raw = await call(prompt.messages)
        generation_ms = _ms(mark)
        remaining = deadline - asyncio.get_running_loop().time()
        if (
            outcome.ok
            or generation.repair_attempts < 1
            or remaining < generation.repair_min_seconds
        ):
            return outcome, generation_ms, 0.0, False
        await emit({"stage": "generating"})
        mark = time.monotonic()
        repair_messages = [
            *prompt.messages,
            {"role": "assistant", "content": raw[:MAX_REPAIR_ECHO]},
            {
                "role": "user",
                "content": "Your previous output failed these checks:\n- "
                + "\n- ".join(outcome.errors)
                + "\nReturn a corrected JSON object that follows all rules and the schema.",
            },
        ]
        repaired, _ = await call(repair_messages)
        return repaired, generation_ms, _ms(mark), repaired.ok

    def _envelope(
        self,
        *,
        request_id: str,
        request: ChatRequest,
        search: SearchResponse,
        status: AnswerStatus,
        origin: AnswerOrigin,
        claims: list[Claim],
        prompt: Prompt | None,
        identity: GenerationIdentity | None,
        warnings: list[str],
        timings: dict[str, float],
        started: float,
    ) -> AnswerEnvelope:
        evidence = prompt.evidence_map() if prompt is not None else {}
        links = SourceLinks.from_lock(self._config.data_dir / "source-lock.json")
        citations = build_citations(claims, evidence, links)
        timings["total"] = _ms(started)
        return AnswerEnvelope(
            request_id=request_id,
            status=status,
            origin=origin,
            question=request.question.strip(),
            claims=claims,
            limitations=[c.text for c in claims if c.kind == "limitation"],
            citations=citations,
            snapshot_id=search.snapshot_id,
            model=identity if origin != "no_evidence" else None,
            retrieval=RetrievalSummary(
                mode=search.mode,
                degraded_reason=search.degraded.reason if search.degraded else None,
                results=len(search.results),
                evidence_supplied=len(evidence),
                evidence_dropped=prompt.evidence_dropped if prompt is not None else 0,
            ),
            warnings=warnings,
            policy_version=POLICY_VERSION,
            timings_ms={k: round(v, 2) for k, v in timings.items()},
        )


def _ms(since: float) -> float:
    return (time.monotonic() - since) * 1000
