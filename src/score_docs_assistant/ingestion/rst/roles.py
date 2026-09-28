"""Interpreted-text roles: references recorded, dynamic roles inert, unknown roles kept as text
(FR-012, FR-013, FR-018)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from docutils import nodes
from docutils.parsers.rst.states import Inliner

from score_docs_assistant.ingestion.links import parse_role_target
from score_docs_assistant.ingestion.rst.context import ParseContext

RoleResult = tuple[list[nodes.Node], list[nodes.system_message]]
RoleFn = Callable[..., RoleResult]

# Sphinx cross-reference roles: their text is kept (title or target) but they point to labels
# or documents, not need IDs, so they are not resolved as need links.
SPHINX_TEXT_ROLES = ("ref", "doc", "term", "numref", "any", "abbr", "download", "envvar")


class reference_node(nodes.Inline, nodes.TextElement):  # noqa: N801 - docutils convention
    pass


class dynamic_inline(nodes.Inline, nodes.Element):  # noqa: N801
    """No children, so it contributes no text: a dynamic function's value is never computed."""


def _ctx(inliner: Inliner) -> ParseContext:
    ctx: ParseContext = inliner.document.settings.f002
    return ctx


def _where(inliner: Inliner, lineno: int) -> tuple[str | None, int | None]:
    source, line = inliner.reporter.get_source_and_line(lineno)
    return (str(source) if source else None), (int(line) if line is not None else None)


def reference_role(
    name: str,
    rawtext: str,
    text: str,
    lineno: int,
    inliner: Inliner,
    options: dict[str, Any] | None = None,
    content: Sequence[str] = (),
) -> RoleResult:
    link = parse_role_target(name, text)
    shown = text.split("<", 1)[0].strip() if "<" in text and text.rstrip().endswith(">") else text
    node = reference_node(rawtext, shown or link.target_id)
    node["link"] = link.model_dump(mode="json")
    return [node], []


def sphinx_text_role(
    name: str,
    rawtext: str,
    text: str,
    lineno: int,
    inliner: Inliner,
    options: dict[str, Any] | None = None,
    content: Sequence[str] = (),
) -> RoleResult:
    shown = text.split("<", 1)[0].strip() if "<" in text and text.rstrip().endswith(">") else text
    return [nodes.inline(rawtext, shown)], []


def dynamic_role(
    name: str,
    rawtext: str,
    text: str,
    lineno: int,
    inliner: Inliner,
    options: dict[str, Any] | None = None,
    content: Sequence[str] = (),
) -> RoleResult:
    source, line = _where(inliner, lineno)
    _ctx(inliner).diag(
        "DYNAMIC_NOT_EVALUATED",
        "info",
        source,
        line,
        f"dynamic role {name!r} kept inert, not evaluated: {rawtext[:200]}",
    )
    node = dynamic_inline(rawtext)
    node["raw"] = rawtext
    return [node], []


def generic_role(
    name: str,
    rawtext: str,
    text: str,
    lineno: int,
    inliner: Inliner,
    options: dict[str, Any] | None = None,
    content: Sequence[str] = (),
) -> RoleResult:
    source, line = _where(inliner, lineno)
    _ctx(inliner).diag("UNKNOWN_ROLE", "info", source, line, f"unknown role {name!r}; text kept")
    return [nodes.literal(rawtext, text)], []
