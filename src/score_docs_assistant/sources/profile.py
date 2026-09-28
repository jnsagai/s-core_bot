"""Parser profiles: which directives are needs, which options are links, which constructs are
dynamic (never evaluated). Versioned data in `config/parser-profiles/` instead of upstream
`conf.py`, which must never be executed (SRC-006, research.md R1)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, PrivateAttr, ValidationError

from score_docs_assistant.domain.errors import ConfigError
from score_docs_assistant.ingestion.canonical import canonical_hash

_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")


class ParserProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    profile_version: int
    need_types: list[str]
    link_options: list[str]
    reference_roles: list[str]
    dynamic_directives: list[str]
    dynamic_roles: list[str]
    literal_directives: dict[str, str | None]
    excluded_directives: list[str]

    _name: str = PrivateAttr(default="")

    @property
    def name(self) -> str:
        return self._name


def _validate(profile: ParserProfile) -> list[tuple[str, str]]:
    errors: list[tuple[str, str]] = []
    lists: dict[str, list[str]] = {
        "need_types": profile.need_types,
        "link_options": profile.link_options,
        "reference_roles": profile.reference_roles,
        "dynamic_directives": profile.dynamic_directives,
        "dynamic_roles": profile.dynamic_roles,
        "literal_directives": list(profile.literal_directives),
        "excluded_directives": profile.excluded_directives,
    }
    for key in ("need_types", "link_options"):
        if not lists[key]:
            errors.append((key, "must not be empty"))
    for key, values in lists.items():
        seen: set[str] = set()
        for index, value in enumerate(values):
            if not _NAME.match(value):
                errors.append((f"{key}.{index}", f"invalid name {value!r}"))
            if value in seen:
                errors.append((f"{key}.{index}", f"duplicate entry {value!r}"))
            seen.add(value)
    for namespace in (
        ("need_types", "dynamic_directives", "literal_directives", "excluded_directives"),
        ("reference_roles", "dynamic_roles"),
    ):
        owner: dict[str, str] = {}
        for key in namespace:
            for value in lists[key]:
                if value in owner and owner[value] != key:
                    errors.append((key, f"{value!r} is also listed in {owner[value]}"))
                owner.setdefault(value, key)
    return errors


def load_profile(path: Path) -> ParserProfile:
    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError([(str(path), f"cannot read parser profile: {exc}")]) from exc
    try:
        profile = ParserProfile.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(
            [(".".join(str(p) for p in e["loc"]), e["msg"]) for e in exc.errors()]
        ) from exc
    errors = _validate(profile)
    if errors:
        raise ConfigError(errors)
    profile._name = path.stem
    return profile


def profile_hash(profile: ParserProfile) -> str:
    return canonical_hash(profile.model_dump(mode="json"))
