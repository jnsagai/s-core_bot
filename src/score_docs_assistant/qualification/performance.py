"""Performance qualification (F008 FR-013, FR-014, master §13.4, research R7).

Warm and cold are measured separately; cold samples unload both models through the local runtime
first (and record whether the unload was verified). Budgets are compared with the master targets;
fewer than 50 warm samples is a failure ("insufficient sample"), never a pass.
"""

from __future__ import annotations

import asyncio
import resource
import shutil
import subprocess
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict

from score_docs_assistant.answers.service import AnswerService
from score_docs_assistant.domain.answers import ChatRequest
from score_docs_assistant.domain.retrieval import SearchRequest
from score_docs_assistant.retrieval.service import SearchService

MIN_SAMPLES = 50
BUDGETS_MS: dict[str, tuple[str, float]] = {
    # name → (statistic, budget)
    "lexical_retrieval": ("p95", 500.0),
    "hybrid_retrieval_warm": ("p95", 2000.0),
    "first_progress_warm": ("p95", 1000.0),
    "answer_warm": ("p95", 30000.0),
    "cancellation_release": ("max", 2000.0),
}
_FORBID = ConfigDict(extra="forbid", frozen=True)


class Distribution(BaseModel):
    model_config = _FORBID

    samples: int
    p50: float | None
    p95: float | None
    max: float | None


class Budget(BaseModel):
    model_config = _FORBID

    name: str
    statistic: str
    target_ms: float
    measured_ms: float | None
    samples: int
    status: str  # pass | fail | fail (insufficient sample) | not run


class PerformanceReport(BaseModel):
    model_config = _FORBID

    created_at: datetime
    snapshot_id: str
    chunks: int | None
    model: dict[str, str | None]
    distributions: dict[str, Distribution]
    budgets: list[Budget]
    cold_unload_verified: bool | None
    memory: dict[str, Any]
    notes: list[str]


