"""Markdown → normalized blocks with markdown-it-py (FR-010, FR-011, FR-013, FR-016; research R4).

`html=True` is used only so raw HTML surfaces as `html_block`/`html_inline` tokens, which are
*excluded* with a diagnostic; nothing is ever rendered. Headings become nested sections.

MyST backtick-fenced directives (```` ```{dec_rec} Title ````, observed upstream in `DR-*.md`) get
the same profile-driven meaning as RST directives: need types become entities, dynamic ones stay
inert, unknown ones are kept generically. Options are the leading `:key: value` lines; the rest is
a Markdown body parsed with absolute line numbers. Without a profile, fences are plain code.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field

from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode

from score_docs_assistant.domain.ingestion import (
    AttrValue,
    Block,
    BlockKind,
    Diagnostic,
    Entity,
    ParseResult,
    Severity,
)
from score_docs_assistant.ingestion.entities import build_entity
from score_docs_assistant.sources.profile import ParserProfile

_MYST = re.compile(r"^\{([A-Za-z0-9][A-Za-z0-9_:+.-]*)\}\s*(.*)$")
_OPTION = re.compile(r"^:([A-Za-z0-9_+.-]+):(?:\s+(.*))?$")
_CODE_NAMES = frozenset({"code", "code-block", "sourcecode"})


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class _Draft:
    kind: BlockKind
    text: str
    heading_path: list[str]
    start: int | None
    end: int | None
    attrs: dict[str, AttrValue] = field(default_factory=dict)
    children: list[_Draft] = field(default_factory=list)
    entity_key: str | None = None


class MarkdownParser:
    """`DocumentParser` for Markdown (CommonMark + tables + MyST backtick directives)."""

    def __init__(self, profile: ParserProfile | None = None) -> None:
        self._profile = profile
        self._md = MarkdownIt("commonmark", {"html": True}).enable("table")

    def parse(
        self,
        *,
        source_id: str,
        revision: str,
        path: str,
        text: str,
        document_key: str,
        id_counter: Counter[str] | None = None,
    ) -> ParseResult:
        state = _State(
            md=self._md,
            profile=self._profile,
            source_id=source_id,
            path=path,
            document_key=document_key,
            lines=text.splitlines(),
            id_counter=id_counter if id_counter is not None else Counter(),
        )
        drafts = state.convert_top(SyntaxTreeNode(self._md.parse(text)).children)
        blocks = [state.freeze(d) for d in drafts]
        title = next((b.text for b in blocks if b.kind == "section"), None)
        return ParseResult(
            title=title, blocks=blocks, entities=state.entities, diagnostics=state.diagnostics
        )


@dataclass
class _State:
    md: MarkdownIt
    profile: ParserProfile | None
    source_id: str
    path: str
    document_key: str
    lines: list[str]
    id_counter: Counter[str]
    diagnostics: list[Diagnostic] = field(default_factory=list)
    entities: list[Entity] = field(default_factory=list)
    line_offset: int = 0

    def diag(
        self, code: str, severity: Severity, path: str | None, line: int | None, msg: str
    ) -> None:
        self.diagnostics.append(
            Diagnostic(
                code=code,
                severity=severity,
                source_id=self.source_id,
                path=path or self.path,
                line=line,
                message=msg,
            )
        )

    def _span(self, node: SyntaxTreeNode) -> tuple[int | None, int | None]:
        if node.map is None:
            return None, None
        start, end = node.map  # 0-based, end exclusive, relative to the parsed text
        return start + 1 + self.line_offset, max(end, start + 1) + self.line_offset

    def _inline_text(self, node: SyntaxTreeNode, line: int | None) -> str:
        parts: list[str] = []
        for child in node.children:
            for token in child.walk():
                if token.type == "html_inline":
                    self.diag("RAW_EXCLUDED", "info", None, line, "inline HTML excluded")
                elif token.type in ("text", "code_inline"):
                    parts.append(token.content)
                elif token.type in ("softbreak", "hardbreak"):
                    parts.append(" ")
        return " ".join("".join(parts).split())

    def _leaf_text(self, node: SyntaxTreeNode) -> str:
        start, _ = self._span(node)
        inline = next((c for c in node.children if c.type == "inline"), None)
        return self._inline_text(inline, start) if inline is not None else ""

    def convert_top(self, nodes: list[SyntaxTreeNode]) -> list[_Draft]:
        """Top level: headings open nested sections (a heading closes deeper/equal ones)."""
        root: list[_Draft] = []
        stack: list[tuple[int, _Draft]] = []
        for node in nodes:
            if node.type == "heading":
                level = int(node.tag[1])
                while stack and stack[-1][0] >= level:
                    stack.pop()
                heading_path = [d.text for _, d in stack]
                start, end = self._span(node)
                section = _Draft("section", self._leaf_text(node), heading_path, start, end)
                (stack[-1][1].children if stack else root).append(section)
                stack.append((level, section))
                continue
            target = stack[-1][1].children if stack else root
            target.extend(self.convert(node, [d.text for _, d in stack]))
        return root

    def convert(self, node: SyntaxTreeNode, hp: list[str]) -> list[_Draft]:  # noqa: PLR0911
        start, end = self._span(node)
        if node.type == "paragraph":
            text = self._leaf_text(node)
            return [_Draft("paragraph", text, hp, start, end)] if text else []
        if node.type == "fence" and self.profile is not None:
            directive = _MYST.match((node.info or "").strip())
            if directive:
                return [self._directive(directive.group(1), directive.group(2), node, hp)]
        if node.type in ("fence", "code_block"):
            language = (node.info or "").split()[0] if node.type == "fence" and node.info else ""
            return [
                _Draft("code", node.content.rstrip("\n"), hp, start, end, {"language": language})
            ]
        if node.type in ("bullet_list", "ordered_list"):
            items = [
                _Draft("list_item", "", hp, *self._span(item), children=self._children(item, hp))
                for item in node.children
            ]
            ordered = "true" if node.type == "ordered_list" else "false"
            return [_Draft("list", "", hp, start, end, {"ordered": ordered}, items)]
        if node.type == "blockquote":
            return [_Draft("block_quote", "", hp, start, end, children=self._children(node, hp))]
        if node.type == "table":
            return [self._table(node, hp, start, end)]
        if node.type == "html_block":
            self.diag("RAW_EXCLUDED", "info", None, start, "HTML block excluded")
            return [_Draft("raw_excluded", "", hp, start, end, {"format": "html"})]
        if node.type == "heading":  # nested heading (e.g. inside a directive body): keep text
            return [_Draft("paragraph", self._leaf_text(node), hp, start, end)]
        return []  # hr and other purely presentational tokens

    def _children(self, node: SyntaxTreeNode, hp: list[str]) -> list[_Draft]:
        drafts: list[_Draft] = []
        for child in node.children:
            drafts.extend(self.convert(child, hp))
        return drafts

    def _nested(self, text: str, first_line: int, hp: list[str]) -> list[_Draft]:
        saved = self.line_offset
        self.line_offset = first_line - 1
        try:
            drafts: list[_Draft] = []
            for child in SyntaxTreeNode(self.md.parse(text)).children:
                drafts.extend(self.convert(child, hp))
            return drafts
        finally:
            self.line_offset = saved

    def _directive(  # noqa: PLR0911
        self, name: str, argument: str, node: SyntaxTreeNode, hp: list[str]
    ) -> _Draft:
        profile = self.profile
        if profile is None:  # the caller only dispatches here with a profile
            raise RuntimeError("MyST directive handling requires a parser profile")
        start, end = self._span(node)
        lines = node.content.split("\n")
        options: dict[str, str] = {}
        index = 0
        while index < len(lines) and (option := _OPTION.match(lines[index])):
            key, value = option.group(1), option.group(2) or ""
            index += 1
            while index < len(lines) and lines[index][:1] in (" ", "\t") and lines[index].strip():
                value += "\n" + lines[index].strip()
                index += 1
            options[key] = value
        while index < len(lines) and not lines[index].strip():
            index += 1
        body_lines = lines[index:]
        body = "\n".join(body_lines).rstrip("\n")
        body_first_line = (start or 0) + 1 + index
        attrs: dict[str, AttrValue] = {"directive": name, "argument": argument, "options": options}

        if name in profile.need_types:
            entity = build_entity(
                source_id=self.source_id,
                need_type=name,
                title=argument,
                options=options,
                link_options=set(profile.link_options),
                document_key=self.document_key,
                path=self.path,
                line_start=start,
                line_end=end,
                id_counter=self.id_counter,
                diag=self.diag,
                origin="markdown",
            )
            if entity is not None:
                self.entities.append(entity)
            children = self._nested(body, body_first_line, hp)
            key = entity.key if entity is not None else None
            return _Draft("need", argument, hp, start, end, attrs, children, entity_key=key)
        if name in profile.literal_directives or name in _CODE_NAMES:
            kind: BlockKind = "code" if name in _CODE_NAMES else "diagram"
            fixed = profile.literal_directives.get(name)
            language = argument or fixed or ""
            return _Draft(kind, body, hp, start, end, {"language": language, "directive": name})
        if name == "toctree":
            entries = [line.strip() for line in body_lines if line.strip()]
            return _Draft("toctree", "\n".join(entries), hp, start, end, {"entries": entries})
        if name in profile.dynamic_directives:
            self.diag(
                "DYNAMIC_NOT_EVALUATED",
                "info",
                None,
                start,
                f"dynamic directive {name!r} kept as inert text, not evaluated",
            )
            attrs["content"] = body
            return _Draft("dynamic_view", "", hp, start, end, attrs)
        if name in profile.excluded_directives or name == "raw":
            self.diag("RAW_EXCLUDED", "info", None, start, "raw directive content excluded")
            return _Draft("raw_excluded", "", hp, start, end, attrs)
        self.diag("UNKNOWN_DIRECTIVE", "info", None, start, f"unknown directive {name!r}")
        if "id" in options:
            self.diag(
                "POSSIBLE_UNCONFIGURED_NEED",
                "warning",
                None,
                start,
                f"directive {name!r} has an :id: option but is not a configured need type",
            )
        children = self._nested(body, body_first_line, hp)
        return _Draft("generic_directive", argument, hp, start, end, attrs, children)

    def _table(
        self, node: SyntaxTreeNode, hp: list[str], start: int | None, end: int | None
    ) -> _Draft:
        rows: list[list[str]] = []
        header_rows = 0
        for part in node.children:
            for row in part.children:
                cells = []
                for cell in row.children:
                    inline = next((c for c in cell.children if c.type == "inline"), None)
                    cells.append(self._inline_text(inline, start) if inline is not None else "")
                rows.append(cells)
                if part.type == "thead":
                    header_rows += 1
        text = "\n".join(" | ".join(r) for r in rows)
        attrs: dict[str, AttrValue] = {"rows": rows, "header_rows": str(header_rows)}
        return _Draft("table", text, hp, start, end, attrs)

    def freeze(self, draft: _Draft) -> Block:
        children = [self.freeze(c) for c in draft.children]
        start, end = draft.start, draft.end
        ends = [c.line_end for c in children if c.line_end is not None]
        if ends and (end is None or max(ends) > end):
            end = max(ends)
        raw = (
            "\n".join(self.lines[start - 1 : end])
            if start is not None and end is not None
            else draft.text
        )
        return Block(
            kind=draft.kind,
            text=draft.text,
            heading_path=draft.heading_path,
            line_start=start,
            line_end=end,
            origin_path=self.path,
            raw_sha256=_sha(raw),
            attrs=draft.attrs,
            children=children,
            entity_key=draft.entity_key,
        )
