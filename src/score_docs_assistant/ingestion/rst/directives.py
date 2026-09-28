"""Directive implementations that keep untrusted RST inert (FR-011–FR-015; research R2, R6).

None of these reads a file or URL except `SafeInclude`/`SafeLiteralInclude`, which read only
selected files of the same pinned revision tree. Every directive records its exact source span
from `block_text` (verified behaviour, research R2).
"""

from __future__ import annotations

import posixpath
from typing import Any, ClassVar

from docutils import nodes
from docutils.parsers.rst import Directive, directives
from docutils.parsers.rst.directives.tables import CSVTable
from docutils.statemachine import string2lines

from score_docs_assistant.ingestion.decode import decode_document
from score_docs_assistant.ingestion.rst.context import MAX_INCLUDE_DEPTH, ParseContext
from score_docs_assistant.sources.paths import UnsafePathError, ensure_within, safe_relative_path


class need_node(nodes.General, nodes.Element):  # noqa: N801 - docutils node naming convention
    pass


class dynamic_node(nodes.General, nodes.Element):  # noqa: N801
    pass


class raw_excluded_node(nodes.General, nodes.Element):  # noqa: N801
    pass


class generic_node(nodes.General, nodes.Element):  # noqa: N801
    pass


class literal_node(nodes.General, nodes.Element):  # noqa: N801
    pass


class image_node(nodes.General, nodes.Element):  # noqa: N801
    pass


class toctree_node(nodes.General, nodes.Element):  # noqa: N801
    pass


class AnyOption(dict[str, Any]):
    """Accept every option as raw text. Must be truthy: docutils skips option parsing entirely
    for a falsy `option_spec`, which would swallow `:id:` into the title (research R2)."""

    def __bool__(self) -> bool:
        return True

    def __contains__(self, key: object) -> bool:
        return True

    def __getitem__(self, key: str) -> Any:
        return directives.unchanged


def ctx_of(directive: Directive) -> ParseContext:
    ctx: ParseContext = directive.state.document.settings.f002
    return ctx


def span(directive: Directive) -> tuple[str, int, int]:
    source, line = directive.state_machine.get_source_and_line(directive.lineno)
    start = int(line) if line is not None else directive.lineno
    end = start + directive.block_text.rstrip("\n").count("\n")
    return str(source), start, end


def _stamp(node: nodes.Element, directive: Directive) -> None:
    source, start, end = span(directive)
    node["origin_path"] = source
    node["line_start"] = start
    node["line_end"] = end
    node["directive"] = directive.name
    node["argument"] = " ".join(directive.arguments).strip()
    node["options"] = {k: ("" if v is None else str(v)) for k, v in directive.options.items()}


class _Base(Directive):
    has_content = True
    optional_arguments = 1
    final_argument_whitespace = True
    option_spec: ClassVar[AnyOption] = AnyOption()


class NeedDirective(_Base):
    def run(self) -> list[nodes.Node]:
        node = need_node()
        _stamp(node, self)
        self.state.nested_parse(self.content, self.content_offset, node)
        return [node]


class DynamicDirective(_Base):
    def run(self) -> list[nodes.Node]:
        node = dynamic_node()
        _stamp(node, self)
        node["content"] = "\n".join(self.content)
        ctx_of(self).diag(
            "DYNAMIC_NOT_EVALUATED",
            "info",
            node["origin_path"],
            node["line_start"],
            f"dynamic directive {self.name!r} kept as inert text, not evaluated",
        )
        return [node]


class GenericDirective(_Base):
    def run(self) -> list[nodes.Node]:
        node = generic_node()
        _stamp(node, self)
        ctx = ctx_of(self)
        ctx.diag(
            "UNKNOWN_DIRECTIVE",
            "info",
            node["origin_path"],
            node["line_start"],
            f"unknown directive {self.name!r}; content kept",
        )
        if "id" in self.options:
            ctx.diag(
                "POSSIBLE_UNCONFIGURED_NEED",
                "warning",
                node["origin_path"],
                node["line_start"],
                f"directive {self.name!r} has an :id: option but is not a configured need type",
            )
        # Unknown containers (e.g. sphinx-design cards, observed upstream) may carry their own
        # heading. Without match_titles docutils rejects it, and against the surrounding title
        # hierarchy it reports a level skip — either way the heading text would be lost. Parse the
        # body with its own title-style memo (the technique of Sphinx's nested_parse_with_titles).
        memo = self.state.memo
        saved_styles, saved_level = memo.title_styles, memo.section_level
        memo.title_styles, memo.section_level = [], 0
        try:
            self.state.nested_parse(self.content, self.content_offset, node, match_titles=True)
        finally:
            memo.title_styles, memo.section_level = saved_styles, saved_level
        return [node]


class LiteralDirective(_Base):
    """code-block/sourcecode/code and diagram sources: content kept verbatim, never parsed."""

    CODE_NAMES: ClassVar[frozenset[str]] = frozenset({"code", "code-block", "sourcecode"})

    def run(self) -> list[nodes.Node]:
        node = literal_node()
        _stamp(node, self)
        fixed = ctx_of(self).profile.literal_directives.get(self.name)
        node["language"] = node["argument"] or fixed or ""
        node["literal_kind"] = "code" if self.name in self.CODE_NAMES else "diagram"
        node["text"] = "\n".join(self.content)
        return [node]


