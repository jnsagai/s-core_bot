"""Structure-aware chunking of normalized documents (FR-001–FR-005).

Algorithm and rationale: specs/003-snapshot-index/research.md R3. Display text is always verbatim
normalized text; the synthetic context prefix exists only in `embedding_input`. Nothing is ever
truncated: a unit that cannot be split under the budget is kept whole if its embedding input fits
the cap, and otherwise the build fails with CHUNK_UNSPLITTABLE.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from score_docs_assistant.domain.errors import SnapshotError
from score_docs_assistant.domain.ingestion import Block, Entity, NormalizedDocument
from score_docs_assistant.domain.snapshots import Chunk, ChunkerConfig, ChunkKind, chunk_id
from score_docs_assistant.ingestion.canonical import sha256_hex
from score_docs_assistant.ingestion.tokens import estimate_tokens

_VERBATIM_KINDS: dict[str, ChunkKind] = {"code": "code", "literal": "literal", "diagram": "diagram"}
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])")
_MAX_OVERLAP = 100
_SEPARATOR = "\n\n"


def _joined_tokens(token_counts: Sequence[int]) -> int:
    """Exact `pretoken-v1` count of pieces joined by whitespace: pretokens never span whitespace,
    so only the two special tokens are shared."""
    if not token_counts:
        return estimate_tokens("")
    return 2 + sum(t - 2 for t in token_counts)


@dataclass
class _Unit:
    kind: ChunkKind
    heading_path: list[str]
    origin_path: str
    line_start: int | None
    line_end: int | None
    texts: list[str] = field(default_factory=list)
    entity_key: str | None = None
    table_header: list[str] = field(default_factory=list)
    table_body: list[str] = field(default_factory=list)


@dataclass
class _Piece:
    """One future chunk before IDs are assigned."""

    kind: ChunkKind
    text: str
    heading_path: list[str]
    origin_path: str
    line_start: int | None
    line_end: int | None
    entity_keys: list[str]
    continuation: str | None = None
    table_rows: tuple[int, int] | None = None


def _span(blocks: Sequence[Block]) -> tuple[int | None, int | None]:
    starts = [b.line_start for b in blocks if b.line_start is not None]
    ends = [b.line_end for b in blocks if b.line_end is not None]
    return (min(starts) if starts else None, max(ends) if ends else None)


def _descendant_texts(block: Block, nested_needs: list[Block]) -> list[str]:
    """Texts of a need's non-need descendants; nested needs are collected separately."""
    texts: list[str] = []
    for child in block.children:
        if child.kind == "need" and child.entity_key is not None:
            nested_needs.append(child)
            continue
        if child.kind in ("dynamic_view", "raw_excluded"):
            continue
        if child.kind != "section" and child.text.strip():
            texts.append(child.text)
        texts.extend(_descendant_texts(child, nested_needs))
    return texts


