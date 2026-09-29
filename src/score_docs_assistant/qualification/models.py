"""Model qualification record (F008 FR-017, research R10).

Read from the model lock and the local runtime's metadata endpoints (`/api/show`, `/api/tags`,
`/api/version`); nothing is pulled. The license is recorded as the artifact reports it: a summary
(first non-empty line and an SPDX guess) plus the full text in a sidecar file.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict

_FORBID = ConfigDict(extra="forbid", frozen=True)
_SPDX_HINTS = {
    "apache license": "Apache-2.0",
    "mit license": "MIT",
    "bsd 3-clause": "BSD-3-Clause",
    "llama 3": "LicenseRef-Llama3",
    "gemma terms": "LicenseRef-Gemma",
}

Fetch = Callable[[str, dict[str, Any] | None], dict[str, Any]]


class ModelRecord(BaseModel):
    model_config = _FORBID

    role: str
    tag: str
    locked_digest: str
    installed_digest: str | None
    lock_match: bool
    family: str | None
    parameter_size: str | None
    quantization: str | None
    context_length: int | None
    license_first_line: str | None
    license_spdx_guess: str | None
    license_sha256: str | None
    license_file: str | None


class ModelQualification(BaseModel):
    model_config = _FORBID

    created_at: datetime
    runtime_version: str | None
    locked_runtime_version: str | None
    profile: str | None
    models: list[ModelRecord]
    notes: list[str]


def http_fetch(base_url: str) -> Fetch:
    def fetch(path: str, body: dict[str, Any] | None) -> dict[str, Any]:
        with httpx.Client(base_url=base_url.rstrip("/"), timeout=30) as client:
            response = client.post(path, json=body) if body is not None else client.get(path)
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            return data

    return fetch


def spdx_guess(text: str) -> str | None:
    lowered = text.lower()
    return next((spdx for hint, spdx in _SPDX_HINTS.items() if hint in lowered), None)


def qualify(lock_path: Path, fetch: Fetch, sidecar_dir: Path) -> ModelQualification:
    lock = json.loads(lock_path.read_text())
    tags = {
        m.get("name"): str(m.get("digest", "")).removeprefix("sha256:")
        for m in fetch("/api/tags", None).get("models", [])
    }
    version = fetch("/api/version", None).get("version")
    records: list[ModelRecord] = []
    sidecar_dir.mkdir(parents=True, exist_ok=True)
    for entry in lock.get("models", []):
        tag = str(entry["tag"])
        normalized = tag if ":" in tag else f"{tag}:latest"
        locked = str(entry["digest"]).removeprefix("sha256:")
        installed = tags.get(normalized) or tags.get(tag)
        show = fetch("/api/show", {"model": tag})
        details = show.get("details") or {}
        info = show.get("model_info") or {}
        context = next((int(v) for k, v in info.items() if k.endswith(".context_length")), None)
        license_text = str(show.get("license") or "")
        license_file = None
        license_sha = None
        if license_text:
            license_sha = hashlib.sha256(license_text.encode()).hexdigest()
            path = sidecar_dir / f"license-{entry['role']}-{license_sha[:12]}.txt"
            path.write_text(license_text)
            license_file = path.name
        first = next((line.strip() for line in license_text.splitlines() if line.strip()), None)
        records.append(
            ModelRecord(
                role=str(entry["role"]),
                tag=tag,
                locked_digest=locked,
                installed_digest=installed,
                lock_match=installed == locked,
                family=details.get("family"),
                parameter_size=details.get("parameter_size"),
                quantization=details.get("quantization_level"),
                context_length=context,
                license_first_line=first,
                license_spdx_guess=spdx_guess(license_text) if license_text else None,
                license_sha256=license_sha,
                license_file=license_file,
            )
        )
    return ModelQualification(
        created_at=datetime.now(UTC),
        runtime_version=version,
        locked_runtime_version=(lock.get("runtime") or {}).get("version"),
        profile=lock.get("profile"),
        models=records,
        notes=[
            "license as reported by the local model artifact; an SPDX guess is not a legal review",
            "the application uses a configured context window, not the model maximum",
        ],
    )
