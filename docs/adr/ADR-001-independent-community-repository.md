# ADR-001: Independent community repository

- Status: Accepted (initial baseline)
- Date: 2026-09-27
- Source: docs/PROJECT_SPEC.md §14.1

## Decision

The assistant lives in its own repository with no runtime dependency on s-core_sw_fabric, X-Verse, Fabro, or any agent-orchestration platform.

## Rationale

Keeps ownership, licensing and release cadence simple; other projects may consume the versioned read-only API later.

## Consequences

Integration with other projects happens only through the published API or a later read-only MCP adapter.
