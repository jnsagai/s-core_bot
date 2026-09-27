# ADR-002: RAG with source provenance instead of fine-tuning

- Status: Accepted (initial baseline)
- Date: 2026-09-27
- Source: docs/PROJECT_SPEC.md §14.1

## Decision

Knowledge comes from retrieval over pinned documentation snapshots with server-owned citations. No model training or fine-tuning.

## Rationale

Fine-tuned knowledge cannot be cited, version-pinned or updated atomically; RAG makes every claim inspectable.

## Consequences

Answer quality depends on retrieval quality; evaluation must measure recall and support precision.
