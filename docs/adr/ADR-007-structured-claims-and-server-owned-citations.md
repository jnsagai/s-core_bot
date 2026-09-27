# ADR-007: Structured claims and server-owned citations

- Status: Accepted (initial baseline)
- Date: 2026-09-27
- Source: docs/PROJECT_SPEC.md §14.1

## Decision

The model returns structured claims with evidence IDs; the server validates membership and renders citations from stored provenance. Only validated final answers are delivered.

## Rationale

Prevents fabricated citations and URLs (constitution II).

## Consequences

Structural validation does not prove semantic support; human review remains required.
