"""Typed exceptions with stable codes, shared across CLI and API layers."""

from __future__ import annotations


class ConfigError(Exception):
    """Configuration failed validation. Carries every (dotted path, reason) found."""

    def __init__(self, errors: list[tuple[str, str]], *, code: str = "CONFIG_INVALID") -> None:
        self.errors = errors
        self.code = code
        super().__init__("; ".join(f"{path}: {reason}" for path, reason in errors))


class RuntimeUnreachable(Exception):
    def __init__(self, base_url: str, message: str) -> None:
        self.base_url = base_url
        super().__init__(message)


class RuntimeTimeout(Exception):
    def __init__(self, base_url: str, message: str) -> None:
        self.base_url = base_url
        super().__init__(message)


class RuntimeIncompatible(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)


class BindNotLoopback(Exception):
    def __init__(self, host: str) -> None:
        self.host = host
        super().__init__(
            "Remote exposure requires the public profile, which is not available in this release."
        )


class DiskInsufficient(Exception):
    def __init__(self, required_bytes: int, available_bytes: int) -> None:
        self.required_bytes = required_bytes
        self.available_bytes = available_bytes
        super().__init__(f"Requires {required_bytes} bytes free, only {available_bytes} available.")


class ProfileNotFound(Exception):
    def __init__(self, profile: str) -> None:
        self.profile = profile
        super().__init__(f"Unknown model profile: {profile}")


class SnapshotError(Exception):
    """F003 operational failure with a stable code (specs/003-snapshot-index/data-model.md).

    The CLI maps every SnapshotError to exit 1 and prints `<CODE>: <message>`.
    """

    CODES = frozenset(
        {
            "BUILD_BUSY",
            "REQUIRED_SOURCE_FAILED",
            "CHUNK_UNSPLITTABLE",
            "EMBEDDING_UNAVAILABLE",
            "EMBEDDING_INPUT_TOO_LONG",
            "EMBEDDING_INVALID_VECTOR",
            "SCHEMA_UNSUPPORTED",
            "CHECKSUM_MISMATCH",
            "NOT_ACTIVATABLE",
            "NO_ROLLBACK_TARGET",
            "SNAPSHOT_NOT_FOUND",
            "LICENSE_REVIEW_REQUIRED",
            "BUNDLE_REJECTED",
            "DISK_INSUFFICIENT",
            "CATALOG_UNREADABLE",
            "BUILD_FAILED",
        }
    )

    def __init__(self, code: str, message: str) -> None:
        if code not in self.CODES:
            raise ValueError(f"unknown SnapshotError code {code!r}")
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")
