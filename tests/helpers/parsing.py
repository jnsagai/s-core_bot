"""Helpers for parser tests: parse a snippet with the committed S-CORE profile."""

from __future__ import annotations

import textwrap
from collections.abc import Iterator
from pathlib import Path

from score_docs_assistant.domain.ingestion import Block, ParseResult
from score_docs_assistant.ingestion.rst.parser import IncludeContext, RstParser
from score_docs_assistant.sources.profile import ParserProfile, load_profile

PROFILE_PATH = Path(__file__).parent.parent.parent / "config" / "parser-profiles" / "s-core.yaml"


def profile() -> ParserProfile:
    return load_profile(PROFILE_PATH)


def parse_rst(
    text: str,
    *,
    path: str = "docs/test.rst",
    source_id: str = "src",
    include_context: IncludeContext | None = None,
    dedent: bool = True,
) -> ParseResult:
    body = textwrap.dedent(text).lstrip("\n") if dedent else text
    return RstParser(profile()).parse(
        source_id=source_id,
        revision="r" * 40,
        path=path,
        text=body,
        document_key="k" * 64,
        include_context=include_context,
    )


def walk(blocks: list[Block]) -> Iterator[Block]:
    for block in blocks:
        yield block
        yield from walk(block.children)


def kinds(result: ParseResult) -> list[str]:
    return [b.kind for b in walk(result.blocks)]


def codes(result: ParseResult) -> list[str]:
    return [d.code for d in result.diagnostics]
