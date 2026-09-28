"""Hardened docutils runtime settings (FR-013, research R2).

`get_default_settings` returns built-in defaults only — no `docutils.conf` or other config file
is read (that is a separate, later step in the docutils settings priority, which we never run).
"""

from __future__ import annotations

import io

from docutils import frontend
from docutils.parsers.rst import Parser

_OVERRIDES: dict[str, object] = {
    "file_insertion_enabled": False,  # include/raw/csv-table file+url reads disabled
    "raw_enabled": False,
    "report_level": 5,  # never write reports anywhere; we collect them via an observer
    "halt_level": 5,  # never raise on markup problems
    "tab_width": 8,
    "smart_quotes": False,
    "syntax_highlight": "none",
    "doctitle_xform": False,
    "docinfo_xform": False,
    "sectsubtitle_xform": False,
    "line_length_limit": 1_000_000,
    "pep_references": False,
    "rfc_references": False,
    "character_level_inline_markup": False,
}


def hardened_settings() -> frontend.Values:
    settings = frontend.get_default_settings(Parser)
    for key, value in _OVERRIDES.items():
        setattr(settings, key, value)
    settings.warning_stream = io.StringIO()
    return settings
