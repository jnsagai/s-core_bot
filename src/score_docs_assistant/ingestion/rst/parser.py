"""RST → normalized blocks and need entities with hardened docutils (FR-010–FR-016; research R2).

docutils keeps module-level directive/role registries. For each parse we register our handlers
(profile-driven need/dynamic/literal/excluded directives, safe replacements for every I/O-capable
built-in, and generic handlers for every unknown name found by a prescan) inside a context manager
that restores the registries afterwards; a module lock serialises parses. Entities are extracted
by a whole-tree pass, independent of block structure, so a need nested anywhere is never lost.
"""

from __future__ import annotations

import hashlib
import re
import threading
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from docutils import nodes
from docutils.parsers.rst import Directive, Parser, directives, roles
from docutils.parsers.rst.languages import en as _english
from docutils.utils import new_document

from score_docs_assistant.domain.ingestion import (
    AttrValue,
    Block,
    BlockKind,
    Entity,
    LinkRef,
    ParseResult,
)
from score_docs_assistant.ingestion.entities import build_entity
from score_docs_assistant.ingestion.rst.context import IncludeContext, ParseContext
from score_docs_assistant.ingestion.rst.directives import (
    DynamicDirective,
    GenericDirective,
    LiteralDirective,
    NeedDirective,
    RawExcludedDirective,
    SafeCsvTable,
    SafeImage,
    SafeInclude,
    SafeLiteralInclude,
    ToctreeDirective,
    dynamic_node,
    generic_node,
    image_node,
    literal_node,
    need_node,
    raw_excluded_node,
    toctree_node,
)
from score_docs_assistant.ingestion.rst.roles import (
    SPHINX_TEXT_ROLES,
    RoleFn,
    dynamic_inline,
    dynamic_role,
    generic_role,
    reference_node,
    reference_role,
    sphinx_text_role,
)
from score_docs_assistant.ingestion.rst.settings import hardened_settings
from score_docs_assistant.sources.profile import ParserProfile

__all__ = ["IncludeContext", "RstParser"]

_LOCK = threading.Lock()
# Directives may also start inside grid-table cells (`| .. centered:: …`, observed upstream);
# over-matching only registers a harmless generic handler.
_DIRECTIVE_NAME = re.compile(
    r"(?:^|\|)[ \t]*\.\.[ \t]+([A-Za-z0-9][A-Za-z0-9_:+.-]*)[ \t]*::", re.M
)
_ROLE_NAME = re.compile(r":([A-Za-z0-9][A-Za-z0-9_+.-]*(?::[A-Za-z0-9][A-Za-z0-9_+.-]*)*):`")
_SKIPPED = (
    nodes.comment,
    nodes.target,
    nodes.substitution_definition,
    nodes.pending,
    nodes.system_message,
    nodes.decoration,
    nodes.transition,
    nodes.title,
)


# docutils' registries are private module-level dicts absent from the type stubs; `vars()` gives
# typed references to the very same dict objects.
_DIRECTIVES: dict[str, Any] = vars(directives)["_directives"]
_DIRECTIVE_REGISTRY: dict[str, Any] = vars(directives)["_directive_registry"]
_ROLES: dict[str, Any] = vars(roles)["_roles"]
_ROLE_REGISTRY: dict[str, Any] = vars(roles)["_role_registry"]


def _known_directive(name: str) -> bool:
    return name in _DIRECTIVES or name in _DIRECTIVE_REGISTRY or name in _english.directives


def _known_role(name: str) -> bool:
    return name in _ROLES or name in _ROLE_REGISTRY or name in _english.roles


@contextmanager
def _registries(
    directive_map: dict[str, type[Directive]], role_map: dict[str, RoleFn]
) -> Iterator[None]:
    saved_directives = dict(_DIRECTIVES)
    saved_roles = dict(_ROLES)
    try:
        _DIRECTIVES.update(directive_map)
        _ROLES.update(role_map)
        yield
    finally:
        _DIRECTIVES.clear()
        _DIRECTIVES.update(saved_directives)
        _ROLES.clear()
        _ROLES.update(saved_roles)


def _register_unknown(text: str) -> None:
    """Called inside `_registries`: generic handlers for names docutils would reject."""
    for name in set(_DIRECTIVE_NAME.findall(text)):
        if not _known_directive(name):
            _DIRECTIVES[name] = GenericDirective
    for name in set(_ROLE_NAME.findall(text)):
        if not _known_role(name):
            _ROLES[name] = generic_role


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _ancestors(node: nodes.Node, stop: nodes.Node) -> Iterator[nodes.Node]:
    current = node.parent
    while current is not None and current is not stop:
        yield current
        current = current.parent


