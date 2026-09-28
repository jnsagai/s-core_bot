"""SemanticStatusCache TTL and invalidation (FR-014, clarification Q3)."""

from __future__ import annotations

from score_docs_assistant.retrieval.status import SemanticStatusCache


def test_ttl_reuse_expiry_and_invalidate() -> None:
    now = [0.0]
    calls: list[str] = []
    cache = SemanticStatusCache(ttl_seconds=30, clock=lambda: now[0])

    def compute(label: str):  # type: ignore[no-untyped-def]
        def inner():  # type: ignore[no-untyped-def]
            calls.append(label)
            return ("enabled", "", [])

        return inner

    assert cache.get("s1", compute("a"))[0] == "enabled"
    now[0] = 29
    cache.get("s1", compute("b"))
    assert calls == ["a"]
    now[0] = 31
    cache.get("s1", compute("c"))
    assert calls == ["a", "c"]
    cache.get("s2", compute("d"))
    assert calls == ["a", "c", "d"]
    cache.invalidate("s1")
    cache.get("s1", compute("e"))
    assert calls[-1] == "e"
    assert cache.peek("s2") is not None and cache.peek("zz") is None


def test_zero_ttl_always_recomputes() -> None:
    calls: list[int] = []
    cache = SemanticStatusCache(ttl_seconds=0, clock=lambda: 5.0)
    for _ in range(3):
        cache.get("s", lambda: (calls.append(1), ("enabled", "", []))[1])  # type: ignore[func-returns-value]
    assert len(calls) == 3
