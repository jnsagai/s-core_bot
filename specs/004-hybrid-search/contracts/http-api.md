# HTTP API Contract: Evidence Endpoints (F004)

Extends `specs/001-foundation/contracts/http-api.md`. All routes sit behind the F001 Host/Origin/
cross-site guard, return `cache-control: no-store` and `x-request-id`, and are logged body-free.
Error envelope (F001), with `retryable` meaningful here:

```json
{"error": {"code": "SEARCH_BUSY", "message": "Too many searches in progress; retry shortly.",
           "request_id": "…", "retryable": true}}
```

Status codes: 400 malformed JSON, 422 schema or filter error, 404 unknown snapshot/chunk/entity,
409 no active or no compatible snapshot, 429 `SEARCH_BUSY`, 503 dependency unavailable (not used
for search, which degrades), 504 `DEADLINE_EXCEEDED`.

## `POST /api/v1/search`

Request (unknown fields → 422):

```json
{"query": "How is the documentation built?", "snapshot_id": null, "limit": 8,
 "sources": ["score-platform"], "kinds": ["prose", "code"]}
```

Response 200 (degraded modes are still 200; example values are synthetic):

```json
{
  "schema_version": 1,
  "snapshot_id": "20260928T140548Z-7c6a05b3",
  "status": "ok",
  "mode": "lexical",
  "degraded": {"reason": "embedding_runtime_unavailable",
               "detail": "no embedding runtime at http://127.0.0.1:11434",
               "guidance": []},
  "semantic_status": "unverified",
  "exact_matches": [],
  "results": [
    {"rank": 1, "chunk_id": "…", "snapshot_id": "…", "source_id": "score-platform",
     "revision": "e2373d8…", "revision_status": "pinned", "path": "docs/…/doc_generation.rst",
     "origin_path": "docs/…/doc_generation.rst", "heading_path": ["Documentation generation"],
     "line_start": 10, "line_end": 24, "kind": "prose", "entity_keys": [],
     "excerpt": "…", "truncated": false, "matched_by": ["keyword"], "ranking_value": 0.0164}
  ],
  "warnings": ["semantic search unavailable: keyword results only"],
  "timings_ms": {"exact": 1, "keyword": 9, "embedding": 0, "semantic": 0, "fusion": 0, "total": 12},
  "retrieval": {"fusion_version": 1, "lexical_candidates": 30, "semantic_candidates": 30,
                "fusion_constant": 60, "max_per_document": 3}
}
```

`ranking_value` is documented in the schema as "relative ordering value within this response; not
a probability, confidence or measure of correctness". No field named `score`, `confidence` or
`probability` exists in any response.

## `GET /api/v1/entities?id=<ID>[&snapshot_id=][&source_id=]`

`id` is the verbatim ID or `source_id:ID`. It returns `LookupResponse` (data-model.md) with status 200
and `status: no_match` plus an empty list when nothing matches (not 404).

## `GET /api/v1/relationships?key=<namespaced key>[&snapshot_id=][&direction=both][&limit=50][&offset=0]`

Returns `RelationshipsResponse`. `limit` ≤ 200. An unknown key → 404 `ENTITY_NOT_FOUND`.

## `GET /api/v1/snapshots`

`{"active": "<id>|null", "snapshots": [SnapshotSummary, …]}`, with queryable states only, newest
first.

## `GET /api/v1/sources?snapshot_id=<id>`

`{"snapshot_id": "…", "sources": [SourceSummary, …]}`. Without `snapshot_id`, the active snapshot
is used.

## `GET /api/v1/citations/{snapshot_id}/{chunk_id}`

`CitationRecord` with the full stored display text. An unknown snapshot or a chunk not in that
snapshot → 404. It never reads another snapshot to find the chunk.

## `GET /api/v1/capabilities` / `/health/ready` changes

`search` is available when an active compatible snapshot exists. The reason list contains
`semantic_unavailable` while the active snapshot's semantic status is not `enabled` (search still
available). `chat` keeps `not_implemented`.
