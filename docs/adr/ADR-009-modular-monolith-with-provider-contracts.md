# ADR-009: Modular monolith with provider contracts

- Status: Accepted (initial baseline)
- Date: 2026-09-27
- Source: docs/PROJECT_SPEC.md §14.1

## Decision

One deployable application with explicit interfaces; ingestion and serving share libraries but have separate lifecycles. One serving worker initially.

## Rationale

Simplest architecture that supports later hosting without redesign.

## Consequences

Scaling to multiple workers needs shared admission control (new ADR).
