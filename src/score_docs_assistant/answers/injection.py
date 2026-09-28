"""Heuristics for evidence that addresses AI assistants (FR-011, SC-004).

A real run showed the local model repeating an injected "you should run rm -rf …" instruction from
a cited excerpt as advice. Such excerpts are marked in the prompt, claims that turn them into
advice are rejected, and they are left out of the extractive fallback. The document text itself
stays visible through citations; it is only never presented as guidance.
"""

from __future__ import annotations

import re

_ADDRESSED_TO_AI = re.compile(
    r"ignore\s+(all\s+|any\s+)?(the\s+)?(previous|prior|above|earlier)\s+(instructions|rules|prompts?)"
    r"|disregard\s+(all\s+|the\s+|any\s+)?(previous|prior|above|earlier)"
    r"|(reveal|print|show|output|repeat)\s+(your|the)\s+(system\s+)?(prompt|instructions)"
    r"|\byou\s+are\s+now\b"
    r"|\bnew\s+instructions\b"
    r"|\bsystem\s+(notice|override|message)\b"
    r"|\bas\s+an?\s+(ai|assistant|language\s+model)\b",
    re.IGNORECASE,
)
_ADVICE = re.compile(
    r"\byou\s+(should|must|need\s+to|have\s+to|can)\b"
    r"|(^|[.:;!]\s+)(please\s+)?(run|execute|type|enter|delete|remove)\b"
    r"|`[^`]+`"
    r"|\brm\s+-",
    re.IGNORECASE,
)


def addresses_assistant(text: str) -> bool:
    return bool(_ADDRESSED_TO_AI.search(text))


def reads_as_advice(text: str) -> bool:
    return bool(_ADVICE.search(text))
