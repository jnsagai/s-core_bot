"""Individual doctor checks as pure functions of (config, runtime client, probes) -> CheckResult.

Order and status/code catalogue: contracts/cli.md. Model storage resolution: research.md R5.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Mapping
from pathlib import Path

from score_docs_assistant.diagnostics.hardware import HardwareInfo
from score_docs_assistant.domain.diagnostics import CheckResult
from score_docs_assistant.domain.errors import (
    RuntimeIncompatible,
    RuntimeTimeout,
    RuntimeUnreachable,
)
from score_docs_assistant.domain.models import InstalledModel, ModelLock, ModelProfile, ProfileModel
from score_docs_assistant.domain.models import RuntimeInfo as RuntimeIdentity
from score_docs_assistant.models.lock import compare_role
from score_docs_assistant.models.runtime import ModelRuntime, normalize_tag
from score_docs_assistant.storage.corpus_probe import CorpusProbe, CorpusState

_KNOWN_OLLAMA_MODEL_PATHS = [
    Path("/var/snap/ollama/common/models"),
    Path("/usr/share/ollama/.ollama/models"),
    Path.home() / ".ollama" / "models",
]


def resolve_models_dir(
    configured: Path | None, env: Mapping[str, str], data_dir: Path
) -> tuple[Path, bool]:
    if configured is not None:
        return configured, False
    env_dir = env.get("OLLAMA_MODELS")
    if env_dir:
        return Path(env_dir), False
    for candidate in _KNOWN_OLLAMA_MODEL_PATHS:
        if candidate.exists():
            return candidate, False
    return data_dir, True


def required_free_bytes(profile: ModelProfile, margin_bytes: int) -> int | None:
    """Sum of approx_size_bytes for every model in the profile, plus margin.

    Returns None if any model's size is unknown (caller must require an explicit override).
    """
    total = 0
    for model in profile.models:
        if model.approx_size_bytes is None:
            return None
        total += model.approx_size_bytes
    return total + margin_bytes


def check_config_valid() -> CheckResult:
    return CheckResult(
        id="config.valid", status="ok", code="CONFIG_VALID", message="Configuration is valid."
    )


def check_app_version(app_version: str) -> CheckResult:
    return CheckResult(
        id="app.version",
        status="info",
        code="APP_VERSION",
        message=f"score-assistant {app_version}",
        details={"version": app_version},
    )


def check_platform(hw: HardwareInfo) -> CheckResult:
    return CheckResult(
        id="platform",
        status="info",
        code="PLATFORM",
        message=f"{hw.os} {hw.arch}, {hw.cpu_count} CPU threads.",
        details={"os": hw.os, "arch": hw.arch, "cpu_count": hw.cpu_count},
    )


def check_memory(hw: HardwareInfo) -> CheckResult:
    return CheckResult(
        id="memory",
        status="info",
        code="MEMORY",
        message=f"{hw.ram_available_bytes} bytes available of {hw.ram_total_bytes} total.",
        details={"total_bytes": hw.ram_total_bytes, "available_bytes": hw.ram_available_bytes},
    )


def check_gpu(hw: HardwareInfo) -> CheckResult:
    if hw.gpu_detection == "detected":
        names = ", ".join(g.name for g in hw.gpus)
        return CheckResult(
            id="gpu",
            status="info",
            code="GPU_DETECTED",
            message=f"Detected: {names}.",
            details={"count": len(hw.gpus)},
        )
    if hw.gpu_detection == "error":
        return CheckResult(
            id="gpu",
            status="info",
            code="GPU_NOT_DETECTED",
            message="GPU probe failed (nvidia-smi timed out or returned malformed output); "
            "continuing CPU-only.",
        )
    return CheckResult(
        id="gpu",
        status="info",
        code="GPU_NOT_DETECTED",
        message="No NVIDIA GPU detected; CPU-only mode.",
    )


def check_disk(
    check_id: str, path: Path, margin_bytes: int, *, is_fallback: bool = False
) -> CheckResult:
    probe_path = path if path.exists() else path.parent
    try:
        free = shutil.disk_usage(probe_path).free
    except OSError:
        return CheckResult(
            id=check_id,
            status="warning",
            code="DISK_LOW",
            message=f"Could not determine free disk space at {path}.",
            next_action="Verify the path exists and is accessible.",
            details={"path": str(path)},
        )
    details: dict[str, str | int | float | bool | None] = {
        "path": str(path),
        "free_bytes": free,
        "is_fallback": is_fallback,
    }
    if free < margin_bytes:
        return CheckResult(
            id=check_id,
            status="warning",
            code="DISK_LOW",
            message=f"Only {free} bytes free at {path}; recommend at least {margin_bytes}.",
            next_action="Free up disk space before pulling models.",
            details=details,
        )
    return CheckResult(
        id=check_id,
        status="ok",
        code="DISK_OK",
        message=f"{free} bytes free at {path}.",
        details=details,
    )


def check_data_dir_writable(data_dir: Path) -> CheckResult:
    if not data_dir.exists():
        return CheckResult(
            id="data_dir.writable",
            status="warning",
            code="DATA_DIR_MISSING",
            message=f"{data_dir} does not exist yet.",
            next_action="It is created automatically on first use, or create it yourself.",
            details={"path": str(data_dir)},
        )
    if not os.access(data_dir, os.W_OK):
        return CheckResult(
            id="data_dir.writable",
            status="failure",
            code="DATA_DIR_NOT_WRITABLE",
            message=f"{data_dir} exists but is not writable.",
            next_action="Fix directory permissions.",
            details={"path": str(data_dir)},
        )
    return CheckResult(
        id="data_dir.writable",
        status="ok",
        code="DATA_DIR_WRITABLE",
        message=f"{data_dir} is writable.",
        details={"path": str(data_dir)},
    )


def check_runtime_reachable(
    runtime: ModelRuntime, base_url: str
) -> tuple[CheckResult, RuntimeIdentity | None, list[InstalledModel] | None]:
    try:
        info = runtime.version()
        models = runtime.list_models()
    except RuntimeTimeout as exc:
        return (
            CheckResult(
                id="runtime.reachable",
                status="failure",
                code="RUNTIME_TIMEOUT",
                message=str(exc),
                next_action=f"Check that Ollama is responsive at {base_url} and retry.",
                details={"base_url": base_url},
            ),
            None,
            None,
        )
    except RuntimeUnreachable as exc:
        return (
            CheckResult(
                id="runtime.reachable",
                status="failure",
                code="RUNTIME_UNREACHABLE",
                message=str(exc),
                next_action="Start Ollama (e.g. `sudo snap start ollama`) and re-run doctor.",
                details={"base_url": base_url},
            ),
            None,
            None,
        )
    except RuntimeIncompatible as exc:
        return (
            CheckResult(
                id="runtime.reachable",
                status="failure",
                code="RUNTIME_INCOMPATIBLE",
                message=str(exc),
                next_action="Check the Ollama version and API compatibility.",
                details={"base_url": base_url},
            ),
            None,
            None,
        )
    return (
        CheckResult(
            id="runtime.reachable",
            status="ok",
            code="RUNTIME_REACHABLE",
            message=f"Ollama {info.version} reachable at {base_url}.",
            details={"base_url": base_url, "version": info.version},
        ),
        info,
        models,
    )


def check_runtime_cloud() -> CheckResult:
    return CheckResult(
        id="runtime.cloud",
        status="info",
        code="RUNTIME_CLOUD_UNVERIFIED",
        message="Cannot verify from this client whether Ollama cloud features are disabled on "
        "the runtime host.",
        next_action='Set OLLAMA_NO_CLOUD=1 or "disable_ollama_cloud": true in '
        "~/.ollama/server.json on the machine running Ollama.",
    )


def check_model(
    role: str,
    profile_model: ProfileModel,
    installed: list[InstalledModel] | None,
    profile_name: str,
) -> CheckResult:
    check_id = f"model.{role}"
    if installed is None:
        return CheckResult(
            id=check_id,
            status="skipped",
            code="RUNTIME_REQUIRED",
            message="Runtime must be reachable to check installed models.",
        )
    tag = normalize_tag(profile_model.tag)
    match = next((m for m in installed if m.tag == tag), None)
    if match is None:
        return CheckResult(
            id=check_id,
            status="warning",
            code="MODEL_MISSING",
            message=f"{tag} is not installed.",
            next_action=f"Run `score-assistant models pull --profile {profile_name}`.",
            details={"tag": tag},
        )
    if match.is_remote:
        return CheckResult(
            id=check_id,
            status="failure",
            code="MODEL_REMOTE",
            message=f"{tag} is proxied to a remote/cloud model, which is not allowed.",
            next_action="Use a local (non-cloud-proxied) model instead.",
            details={"tag": tag},
        )
    return CheckResult(
        id=check_id,
        status="ok",
        code="MODEL_PRESENT",
        message=f"{tag} is installed.",
        details={"tag": tag, "digest": match.digest},
    )


def check_model_lock(
    profile: ModelProfile, installed: list[InstalledModel] | None, lock: ModelLock | None
) -> CheckResult:
    if installed is None:
        return CheckResult(
            id="model.lock",
            status="skipped",
            code="RUNTIME_REQUIRED",
            message="Runtime must be reachable to check the model lock.",
        )
    statuses = {model.role: compare_role(lock, model.role, installed) for model in profile.models}
    details: dict[str, str | int | float | bool | None] = {
        role: str(status) for role, status in statuses.items()
    }
    if "mismatch" in statuses.values():
        mismatched = [role for role, status in statuses.items() if status == "mismatch"]
        return CheckResult(
            id="model.lock",
            status="failure",
            code="MODEL_LOCK_MISMATCH",
            message=f"Installed model digest differs from the lock for: {', '.join(mismatched)}.",
            next_action="Re-run `models pull` to re-lock, or investigate the installed model.",
            details=details,
        )
    if all(status == "match" for status in statuses.values()):
        return CheckResult(
            id="model.lock",
            status="ok",
            code="MODEL_LOCK_MATCH",
            message="Installed models match the lock.",
            details=details,
        )
    return CheckResult(
        id="model.lock",
        status="warning",
        code="MODEL_NOT_LOCKED",
        message="One or more configured models are not locked.",
        next_action="Run `models pull` to (re)lock installed models.",
        details=details,
    )


def check_corpus_state(probe: CorpusProbe) -> CheckResult:
    state = probe.probe()
    if state == CorpusState.ABSENT:
        return CheckResult(
            id="corpus.state",
            status="warning",
            code="CORPUS_ABSENT",
            message="No document corpus is installed yet.",
            next_action="Corpus ingestion is not implemented in F001; see F002+.",
        )
    return CheckResult(
        id="corpus.state",
        status="failure",
        code="CORPUS_INCOMPATIBLE",
        message="An existing corpus catalog is not compatible with this version.",
        next_action="Reinstall or re-ingest the corpus once ingestion is available.",
    )
