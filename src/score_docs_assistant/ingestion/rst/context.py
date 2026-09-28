"""Per-parse state shared by our directives, roles and the doctree walker.

Attached to the docutils document as `document.settings.f002` for the duration of one parse.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from score_docs_assistant.domain.ingestion import Diagnostic, Severity
from score_docs_assistant.sources.profile import ParserProfile

MAX_INCLUDE_DEPTH = 8


@dataclass(frozen=True)
class IncludeContext:
    """The acquired revision tree an include may read from, and the files selected in it."""

    root: Path
    selected: set[str]


@dataclass
class ParseContext:
    source_id: str
    path: str
    profile: ParserProfile
    include: IncludeContext | None
    texts: dict[str, list[str]]
    diagnostics: list[Diagnostic] = field(default_factory=list)
    include_parent: dict[str, str] = field(default_factory=dict)

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

    def include_chain(self, current: str) -> list[str]:
        chain = [current]
        while chain[-1] in self.include_parent:
            chain.append(self.include_parent[chain[-1]])
        return chain
