# Data Model: F005 Grounded Local Answers

Frozen Pydantic records in `src/score_docs_assistant/domain/answers.py`, independent of FastAPI and
Ollama types. Nothing is persisted server-side except evaluation reports and review sheets under
`data/reports/`.

## ChatRequest

| Field | Type | Rules |
| --- | --- | --- |
| `question` | str | 1 ≤ stripped length ≤ `limits.question_characters` |
| `snapshot_id` | str \| None | snapshot-ID pattern; None → active |
| `history` | list[Turn] | ≤ 10 turns; Σ content ≤ `limits.history_characters` |
| `response_language` | `en` | any other value → 422 `UNSUPPORTED_LANGUAGE` |

`extra="forbid"`, so model names, URLs, system prompts and options are rejected.
**Turn**: `role: user | assistant`, `content: str`, `snapshot_id: str | None` (assistant turns
only).

## EvidenceItem (internal)

`evidence_id` (`E1`…), `chunk_id`, `rank`, `source_id`, `revision`, `revision_status`, `path`,
`heading_path`, `line_start`, `line_end`, `kind`, `excerpt` (F004 excerpt, the exact text shown to
the model), `estimated_tokens`.

## ModelDraft (parsed model output)

`status` ∈ statuses, `claims: list[DraftClaim]` (`text`, `kind`, `evidence_ids`). JSON schema in
[contracts/answer-schema.md](contracts/answer-schema.md).

## Claim (validated)

`text`, `kind: documented | interpretation | limitation`, `evidence_ids: list[str]`.

## Citation

`evidence_id`, `chunk_id`, `snapshot_id`, `source_id`, `revision`, `revision_status`, `path`,
`heading_path`, `line_start`, `line_end`, `excerpt`, `immutable_url: str | None`,
`revision_match: exact | unverified | none`. Built only from stored provenance (R6).

## AnswerEnvelope

| Field | Notes |
| --- | --- |
| `schema_version` | 1 |
| `request_id` | from the request context (CLI: generated UUID) |
| `status` | `answered` \| `partial` \| `insufficient_evidence` \| `clarification_needed` |
| `origin` | `model` \| `extractive_fallback` \| `no_evidence` |
| `question` | echoed (client-side export; never logged) |
| `claims` | list[Claim] |
| `limitations` | text of limitation claims (convenience) |
| `citations` | list[Citation], one per cited evidence ID, in first-use order |
| `snapshot_id` | pinned snapshot |
| `model` | `GenerationIdentity`: `provider`, `name`, `digest`, `runtime_version`; null when not called |
| `retrieval` | `{mode, degraded_reason, results, evidence_supplied, evidence_dropped}` |
| `warnings` | list[str] codes and messages (`model_output_invalid`, `repaired`, `evidence_reduced`, `history_reduced`, `new_evidence_context`, `semantic_unavailable`) |
| `policy_version` | 1 |
| `timings_ms` | `queue`, `retrieval`, `generation`, `repair`, `validation`, `total` |

## GenerationError (typed failures; HTTP error envelope)

Codes: `GENERATION_UNAVAILABLE` (503; reasons `runtime_unreachable`, `model_missing`,
`model_identity_mismatch`), `CHAT_BUSY` (429, retryable), `DEADLINE_EXCEEDED` (504, retryable),
`ANSWER_INVALID` (502; only when no fallback is possible), `UNSUPPORTED_LANGUAGE` (422),
`REQUEST_INVALID` (422), plus F004's `NO_ACTIVE_SNAPSHOT` (409) and `SNAPSHOT_NOT_FOUND` (404).
CLI: 422 → exit 2; others → exit 1.

## Configuration (`config/schema.py`, new `GenerationConfig` under `generation:`)

```yaml
generation:
  temperature: 0.1              # 0..1
  history_turns: 10             # 0..50
  history_tokens: 1000          # budget for history + question (estimated tokens)
  evidence_tokens: 4500         # budget for evidence
  evidence_items: 8             # max excerpts supplied (≤ retrieval.max_limit)
  max_claims: 12
  max_claim_characters: 1200
  repair_attempts: 1            # 0..1 (master spec: at most one)
  fallback_excerpts: 3
```

The existing `runtime.context_tokens` (8 192) and `runtime.output_tokens` (900) bound the call, and
`limits.active_generations` (1), `queued_generations` (4) and `request_deadline_seconds` (120)
bound admission and time.

## Evaluation records

**AnswerCase**: `id`, `category` (F004 categories + `unanswerable`, `injection`), `question`,
`expected_status` (status or `safe_handling`), `expected` (optional evidence groups, F004 locator
format), `notes`. **AnswerCaseFile**: `schema_version: 1`, `review_status`, `written_against`,
`snapshot_fixture: real | injection` (injection cases run on the synthetic snapshot), `cases`.
**AnswerCaseResult**: `id`, `category`, `status`, `expected_status`, `status_ok`, `origin`,
`citation_integrity: bool`, `evidence_overlap: float | None`, `claims`, `latency_ms`,
`warnings`. **AnswerReport**: snapshot, model identity, case-file hash, labels, per-case results,
aggregates by category (counts), `safe_handling: {handled, total}`, `citation_integrity: {ok,
total}`, `human_review: {support_precision: "not run" | value, required_fact_coverage: "not run" |
value}`. **ReviewSheet**: `cases: [{id, question, claims: [{text, kind, citations: [{path, lines,
excerpt}], supported: null, reviewer: null}]}]`.
