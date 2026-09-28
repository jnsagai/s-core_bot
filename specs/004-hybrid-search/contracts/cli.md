# CLI Contract: `search`, `lookup`, `eval` (F004)

Exit codes: `0` success (including `no_results` / `no_match`), `1` operational failure (no active
snapshot, unknown snapshot, catalog unreadable), `2` usage or validation error (empty/too-long
query, unknown filter value), `130` interrupted. The global `--config` comes first. None of these
commands downloads anything; the only network use is the loopback embedding runtime for query
embeddings (search, eval), and help texts say so.

## `search "QUERY" [--snapshot ID] [--source S]… [--kind K]… [--limit N] [--lexical] [--json]`

Help first line: **"Searches one snapshot offline; may use the local embedding runtime (no
downloads, no generation)."** `--lexical` forces keyword-only mode. Text output:

```text
snapshot 20260928T140548Z-7c6a05b3  mode hybrid  8 results
 1. [exact] score-platform  docs/features/…/index.rst:42-58  (need)  Features > Baselibs
    feat_req__com__interfaces: Communication Interfaces …
 2. [keyword semantic] score-process  process/…/workflow.rst:10-24  (prose)  …
    excerpt text…
```

Degraded mode adds a first line `warning: semantic search unavailable (<reason>): keyword results
only` plus guidance. `--json` prints the `SearchResponse` of contracts/http-api.md.

## `lookup ID [--snapshot ID] [--source S] [--relationships] [--json]`

Help first line: **"Looks up a requirement ID exactly in one snapshot. Offline."** It prints every
match (`exact` or `alias`, with key, type, title, status, source@revision, path:lines,
excerpt) and, with `--relationships`, outgoing and incoming links with resolution. `no exact match
for "<ID>"` → exit 0.

## `eval retrieval --cases FILE [--snapshot ID] [--lexical] [--json] [--output FILE]`

Help first line: **"Measures retrieval recall@10 against a case file; may use the local embedding
runtime."** It prints per-category recall@10 with counts, overall macro recall, the list of cases
with a missed group, and the review-status label. The report is written to
`data/reports/retrieval-<snapshot>-<utc>.json` (or `--output`). Malformed case file → exit 2.

## `eval exact-ids [--snapshot ID] [--json]`

Help first line: **"Checks that every requirement ID in a snapshot is found first by exact
lookup. Offline."** Exit 0 when all are correct, 1 when any failure occurs (listed).

## `eval latency [--snapshot ID] [--cases FILE] [--queries 50] [--json]`

Help first line: **"Measures search latency percentiles for keyword-only and hybrid modes; uses
the local embedding runtime."** It prints p50/p95 per mode, environment identity and warm state.
When the runtime is unavailable, hybrid is reported as "not run" (never as a number).
