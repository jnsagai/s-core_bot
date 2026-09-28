# ADR-005: Safe source parsing; no execution of upstream doc builds

- Status: Accepted (initial baseline)
- Date: 2026-09-27
- Source: docs/PROJECT_SPEC.md §14.1

## Decision

Markdown and a documented RST subset are parsed directly. Upstream conf.py, directives, scripts and hooks are never executed. Sphinx-Needs exports are imported with strict validation and verified or labelled unverified provenance.

## Rationale

Documentation is untrusted input (constitution IV).

## Consequences

Parser coverage is limited; unsupported constructs produce diagnostics.
