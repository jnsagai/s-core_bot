# ADR-010: Evaluation thresholds, frozen cases, human semantic review

- Status: Accepted (initial baseline)
- Date: 2026-09-27
- Source: docs/PROJECT_SPEC.md §14.1

## Decision

Release quality is judged against a reviewed 100-case suite with a frozen 40-case held-out split and the thresholds in PROJECT_SPEC §13.3. An LLM judge may assist but is never the sole oracle.

## Rationale

Honest verification (constitution VII).

## Consequences

Human review effort is required before each release.
