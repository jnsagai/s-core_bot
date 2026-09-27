# HTTP Contract (F001)

All responses are JSON, `Cache-Control: no-store`, and carry `X-Request-ID`. No `Server` header.
Every request first passes the Host/Origin guard.

## Guard (applies to all routes, before routing)

| Condition (evaluated in order) | Response |
| --- | --- |
| `Host` not allowed: an `allowed_hosts` entry without a port matches that host with no port or with the bound port; an entry with a port matches exactly; hosts compared case-insensitively, IPv6 in brackets | 400 `HOST_NOT_ALLOWED` |
| `Origin` present and not in `server.allowed_origins` (including `null`) | 403 `ORIGIN_NOT_ALLOWED` |
| `Sec-Fetch-Site: cross-site` | 403 `CROSS_SITE_REQUEST` |
| `OPTIONS` preflight from allowed origin | 204 with `Access-Control-Allow-Origin: <origin>`, `Vary: Origin`, allowed methods `GET, POST`, allowed headers `Content-Type` |
| Allowed origin, simple request | `Access-Control-Allow-Origin: <origin>`, `Vary: Origin`; never `*`, never credentials |
| No `Origin`, valid `Host`, not cross-site | passes (CLI/curl clients) |

## Error envelope

```json
{"error": {"code": "ORIGIN_NOT_ALLOWED", "message": "Request origin is not allowed.",
           "request_id": "…", "retryable": false}}
```

Unknown route → 404 `NOT_FOUND`; method not allowed → 405 `METHOD_NOT_ALLOWED`; unhandled → 500
`INTERNAL_ERROR` (no stack trace in body).

## `GET /health/live`

200 `{"status": "alive"}` — no other fields.

## `GET /health/ready`

200 when `search` available, else 503. Body (both cases):

```json
{"ready": false,
 "capabilities": {
   "search": {"available": false, "reasons": ["corpus_missing"]},
   "chat":   {"available": false, "reasons": ["corpus_missing", "generation_model_missing"]},
   "compare":{"available": false, "reasons": ["not_implemented"]}}}
```

No paths, URLs, versions, or model names.

## `GET /api/v1/capabilities`

Always 200 while live:

```json
{"schema_version": 1,
 "app": {"name": "S-CORE Docs Assistant — Community Project", "version": "0.1.0"},
 "profile": "local",
 "runs_locally": true,
 "modes": {"search": {...}, "chat": {...}, "compare": {...}},
 "limits": {"question_characters": 4000, "history_characters": 12000,
            "active_generations": 1, "queued_generations": 4, "request_deadline_seconds": 120},
 "models": {"generation": "qwen3:4b-instruct", "embedding": "nomic-embed-text"},
 "response_languages": ["en"]}
```

`modes` has the same shape as readiness `capabilities`. Model values are configured labels only
(no digests or runtime URL).

## Route inventory

F001 exposes exactly: `GET /health/live`, `GET /health/ready`, `GET /api/v1/capabilities` (plus
`OPTIONS` handling in the guard). No OpenAPI docs UI routes (`/docs`, `/redoc` disabled; the
OpenAPI JSON is generated in tests for contract snapshots only).
