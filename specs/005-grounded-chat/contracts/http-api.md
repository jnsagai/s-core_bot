# HTTP API Contract: `POST /api/v1/chat` (F005)

Behind the F001 guard (Host/Origin/cross-site), `cache-control: no-store`, body-free access log.

## Request

```json
{"question": "Which work products does the architecture process require?",
 "snapshot_id": null,
 "history": [
   {"role": "user", "content": "What is the architecture process?"},
   {"role": "assistant", "content": "…", "snapshot_id": "20260928T140548Z-7c6a05b3"}
 ],
 "response_language": "en"}
```

Unknown fields → 422 `REQUEST_INVALID`. `response_language` ≠ `en` → 422 `UNSUPPORTED_LANGUAGE`.
More than 10 turns or `history_characters` exceeded → 422 `REQUEST_INVALID`.

## JSON response (default)

200 with the `AnswerEnvelope` (data-model.md). Synthetic example:

```json
{
  "schema_version": 1, "request_id": "…", "status": "answered", "origin": "model",
  "question": "…",
  "claims": [{"text": "The feature architecture is a required work product.", "kind": "documented",
              "evidence_ids": ["E1"]}],
  "limitations": [],
  "citations": [{"evidence_id": "E1", "chunk_id": "…", "snapshot_id": "…",
                 "source_id": "score-process", "revision": "66321fe…", "revision_status": "pinned",
                 "path": "process/…/architecture_workproducts.rst", "heading_path": ["…"],
                 "line_start": 31, "line_end": 44, "excerpt": "…",
                 "immutable_url": "https://github.com/eclipse-score/process_description/blob/66321fe…/process/…/architecture_workproducts.rst#L31-L44",
                 "revision_match": "exact"}],
  "snapshot_id": "…",
  "model": {"provider": "ollama", "name": "qwen3:4b-instruct", "digest": "0edcdef3…",
            "runtime_version": "0.34.0"},
  "retrieval": {"mode": "hybrid", "degraded_reason": null, "results": 8,
                "evidence_supplied": 8, "evidence_dropped": 0},
  "warnings": [], "policy_version": 1,
  "timings_ms": {"queue": 0, "retrieval": 120, "generation": 2900, "repair": 0,
                 "validation": 2, "total": 3030}
}
```

## Streaming response (`Accept: text/event-stream`)

```text
id: 1
event: progress
data: {"stage": "queued", "position": 1}

id: 2
event: progress
data: {"stage": "searching"}

id: 3
event: progress
data: {"stage": "generating"}

id: 4
event: progress
data: {"stage": "validating"}

id: 5
event: answer
data: {…AnswerEnvelope…}

id: 6
event: done
data: {}
```

A failure after headers are sent becomes `event: error` with the error envelope, followed by
`done`. No claim text appears before the `answer` event.

## Errors (JSON mode, F001 envelope with `retryable`)

| Status | Code | When |
| --- | --- | --- |
| 404 | `SNAPSHOT_NOT_FOUND` | unknown/unqueryable snapshot |
| 409 | `NO_ACTIVE_SNAPSHOT` | no snapshot given and none active |
| 422 | `REQUEST_INVALID`, `UNSUPPORTED_LANGUAGE`, `QUERY_INVALID` | validation |
| 429 | `CHAT_BUSY` | active slot taken and queue full (retryable) |
| 502 | `ANSWER_INVALID` | invalid model output and no evidence for a fallback |
| 503 | `GENERATION_UNAVAILABLE` | runtime unreachable, model missing, digest ≠ lock (reason in message) |
| 504 | `DEADLINE_EXCEEDED` | deadline reached (retryable) |
