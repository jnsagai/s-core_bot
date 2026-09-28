# Contract: Model Output Schema and Validation (F005)

The JSON schema sent to the runtime as `format` (structured output) and enforced again by the
server:

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["status", "claims"],
  "properties": {
    "status": {"type": "string",
               "enum": ["answered", "partial", "insufficient_evidence", "clarification_needed"]},
    "claims": {
      "type": "array", "maxItems": 12,
      "items": {
        "type": "object", "additionalProperties": false,
        "required": ["text", "kind", "evidence_ids"],
        "properties": {
          "text": {"type": "string", "maxLength": 1200},
          "kind": {"type": "string", "enum": ["documented", "interpretation", "limitation"]},
          "evidence_ids": {"type": "array", "items": {"type": "string", "pattern": "^E[0-9]{1,2}$"}}
        }
      }
    }
  }
}
```

## Server validation (error codes used in the repair prompt and warnings)

| Code | Rule |
| --- | --- |
| `JSON_INVALID` | output is not a JSON object |
| `SCHEMA_INVALID` | unknown keys, wrong types, enum or size violations |
| `UNKNOWN_EVIDENCE_ID` | a cited ID was not supplied for this request |
| `MISSING_CITATION` | a documented or interpretation claim cites nothing |
| `STATUS_INCONSISTENT` | status/claim rules violated (research R4), e.g. `insufficient_evidence` with documented claims, `answered` without a documented claim |
| `QUOTE_NOT_IN_EVIDENCE` | a quoted string of ≥ 12 characters (`"…"` or backticks) is absent from the claim's cited excerpts (whitespace-normalized) |
| `URL_IN_TEXT` | claim text contains `http://`, `https://`, `www.`, `file:` or `mailto:` |
| `HIDDEN_THOUGHT` | `<think>`/`</think>` or similar markers |
| `EMPTY_CLAIM` | whitespace-only claim text |
| `INJECTION_SUSPECTED` | a claim cites an excerpt marked `untrusted="instructions-like"` (text addressed to AI assistants) and reads as advice (you should…, run/execute…, a backtick command, `rm -`). Added after a real-model run repeated an injected command (verification.md) |

At most one repair round (`generation.repair_attempts`). Then an extractive fallback (research
R5). When no usable excerpt remains for the fallback (every supplied excerpt is instruction-like),
the result is `insufficient_evidence` with the fallback limitation rather than `ANSWER_INVALID`,
because that is the honest answer status and nothing unchecked is returned (ASSUMPTIONS A-033).
`ANSWER_INVALID` remains defined for completeness but is not produced by the current flow.