def _text(node: nodes.Node) -> str:
    """Normalized text, skipping system messages and dynamic (never-evaluated) inline content."""
    parts = [
        t.astext()
        for t in node.findall(nodes.Text)
        if not any(
            isinstance(a, nodes.system_message | dynamic_inline) for a in _ancestors(t, node)
        )
    ]
    return " ".join("".join(parts).split())


def _is_adornment(line: str) -> bool:
    stripped = line.strip()
    return len(stripped) >= 2 and len(set(stripped)) == 1 and not stripped[0].isalnum()


class _Walker:
    def __init__(self, ctx: ParseContext) -> None:
        self.ctx = ctx

    # -- spans ---------------------------------------------------------------------------------

    def _origin(self, node: nodes.Element) -> str:
        return str(node.get("origin_path") or node.source or self.ctx.path)

    def _span(self, node: nodes.Element) -> tuple[int | None, int | None]:
        if "line_start" in node.attributes:
            return int(node["line_start"]), int(node["line_end"])
        start = node.line
        if start is None:
            return None, None
        raw = getattr(node, "rawsource", "") or ""
        return start, start + raw.rstrip("\n").count("\n")

    def _section_start(self, title: nodes.title) -> int | None:
        # docutils reports a section title's *underline* line; find the title text above it,
        # and an overline above that if present (behaviour verified in research R2).
        line = title.line
        lines = self.ctx.texts.get(self._origin(title))
        if line is None or lines is None:
            return line
        wanted = " ".join((title.rawsource or title.astext()).split())
        for candidate in (line - 1, line, line - 2):
            if 1 <= candidate <= len(lines) and " ".join(lines[candidate - 1].split()) == wanted:
                above = candidate - 1
                if above >= 1 and _is_adornment(lines[above - 1]):
                    return above
                return candidate
        return line

    def _raw_sha(self, origin: str, start: int | None, end: int | None, fallback: str) -> str:
        lines = self.ctx.texts.get(origin)
        if lines is not None and start is not None and end is not None:
            return _sha("\n".join(lines[start - 1 : end]))
        return _sha(fallback)

    def _block(
        self,
        kind: BlockKind,
        node: nodes.Element,
        heading_path: list[str],
        text: str,
        *,
        children: list[Block] | None = None,
        attrs: dict[str, AttrValue] | None = None,
        references: list[LinkRef] | None = None,
        start: int | None = None,
        end: int | None = None,
        entity_key: str | None = None,
    ) -> Block:
        kids = children or []
        span_start, span_end = self._span(node)
        start = start if start is not None else span_start
        end = end if end is not None else span_end
        if start is None and kids:
            start = next((k.line_start for k in kids if k.line_start is not None), None)
        ends = [
            k.line_end
            for k in kids
            if k.line_end is not None and k.origin_path == kids[0].origin_path
        ]
        if ends and (end is None or max(ends) > end) and self._origin(node) == kids[0].origin_path:
            end = max(ends)
        if start is not None and (end is None or end < start):
            end = start
        origin = self._origin(node)
        return Block(
            kind=kind,
            text=text,
            heading_path=list(heading_path),
            line_start=start,
            line_end=end,
            origin_path=origin,
            raw_sha256=self._raw_sha(origin, start, end, text),
            attrs=attrs or {},
            references=references or [],
            children=kids,
            entity_key=entity_key,
        )

    @staticmethod
    def _refs(node: nodes.Node) -> list[LinkRef]:
        return [LinkRef.model_validate(n["link"]) for n in node.findall(reference_node)]

    # -- conversion ----------------------------------------------------------------------------

    def convert(self, children: list[nodes.Node], heading_path: list[str]) -> list[Block]:
        blocks: list[Block] = []
        for child in children:
            blocks.extend(self.node(child, heading_path))
        return blocks

    def _directive_attrs(self, node: nodes.Element) -> dict[str, AttrValue]:
        return {
            "directive": str(node["directive"]),
            "argument": str(node["argument"]),
            "options": dict(node["options"]),
        }

    def node(self, node: nodes.Node, hp: list[str]) -> list[Block]:  # noqa: C901, PLR0911, PLR0912
        if not isinstance(node, nodes.Element) or isinstance(node, _SKIPPED):
            return []
        if isinstance(node, need_node):
            return [
                self._block(
                    "need",
                    node,
                    hp,
                    str(node["argument"]),
                    children=self.convert(node.children, hp),
                    attrs=self._directive_attrs(node),
                    entity_key=node.get("entity_key"),
                )
            ]
        if isinstance(node, dynamic_node):
            attrs = self._directive_attrs(node)
            attrs["content"] = str(node["content"])
            return [self._block("dynamic_view", node, hp, "", attrs=attrs)]
        if isinstance(node, raw_excluded_node):
            return [self._block("raw_excluded", node, hp, "", attrs=self._directive_attrs(node))]
        if isinstance(node, generic_node):
            return [
                self._block(
                    "generic_directive",
                    node,
                    hp,
                    str(node["argument"]),
                    children=self.convert(node.children, hp),
                    attrs=self._directive_attrs(node),
                )
            ]
        if isinstance(node, literal_node):
            kind: BlockKind = "code" if node["literal_kind"] == "code" else "diagram"
            attrs = {"language": str(node["language"]), "directive": str(node["directive"])}
            return [self._block(kind, node, hp, str(node["text"]), attrs=attrs)]
        if isinstance(node, image_node):
            caption = " ".join(_text(c) for c in node.children if _text(c))
            alt = str(node["options"].get("alt", ""))
            attrs = {"uri": str(node["argument"]), "alt": alt, "directive": str(node["directive"])}
            return [self._block("image", node, hp, caption or alt, attrs=attrs)]
        if isinstance(node, toctree_node):
            entries = [str(e) for e in node["entries"]]
            return [
                self._block("toctree", node, hp, "\n".join(entries), attrs={"entries": entries})
            ]
        if isinstance(node, nodes.section):
            title = node.next_node(nodes.title)
            heading = _text(title) if title is not None else ""
            body = self.convert(node.children, [*hp, heading])
            start = self._section_start(title) if title is not None else None
            return [
                self._block("section", node, hp, heading, children=body, start=start, end=start)
            ]
        if isinstance(node, nodes.paragraph | nodes.rubric | nodes.line_block):
            text = _text(node)
            return (
                [self._block("paragraph", node, hp, text, references=self._refs(node))]
                if text
                else []
            )
        if isinstance(node, nodes.literal_block | nodes.doctest_block | nodes.math_block):
            return [self._block("literal", node, hp, node.astext(), attrs={"language": ""})]
        if isinstance(node, nodes.bullet_list | nodes.enumerated_list):
            items = [
                self._list_item(item, hp, list(item.children))
                for item in node.children
                if isinstance(item, nodes.Element)
            ]
            ordered = "true" if isinstance(node, nodes.enumerated_list) else "false"
            return [self._block("list", node, hp, "", children=items, attrs={"ordered": ordered})]
        if isinstance(node, nodes.definition_list):
            definitions: list[Block] = []
            for item in node.children:
                if not isinstance(item, nodes.Element):
                    continue
                term = item.next_node(nodes.term)
                definition = item.next_node(nodes.definition)
                item_body = list(definition.children) if definition is not None else []
                label = _text(term) if term is not None else ""
                definitions.append(self._list_item(item, hp, item_body, text=label))
            return [self._block("definition_list", node, hp, "", children=definitions)]
        if isinstance(node, nodes.field_list):
            fields = [
                [_text(field_name), _text(field_body)]
                for f in node.children
                if isinstance(f, nodes.field)
                and (field_name := f.next_node(nodes.field_name)) is not None
                and (field_body := f.next_node(nodes.field_body)) is not None
            ]
            text = "\n".join(f"{name}: {body}" for name, body in fields)
            return [
                self._block(
                    "field_list",
                    node,
                    hp,
                    text,
                    attrs={"fields": fields},
                    references=self._refs(node),
                )
            ]
        if isinstance(node, nodes.table):
            return [self._table(node, hp)]
        if isinstance(node, nodes.Admonition):
            title = node.next_node(nodes.title)
            label = _text(title) if title is not None else ""
            body = self.convert([c for c in node.children if c is not title], hp)
            return [
                self._block(
                    "admonition", node, hp, label, children=body, attrs={"admonition": node.tagname}
                )
            ]
        if isinstance(node, nodes.block_quote):
            return [
                self._block("block_quote", node, hp, "", children=self.convert(node.children, hp))
            ]
        if isinstance(node, nodes.image):
            alt = str(node.get("alt", ""))
            return [self._block("image", node, hp, alt, attrs={"uri": str(node.get("uri", ""))})]
        if isinstance(node, nodes.TextElement):
            text = _text(node)
            return (
                [self._block("paragraph", node, hp, text, references=self._refs(node))]
                if text
                else []
            )
        return self.convert(node.children, hp)

    def _list_item(
        self, item: nodes.Element, hp: list[str], body: list[nodes.Node], text: str = ""
    ) -> Block:
        return self._block("list_item", item, hp, text, children=self.convert(body, hp))

    def _table(self, node: nodes.table, hp: list[str]) -> Block:
        rows: list[list[str]] = []
        header_rows = 0
        tgroup = node.next_node(nodes.tgroup)
        if tgroup is not None:
            for part in tgroup.children:
                if isinstance(part, nodes.thead | nodes.tbody):
                    for row in part.children:
                        rows.append([_text(entry) for entry in row.children])
                        if isinstance(part, nodes.thead):
                            header_rows += 1
        caption_node = node.next_node(nodes.title)
        attrs: dict[str, AttrValue] = {"rows": rows, "header_rows": str(header_rows)}
        if caption_node is not None:
            attrs["caption"] = _text(caption_node)
        lines = [
            p.line + (p.rawsource or "").rstrip("\n").count("\n")
            for p in node.findall(nodes.paragraph)
            if p.line
        ]
        text = "\n".join(" | ".join(row) for row in rows)
        return self._block(
            "table",
            node,
            hp,
            text,
            attrs=attrs,
            references=self._refs(node),
            end=max(lines) if lines else None,
        )


