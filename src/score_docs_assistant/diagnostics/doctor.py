"""Orchestrates the checks into a `DiagnosticReport`; renders text and JSON (both redacted)."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from typing import Any

from score_docs_assistant.config.loader import EffectiveConfig
from score_docs_assistant.config.redact import redact_mapping, redact_text
from score_docs_assistant.diagnostics import checks as checks_mod
from score_docs_assistant.diagnostics.hardware import probe_hardware
from score_docs_assistant.domain.diagnostics import CheckResult, DiagnosticReport
from score_docs_assistant.domain.models import ModelProfile
from score_docs_assistant.models.lock import read_lock
from score_docs_assistant.models.runtime import ModelRuntime
from score_docs_assistant.storage.corpus_probe import CorpusProbe


def run_doctor(
    *,
    effective: EffectiveConfig,
    runtime: ModelRuntime,
    profile: ModelProfile,
    corpus_probe: CorpusProbe,
    app_version: str,
    env: Mapping[str, str] | None = None,
) -> DiagnosticReport:
    env = os.environ if env is None else env
    config = effective.config
    results: list[CheckResult] = [checks_mod.check_config_valid()]

    hw = probe_hardware(config.data_dir)
    results.append(checks_mod.check_app_version(app_version))
    results.append(checks_mod.check_platform(hw))
    results.append(checks_mod.check_memory(hw))
    results.append(checks_mod.check_gpu(hw))
    results.append(
        checks_mod.check_disk("disk.data", config.data_dir, config.diagnostics.disk_margin_bytes)
    )

    models_dir, is_fallback = checks_mod.resolve_models_dir(
        config.runtime.models_dir, env, config.data_dir
    )
    results.append(
        checks_mod.check_disk(
            "disk.models",
            models_dir,
            config.diagnostics.disk_margin_bytes,
            is_fallback=is_fallback,
        )
    )
    results.append(checks_mod.check_data_dir_writable(config.data_dir))

    reachable_result, _runtime_info, installed = checks_mod.check_runtime_reachable(
        runtime, config.runtime.base_url
    )
    results.append(reachable_result)
    results.append(checks_mod.check_runtime_cloud())

    lock = read_lock(config.data_dir / "model-lock.json")
    results.append(
        checks_mod.check_model(
            "generation",
            profile.model_for_role("generation"),
            installed,
            config.runtime.model_profile,
        )
    )
    results.append(
        checks_mod.check_model(
            "embedding",
            profile.model_for_role("embedding"),
            installed,
            config.runtime.model_profile,
        )
    )
    results.append(checks_mod.check_model_lock(profile, installed, lock))

    results.append(checks_mod.check_corpus_state(corpus_probe))
    results.append(checks_mod.check_refresh_state(config.data_dir))

    return DiagnosticReport.from_checks(app_version, results)


def config_error_report(app_version: str, message: str) -> DiagnosticReport:
    check = CheckResult(
        id="config.valid",
        status="failure",
        code="CONFIG_INVALID",
        message=message,
        next_action="Fix the configuration and re-run doctor.",
    )
    return DiagnosticReport.from_config_error(app_version, check)


def render_text(report: DiagnosticReport) -> str:
    lines: list[str] = []
    for check in report.checks:
        lines.append(f"[{check.status.upper()}] {check.id}: {redact_text(check.message)}")
        if check.next_action:
            lines.append(f"  → {redact_text(check.next_action)}")
    return "\n".join(lines)


def render_json(report: DiagnosticReport, *, effective: EffectiveConfig | None) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(report.model_dump_json())
    if effective is not None:
        data["config"] = {
            "file": str(effective.config_file) if effective.config_file else None,
            "sources": effective.sources,
        }
    else:
        data["config"] = {"file": None, "sources": {}}
    return redact_mapping(data)
