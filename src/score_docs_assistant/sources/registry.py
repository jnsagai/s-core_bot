"""The operator-maintained source registry `config/sources.yaml` (FR-001, FR-002;
contracts/registry.md). Structural errors come from Pydantic; semantic rules (URLs, globs, refs,
cross-references) are checked afterwards so every problem is reported at once."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, ValidationError

from score_docs_assistant.domain.errors import ConfigError
from score_docs_assistant.sources.paths import UnsafePathError, safe_relative_path
from score_docs_assistant.sources.selectors import validate_glob

_SOURCE_ID = re.compile(r"^[a-z][a-z0-9-]{1,62}$")
_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
_ABBREVIATED_SHA = re.compile(r"^[0-9a-f]{7,39}$")
_REF_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")

_STRICT = ConfigDict(frozen=True, extra="forbid")


class SyncLimits(BaseModel):
    model_config = _STRICT

    max_text_file_bytes: int
    max_export_bytes: int
    max_sync_bytes: int
    connect_timeout_seconds: int
    read_timeout_seconds: int


class _SourceBase(BaseModel):
    model_config = _STRICT

    source_id: str
    authority: str
    repository_license: str | None = None
    license_policy: Literal["inspect-file-and-repository-notices"]
    required: bool


class GitSource(_SourceBase):
    kind: Literal["git"]
    repository: str
    ref: str
    include: list[str]
    exclude: list[str] = []
    parser_profile: str


class ExportSource(_SourceBase):
    kind: Literal["needs-export"]
    url: str
    associated_source: str | None = None
    docs_root: str | None = None


SourceDefinition = Annotated[GitSource | ExportSource, Field(discriminator="kind")]


class SourceRegistry(BaseModel):
    model_config = _STRICT

    schema_version: Literal[1]
    allowed_hosts: list[str] = Field(min_length=1)
    redistribution_allowed_licenses: list[str]
    limits: SyncLimits
    sources: list[SourceDefinition]

    _sha256: str = PrivateAttr(default="")
    _profiles_dir: Path = PrivateAttr(default=Path("config/parser-profiles"))

    @property
    def sha256(self) -> str:
        return self._sha256

    @property
    def profiles_dir(self) -> Path:
        return self._profiles_dir


def url_problem(url: str, allowed_hosts: list[str]) -> str | None:
    """Reason `url` is not an acceptable origin, or None (SEC-005)."""
    if any(c.isspace() for c in url):
        return "must not contain whitespace"
    parts = urlsplit(url)
    if parts.scheme != "https":
        return "must use https"
    if parts.username is not None or parts.password is not None:
        return "must not contain credentials"
    if parts.query or parts.fragment:
        return "must not contain a query or fragment"
    try:
        port = parts.port
    except ValueError:
        return "invalid port"
    if port not in (None, 443):
        return "must not use a non-standard port"
    host = (parts.hostname or "").lower()
    if host not in {h.lower() for h in allowed_hosts}:
        return f"host {host!r} is not in allowed_hosts"
    return None


def _loc(loc: tuple[Any, ...]) -> str:
    # Drop the discriminator tag Pydantic inserts after a list index ("sources.0.git.refs").
    parts = [str(p) for p in loc if p not in ("git", "needs-export")]
    return ".".join(parts)


def _semantic_errors(registry: SourceRegistry, profiles_dir: Path) -> list[tuple[str, str]]:
    errors: list[tuple[str, str]] = []
    limits = registry.limits
    for key in SyncLimits.model_fields:
        if getattr(limits, key) <= 0:
            errors.append((f"limits.{key}", "must be positive"))
    if limits.max_text_file_bytes > limits.max_sync_bytes:
        errors.append(("limits.max_text_file_bytes", "must not exceed max_sync_bytes"))

    kinds = {s.source_id: s.kind for s in registry.sources}
    seen: set[str] = set()
    for i, source in enumerate(registry.sources):
        base = f"sources.{i}"
        if not _SOURCE_ID.match(source.source_id):
            errors.append((f"{base}.source_id", "must match ^[a-z][a-z0-9-]{1,62}$"))
        if source.source_id in seen:
            errors.append((f"{base}.source_id", f"duplicate source_id {source.source_id!r}"))
        seen.add(source.source_id)
        if isinstance(source, GitSource):
            if (problem := url_problem(source.repository, registry.allowed_hosts)) is not None:
                errors.append((f"{base}.repository", problem))
            if _FULL_SHA.match(source.ref):
                pass
            elif _ABBREVIATED_SHA.match(source.ref):
                errors.append((f"{base}.ref", "abbreviated commit SHAs are not allowed"))
            elif not _REF_NAME.match(source.ref) or ".." in source.ref:
                errors.append((f"{base}.ref", "invalid branch or tag name"))
            if not source.include:
                errors.append((f"{base}.include", "must not be empty"))
            for key in ("include", "exclude"):
                for j, pattern in enumerate(getattr(source, key)):
                    if (reason := validate_glob(pattern)) is not None:
                        errors.append((f"{base}.{key}.{j}", reason))
            if not (profiles_dir / f"{source.parser_profile}.yaml").is_file():
                errors.append(
                    (f"{base}.parser_profile", f"no profile file {source.parser_profile}.yaml")
                )
        else:
            if (problem := url_problem(source.url, registry.allowed_hosts)) is not None:
                errors.append((f"{base}.url", problem))
            if source.associated_source is not None:
                if kinds.get(source.associated_source) != "git":
                    errors.append(
                        (f"{base}.associated_source", "must name a git source in this registry")
                    )
                if source.docs_root is None:
                    errors.append((f"{base}.docs_root", "required when associated_source is set"))
            if source.docs_root is not None:
                try:
                    safe_relative_path(source.docs_root)
                except UnsafePathError as exc:
                    errors.append((f"{base}.docs_root", str(exc)))
    return errors


def load_registry(path: Path, profiles_dir: Path | None = None) -> SourceRegistry:
    try:
        data = path.read_bytes()
        raw: Any = yaml.safe_load(data.decode("utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise ConfigError([(str(path), f"cannot read registry: {exc}")]) from exc
    try:
        registry = SourceRegistry.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError([(_loc(e["loc"]), e["msg"]) for e in exc.errors()]) from exc
    profiles = profiles_dir if profiles_dir is not None else path.parent / "parser-profiles"
    errors = _semantic_errors(registry, profiles)
    if errors:
        raise ConfigError(errors)
    registry._sha256 = hashlib.sha256(data).hexdigest()
    registry._profiles_dir = profiles
    return registry
