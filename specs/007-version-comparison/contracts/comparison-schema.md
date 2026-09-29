# Comparison Schema (F007)

## Model output schema (comparison step)

```json
{"type": "object", "additionalProperties": false, "required": ["differences"],
 "properties": {"differences": {"type": "array", "maxItems": 8, "items": {
   "type": "object", "additionalProperties": false,
   "required": ["type", "statement", "left_evidence_ids", "right_evidence_ids"],
   "properties": {
     "type": {"enum": ["changed", "unchanged", "conflicting", "not_established"]},
     "statement": {"type": "string", "maxLength": 1200},
     "left_evidence_ids": {"type": "array", "items": {"pattern": "^L[0-9]{1,2}$"}},
     "right_evidence_ids": {"type": "array", "items": {"pattern": "^R[0-9]{1,2}$"}}}}}}}
```

## Comparison policy (versioned, `COMPARISON_POLICY_VERSION = 1`)

The rules restate F005's data/untrusted rules for two evidence blocks and add:
- compare only what the excerpts state;
- use `changed` when both sides address the point differently;
- use `unchanged` when both state the same thing;
- use `conflicting` when the two sides' guidance on the same point is mutually exclusive (one
  requires what the other forbids or replaces), and never choose between them or say which is
  newer;
- use `not_established` when only one side addresses the point, citing only that side;
- never say that something was removed, deleted, added or is no longer present;
- never invent a release name.

## Validation codes

`JSON_INVALID`, `SCHEMA_INVALID`, `UNKNOWN_EVIDENCE_ID`, `WRONG_SIDE_ID`, `MISSING_SIDE_EVIDENCE`
(changed/unchanged/conflicting without both sides), `ONE_SIDE_ONLY` (not_established with IDs on
both sides or neither), `CHANGED_WITHOUT_DIFFERENCE`, `DELETION_CLAIM`, `URL_IN_TEXT`,
`HIDDEN_THOUGHT`, `QUOTE_NOT_IN_EVIDENCE`, `INJECTION_SUSPECTED`, `EMPTY_STATEMENT`.

## Result

See [data-model.md](../data-model.md) `ComparisonResult`. Example (abridged):

```json
{"schema_version": 1, "request_id": "…", "question": "…",
 "left": {"snapshot_id": "A", "status": "partial", "claims": [], "citations": []},
 "right": {"snapshot_id": "B", "status": "answered", "claims": [], "citations": []},
 "differences": [
   {"type": "not_established", "statement": "Only the right snapshot describes the checklist.",
    "left_evidence_ids": [], "right_evidence_ids": ["R1"], "origin": "model",
    "coverage_reason": "not_retrieved", "missing_side": "left"}],
 "evidence": {"left": [], "right": [{"evidence_id": "R1", "snapshot_id": "B"}]},
 "snapshots": {"left_snapshot_id": "A", "right_snapshot_id": "B", "sources": [],
               "processing": [], "release_label": null, "warnings": []},
 "model": {"provider": "ollama", "name": "qwen3:4b-instruct", "digest": "…"},
 "origin": "model", "warnings": [], "policy_version": 1, "timings_ms": {"total": 9100}}
```