class Chunker:
    def __init__(self, config: ChunkerConfig) -> None:
        self._config = config

    # --- unit extraction -------------------------------------------------------------------

    def _units(self, blocks: Sequence[Block]) -> Iterator[_Unit]:
        for block in blocks:
            yield from self._block_units(block)

    def _block_units(self, block: Block) -> Iterator[_Unit]:
        if block.kind == "need" and block.entity_key is not None:
            yield from self._need_units(block)
            return
        if block.kind in ("dynamic_view", "raw_excluded"):
            return
        if block.kind == "table":
            yield self._table_unit(block)
            return
        if block.kind in _VERBATIM_KINDS:
            if block.text.strip():
                yield _Unit(
                    kind=_VERBATIM_KINDS[block.kind],
                    heading_path=list(block.heading_path),
                    origin_path=block.origin_path,
                    line_start=block.line_start,
                    line_end=block.line_end,
                    texts=[block.text],
                )
            return
        if block.kind != "section" and block.text.strip():
            yield _Unit(
                kind="prose",
                heading_path=list(block.heading_path),
                origin_path=block.origin_path,
                line_start=block.line_start,
                line_end=block.line_end,
                texts=[block.text],
            )
        yield from self._units(block.children)

    def _need_units(self, block: Block) -> Iterator[_Unit]:
        nested: list[Block] = []
        options = block.attrs.get("options")
        option_lines = (
            [f":{key}: {value}" for key, value in options.items()]
            if isinstance(options, dict)
            else []
        )
        header = "\n".join([block.text, *option_lines]).strip()
        texts = [header] if header else []
        texts.extend(_descendant_texts(block, nested))
        yield _Unit(
            kind="need",
            heading_path=list(block.heading_path),
            origin_path=block.origin_path,
            line_start=block.line_start,
            line_end=block.line_end,
            texts=texts,
            entity_key=block.entity_key,
        )
        for child in nested:
            yield from self._need_units(child)

    @staticmethod
    def _table_unit(block: Block) -> _Unit:
        rows = block.attrs.get("rows")
        header_count_raw = block.attrs.get("header_rows", "0")
        header_count = int(header_count_raw) if isinstance(header_count_raw, str) else 0
        rendered: list[str] = []
        if isinstance(rows, list):
            for row in rows:
                cells = row if isinstance(row, list) else [str(row)]
                rendered.append(" | ".join(str(c) for c in cells))
        if not rendered and block.text.strip():
            rendered = block.text.split("\n")
        return _Unit(
            kind="table",
            heading_path=list(block.heading_path),
            origin_path=block.origin_path,
            line_start=block.line_start,
            line_end=block.line_end,
            table_header=rendered[:header_count],
            table_body=rendered[header_count:],
        )

    # --- splitting ---------------------------------------------------------------------------

    def _fits_cap(self, text: str) -> bool:
        # Worst case prefix plus the document prefix must still fit (research R3.7).
        budget = self._config.embedding_max_input_tokens - self._config.prefix_max_tokens
        return estimate_tokens(self._config.document_prefix + text) <= budget

    def _check_unsplittable(self, text: str, unit: _Unit, what: str) -> None:
        if not self._fits_cap(text):
            raise SnapshotError(
                "CHUNK_UNSPLITTABLE",
                f"{unit.origin_path}:{unit.line_start or '?'}: a single {what} of "
                f"{estimate_tokens(text)} estimated tokens exceeds the embedding input cap "
                f"{self._config.embedding_max_input_tokens}",
            )

    def _windows(self, parts: list[str]) -> list[list[str]]:
        """Greedy windows of whole parts under `max_tokens`; an oversize part stands alone."""
        max_tokens = self._config.max_tokens
        windows: list[list[str]] = []
        current: list[str] = []
        current_counts: list[int] = []
        for part in parts:
            count = estimate_tokens(part)
            if current and _joined_tokens([*current_counts, count]) > max_tokens:
                windows.append(current)
                current, current_counts = [], []
            current.append(part)
            current_counts.append(count)
        if current:
            windows.append(current)
        return windows

    def _split_words(self, text: str, unit: _Unit) -> list[str]:
        words = text.split()
        pieces = [" ".join(w) for w in self._windows(words)]
        for piece in pieces:
            if estimate_tokens(piece) > self._config.max_tokens:
                self._check_unsplittable(piece, unit, "word")
        return pieces

    def _split_paragraph(self, text: str, unit: _Unit) -> list[str]:
        sentences: list[str] = []
        for sentence in _SENTENCE_BREAK.split(text):
            if estimate_tokens(sentence) > self._config.max_tokens:
                sentences.extend(self._split_words(sentence, unit))
            else:
                sentences.append(sentence)
        pieces: list[str] = []
        index = 0
        max_tokens = self._config.max_tokens
        while index < len(sentences):
            window: list[str] = []
            counts: list[int] = []
            if pieces:
                window, counts = self._overlap(sentences[:index])
            start = index
            while index < len(sentences):
                count = estimate_tokens(sentences[index])
                if index > start and _joined_tokens([*counts, count]) > max_tokens:
                    break
                window.append(sentences[index])
                counts.append(count)
                index += 1
            pieces.append(" ".join(window))
        return pieces

    def _overlap(self, previous: list[str]) -> tuple[list[str], list[int]]:
        chosen: list[str] = []
        counts: list[int] = []
        for sentence in reversed(previous):
            count = estimate_tokens(sentence) - 2
            if sum(counts) + count > _MAX_OVERLAP:
                break
            chosen.insert(0, sentence)
            counts.insert(0, count + 2)
            if sum(c - 2 for c in counts) >= self._config.overlap_tokens:
                break
        return chosen, counts

    def _unit_pieces(self, unit: _Unit) -> list[_Piece]:
        keys = [unit.entity_key] if unit.entity_key else []

        def piece(text: str, **extra: Any) -> _Piece:
            return _Piece(
                kind=unit.kind,
                text=text,
                heading_path=unit.heading_path,
                origin_path=unit.origin_path,
                line_start=unit.line_start,
                line_end=unit.line_end,
                entity_keys=keys,
                **extra,
            )

        max_tokens = self._config.max_tokens
        if unit.kind == "table":
            return self._table_pieces(unit, piece)
        if unit.kind in ("code", "literal", "diagram"):
            text = unit.texts[0]
            if estimate_tokens(text) <= max_tokens:
                return [piece(text)]
            lines = text.split("\n")
            for line in lines:
                if estimate_tokens(line) > max_tokens:
                    self._check_unsplittable(line, unit, "line")
            windows = ["\n".join(w) for w in self._windows(lines)]
            return [piece(w, continuation=f"{i}/{len(windows)}") for i, w in enumerate(windows, 1)]
        # need or prose unit: split at text boundaries, then sentences
        parts: list[str] = []
        for text in unit.texts:
            if estimate_tokens(text) > max_tokens:
                parts.extend(self._split_paragraph(text, unit))
            else:
                parts.append(text)
        windows = [_SEPARATOR.join(w) for w in self._windows(parts)]
        if len(windows) == 1:
            return [piece(windows[0])]
        return [piece(w, continuation=f"{i}/{len(windows)}") for i, w in enumerate(windows, 1)]

    def _table_pieces(self, unit: _Unit, make: Callable[..., _Piece]) -> list[_Piece]:
        header = unit.table_header
        body = unit.table_body
        header_counts = [estimate_tokens(h) for h in header]
        whole = "\n".join([*header, *body])
        if not body or estimate_tokens(whole) <= self._config.max_tokens:
            return [make(whole, table_rows=(0, len(body) - 1) if body else None)]
        pieces: list[_Piece] = []
        start = 0
        while start < len(body):
            counts = list(header_counts)
            end = start
            while end < len(body):
                count = estimate_tokens(body[end])
                if end > start and _joined_tokens([*counts, count]) > self._config.max_tokens:
                    break
                counts.append(count)
                end += 1
            text = "\n".join([*header, *body[start:end]])
            if end - start == 1 and estimate_tokens(text) > self._config.max_tokens:
                self._check_unsplittable(text, unit, "table row")
            pieces.append(make(text, table_rows=(start, end - 1)))
            start = end
        total = len(pieces)
        return [replace(p, continuation=f"{i}/{total}") for i, p in enumerate(pieces, 1)]

    # --- grouping, prefixes, IDs -------------------------------------------------------------

    def _pieces(self, units: Sequence[_Unit]) -> list[_Piece]:
        pieces: list[_Piece] = []
        prose: list[_Unit] = []

        def flush() -> None:
            if not prose:
                return
            merged_texts = [t for u in prose for t in u.texts]
            starts = [u.line_start for u in prose if u.line_start is not None]
            ends = [u.line_end for u in prose if u.line_end is not None]
            group = _Unit(
                kind="prose",
                heading_path=prose[0].heading_path,
                origin_path=prose[0].origin_path,
                line_start=min(starts) if starts else None,
                line_end=max(ends) if ends else None,
            )
            parts: list[str] = []
            for text in merged_texts:
                if estimate_tokens(text) > self._config.max_tokens:
                    parts.extend(self._split_paragraph(text, group))
                else:
                    parts.append(text)
            windows = self._windows(parts)
            total = len(windows)
            for i, window in enumerate(windows, 1):
                pieces.append(
                    _Piece(
                        kind="prose",
                        text=_SEPARATOR.join(window),
                        heading_path=group.heading_path,
                        origin_path=group.origin_path,
                        line_start=group.line_start,
                        line_end=group.line_end,
                        entity_keys=[],
                        continuation=f"{i}/{total}" if total > 1 else None,
                    )
                )
            prose.clear()

        for unit in units:
            if unit.kind == "prose":
                if prose and (
                    prose[0].heading_path != unit.heading_path
                    or prose[0].origin_path != unit.origin_path
                ):
                    flush()
                prose.append(unit)
                continue
            flush()
            pieces.extend(self._unit_pieces(unit))
        flush()
        return pieces

    def _prefix(
        self, document: NormalizedDocument, heading_path: list[str], need_ids: list[str]
    ) -> str:
        title = document.title or document.path
        sections = list(heading_path)
        while True:
            lines = [f"Title: {title}"]
            if sections:
                lines.append("Section: " + " > ".join(sections))
            if need_ids:
                lines.append("IDs: " + " ".join(need_ids))
            lines.append(f"Source: {document.source_id} ({document.format})")
            prefix = "\n".join(lines)
            if estimate_tokens(prefix) <= self._config.prefix_max_tokens:
                return prefix
            # The prefix is synthetic context, so shortening it never drops source content.
            real = [s for s in sections if s != "…"]
            if len(real) > 2:
                real.pop(len(real) // 2)
                sections = [real[0], "…", *real[1:]] if len(real) > 1 else real
            elif len(title) > 16:
                title = title[: len(title) // 2] + "…"
            elif len(need_ids) > 1:
                need_ids = need_ids[:1]
            else:
                return prefix[: self._config.prefix_max_tokens]

    def chunk_document(
        self, document: NormalizedDocument, entity_ids: dict[str, str]
    ) -> list[Chunk]:
        """`entity_ids` maps entity key → need ID (needed for the `IDs:` prefix and FTS)."""
        chunks: list[Chunk] = []
        for ordinal, piece in enumerate(self._pieces(list(self._units(document.blocks)))):
            need_ids = sorted({entity_ids.get(k, k.split(":", 1)[-1]) for k in piece.entity_keys})
            prefix = self._prefix(document, piece.heading_path, need_ids)
            embedding_input = f"{self._config.document_prefix}{prefix}{_SEPARATOR}{piece.text}"
            embedding_tokens = estimate_tokens(embedding_input)
            if embedding_tokens > self._config.embedding_max_input_tokens:
                raise SnapshotError(
                    "CHUNK_UNSPLITTABLE",
                    f"{document.source_id}:{piece.origin_path}:{piece.line_start or '?'}: "
                    f"embedding input of {embedding_tokens} estimated tokens exceeds the cap",
                )
            content_hash = sha256_hex(piece.text.encode("utf-8"))
            chunks.append(
                Chunk(
                    chunk_id=chunk_id(
                        self._config.chunker_version, document.document_key, ordinal, content_hash
                    ),
                    document_key=document.document_key,
                    ordinal=ordinal,
                    source_id=document.source_id,
                    revision=document.revision,
                    path=document.path,
                    origin_path=piece.origin_path,
                    heading_path=piece.heading_path,
                    kind=piece.kind,
                    text=piece.text,
                    embedding_input=embedding_input,
                    line_start=piece.line_start,
                    line_end=piece.line_end,
                    entity_keys=sorted(piece.entity_keys),
                    need_ids=need_ids,
                    continuation=piece.continuation,
                    table_rows=piece.table_rows,
                    token_estimate=estimate_tokens(piece.text),
                    embedding_token_estimate=embedding_tokens,
                    content_hash=content_hash,
                    embedding_input_hash=sha256_hex(embedding_input.encode("utf-8")),
                )
            )
        return chunks

    def chunk_all(
        self, documents: Sequence[NormalizedDocument], entities: Sequence[Entity]
    ) -> list[Chunk]:
        """Corpus order: sources by ID, documents by path (bytewise), then ordinal (FR-005)."""
        entity_ids = {e.key: e.need_id for e in entities}
        ordered = sorted(documents, key=lambda d: (d.source_id, d.path.encode("utf-8")))
        return [c for d in ordered for c in self.chunk_document(d, entity_ids)]
