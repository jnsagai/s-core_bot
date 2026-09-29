# HTTP Contract: comparison (F007)

Same guard, loopback bind, error envelope and no-body logging as F004–F006.

## `POST /api/v1/compare`

Request (`application/json`), unknown fields → 422:

```json
{"question": "How are inspections performed?",
 "left_snapshot_id": "20260929T101500Z-1a2b3c4d",
 "right_snapshot_id": "20260928T140548Z-7c6a05b3"}
```

JSON response 200: a `ComparisonResult` (see [comparison-schema.md](comparison-schema.md)).

With `Accept: text/event-stream`: `progress` events `{"stage": "queued", "position": 1}`,
`{"stage": "searching", "side": "left"}`, `{"stage": "generating", "side": "left"}`,
`{"stage": "validating", "side": "right"}`, `{"stage": "comparing"}`; then a single `comparison`
event (the full result) or an `error` event; then `done`. Event IDs increase monotonically. No
claim or difference text appears before the `comparison` event.

Errors: 422 `REQUEST_INVALID` (same snapshot twice, bad ID format, question length, language);
404 `SNAPSHOT_NOT_FOUND`; 409 `SNAPSHOT_INCOMPATIBLE`; 429 `QUEUE_FULL`; 503
`GENERATION_UNAVAILABLE`; 504 `DEADLINE_EXCEEDED`. Cross-site → 403 (guard, unchanged).

## `GET /api/v1/snapshots/diff?left=<id>&right=<id>`

200: a `SnapshotDiff`. No generation or runtime call. 422 for a missing, malformed or identical
ID pair; 404/409 as above.

## `GET /api/v1/capabilities` and `/health/ready`

The existing `compare` mode (so far `not_implemented`) becomes real. It is available when chat is
available and at least two snapshots are queryable; otherwise it reports the chat reasons or the
new reason `snapshots_insufficient`. `limits` adds `comparison_deadline_seconds`. Overall
readiness is unchanged: it does not depend on `compare`.
