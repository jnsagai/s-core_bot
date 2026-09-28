"""Path safety for files written from untrusted repository trees (FR-006, plan Key Design 2).

git's `transfer.fsckObjects` already rejects malformed trees at fetch time; these checks are the
second, independent layer applied before every write.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

_MAX_SEGMENT_BYTES = 255
_MAX_PATH_BYTES = 4096


class UnsafePathError(ValueError):
    pass


def safe_relative_path(path: str) -> PurePosixPath:
    if not path:
        raise UnsafePathError("empty path")
    if "\x00" in path:
        raise UnsafePathError("NUL byte in path")
    if "\\" in path:
        raise UnsafePathError("backslash in path")
    if path.startswith("/"):
        raise UnsafePathError("absolute path")
    if path.endswith("/"):
        raise UnsafePathError("trailing slash")
    if len(path.encode("utf-8")) > _MAX_PATH_BYTES:
        raise UnsafePathError("path too long")
    for segment in path.split("/"):
        if segment in ("", ".", ".."):
            raise UnsafePathError(f"forbidden path segment {segment!r}")
        if len(segment.encode("utf-8")) > _MAX_SEGMENT_BYTES:
            raise UnsafePathError("path segment too long")
    return PurePosixPath(path)


def ensure_within(root: Path, relative: PurePosixPath) -> Path:
    """Return `root / relative` after proving no existing component is a symlink and the result
    resolves inside `root`."""
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise UnsafePathError(f"symlink in path: {relative}")
    target = root / Path(*relative.parts)
    if not target.resolve(strict=False).is_relative_to(root.resolve()):
        raise UnsafePathError(f"path escapes root: {relative}")
    return target
