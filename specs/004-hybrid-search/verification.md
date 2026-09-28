# Verification Record: F004 Evidence Search and Exact-ID Navigation

Commands actually run, with results. Categories are kept apart (constitution VII): **mocked**
(fixture snapshots + `FakeEmbeddingProvider`), **real runtime** (local Ollama), **real snapshot**
(active snapshot `20260928T140548Z-7c6a05b3` built from the pinned F002 lock). "Not run" means
not run.

## Phases 1–3 (setup, foundation, US1 exact lookup) checkpoint — 2026-09-28

```text
$ uv run ruff format --check . && uv run ruff check . && uv run mypy src
281 files already formatted / All checks passed! / Success: no issues found in 95 source files
$ uv run pytest -q
635 passed, 6 skipped (opt-in markers, not run)
```

Mocked coverage: config additions; query tokenization, alias rule, quoted-literal FTS expressions
(checked valid against a real FTS5 table for operator-only inputs), 64-term cap, excerpts;
identifier validation, including `FileSnapshotStore.pin()` refusing `../../escape` **before**
creating any file; exact/alias lookup, pinned-before-unverified ordering, export-only records,
namespaced queries, no fuzzy matches; relationships exactly as stored (resolved and unresolved,
incoming via resolved keys, paging bounds); snapshot binding (active, validated, retired queryable;
failed/deleted/building → `SNAPSHOT_NOT_FOUND`; no active → `NO_ACTIVE_SNAPSHOT`); `lookup` CLI.

Real snapshot:

```text
$ score-assistant --config config/local.yaml lookup feat_req__com__interfaces --relationships
[exact] score-platform:feat_req__com__interfaces  feat_req  'Communication Interfaces'  status valid
  score-platform@e2373d822fc2 (pinned)  docs/features/communication/requirements/index.rst:67-82
  links: 6 outgoing, 7 incoming   (all listed with resolution)
$ … lookup feat_req__com__interfaces --json | jq -r '.entities[] | .key+" "+.revision_status'
score-platform:feat_req__com__interfaces pinned
score-platform-needs:feat_req__com__interfaces unverified
$ … lookup STD_REQ-ASPICE_40-SWE-5-BP2
[alias] score-process:std_req__aspice_40__SWE-5-BP2 … process/standards/aspice_40/swe/swe.5.rst:83-99
```

- Deviations: the quickstart example ID `feat_req__baselibs__json` (written during planning) does
  not exist in the corpus. It was replaced with the real `feat_req__com__interfaces`.
- `id_tokens` also strips leading `([\"'` (an ID in parentheses would otherwise never match); FR-006
  updated accordingly.
- Environment: planning was interrupted when the root filesystem filled up (0 MB free), caused by
  a 30 GB `~/.fabro/storage/logs/server.log` outside this project; the owner truncated it and
  work resumed.

## Phase 4 (US2 — search) checkpoint — 2026-09-28

```text
$ uv run ruff format --check . && uv run ruff check . && uv run mypy src
All checks passed! / Success: no issues found in 95 source files
$ uv run pytest -q
702 passed, 7 skipped (opt-in markers, not run)
$ SCORE_ASSISTANT_REAL_RUNTIME=1 uv run pytest -q tests/integration/test_real_runtime.py -k hybrid
1 passed   (real Ollama: fixture snapshot, query "How is the documentation built?" → hybrid,
            semantic matches, docs/build.md first)
```

Mocked coverage: keyword candidates with filters inside the ranking statement (a source that
loses at top-1 still fills a filtered top-1); operator-only queries never error; ID-column
weighting; masked cosine top-k with row tie-breaks; RRF math, exact-first, dedup within a source
but not across, per-document cap, determinism; status cache TTL and invalidation; hybrid default;
an ID in a question ranks first; dictated semantic ranking; degraded modes (runtime unreachable,
identity mismatch with reindex guidance, query embedding failure, too-long query, lexical-only
snapshot, forced lexical, no provider); filters; validation; excerpt bound; citations, sources and
snapshots; **isolation**: another snapshot's content never returned, and activating snapshot B
while a request on A is inside the service still yields only A. HTTP: all six routes, 400/404/409/
422/429 with the F001 envelope and `retryable`, unknown fields (`model`, `url`) rejected, invalid
snapshot/chunk IDs, cross-origin 403, access log without query text, no probability-like field
names, readiness `search` available (`semantic_unavailable` when degraded) and chat still
`not_implemented`. The F003 readiness test was updated for FR-015.

Real snapshot (CLI and HTTP):

```text
$ score-assistant --config config/local.yaml search "How do I build the documentation locally?"
snapshot 20260928T140548Z-7c6a05b3  mode hybrid  8 results
 1. [keyword semantic] score-platform  docs/users_guide/building_simple_application/doc_generation.rst:103-105 …
 3. [keyword semantic] … doc_generation.rst:98-101  (code)  % bazel build //:docs
real 0m0.757s (whole CLI process incl. Python start-up)
$ … search "feat_req__com__interfaces dependencies" --json | jq -c '.results[0] | [.matched_by, .entity_keys]'
[["exact","keyword","semantic"],["score-platform:feat_req__com__interfaces"]]
$ … search "safety analysis" --source score-process --kind prose --json   → hybrid, only score-process, only prose
$ serve; GET /health/ready → search {"available":true,"reasons":[]}, chat not_implemented
POST /api/v1/search {"query":"code review guideline","limit":5} → hybrid, 5 process guideline paths
GET /api/v1/entities?id=feat_req__com__interfaces → git record, then its needs-export copy
POST with Origin: https://evil.example → 403;  {"model":"gpt-4"} → 422 REQUEST_INVALID
server log: 0 occurrences of the query text
```
