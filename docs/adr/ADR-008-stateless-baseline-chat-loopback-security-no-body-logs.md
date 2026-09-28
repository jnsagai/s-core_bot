# ADR-008: Stateless baseline chat, loopback security, no body logs

- Status: Accepted (initial baseline)
- Date: 2026-09-27
- Source: docs/PROJECT_SPEC.md §14.1

## Decision

Chat state lives in the client; the server binds to loopback, validates Host/Origin, and never logs question/answer bodies by default.

## Rationale

Privacy by default and DNS-rebinding protection for a local service.

## Consequences

No server-side history; exports are explicit user actions.
