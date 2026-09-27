# ADR-004: SQLite FTS5 plus NumPy exact vector search

- Status: Accepted (initial baseline)
- Date: 2026-09-27
- Source: docs/PROJECT_SPEC.md §14.1

## Decision

Lexical search uses SQLite FTS5; semantic search uses normalized float32 matrices with exact cosine in NumPy, behind a SearchIndex interface.

## Rationale

Sufficient for the initial ~25,000-chunk budget with no extra services.

## Consequences

A larger corpus triggers a new ADR backed by measurements.
