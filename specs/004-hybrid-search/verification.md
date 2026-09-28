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

## Phases 5–6 (US3 evaluation, polish) — 2026-09-28

### Full gate

```text
$ uv run ruff format --check . && uv run ruff check . && uv run mypy src
290 files already formatted / All checks passed! / Success: no issues found in 95 source files
$ uv run pytest -q
723 passed, 7 skipped (opt-in markers, not run in this invocation)
$ SCORE_ASSISTANT_REAL_RUNTIME=1 uv run pytest -q -m real_runtime
5 passed, 1 skipped (real model pull, separate opt-in: not run)
$ uv run python scripts/check_licenses.py
License check passed: 42 packages, all allowed or reviewed.
```

Mocked coverage for US3: case-file schema (unknown keys, duplicate IDs, empty groups, locator shape,
line order, bad category/version, invalid YAML → exit 2); locator matching (path, line overlap,
entity key); recall@10 per case, macro and by category; unreviewed labels; `written_against`
mismatch warning; exact-ID suite; nearest-rank percentiles; latency report with hybrid "not run"
when the runtime is unavailable; `eval` CLI help lines, exit codes and report files.

### Real snapshot measurements (reference workstation)

**Exact-ID suite (SC-001, real snapshot)**: `eval exact-ids` → **2168/2168** IDs return the
expected entity first (the pinned git record ahead of its `needs-export` copy), no duplicates within
one source.

**Retrieval recall@10 (SC-005): development measurement on 32 unreviewed, agent-authored cases
(`eval/retrieval-dev.yaml`, 8 per category); not release evidence**:

```text
$ score-assistant --config config/local.yaml eval retrieval --cases eval/retrieval-dev.yaml
snapshot 20260928T140548Z-7c6a05b3  mode hybrid  review: unreviewed (agent-authored)
  [development measurement, not release evidence]
  architecture_interfaces    recall@10 100.0%  (8 cases)
  onboarding_build           recall@10 100.0%  (8 cases)
  process_work_products      recall@10 100.0%  (8 cases)
  requirements_templates     recall@10  62.5%  (8 cases)
  overall (macro)            recall@10  90.6%  (32 cases)
  missed group(s): req-002, req-004, req-008
```

Diagnosis of the 3 misses (gold labels deliberately **not** changed after seeing results): each
expects the template's entity key. The template *file* is retrieved at ranks 1–6, but its
need-directive chunk holds only the title and options, while the template body follows in chunks
without the entity key. Recorded as docs/ASSUMPTIONS.md A-028 (a candidate improvement for
F005/F008), not tuned away. Gold locations came from reading the pinned sources and entity records,
not from search output. The case set is small and self-authored, so the 90.6 % says nothing about
the ≥ 90 % held-out release target (F008).

**Latency (SC-004)**, 5 warm-up + 50 timed queries per mode, measured in the service (excludes
HTTP and process start-up), embedding model warm:

```text
$ score-assistant --config config/local.yaml eval latency --cases eval/retrieval-dev.yaml --queries 50
  lexical  p50      6.5 ms   p95      8.1 ms   n=50
  hybrid   p50     55.8 ms   p95    111.0 ms   n=50
  environment: Linux 6.8 x86-64, 32 CPUs, 31.0 GiB RAM, NVIDIA GeForce RTX 4070 Laptop GPU,
  Ollama 0.34.0, nomic-embed-text:latest 0a109f42…e59f
```

Targets (master spec §13.4): keyword p95 ≤ 500 ms, hybrid p95 ≤ 2 s → both met. Cold-model hybrid
latency was not measured separately (not run).

**Offline (quickstart F, `unshare -rn`)**: `lookup` (exit 0), `eval exact-ids` (2168/2168), and
`search` (degraded to lexical with the warning `semantic search unavailable
(embedding_runtime_unavailable): keyword results only`) all succeeded with no network.

### Polish

README (Status, Quickstart) and CLAUDE.md commands updated, and documented commands re-run.
TRACEABILITY: RET-001–RET-004, RET-008 and LOC-006 are verified (F004 scope); RET-005 notes
search-level binding. ASSUMPTIONS: A-025–A-028 added. BACKLOG: F003 done; F004 implemented, with
converge pending at this point.
