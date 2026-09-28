"""`score-assistant models inspect|pull` (contracts/cli.md)."""

from __future__ import annotations

import json
import os
import shutil
from datetime import UTC, datetime
from typing import Annotated, Any

import typer

from score_docs_assistant.cli.config_paths import profiles_path_for
from score_docs_assistant.cli.main import cli_app, handle_common_errors
from score_docs_assistant.cli.runtime_factory import build_runtime
from score_docs_assistant.config.loader import EffectiveConfig, load_config
from score_docs_assistant.diagnostics.checks import required_free_bytes, resolve_models_dir
from score_docs_assistant.domain.errors import (
    ConfigError,
    ProfileNotFound,
    RuntimeIncompatible,
    RuntimeTimeout,
    RuntimeUnreachable,
)
from score_docs_assistant.domain.models import (
    ModelLock,
    ModelLockEntry,
    ModelLockRuntime,
    ModelProfile,
)
from score_docs_assistant.models.lock import compare_role, read_lock, write_lock
from score_docs_assistant.models.profiles import get_profile, load_profiles
from score_docs_assistant.models.runtime import normalize_tag

models_app = typer.Typer(add_completion=False, help="Inspect and acquire local models.")
cli_app.add_typer(models_app, name="models")


def _load_effective_and_profile(
    ctx: typer.Context, profile_name: str | None = None
) -> tuple[EffectiveConfig, ModelProfile]:
    config_path = (ctx.obj or {}).get("config_path")
    effective = load_config(config_path=config_path)
    profiles = load_profiles(profiles_path_for(effective.config_file or config_path))
    name = profile_name or effective.config.runtime.model_profile
    try:
        profile = get_profile(profiles, name)
    except ProfileNotFound as exc:
        raise ConfigError(
            [("runtime.model_profile", f"unknown model profile: {exc.profile}")]
        ) from exc
    return effective, profile


@models_app.command("inspect")
@handle_common_errors
def inspect_command(
    ctx: typer.Context,
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit machine-readable JSON.")
    ] = False,
) -> None:
    """List each profile model's presence, digest, and lock status. Never downloads."""
    effective, profile = _load_effective_and_profile(ctx)
    config = effective.config
    runtime = build_runtime(config)
    try:
        try:
            installed = runtime.list_models()
        except (RuntimeUnreachable, RuntimeTimeout, RuntimeIncompatible) as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from None
    finally:
        close = getattr(runtime, "close", None)
        if close is not None:
            close()

    lock = read_lock(config.data_dir / "model-lock.json")
    rows: list[dict[str, Any]] = []
    for model in profile.models:
        tag = normalize_tag(model.tag)
        match = next((m for m in installed if m.tag == tag), None)
        rows.append(
            {
                "role": model.role,
                "tag": tag,
                "present": match is not None,
                "digest": match.digest if match else None,
                "size_bytes": match.size_bytes if match else None,
                "family": match.family if match else None,
                "quantization": match.quantization if match else None,
                "is_remote": match.is_remote if match else False,
                "lock_status": compare_role(lock, model.role, installed),
            }
        )

    if json_output:
        typer.echo(json.dumps({"profile": profile.name, "models": rows}))
    else:
        for row in rows:
            presence = "present" if row["present"] else "missing"
            typer.echo(f"{row['role']}: {row['tag']} ({presence}, lock={row['lock_status']})")
    raise typer.Exit(code=0)


@models_app.command("pull")
@handle_common_errors
def pull_command(
    ctx: typer.Context,
    profile_name: Annotated[
        str, typer.Option("--profile", help="Model profile name from config/model-profiles.yaml.")
    ],
    allow_unknown_size: Annotated[
        bool,
        typer.Option(
            "--allow-unknown-size", help="Proceed even if a model's download size is unknown."
        ),
    ] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit machine-readable JSON.")
    ] = False,
) -> None:
    """Uses the network: downloads models via the local runtime.

    Acquires the models for a profile (skipping ones already installed) and writes the model
    lock. Never re-downloads an already-present model.
    """
    effective, profile = _load_effective_and_profile(ctx, profile_name)
    config = effective.config

    runtime = build_runtime(config)
    results: list[dict[str, Any]] = []
    lock_path = config.data_dir / "model-lock.json"
    try:
        try:
            version_info = runtime.version()
        except (RuntimeUnreachable, RuntimeTimeout, RuntimeIncompatible) as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from None

        required = required_free_bytes(profile, config.diagnostics.disk_margin_bytes)
        if required is None and not allow_unknown_size:
            typer.echo(
                "One or more models have an unknown download size; pass --allow-unknown-size "
                "to proceed anyway.",
                err=True,
            )
            raise typer.Exit(code=2)
        if required is not None:
            models_dir, _is_fallback = resolve_models_dir(
                config.runtime.models_dir, os.environ, config.data_dir
            )
            probe_path = models_dir if models_dir.exists() else models_dir.parent
            free = shutil.disk_usage(probe_path).free
            if free < required:
                typer.echo(
                    f"DISK_INSUFFICIENT: need {required} bytes free at {models_dir}, "
                    f"only {free} available.",
                    err=True,
                )
                raise typer.Exit(code=1)

        installed = runtime.list_models()
        for model in profile.models:
            tag = normalize_tag(model.tag)
            match = next((m for m in installed if m.tag == tag), None)
            if match is not None:
                if match.is_remote:
                    typer.echo(
                        f"MODEL_REMOTE: {tag} is proxied to a remote/cloud model; refusing to "
                        "pull it as a local model.",
                        err=True,
                    )
                    raise typer.Exit(code=1)
                results.append(
                    {
                        "tag": tag,
                        "digest": match.digest,
                        "size_bytes": match.size_bytes,
                        "action": "already_present",
                    }
                )
                continue

            for progress in runtime.pull(model.tag):
                typer.echo(json.dumps(progress), err=True)

            installed = runtime.list_models()
            new_match = next((m for m in installed if m.tag == tag), None)
            if new_match is None:
                typer.echo(
                    f"Pull reported completion for {tag} but it is not present afterwards.",
                    err=True,
                )
                raise typer.Exit(code=1)
            results.append(
                {
                    "tag": tag,
                    "digest": new_match.digest,
                    "size_bytes": new_match.size_bytes,
                    "action": "pulled",
                }
            )

        lock_entries = []
        for model in profile.models:
            tag = normalize_tag(model.tag)
            match = next((m for m in installed if m.tag == tag), None)
            if match is None:
                continue
            lock_entries.append(
                ModelLockEntry(
                    role=model.role,
                    tag=tag,
                    digest=match.digest,
                    size_bytes=match.size_bytes,
                    acquired_at=datetime.now(UTC),
                )
            )
        lock = ModelLock(
            profile=profile.name,
            runtime=ModelLockRuntime(provider="ollama", version=version_info.version),
            models=lock_entries,
        )
        write_lock(lock_path, lock)
    finally:
        close = getattr(runtime, "close", None)
        if close is not None:
            close()

    result = {
        "profile": profile.name,
        "network_used": True,
        "models": results,
        "lock_path": str(lock_path),
    }
    if json_output:
        typer.echo(json.dumps(result))
    else:
        for row in results:
            typer.echo(f"{row['tag']}: {row['action']}")
    raise typer.Exit(code=0)
