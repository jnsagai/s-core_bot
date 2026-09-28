"""Strict UTF-8 decoding: invalid bytes fail the file instead of being silently replaced."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DecodeResult:
    text: str | None
    codes: list[str] = field(default_factory=list)


def decode_document(data: bytes) -> DecodeResult:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return DecodeResult(text=None, codes=["ENCODING_ERROR"])
    if not text.strip():
        return DecodeResult(text=text, codes=["EMPTY_DOCUMENT"])
    return DecodeResult(text=text)
