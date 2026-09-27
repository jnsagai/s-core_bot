# ADR-006: Immutable multi-repository snapshots with atomic activation

- Status: Accepted (initial baseline)
- Date: 2026-09-27
- Source: docs/PROJECT_SPEC.md §14.1

## Decision

Each snapshot records per-source commit SHAs and hashes, is built in staging, validated, and activated by an atomic pointer update. Requests pin their snapshot.

## Rationale

Prevents version mixing and keeps failed updates from affecting service.

## Consequences

Disk must hold active, previous and staging snapshots.
