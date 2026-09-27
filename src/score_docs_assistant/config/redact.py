"""Secret redaction for diagnostic and log output (FR-008).

Three layers, all case-insensitive:
1. URL userinfo (`scheme://user:pass@host` -> `scheme://***@host`).
2. Mapping values whose key (a config path segment or environment variable name) looks
   secret-shaped.
3. Free-text `key=value` / `key: value` fragments inside strings that quote raw input (e.g. an
   error message echoing an environment variable assignment).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

SECRET_KEY_PATTERN = re.compile(
    r"(?i)(secret|token|password|passwd|api[_-]?key|authorization|credential)"
)

_USERINFO_RE = re.compile(r"(://)[^/@\s]+@")
_KV_RE = re.compile(
    r"(?i)([\w.-]*(?:secret|token|password|passwd|api[_-]?key|authorization|credential)[\w.-]*)"
    r"(\s*[=:]\s*)(.+)$",
    re.MULTILINE,
)

MASK = "***"


def redact_url(text: str) -> str:
    return _USERINFO_RE.sub(rf"\1{MASK}@", text)


def redact_text(text: str) -> str:
    text = redact_url(text)
    return _KV_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}{MASK}", text)


def _redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        return redact_mapping(value)
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def redact_mapping(data: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in data.items():
        if SECRET_KEY_PATTERN.search(str(key)):
            result[key] = MASK
        else:
            result[key] = _redact_value(value)
    return result