class RstParser:
    """`DocumentParser` for RST (master spec §5.1)."""

    def __init__(self, profile: ParserProfile) -> None:
        self._profile = profile

    def _directive_map(self) -> dict[str, type[Directive]]:
        profile = self._profile
        mapping: dict[str, type[Directive]] = {
            "include": SafeInclude,
            "literalinclude": SafeLiteralInclude,
            "image": SafeImage,
            "figure": SafeImage,
            "csv-table": SafeCsvTable,
            "toctree": ToctreeDirective,
            "raw": RawExcludedDirective,  # regardless of profile: raw is never enabled
        }
        for name in {*profile.literal_directives, *LiteralDirective.CODE_NAMES}:
            mapping[name] = LiteralDirective
        for name in profile.excluded_directives:
            mapping[name] = RawExcludedDirective
        for name in profile.dynamic_directives:
            mapping[name] = DynamicDirective
        for name in profile.need_types:  # need types win, e.g. S-CORE `role` vs docutils `role`
            mapping[name] = NeedDirective
        return mapping

    def _role_map(self) -> dict[str, RoleFn]:
        mapping: dict[str, RoleFn] = dict.fromkeys(SPHINX_TEXT_ROLES, sphinx_text_role)
        mapping.update(dict.fromkeys(self._profile.dynamic_roles, dynamic_role))
        mapping.update(dict.fromkeys(self._profile.reference_roles, reference_role))
        return mapping

    def parse(
        self,
        *,
        source_id: str,
        revision: str,
        path: str,
        text: str,
        document_key: str,
        include_context: IncludeContext | None = None,
        id_counter: Counter[str] | None = None,
    ) -> ParseResult:
        ctx = ParseContext(
            source_id=source_id,
            path=path,
            profile=self._profile,
            include=include_context,
            texts={path: text.splitlines()},
        )
        with _LOCK, _registries(self._directive_map(), self._role_map()):
            _register_unknown(text)
            document = self._doctree(text, path, ctx)
        entities = self._entities(document, ctx, document_key, id_counter or Counter())
        blocks = _Walker(ctx).convert(document.children, [])
        title = next((b.text for b in blocks if b.kind == "section"), None)
        return ParseResult(
            title=title, blocks=blocks, entities=entities, diagnostics=list(ctx.diagnostics)
        )

    @staticmethod
    def _doctree(text: str, path: str, ctx: ParseContext) -> nodes.document:
        settings = hardened_settings()
        settings.f002 = ctx
        settings.f002_on_include = _register_unknown
        document = new_document(path, settings)

        def observe(message: nodes.system_message) -> None:
            if message["level"] >= 3:
                ctx.diag(
                    "PARSE_ERROR",
                    "warning",
                    message.get("source"),
                    message.get("line"),
                    " ".join(message.astext().split())[:300],
                )

        document.reporter.attach_observer(observe)
        Parser().parse(text, document)
        return document

    def _entities(
        self,
        document: nodes.document,
        ctx: ParseContext,
        document_key: str,
        id_counter: Counter[str],
    ) -> list[Entity]:
        link_options = set(self._profile.link_options)
        entities: list[Entity] = []
        for node in document.findall(need_node):
            entity = build_entity(
                source_id=ctx.source_id,
                need_type=str(node["directive"]),
                title=str(node["argument"]),
                options=dict(node["options"]),
                link_options=link_options,
                document_key=document_key,
                path=str(node["origin_path"]),
                line_start=int(node["line_start"]),
                line_end=int(node["line_end"]),
                id_counter=id_counter,
                diag=ctx.diag,
                origin="rst",
            )
            if entity is not None:
                node["entity_key"] = entity.key
                entities.append(entity)
        return entities