class RawExcludedDirective(_Base):
    def run(self) -> list[nodes.Node]:
        node = raw_excluded_node()
        _stamp(node, self)
        ctx_of(self).diag(
            "RAW_EXCLUDED",
            "info",
            node["origin_path"],
            node["line_start"],
            f"raw content ({node['argument'] or 'unspecified'}) excluded from normalized text",
        )
        return [node]


class SafeImage(_Base):
    """Keeps URI and caption; the image target is never opened or fetched."""

    has_content = True
    required_arguments = 1
    optional_arguments = 0

    def run(self) -> list[nodes.Node]:
        node = image_node()
        _stamp(node, self)
        ctx_of(self).diag(
            "EXTERNAL_RESOURCE_NOT_READ",
            "info",
            node["origin_path"],
            node["line_start"],
            f"{self.name} target not read: {node['argument']}",
        )
        self.state.nested_parse(self.content, self.content_offset, node)
        return [node]


class SafeCsvTable(Directive):
    """Inline CSV content is parsed by docutils as usual; `:file:`/`:url:` are refused and never
    read (composition rather than subclassing keeps docutils' own table logic unchanged)."""

    has_content = True
    required_arguments = 0
    optional_arguments = 1
    final_argument_whitespace = True
    option_spec = CSVTable.option_spec

    def run(self) -> list[nodes.Node]:
        if "file" in self.options or "url" in self.options:
            node = generic_node()
            _stamp(node, self)
            ctx_of(self).diag(
                "EXTERNAL_RESOURCE_NOT_READ",
                "info",
                node["origin_path"],
                node["line_start"],
                "csv-table :file:/:url: data not read",
            )
            return [node]
        table = CSVTable(
            self.name,
            self.arguments,
            self.options,
            self.content,
            self.lineno,
            self.content_offset,
            self.block_text,
            self.state,
            self.state_machine,
        )
        return list(table.run())


class ToctreeDirective(_Base):
    def run(self) -> list[nodes.Node]:
        node = toctree_node()
        _stamp(node, self)
        node["entries"] = [line.strip() for line in self.content if line.strip()]
        return [node]


class _IncludeBase(_Base):
    required_arguments = 1
    optional_arguments = 0
    has_content = False

    def _refuse(self, reason: str) -> list[nodes.Node]:
        source, start, _ = span(self)
        ctx_of(self).diag(
            "INCLUDE_UNRESOLVED",
            "warning",
            source,
            start,
            f"include {self.arguments[0]!r} not followed: {reason}",
        )
        return []

    def _resolve(self) -> tuple[str, str] | str:
        """Return (target path, text), or a refusal reason."""
        ctx = ctx_of(self)
        argument = self.arguments[0].strip()
        if ctx.include is None:
            return "no acquired source tree available"
        if argument.startswith("<") and argument.endswith(">"):
            return "standard includes are not supported"
        if "url" in self.options or "://" in argument:
            return "URL includes are not allowed"
        if argument.startswith("/"):
            return "absolute paths are not allowed"
        current, _, _ = span(self)
        target = posixpath.normpath(posixpath.join(posixpath.dirname(current), argument))
        try:
            safe_relative_path(target)
        except UnsafePathError:
            return "path escapes the source root"
        if target not in ctx.include.selected:
            return "target is not a selected file of this source"
        chain = ctx.include_chain(current)
        if target in chain:
            return "include cycle"
        if len(chain) > MAX_INCLUDE_DEPTH:
            return f"nesting deeper than {MAX_INCLUDE_DEPTH}"
        try:
            data = ensure_within(ctx.include.root, safe_relative_path(target)).read_bytes()
        except (OSError, UnsafePathError):
            return "target not readable"
        decoded = decode_document(data)
        if decoded.text is None:
            return "target is not valid UTF-8"
        ctx.include_parent[target] = current
        ctx.texts[target] = decoded.text.splitlines()
        return target, decoded.text


class SafeInclude(_IncludeBase):
    def run(self) -> list[nodes.Node]:
        resolved = self._resolve()
        if isinstance(resolved, str):
            return self._refuse(resolved)
        target, text = resolved
        # Register generic handlers for unknown directives/roles in the included text too.
        on_include = getattr(self.state.document.settings, "f002_on_include", None)
        if on_include is not None:
            on_include(text)
        tab_width = self.state.document.settings.tab_width
        self.state_machine.insert_input(string2lines(text, tab_width, True), target)
        return []


class SafeLiteralInclude(_IncludeBase):
    def run(self) -> list[nodes.Node]:
        resolved = self._resolve()
        if isinstance(resolved, str):
            return self._refuse(resolved)
        target, text = resolved
        node = literal_node()
        _stamp(node, self)
        lines = text.splitlines()
        node["origin_path"] = target
        node["line_start"] = 1
        node["line_end"] = max(len(lines), 1)
        node["language"] = str(self.options.get("language", "") or "")
        node["literal_kind"] = "code"
        node["text"] = "\n".join(lines)
        return [node]
