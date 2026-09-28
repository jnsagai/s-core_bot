"""Exact and alias requirement-ID lookup, and stored relationships (FR-001–FR-005, research R1).

Matching is verbatim first, then by the documented alias; never fuzzy. When several entities share
an ID, all are returned: records bound to a pinned git revision before `unverified` export copies,
then by source ID and key. That is the only preference, and it follows from exports being
unverified by definition.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Literal

from score_docs_assistant.domain.errors import SearchError
from score_docs_assistant.domain.retrieval import EntityRecord, EntitySummary, Relationship
from score_docs_assistant.domain.snapshots import SnapshotManifest
from score_docs_assistant.retrieval.query import alias, excerpt, id_tokens

MatchKind = Literal["exact", "alias"]
MAX_RELATIONSHIPS = 200


@dataclass(frozen=True)
class EntityRow:
    key: str
    need_id: str
    type: str
    title: str
    source_id: str
    path: str
    line_start: int | None
    line_end: int | None
    origin: str
    revision_status: str
    options: dict[str, str]

    def order(self) -> tuple[int, str, str]:
        return (0 if self.revision_status == "pinned" else 1, self.source_id, self.key)


class EntityIndex:
    """In-memory ID and alias index for one snapshot (a few thousand rows; built once, cached)."""

    def __init__(self, conn: sqlite3.Connection, manifest: SnapshotManifest) -> None:
        self.sources = {s.source_id for s in manifest.sources}
        self.revisions = dict(manifest.source_revisions)
        self._by_id: dict[str, list[EntityRow]] = {}
        self._by_alias: dict[str, list[EntityRow]] = {}
        self.by_key: dict[str, EntityRow] = {}
        rows = conn.execute(
            "SELECT key, need_id, type, title, source_id, path, line_start, line_end, origin, "
            "revision_status, options_json FROM entities"
        ).fetchall()
        for row in rows:
            options = json.loads(row[10])
            entity = EntityRow(
                key=row[0],
                need_id=row[1],
                type=row[2],
                title=row[3],
                source_id=row[4],
                path=row[5],
                line_start=row[6],
                line_end=row[7],
                origin=row[8],
                revision_status=row[9],
                options={str(k): str(v) for k, v in options.items()},
            )
            self.by_key[entity.key] = entity
            self._by_id.setdefault(entity.need_id, []).append(entity)
            self._by_alias.setdefault(alias(entity.need_id), []).append(entity)
        for bucket in (*self._by_id.values(), *self._by_alias.values()):
            bucket.sort(key=EntityRow.order)
        # First chunk (lowest rowid) carrying each entity key: its evidence in results.
        self.first_chunk: dict[str, int] = {
            key: rowid
            for key, rowid in conn.execute(
                "SELECT ce.entity_key, min(c.rowid) FROM chunk_entities ce "
                "JOIN chunks c ON c.chunk_id = ce.chunk_id GROUP BY ce.entity_key"
            )
        }

    def match(self, token: str, source_id: str | None = None) -> list[tuple[EntityRow, MatchKind]]:
        """Verbatim matches, else alias matches; optionally restricted to one source."""
        if source_id is None and ":" in token:
            prefix, _, rest = token.partition(":")
            if prefix in self.sources and rest:
                source_id, token = prefix, rest
        found: list[tuple[EntityRow, MatchKind]] = [
            (e, "exact") for e in self._by_id.get(token, []) if source_id in (None, e.source_id)
        ]
        if not found:
            found = [
                (e, "alias")
                for e in self._by_alias.get(alias(token), [])
                if source_id in (None, e.source_id)
            ]
        return found

    def match_query(self, query: str) -> list[tuple[EntityRow, MatchKind]]:
        """Exact/alias hits for every query token, in query order, without duplicates."""
        seen: set[str] = set()
        hits: list[tuple[EntityRow, MatchKind]] = []
        for token in id_tokens(query):
            for entity, kind in self.match(token):
                if entity.key not in seen:
                    seen.add(entity.key)
                    hits.append((entity, kind))
        return hits

    def record(
        self,
        conn: sqlite3.Connection,
        entity: EntityRow,
        kind: MatchKind,
        excerpt_characters: int,
    ) -> EntityRecord:
        rowid = self.first_chunk.get(entity.key)
        text: str | None = None
        chunk_id: str | None = None
        truncated = False
        if rowid is not None:
            chunk_id, full = conn.execute(
                "SELECT chunk_id, text FROM chunks WHERE rowid = ?", (rowid,)
            ).fetchone()
            text, truncated = excerpt(full, excerpt_characters)
        return EntityRecord(
            key=entity.key,
            need_id=entity.need_id,
            match=kind,
            type=entity.type,
            title=entity.title,
            status=entity.options.get("status"),
            source_id=entity.source_id,
            revision=self.revisions.get(entity.source_id),
            revision_status=entity.revision_status,
            path=entity.path,
            line_start=entity.line_start,
            line_end=entity.line_end,
            origin=entity.origin,
            options=entity.options,
            excerpt=text,
            chunk_id=chunk_id,
            truncated=truncated,
        )

    @staticmethod
    def summary(entity: EntityRow, kind: MatchKind) -> EntitySummary:
        return EntitySummary(
            key=entity.key,
            need_id=entity.need_id,
            match=kind,
            source_id=entity.source_id,
            revision_status=entity.revision_status,
            title=entity.title,
        )


def relationships(
    conn: sqlite3.Connection,
    index: EntityIndex,
    key: str,
    *,
    direction: str = "both",
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, int, list[Relationship]]:
    """(outgoing_total, incoming_total, page) exactly as stored; nothing inferred."""
    if direction not in ("out", "in", "both"):
        raise SearchError("QUERY_INVALID", "direction must be out, in or both")
    if not 1 <= limit <= MAX_RELATIONSHIPS or offset < 0:
        raise SearchError("QUERY_INVALID", f"limit must be 1..{MAX_RELATIONSHIPS}, offset ≥ 0")
    entity = index.by_key.get(key)
    if entity is None:
        raise SearchError("ENTITY_NOT_FOUND", f"no entity {key!r} in this snapshot")
    outgoing = [
        _relationship("out", row)
        for row in conn.execute(
            "SELECT id, from_key, via, target_id, qualifier, resolution, resolved_keys_json, raw "
            "FROM relations WHERE from_key = ? ORDER BY via, target_id, id",
            (key,),
        )
    ]
    incoming = [
        _relationship("in", row)
        for row in conn.execute(
            "SELECT id, from_key, via, target_id, qualifier, resolution, resolved_keys_json, raw "
            "FROM relations WHERE target_id = ? ORDER BY via, from_key, id",
            (entity.need_id,),
        )
        if key in json.loads(row[6])
    ]
    items = (outgoing if direction != "in" else []) + (incoming if direction != "out" else [])
    return len(outgoing), len(incoming), items[offset : offset + limit]


def _relationship(direction: Literal["out", "in"], row: tuple[object, ...]) -> Relationship:
    return Relationship(
        direction=direction,
        from_key=str(row[1]),
        via=str(row[2]),
        target_id=str(row[3]),
        qualifier=None if row[4] is None else str(row[4]),
        resolution=str(row[5]),
        resolved_keys=json.loads(str(row[6])),
        raw=str(row[7]),
    )
