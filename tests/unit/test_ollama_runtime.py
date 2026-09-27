"""OllamaRuntime against the fake transport (research.md R3)."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from score_docs_assistant.domain.errors import (
    RuntimeIncompatible,
    RuntimeTimeout,
    RuntimeUnreachable,
)
from score_docs_assistant.models.ollama import OllamaRuntime

FakeRuntime = Callable[[dict | None], httpx.Client]


def _runtime(fake_runtime: FakeRuntime, scenario: dict | None = None) -> OllamaRuntime:
    return OllamaRuntime("http://127.0.0.1:11434", client=fake_runtime(scenario))


def test_version_parses(fake_runtime: FakeRuntime) -> None:
    runtime = _runtime(fake_runtime, {"version": {"json": {"version": "0.34.0"}}})
    info = runtime.version()
    assert info.provider == "ollama"
    assert info.version == "0.34.0"


def test_list_models_parses_and_normalises_tag(fake_runtime: FakeRuntime) -> None:
    runtime = _runtime(
        fake_runtime,
        {
            "tags": {
                "json": {
                    "models": [
                        {
                            "name": "qwen3",
                            "digest": "sha256:abc123",
                            "size": 123456,
                            "details": {
                                "family": "qwen3",
                                "parameter_size": "4B",
                                "quantization_level": "Q4_K_M",
                            },
                        }
                    ]
                }
            }
        },
    )
    models = runtime.list_models()
    assert len(models) == 1
    assert models[0].tag == "qwen3:latest"
    assert models[0].digest == "sha256:abc123"
    assert models[0].family == "qwen3"
    assert models[0].is_remote is False


@pytest.mark.parametrize("remote_field", ["remote_model", "remote_host"])
def test_list_models_flags_remote_models(fake_runtime: FakeRuntime, remote_field: str) -> None:
    runtime = _runtime(
        fake_runtime,
        {
            "tags": {
                "json": {
                    "models": [
                        {
                            "name": "cloud-model:latest",
                            "digest": "sha256:def456",
                            "size": 1,
                            remote_field: "yes",
                        }
                    ]
                }
            }
        },
    )
    models = runtime.list_models()
    assert models[0].is_remote is True


def test_connect_refused_raises_runtime_unreachable(fake_runtime: FakeRuntime) -> None:
    runtime = _runtime(
        fake_runtime, {"version": {"raise": httpx.ConnectError("connection refused")}}
    )
    with pytest.raises(RuntimeUnreachable):
        runtime.version()


def test_timeout_raises_runtime_timeout(fake_runtime: FakeRuntime) -> None:
    runtime = _runtime(fake_runtime, {"version": {"raise": httpx.ConnectTimeout("timed out")}})
    with pytest.raises(RuntimeTimeout):
        runtime.version()


def test_non_json_response_raises_runtime_incompatible(fake_runtime: FakeRuntime) -> None:
    runtime = _runtime(fake_runtime, {"version": {"content": b"not json"}})
    with pytest.raises(RuntimeIncompatible):
        runtime.version()


def test_unexpected_shape_raises_runtime_incompatible(fake_runtime: FakeRuntime) -> None:
    runtime = _runtime(fake_runtime, {"version": {"json": {"unexpected": "shape"}}})
    with pytest.raises(RuntimeIncompatible):
        runtime.version()
