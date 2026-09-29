"""ComparisonService: one question, two explicitly chosen snapshots (FR-001–FR-016, research R1–R8).

Flow under one deadline: validate → model identity → pin both snapshots for the whole request →
one generation slot → the F005 answer flow per side → side-namespaced evidence → deterministic
differences (exact records, coverage) → one validated comparison step (≤ 1 repair, otherwise
deterministic differences only). No envelope ever mixes versions, absence is never reported as
removal, and nothing here logs question or answer text.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any

from score_docs_assistant.answers.citations import SourceLinks, citation_for
from score_docs_assistant.answers.injection import addresses_assistant
from score_docs_assistant.answers.prompt import EvidenceItem, escape
from score_docs_assistant.answers.service import AnswerService
from score_docs_assistant.comparison.coverage import missing_reason, reason_text, source_reason
from score_docs_assistant.comparison.metadata import snapshot_diff
from score_docs_assistant.comparison.policy import COMPARISON_POLICY_VERSION, comparison_schema
from score_docs_assistant.comparison.prompt import (
    ComparisonPrompt,
    build_comparison_prompt,
    order_side,
    relabel,
)
from score_docs_assistant.comparison.records import RecordPair, compare_records
from score_docs_assistant.comparison.validate import ComparisonOutcome, validate_comparison
from score_docs_assistant.config.schema import AppConfig
from score_docs_assistant.domain.answers import AnswerEnvelope, ChatRequest
from score_docs_assistant.domain.comparison import (
    ComparisonEvidence,
    ComparisonOrigin,
    ComparisonRequest,
    ComparisonResult,
    CoverageReason,
    Difference,
    MissingSide,
    SnapshotDiff,
)
from score_docs_assistant.domain.errors import GenerationError
from score_docs_assistant.domain.retrieval import EvidenceResult
from score_docs_assistant.domain.snapshots import SnapshotManifest
from score_docs_assistant.retrieval.query import excerpt, valid_snapshot_id
from score_docs_assistant.retrieval.service import SearchService
from score_docs_assistant.storage.snapshot_store import FileSnapshotHandle

Progress = Callable[[dict[str, Any]], Awaitable[None]]
MAX_REPAIR_ECHO = 4000
# Generic guidance per validation code, appended to the single repair request.
REPAIR_HINTS = {
    "DELETION_CLAIM": "Describe both sides neutrally: instead of 'the right adds X' write "
    "'only the right excerpts state X'.",
    "MISSING_SIDE_EVIDENCE": "When only one side's excerpts address a point, use type "
    "not_established and cite only that side.",
    "ONE_SIDE_ONLY": "A not_established difference cites exactly one side; if both sides "
    "address the point, use changed, unchanged or conflicting.",
    "CHANGED_WITHOUT_DIFFERENCE": "The cited excerpts are identical on both sides; use unchanged, "
    "or cite the excerpts that actually differ.",
}


async def _no_progress(_event: dict[str, Any]) -> None:
    return None


def _ms(since: float) -> float:
    return round((time.monotonic() - since) * 1000, 2)


def check_pair(left: str, right: str) -> None:
    if not valid_snapshot_id(left) or not valid_snapshot_id(right):
        raise GenerationError("REQUEST_INVALID", "snapshot IDs have an invalid format")
    if left == right:
        raise GenerationError("REQUEST_INVALID", "a comparison needs two different snapshots")


class _Side:
    """Evidence items of one side and their L/R numbering."""

    def __init__(self, prefix: str) -> None:
        self.prefix = prefix
        self.items: list[EvidenceItem] = []

    def add(self, result: EvidenceResult) -> str:
        for item in self.items:
            if item.result.chunk_id == result.chunk_id:
                return item.evidence_id
        evidence_id = f"{self.prefix}{len(self.items) + 1}"
        self.items.append(
            EvidenceItem(
                evidence_id=evidence_id,
                result=result,
                shown=escape(result.excerpt),
                tokens=0,
                suspicious=addresses_assistant(result.excerpt),
            )
        )
        return evidence_id


class ComparisonService:
    def __init__(self, *, config: AppConfig, search: SearchService, answers: AnswerService) -> None:
        self._config = config
        self._search = search
        self._answers = answers
        # Test seam: awaited after both side answers, while both snapshots are pinned.
        self.after_answers: Callable[[], Awaitable[None]] | None = None

    # --- metadata only (no model) --------------------------------------------------------------

    def diff(self, left: str, right: str) -> SnapshotDiff:
        check_pair(left, right)
        with self._search.pinned(left) as a, self._search.pinned(right) as b:
            return snapshot_diff(a.manifest, b.manifest)

    async def available(self) -> tuple[bool, str | None]:
        return await self._answers.generation_available()

    # --- comparison ----------------------------------------------------------------------------

    def _check(self, request: ComparisonRequest) -> str:
        if request.response_language != "en":
            raise GenerationError(
                "UNSUPPORTED_LANGUAGE", "only response_language 'en' is supported"
            )
        question = request.question.strip()
        limit = self._config.limits.question_characters
        if not question or len(question) > limit:
            raise GenerationError("REQUEST_INVALID", f"question must be 1..{limit} characters")
        check_pair(request.left_snapshot_id, request.right_snapshot_id)
        return question

    async def compare(
        self,
        request: ComparisonRequest,
        *,
        request_id: str,
        progress: Progress | None = None,
    ) -> ComparisonResult:
        question = self._check(request)
        emit = progress or _no_progress
        identity = await self._answers.identity()
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._config.comparison.deadline_seconds
        try:
            async with asyncio.timeout_at(deadline):
                with (
                    self._search.pinned(request.left_snapshot_id) as left,
                    self._search.pinned(request.right_snapshot_id) as right,
                ):
                    return await self._compare(
                        question, request_id, left, right, identity, emit, deadline
                    )
        except TimeoutError:
            raise GenerationError(
                "DEADLINE_EXCEEDED", "the comparison did not finish within its deadline"
            ) from None

    async def _compare(
        self,
        question: str,
        request_id: str,
        left: FileSnapshotHandle,
        right: FileSnapshotHandle,
        identity: Any,
        emit: Progress,
        deadline: float,
    ) -> ComparisonResult:
        started = time.monotonic()
        timings: dict[str, float] = {}

        async def on_queued(position: int) -> None:
            await emit({"stage": "queued", "position": position})

        async with self._answers.queue.slot(on_queued):
            timings["queue"] = _ms(started)
            envelopes: dict[str, AnswerEnvelope] = {}
            items: dict[str, list[EvidenceItem]] = {}
            for side, handle in (("left", left), ("right", right)):

                async def side_emit(event: dict[str, Any], side: str = side) -> None:
                    await emit({**event, "side": side})

                mark = time.monotonic()
                envelopes[side], items[side] = await self._answers.answer_in_slot(
                    ChatRequest(question=question, snapshot_id=handle.snapshot_id),
                    request_id=request_id,
                    deadline=deadline,
                    progress=side_emit,
                )
                timings[side] = _ms(mark)
            if self.after_answers is not None:
                await self.after_answers()

            per_side = self._config.comparison.evidence_items_per_side
            ordered = {
                side: relabel(
                    order_side(
                        items[side],
                        {c.evidence_id for c in envelopes[side].citations},
                        per_side,
                    ),
                    "L" if side == "left" else "R",
                )
                for side in ("left", "right")
            }
            prompt = build_comparison_prompt(
                question,
                left.snapshot_id,
                right.snapshot_id,
                ordered["left"],
                ordered["right"],
                evidence_tokens=self._config.generation.evidence_tokens,
                context_tokens=self._config.runtime.context_tokens,
                output_tokens=self._config.runtime.output_tokens,
            )
            sides = {"left": _Side("L"), "right": _Side("R")}
            sides["left"].items = list(prompt.left)
            sides["right"].items = list(prompt.right)
            warnings = list(prompt.warnings)

            pairs = await asyncio.to_thread(self._record_pairs, question, left, right)
            differences = self._coverage_differences(prompt)
            differences += self._record_differences(pairs, sides, left, right)

            origin: ComparisonOrigin = "deterministic_only"
            if prompt.left and prompt.right:
                await emit({"stage": "comparing"})
                mark = time.monotonic()
                outcome, repaired = await self._generate(prompt, deadline)
                timings["comparison"] = _ms(mark)
                codes = sorted({e.split(":")[0] for e in outcome.errors})
                if outcome.ok:
                    origin = "model"
                    if repaired:
                        warnings.append("repaired: the first comparison output failed validation")
                    differences += self._model_differences(outcome, prompt, left, right)
                elif outcome.structural and outcome.differences:
                    # After the repair, keep only differences that passed every check themselves.
                    origin = "model"
                    warnings.append(
                        f"comparison_differences_dropped: {outcome.rejected} model difference(s) "
                        f"failed validation ({', '.join(codes)}) and are not shown"
                    )
                    differences += self._model_differences(outcome, prompt, left, right)
                else:
                    warnings.append(
                        "comparison_output_invalid: the model output failed validation "
                        f"({', '.join(codes)}); showing deterministic differences only"
                    )

            links = SourceLinks.for_data_dir(self._config.data_dir)
            evidence = ComparisonEvidence(
                left=[citation_for(i.evidence_id, i, links) for i in sides["left"].items],
                right=[citation_for(i.evidence_id, i, links) for i in sides["right"].items],
            )
            timings["total"] = _ms(started)
            return ComparisonResult(
                request_id=request_id,
                question=question,
                left=envelopes["left"],
                right=envelopes["right"],
                differences=differences,
                evidence=evidence,
                snapshots=snapshot_diff(left.manifest, right.manifest),
                model=identity,
                origin=origin,
                warnings=warnings,
                policy_version=COMPARISON_POLICY_VERSION,
                timings_ms=timings,
            )

    # --- model step ----------------------------------------------------------------------------

    async def _generate(
        self, prompt: ComparisonPrompt, deadline: float
    ) -> tuple[ComparisonOutcome, bool]:
        generation = self._config.generation
        comparison = self._config.comparison
        schema = comparison_schema(comparison.max_differences, comparison.max_statement_characters)
        evidence = prompt.evidence_map()

        async def call(messages: list[dict[str, str]]) -> tuple[ComparisonOutcome, str]:
            result = await self._answers.generate_json(messages, schema)
            outcome = validate_comparison(
                result.text,
                truncated=result.truncated,
                evidence=evidence,
                max_differences=comparison.max_differences,
                max_statement_characters=comparison.max_statement_characters,
            )
            return outcome, result.text

        outcome, raw = await call(prompt.messages)
        remaining = deadline - asyncio.get_running_loop().time()
        if (
            outcome.ok
            or generation.repair_attempts < 1
            or remaining < generation.repair_min_seconds
        ):
            return outcome, False
        repair = [
            *prompt.messages,
            {"role": "assistant", "content": raw[:MAX_REPAIR_ECHO]},
            {
                "role": "user",
                "content": "Your previous output failed these checks:\n- "
                + "\n- ".join(outcome.errors)
                + "".join(
                    f"\n{hint}"
                    for code, hint in REPAIR_HINTS.items()
                    if any(e.startswith(code) for e in outcome.errors)
                )
                + "\nReturn a corrected JSON object that follows all rules and the schema.",
            },
        ]
        repaired, _ = await call(repair)
        return repaired, repaired.ok

    def _model_differences(
        self,
        outcome: ComparisonOutcome,
        prompt: ComparisonPrompt,
        left: FileSnapshotHandle,
        right: FileSnapshotHandle,
    ) -> list[Difference]:
        evidence = prompt.evidence_map()
        out: list[Difference] = []
        for d in outcome.differences:
            if d.type != "not_established":
                out.append(
                    Difference(
                        type=d.type,
                        statement=d.statement,
                        left_evidence_ids=d.left_evidence_ids,
                        right_evidence_ids=d.right_evidence_ids,
                        origin="model",
                    )
                )
                continue
            missing: MissingSide = "right" if d.left_evidence_ids else "left"
            present_ids = d.left_evidence_ids or d.right_evidence_ids
            sources = sorted({evidence[e].result.source_id for e in present_ids})
            manifest = right.manifest if missing == "right" else left.manifest
            reason = missing_reason(manifest, sources, "not_retrieved")
            out.append(
                Difference(
                    type="not_established",
                    statement=d.statement,
                    left_evidence_ids=d.left_evidence_ids,
                    right_evidence_ids=d.right_evidence_ids,
                    origin="model",
                    coverage_reason=reason,
                    missing_side=missing,
                )
            )
        return out

    # --- deterministic differences -------------------------------------------------------------

    @staticmethod
    def _coverage_differences(prompt: ComparisonPrompt) -> list[Difference]:
        empty = [
            side for side, items in (("left", prompt.left), ("right", prompt.right)) if not items
        ]
        if not empty:
            return []
        missing: MissingSide = "both" if len(empty) == 2 else empty[0]  # type: ignore[assignment]
        text = (
            "Neither snapshot returned evidence for this question; nothing can be compared."
            if missing == "both"
            else f"The {missing} snapshot returned no evidence for this question; the other "
            "side's answer cannot be compared with it."
        )
        return [
            Difference(
                type="not_established",
                statement=text,
                origin="coverage",
                coverage_reason="no_evidence",
                missing_side=missing,
            )
        ]

    def _record_pairs(
        self, question: str, left: FileSnapshotHandle, right: FileSnapshotHandle
    ) -> list[RecordPair]:
        return compare_records(
            question,
            (self._search.entity_index(left), left.corpus()),
            (self._search.entity_index(right), right.corpus()),
        )

    def _record_evidence(
        self, handle: FileSnapshotHandle, chunk_id: str | None
    ) -> EvidenceResult | None:
        if chunk_id is None:
            return None
        record = self._search.citation(handle.snapshot_id, chunk_id)
        shown, truncated = excerpt(record.text, self._config.retrieval.excerpt_characters)
        return EvidenceResult(
            rank=0,
            chunk_id=record.chunk_id,
            snapshot_id=record.snapshot_id,
            source_id=record.source_id,
            revision=record.revision,
            revision_status=record.revision_status,
            path=record.path,
            origin_path=record.origin_path,
            heading_path=record.heading_path,
            line_start=record.line_start,
            line_end=record.line_end,
            kind=record.kind,
            entity_keys=record.entity_keys,
            excerpt=shown,
            truncated=truncated,
            matched_by=["exact"],
        )

    def _record_differences(
        self,
        pairs: list[RecordPair],
        sides: dict[str, _Side],
        left: FileSnapshotHandle,
        right: FileSnapshotHandle,
    ) -> list[Difference]:
        out: list[Difference] = []
        for pair in pairs:
            a = self._record_evidence(left, pair.left.chunk_id) if pair.left else None
            b = self._record_evidence(right, pair.right.chunk_id) if pair.right else None
            left_ids = [sides["left"].add(a)] if a else []
            right_ids = [sides["right"].add(b)] if b else []
            moved = " Its file location differs." if pair.moved else ""
            if pair.verdict in ("unchanged", "changed") and a and b:
                statement = (
                    f"{pair.need_id} has the same type, title, status, options and text in both "
                    f"snapshots.{moved}"
                    if pair.verdict == "unchanged"
                    else f"{pair.need_id} differs between the snapshots in: "
                    f"{', '.join(pair.changed_fields)}.{moved}"
                )
                out.append(
                    Difference(
                        type=pair.verdict,
                        statement=statement,
                        left_evidence_ids=left_ids,
                        right_evidence_ids=right_ids,
                        origin="exact_record",
                    )
                )
                continue
            reason: CoverageReason
            missing: MissingSide
            if pair.verdict in ("unchanged", "changed"):
                reason = "record_without_excerpt"
                missing = "both" if not a and not b else ("left" if not a else "right")
                left_ids = [] if missing in ("left", "both") else left_ids
                right_ids = [] if missing in ("right", "both") else right_ids
                where = "either snapshot" if missing == "both" else f"the {missing} snapshot"
                statement = (
                    f"{pair.need_id} is a record in both snapshots, but it has no excerpt in "
                    f"{where}, so its content cannot be compared."
                )
            else:
                present = pair.left if pair.verdict == "left_only" else pair.right
                assert present is not None
                missing = "right" if pair.verdict == "left_only" else "left"
                manifest: SnapshotManifest = right.manifest if missing == "right" else left.manifest
                reason = source_reason(manifest, present.source_id) or "record_not_found"
                statement = (
                    f"{pair.need_id} is in the {'left' if missing == 'right' else 'right'} "
                    f"snapshot's records; {reason_text(reason, missing)}. This does not show "
                    "that it changed or disappeared."
                )
            out.append(
                Difference(
                    type="not_established",
                    statement=statement,
                    left_evidence_ids=left_ids,
                    right_evidence_ids=right_ids,
                    origin="exact_record",
                    coverage_reason=reason,
                    missing_side=missing,
                )
            )
        return out
