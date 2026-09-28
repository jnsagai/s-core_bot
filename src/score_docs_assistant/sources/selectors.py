"""Include/exclude globs with POSIX path semantics (research.md R8).

`**` (a whole segment) matches zero or more path segments; `*` matches any run of characters
other than `/`; `?` matches one such character. Python 3.12 has no `PurePath.full_match`, and
`fnmatch` lets `*` cross `/`, so neither is used.
"""

from __future__ import annotations

import re

_ALWAYS_EXCLUDED = (".git/**",)


class SelectorError(ValueError):
    pass


def validate_glob(pattern: str) -> str | None:
    """Return a reason the pattern is unsupported, or None if it is valid."""
    if not pattern:
        return "empty pattern"
    if pattern.startswith("/"):
        return "must be relative (no leading '/')"
    if pattern.endswith("/"):
        return "must not end with '/'"
    if "\\" in pattern:
        return "backslashes are not allowed"
    if "[" in pattern or "]" in pattern:
        return "character classes '[...]' are not supported"
    for segment in pattern.split("/"):
        if segment == "":
            return "empty path segment"
        if segment in (".", ".."):
            return f"'{segment}' segments are not allowed"
        if "**" in segment and segment != "**":
            return "'**' must be a whole path segment"
    return None


def _translate_segment(segment: str) -> str:
    out = []
    for char in segment:
        if char == "*":
            out.append("[^/]*")
        elif char == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(char))
    return "".join(out)


def compile_glob(pattern: str) -> re.Pattern[str]:
    reason = validate_glob(pattern)
    if reason is not None:
        raise SelectorError(f"{pattern!r}: {reason}")
    segments = pattern.split("/")
    parts: list[str] = []
    for index, segment in enumerate(segments):
        last = index == len(segments) - 1
        if segment == "**":
            parts.append("(?:[^/]+/)*[^/]+" if last else "(?:[^/]+/)*")
        else:
            parts.append(_translate_segment(segment) + ("" if last else "/"))
    return re.compile("^" + "".join(parts) + "$")


class Selector:
    def __init__(self, include: list[str], exclude: list[str]) -> None:
        self._include = [compile_glob(p) for p in include]
        self._exclude = [compile_glob(p) for p in (*exclude, *_ALWAYS_EXCLUDED)]

    def matches(self, path: str) -> bool:
        if any(p.match(path) for p in self._exclude):
            return False
        return any(p.match(path) for p in self._include)
