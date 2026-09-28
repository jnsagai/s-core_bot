"""Per-document license records (FR-021).

Upstream files declare `SPDX-License-Identifier:` in their header comment (RST `..` comment or
Markdown `<!-- -->`). Only the first 20 lines are searched, so a license quoted in body text is
never mistaken for the file's own. Compound expressions (`A OR B`) always require review: deciding
which branch applies is a human call.
"""

from __future__ import annotations

import re

from score_docs_assistant.domain.ingestion import LicenseRecord

_HEADER_LINES = 20
_SPDX = re.compile(r"SPDX-License-Identifier:\s*(.+?)\s*(?:-->\s*)?$")


def _declared(text: str) -> str | None:
    for line in text.splitlines()[:_HEADER_LINES]:
        match = _SPDX.search(line)
        if match:
            return match.group(1)
    return None


def detect_license(
    text: str, repository_license: str | None, redistribution_allowed: set[str]
) -> tuple[LicenseRecord, list[str]]:
    declared = _declared(text)
    if declared is not None:
        spdx, basis = declared, "declared"
    elif repository_license is not None:
        spdx, basis = repository_license, "inherited"
    else:
        record = LicenseRecord(spdx=None, basis="unknown", redistribution="requires_review")
        return record, ["LICENSE_UNKNOWN"]
    allowed = spdx in redistribution_allowed
    record = LicenseRecord(
        spdx=spdx,
        basis="declared" if basis == "declared" else "inherited",
        redistribution="allowed" if allowed else "requires_review",
    )
    return record, []
