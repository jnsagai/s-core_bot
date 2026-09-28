# ADR-003: Ollama as local generation and embedding provider

- Status: Accepted (initial baseline)
- Date: 2026-09-27
- Source: docs/PROJECT_SPEC.md §14.1

## Decision

Ollama is the first provider for both generation and embeddings, behind GenerationProvider/EmbeddingProvider interfaces. Model tags resolve to recorded digests; changing a digest requires requalification.

## Rationale

Free, local, supports CPU and NVIDIA; exposes chat and embed APIs.

## Consequences

Ollama cloud features must be disabled and verified with blocked-egress tests. No cloud fallback.
