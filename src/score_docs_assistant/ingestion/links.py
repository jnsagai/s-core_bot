"""Link values `ID[qualifier]` and cross-source resolution (FR-011, FR-018; plan Key Design 7).

Observed upstream: comma-separated IDs, optional bracket qualifier (`[version==1]`), values
continued over several indented lines, repeated targets. Resolution never guesses: same source
first, then a unique match among other git sources, otherwise ambiguous or unresolved. Exports
form separate namespaces (FR-019).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from score_docs_assistant.domain.ingestion import LinkRef

_ITEM = re.compile(r"^(?P<id>[^\s\[\],<>]+)(?:\[(?P<q>[^\]]*)\])?$")
_TITLED = re.compile(r"^(?P<title>.*?)\s*<(?P<id>[^<>]+)>$", re.DOTALL)


def _split_outside_brackets(raw: str) -> list[str]:
    items: list[str] = []
    depth = 0
    current: list[str] = []
    for char in raw:
        if char == "[":
            depth += 1
        elif char == "]" and depth:
            depth -= 1
        if char == "," and depth == 0:
            items.append("".join(current))
            current = []
        else:
            current.append(char)
    items.append("".join(current))
    return items


def parse_link_value(via: str, raw: str) -> list[LinkRef]:
    refs: list[LinkRef] = []
    for item in _split_outside_brackets(raw):
        text = " ".join(item.split())
        match = _ITEM.match(text)
        if match:
            refs.append(
                LinkRef(via=via, target_id=match.group("id"), qualifier=match.group("q"), raw=text)
            )
        elif text or len(raw.split(",")) > 1:
            refs.append(LinkRef(via=via, target_id="", raw=text, resolution="malformed"))
    return refs


def parse_role_target(role: str, text: str) -> LinkRef:
    """`:need:`/`:ref:` content: either `target` or `Title <target>`."""
    stripped = text.strip()
    titled = _TITLED.match(stripped)
    target = titled.group("id").strip() if titled else stripped
    via = f"role:{role}"
    if not target or any(c.isspace() for c in target):
        return LinkRef(via=via, target_id="", raw=stripped, resolution="malformed")
    return LinkRef(via=via, target_id=target, raw=stripped)


@dataclass(frozen=True)
class EntityIndex:
    """need_id → keys per source; which sources are exports (separate namespaces)."""

    by_source: Mapping[str, Mapping[str, list[str]]]
    export_sources: frozenset[str]

    @classmethod
    def build(
        cls, need_ids_by_source: Mapping[str, list[str]], export_sources: set[str]
    ) -> EntityIndex:
        by_source: dict[str, dict[str, list[str]]] = {}
        for source_id, need_ids in need_ids_by_source.items():
            table: dict[str, list[str]] = {}
            for need_id in need_ids:
                keys = table.setdefault(need_id, [])
                keys.append(f"{source_id}:{need_id}" + (f"#{len(keys) + 1}" if keys else ""))
            by_source[source_id] = table
        return cls(by_source=by_source, export_sources=frozenset(export_sources))


def resolve(ref: LinkRef, from_source: str, index: EntityIndex) -> LinkRef:
    if ref.resolution == "malformed":
        return ref
    own = index.by_source.get(from_source, {}).get(ref.target_id, [])
    if own:
        status = "resolved" if len(own) == 1 else "ambiguous"
        return ref.model_copy(update={"resolution": status, "resolved_keys": list(own)})
    if from_source in index.export_sources:
        return ref.model_copy(update={"resolution": "unresolved", "resolved_keys": []})
    candidates = sorted(
        key
        for source_id, table in index.by_source.items()
        if source_id != from_source and source_id not in index.export_sources
        for key in table.get(ref.target_id, [])
    )
    if len(candidates) == 1:
        return ref.model_copy(update={"resolution": "resolved", "resolved_keys": candidates})
    if candidates:
        return ref.model_copy(update={"resolution": "ambiguous", "resolved_keys": candidates})
    return ref.model_copy(update={"resolution": "unresolved", "resolved_keys": []})