def percentile(values: Sequence[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return round(ordered[index], 2)


def distribution(values: Sequence[float]) -> Distribution:
    return Distribution(
        samples=len(values),
        p50=percentile(values, 0.5),
        p95=percentile(values, 0.95),
        max=round(max(values), 2) if values else None,
    )


def evaluate_budgets(distributions: dict[str, Distribution]) -> list[Budget]:
    budgets: list[Budget] = []
    for name, (statistic, target) in BUDGETS_MS.items():
        dist = distributions.get(name)
        if dist is None or dist.samples == 0:
            budgets.append(
                Budget(
                    name=name,
                    statistic=statistic,
                    target_ms=target,
                    measured_ms=None,
                    samples=0,
                    status="not run",
                )
            )
            continue
        measured = getattr(dist, statistic)
        needs_sample = name != "cancellation_release"
        if needs_sample and dist.samples < MIN_SAMPLES:
            status = "fail (insufficient sample)"
        else:
            status = "pass" if measured is not None and measured <= target else "fail"
        budgets.append(
            Budget(
                name=name,
                statistic=statistic,
                target_ms=target,
                measured_ms=measured,
                samples=dist.samples,
                status=status,
            )
        )
    return budgets


class OllamaControl:
    """Unload models and read loaded sizes through the local runtime API (loopback only)."""

    def __init__(self, base_url: str, models: Sequence[str]) -> None:
        self._base_url = base_url.rstrip("/")
        self._models = list(models)

    def unload(self) -> bool:
        with httpx.Client(base_url=self._base_url, timeout=30) as client:
            for model in self._models:
                client.post("/api/generate", json={"model": model, "keep_alive": 0})
                client.post("/api/embed", json={"model": model, "input": [], "keep_alive": 0})
            for _ in range(20):
                if not client.get("/api/ps").json().get("models"):
                    return True
                time.sleep(0.25)
        return False

    def loaded(self) -> list[dict[str, Any]]:
        with httpx.Client(base_url=self._base_url, timeout=10) as client:
            return [
                {"name": m.get("name"), "size_vram": m.get("size_vram"), "size": m.get("size")}
                for m in client.get("/api/ps").json().get("models", [])
            ]


def gpu_memory() -> dict[str, Any] | None:
    """Used/total GPU memory in MiB via nvidia-smi, or None when unavailable."""
    tool = shutil.which("nvidia-smi")
    if tool is None:
        return None
    try:
        out = (
            subprocess.run(  # noqa: S603 — fixed local tool, no shell
                [
                    tool,
                    "--query-gpu=name,memory.used,memory.total",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            )
            .stdout.strip()
            .splitlines()[0]
        )
    except (OSError, subprocess.SubprocessError, IndexError):
        return None
    name, used, total = (part.strip() for part in out.split(","))
    return {"gpu": name, "used_mib": int(used), "total_mib": int(total)}


async def measure(
    *,
    search: SearchService,
    answers: AnswerService,
    questions: Sequence[str],
    answers_n: int = MIN_SAMPLES,
    warmup: int = 3,
    cold_samples: int = 5,
    cancel_samples: int = 3,
    unload: Callable[[], bool] | None = None,
    loaded: Callable[[], list[dict[str, Any]]] | None = None,
    gpu: Callable[[], dict[str, Any] | None] = gpu_memory,
) -> PerformanceReport:
    notes = [
        "first progress is timed in-process from the call to the first progress event (R7)",
        f"answers measured on the first {answers_n} distinct questions",
    ]
    unique = list(dict.fromkeys(q.strip() for q in questions if q.strip()))
    timings: dict[str, list[float]] = {
        k: []
        for k in (
            "lexical_retrieval",
            "hybrid_retrieval_warm",
            "first_progress_warm",
            "answer_warm",
            "hybrid_retrieval_cold",
            "first_progress_cold",
            "answer_cold",
            "cancellation_release",
        )
    }
    gpu_peak: dict[str, Any] | None = None

    def sample_gpu() -> None:
        nonlocal gpu_peak
        reading = gpu()
        if reading is not None and (gpu_peak is None or reading["used_mib"] > gpu_peak["used_mib"]):
            gpu_peak = reading

    async def timed_answer(question: str) -> tuple[float, float]:
        started = time.monotonic()
        first: list[float] = []

        async def progress(_event: dict[str, Any]) -> None:
            if not first:
                first.append((time.monotonic() - started) * 1000)

        await answers.answer(ChatRequest(question=question), request_id="perf", progress=progress)
        return (first[0] if first else float("nan")), (time.monotonic() - started) * 1000

    def timed_search(question: str, lexical: bool) -> float:
        started = time.monotonic()
        search.search(SearchRequest(query=question), force_lexical=lexical)
        return (time.monotonic() - started) * 1000

    snapshot_id = search.search(SearchRequest(query=unique[0])).snapshot_id if unique else ""
    for question in unique[:warmup]:
        timed_search(question, False)
        await timed_answer(question)
    for question in unique:
        timings["lexical_retrieval"].append(timed_search(question, True))
        timings["hybrid_retrieval_warm"].append(timed_search(question, False))
    for question in unique[:answers_n]:
        first, total = await timed_answer(question)
        timings["first_progress_warm"].append(first)
        timings["answer_warm"].append(total)
        sample_gpu()
    loaded_models = loaded() if loaded else []
    unload_ok: bool | None = None
    if unload is not None:
        results = []
        for question in unique[:cold_samples]:
            results.append(unload())
            timings["hybrid_retrieval_cold"].append(timed_search(question, False))
            unload()
            first, total = await timed_answer(question)
            timings["first_progress_cold"].append(first)
            timings["answer_cold"].append(total)
        unload_ok = all(results) if results else None
    else:
        notes.append("cold samples not run (no runtime control)")
    for question in unique[:cancel_samples]:
        generating = asyncio.Event()

        async def progress(event: dict[str, Any], generating: asyncio.Event = generating) -> None:
            if event.get("stage") == "generating":
                generating.set()

        task = asyncio.create_task(
            answers.answer(
                ChatRequest(question=question), request_id="perf-cancel", progress=progress
            )
        )
        try:
            await asyncio.wait_for(generating.wait(), 120)
        except TimeoutError:
            task.cancel()
            continue
        started = time.monotonic()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        while answers.queue.active:
            await asyncio.sleep(0.005)
        timings["cancellation_release"].append((time.monotonic() - started) * 1000)
    distributions = {name: distribution(values) for name, values in timings.items()}
    with search.pinned(snapshot_id or None) as handle:
        chunks = handle.manifest.counts.chunks
    identity = await answers.identity()
    return PerformanceReport(
        created_at=datetime.now(UTC),
        snapshot_id=snapshot_id,
        chunks=chunks,
        model={"name": identity.name, "digest": identity.digest},
        distributions=distributions,
        budgets=evaluate_budgets(distributions),
        cold_unload_verified=unload_ok,
        memory={
            "gpu_peak": gpu_peak or "not available",
            "runtime_loaded_models": loaded_models or "not available",
            "process_peak_rss_mib": round(
                resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1
            ),
        },
        notes=notes,
    )
