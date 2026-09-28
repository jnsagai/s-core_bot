"""Every check in contracts/cli.md order returns the specified status/code for its scenarios;
every warning/failure carries a next_action (FR-005, FR-006, FR-022, FR-024)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from score_docs_assistant.diagnostics import checks
from score_docs_assistant.diagnostics.hardware import DiskInfo, GpuInfo, HardwareInfo
from score_docs_assistant.domain.errors import (
    RuntimeIncompatible,
    RuntimeTimeout,
    RuntimeUnreachable,
)
from score_docs_assistant.domain.models import (
    InstalledModel,
    ModelLock,
    ModelLockEntry,
    ModelLockRuntime,
    ModelProfile,
    ProfileModel,
)
from score_docs_assistant.storage.corpus_probe import CorpusState


def _hw(**overrides: object) -> HardwareInfo:
    base = dict(
        os="Linux",
        arch="x86_64",
        cpu_count=8,
        ram_total_bytes=1000,
        ram_available_bytes=500,
        gpus=[],
        gpu_detection="not_detected",
        disk=DiskInfo(path="/", free_bytes=1_000_000, total_bytes=2_000_000, is_fallback=False),
    )
    base.update(overrides)
    return HardwareInfo(**base)  # type: ignore[arg-type]


class _RaisingRuntime:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def version(self) -> object:
        raise self._exc

    def list_models(self) -> object:
        raise self._exc


def _assert_next_action_when_required(result: object) -> None:
    if result.status in ("warning", "failure"):  # type: ignore[attr-defined]
        assert result.next_action, result  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("exc", "expected_code"),
    [
        (RuntimeUnreachable("http://x", "unreachable"), "RUNTIME_UNREACHABLE"),
        (RuntimeTimeout("http://x", "timed out"), "RUNTIME_TIMEOUT"),
        (RuntimeIncompatible("bad shape"), "RUNTIME_INCOMPATIBLE"),
    ],
)
def test_runtime_reachable_scenarios(exc: Exception, expected_code: str) -> None:
    result, info, installed = checks.check_runtime_reachable(_RaisingRuntime(exc), "http://x")
    assert result.status == "failure"
    assert result.code == expected_code
    assert info is None
    assert installed is None
    _assert_next_action_when_required(result)


def test_model_missing_present_remote() -> None:
    profile_model = ProfileModel(role="generation", tag="qwen3:4b-instruct", size_source="test")

    missing = checks.check_model("generation", profile_model, [], "local-small")
    assert missing.status == "warning"
    assert missing.code == "MODEL_MISSING"
    assert missing.next_action

    present = checks.check_model(
        "generation",
        profile_model,
        [InstalledModel(tag="qwen3:4b-instruct", digest="sha256:a", size_bytes=1)],
        "local-small",
    )
    assert present.status == "ok"
    assert present.code == "MODEL_PRESENT"

    remote = checks.check_model(
        "generation",
        profile_model,
        [InstalledModel(tag="qwen3:4b-instruct", digest="sha256:a", size_bytes=1, is_remote=True)],
        "local-small",
    )
    assert remote.status == "failure"
    assert remote.code == "MODEL_REMOTE"
    assert remote.next_action

    skipped = checks.check_model("generation", profile_model, None, "local-small")
    assert skipped.status == "skipped"
    assert skipped.code == "RUNTIME_REQUIRED"


def _profile() -> ModelProfile:
    return ModelProfile(
        name="local-small",
        models=[
            ProfileModel(role="generation", tag="gen:latest", size_source="t"),
            ProfileModel(role="embedding", tag="emb:latest", size_source="t"),
        ],
    )


def _lock(gen_digest: str, emb_digest: str) -> ModelLock:
    now = datetime.now(UTC)
    return ModelLock(
        profile="local-small",
        runtime=ModelLockRuntime(provider="ollama", version="0.34.0"),
        models=[
            ModelLockEntry(
                role="generation",
                tag="gen:latest",
                digest=gen_digest,
                size_bytes=1,
                acquired_at=now,
            ),
            ModelLockEntry(
                role="embedding", tag="emb:latest", digest=emb_digest, size_bytes=1, acquired_at=now
            ),
        ],
    )


def test_model_lock_match_mismatch_not_locked() -> None:
    installed = [
        InstalledModel(tag="gen:latest", digest="sha256:a", size_bytes=1),
        InstalledModel(tag="emb:latest", digest="sha256:b", size_bytes=1),
    ]

    matching = checks.check_model_lock(_profile(), installed, _lock("sha256:a", "sha256:b"))
    assert matching.status == "ok"
    assert matching.code == "MODEL_LOCK_MATCH"

    mismatched = checks.check_model_lock(_profile(), installed, _lock("sha256:WRONG", "sha256:b"))
    assert mismatched.status == "failure"
    assert mismatched.code == "MODEL_LOCK_MISMATCH"
    assert mismatched.next_action

    not_locked = checks.check_model_lock(_profile(), installed, None)
    assert not_locked.status == "warning"
    assert not_locked.code == "MODEL_NOT_LOCKED"
    assert not_locked.next_action


def test_data_dir_missing_and_not_writable(tmp_path: Path) -> None:
    missing = checks.check_data_dir_writable(tmp_path / "does-not-exist")
    assert missing.status == "warning"
    assert missing.code == "DATA_DIR_MISSING"
    assert missing.next_action

    unwritable = tmp_path / "locked"
    unwritable.mkdir(mode=0o000)
    try:
        result = checks.check_data_dir_writable(unwritable)
        assert result.status == "failure"
        assert result.code == "DATA_DIR_NOT_WRITABLE"
        assert result.next_action
    finally:
        unwritable.chmod(0o755)


def test_disk_low_warns(tmp_path: Path) -> None:
    result = checks.check_disk("disk.data", tmp_path, margin_bytes=2**62)
    assert result.status == "warning"
    assert result.code == "DISK_LOW"
    assert result.next_action


def test_gpu_not_detected() -> None:
    result = checks.check_gpu(_hw(gpu_detection="not_detected", gpus=[]))
    assert result.status == "info"
    assert result.code == "GPU_NOT_DETECTED"


def test_gpu_detected() -> None:
    result = checks.check_gpu(
        _hw(
            gpu_detection="detected",
            gpus=[GpuInfo(name="RTX", memory_total_mib=1, memory_free_mib=1)],
        )
    )
    assert result.status == "info"
    assert result.code == "GPU_DETECTED"


def test_corpus_absent_and_incompatible() -> None:
    class _Probe:
        def __init__(self, state: CorpusState) -> None:
            self._state = state

        def probe(self) -> CorpusState:
            return self._state

    absent = checks.check_corpus_state(_Probe(CorpusState.ABSENT))
    assert absent.status == "warning"
    assert absent.code == "CORPUS_ABSENT"
    assert absent.next_action

    assert "index build --activate" in (absent.next_action or "")

    compatible = checks.check_corpus_state(_Probe(CorpusState.COMPATIBLE))
    assert compatible.status == "ok"
    assert compatible.code == "CORPUS_COMPATIBLE"

    incompatible = checks.check_corpus_state(_Probe(CorpusState.INCOMPATIBLE))
    assert incompatible.status == "failure"
    assert incompatible.code == "CORPUS_INCOMPATIBLE"
    assert incompatible.next_action
