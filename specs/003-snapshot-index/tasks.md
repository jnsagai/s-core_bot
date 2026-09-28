---

description: "Task list for F003 Immutable Snapshots and Local Embedding Index"
---

# Tasks: F003 Immutable Snapshots and Local Embedding Index

**Input**: Design documents from `specs/003-snapshot-index/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md,
checklists/security.md

**Tests**: MANDATORY (constitution VII). Within each story, write tests first and confirm they
fail before implementing. Deterministic tests use `FakeEmbeddingProvider` (mocked, labelled as
such); real-runtime checks carry the `real_runtime` marker and count as "not run" when skipped.
Synthetic fixtures carry a `SYNTHETIC — not S-CORE guidance` comment.

**Organization**: grouped by user story; each task lists the requirement IDs / research decisions it serves.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on incomplete tasks)
- **[Story]**: US1–US3 from spec.md
- Paths are repository-relative (package root `src/score_docs_assistant/`)

---

## Phase 1: Setup (Shared Infrastructure)

- [x] T001 Add `numpy` to `[project].dependencies` in `pyproject.toml`; run `uv lock` and `uv sync --locked`; run `uv run python scripts/check_licenses.py --write-notices` (must pass without an exception, BSD-3-Clause) and record the resolved version in `docs/toolchain.md` (research R5)
- [x] T002 [P] Set the `nomic-embed-text` license to `Apache-2.0` in `config/model-profiles.yaml`, with a comment citing `/api/show` on 2026-09-28 (research R1, constitution XI)
- [x] T003 [P] Create empty modules/packages: `src/score_docs_assistant/domain/snapshots.py`, `src/score_docs_assistant/ingestion/tokens.py`, `src/score_docs_assistant/ingestion/chunking.py`, `src/score_docs_assistant/models/ollama_embed.py`, `src/score_docs_assistant/storage/{sqlite_util,corpus_db,vectors,manifest,catalog,locks,pins,validation,snapshot_store,build,lifecycle,bundles}.py`, `src/score_docs_assistant/cli/{index,snapshots,bundle}.py` (docstring only)

---

## Phase 2: Foundational (Blocking Prerequisites)

**⚠️ CRITICAL**: no user story work can begin until this phase is complete

### Tests for Foundational

- [x] T004 [P] Write `tests/unit/test_index_config.py`: defaults from data-model "Configuration additions"; `config/local.yaml` without `index`/`bundles` still loads; unknown keys rejected; `retention_count < 2`, overlap outside 50–100, `chunk_min_tokens > chunk_max_tokens`, `chunk_max_tokens > embedding_max_input_tokens - 200`, non-positive caps → errors (data-model config)
- [x] T005 [P] Write `tests/unit/test_tokens.py`: `pretoken-v1` on fixed cases (empty → 2; `hello` → 5; `feat_req__x` counts letters ÷2 ceil plus one per `_`; digits and punctuation one per byte; `ä` two; CJK three per char); monotonic under concatenation (est(a+" "+b) ≤ est(a)+est(b)); deterministic (FR-003, research R2)
- [x] T006 [P] Write `tests/unit/test_snapshot_records.py`: frozen/extra-forbid models in `domain/snapshots.py`; `EmbeddingIdentity` equality over all six fields; manifest JSON round-trip; `chunk_id` derivation stable and sensitive to chunker version, document key, ordinal and content hash (FR-004, FR-005, data-model)
- [x] T007 [P] Write `tests/unit/test_sqlite_hardening.py`: helper `open_hardened(path, readonly)` sets `trusted_schema=OFF`, `cell_size_check=ON`, `SQLITE_DBCONFIG_DEFENSIVE`; read-only URIs use `mode=ro` (+ `immutable=1` for snapshot corpora); a grep test asserts `enable_load_extension` appears nowhere in `src/` (FR-006, research R4, checklist CHK007)

### Implementation for Foundational

- [x] T008 Add `IndexConfig` and `BundleConfig` to `src/score_docs_assistant/config/schema.py` (fields, defaults and validators per data-model) and wire them into `AppConfig` — makes T004 pass
- [x] T009 [P] Implement `estimate_tokens()` (`pretoken-v1`) in `src/score_docs_assistant/ingestion/tokens.py` — makes T005 pass (research R2)
- [x] T010 [P] Implement the records in `src/score_docs_assistant/domain/snapshots.py` (`Chunk`, `ChunkerConfig`, `EmbeddingIdentity`, `SnapshotManifest`, `EmbeddingManifest`, `CorpusSnapshot`, `ActivationRecord`, `BuildJob`, `ValidationReport`, `BundleManifest`, `SnapshotStore` protocol) and `chunk_id()` — makes T006 pass (data-model)
- [x] T011 [P] Add the `SnapshotError` family with the codes listed in data-model "Error types" to `src/score_docs_assistant/domain/errors.py`, and make `handle_common_errors` in `src/score_docs_assistant/cli/main.py` map `SnapshotError` to exit 1, printing `<CODE>: <message>` on stderr
- [x] T012 [P] Implement `open_hardened()` in `src/score_docs_assistant/storage/sqlite_util.py` — makes T007 pass (research R4)
- [x] T013 Fill in the `EmbeddingProvider` protocol in `src/score_docs_assistant/models/runtime.py` (`identity() -> EmbeddingIdentity`, `context_tokens() -> int`, `embed(texts: Sequence[str]) -> list[list[float]]`), and create `tests/helpers/fake_embedding.py` `FakeEmbeddingProvider` (deterministic SHA-256-seeded unit vectors; records calls and the `truncate` flag; configurable modes: unreachable, wrong dimension, NaN, too-long threshold, digest override) (plan Testing)

**Checkpoint**: `uv run pytest tests/unit && uv run mypy src && uv run ruff check .` green.

---

## Phase 3: User Story 1 — Build a validated, self-describing snapshot (Priority: P1) 🎯 MVP

**Goal**: `index build` turns the source lock into a `validated` snapshot in staging-then-publish
fashion, with chunks, corpus DB, vectors (with reuse), manifests and reports.

**Independent Test**: build twice from a fixture lock → identical chunk rows; kill at every
stage → active and catalog unchanged; runtime unavailable with and without `--lexical-only`.

### Tests for User Story 1

- [x] T014 [P] [US1] Create `tests/fixtures/snapshot/` (SYNTHETIC): RST/MD sources with a short need, a need longer than 700 tokens with nested blocks, two sections with small paragraphs, a 60-row list-table, a 200-line code block, a `uml` diagram, a paragraph > 700 tokens with sentences, one > 700-token whitespace-free line (over cap variant separately), a `raw:: html`, a `needtable`, identical paragraphs in two sources, plus a CC-BY-SA-4.0 SPDX file; and `tests/helpers/snapshot_env.py` building a lock + `data/sources` tree in `tmp_path` from them, reusing `tests/helpers/pipeline.py` patterns (US1, US3)
- [x] T015 [P] [US1] Write `tests/unit/test_chunking.py` (golden): need = one chunk carrying its entity key; long need → ordered `i/n` continuations all carrying the key; prose never crosses a heading path; small sections stay separate; table pieces repeat header rows and record row ranges; code split only at line boundaries with continuations; long paragraph split at sentences with 50–100-token overlap; whitespace-free unit over max but under cap → own chunk; over cap → `CHUNK_UNSPLITTABLE` naming path and line; `dynamic_view`/`raw_excluded`/`section` blocks contribute no text; display text has no synthetic prefix; embedding input = `search_document: ` + prefix + text; prefix elided to ≤ 160 tokens; every `embedding_token_estimate ≤ cap`; reconstruction test (no text lost); export documents yield zero chunks (FR-001–FR-004, research R3)
- [x] T016 [P] [US1] Write `tests/unit/test_chunk_determinism.py`: same documents + config → byte-identical canonical chunk records; changing any `ChunkerConfig` field changes `chunker_config_sha256` and embedding-input hashes; identical text in two sources → same `content_hash`, different `chunk_id` (FR-005, SC-002, spec Edge Cases)
- [x] T017 [P] [US1] Write `tests/unit/test_corpus_db.py`: schema exactly per contracts/snapshot-files.md; `user_version = 1`; `journal_mode=DELETE`, no sidecar files after close; export entities stored `unverified`; one relation row per link item with resolution; FTS `MATCH` finds `feat_req__baselibs__json`, `MLE.3.BP1` and a heading term; `chunks` rowid order = corpus order (FR-006, research R4)
- [x] T018 [P] [US1] Write `tests/unit/test_vectors.py`: write → file size = rows × dim × 4, little-endian float32; re-normalization to unit norm; NaN/inf or wrong dimension → `EMBEDDING_INVALID_VECTOR`; read via memmap returns identical rows; row map length mismatch rejected (FR-007, research R5)
- [x] T019 [P] [US1] Write `tests/unit/test_ollama_embed.py` with `httpx.MockTransport`: request body has `truncate: false` and the list input; 400 "exceeds the context length" → `EMBEDDING_INPUT_TOO_LONG` naming the batch item; connection error → `EMBEDDING_UNAVAILABLE`; `identity()` combines `/api/tags` digest and `/api/show` `*.embedding_length`/`*.context_length`; only loopback base URLs accepted (FR-007, FR-022, research R1)
- [x] T020 [P] [US1] Write `tests/unit/test_manifest.py`: manifest has every FR-010 field; `files` sorted and covering every file except `manifest.json`; hashes match; `license_review` lists the CC-BY-SA fixture; `limitations` includes the exports-no-chunks note and failed optional sources; newer `schema_version`/`corpus_schema_version` → `SCHEMA_UNSUPPORTED` before other fields are read (FR-010, FR-017)
- [x] T021 [P] [US1] Write `tests/unit/test_validation.py`: a valid snapshot passes; each crafted defect fails its check (tampered file, unlisted file, missing file, bad `user_version`, extra trigger/view/table in `corpus.sqlite`, FTS index corruption, truncated `embeddings.f32`, NaN row, non-unit row, row map ≠ chunk IDs, count mismatch); semantic `absent` for lexical-only; `disabled` on digest, dimension or preprocessing mismatch vs model lock (message contains reindex guidance); `disabled` on runtime digest mismatch; `unverified` when runtime unreachable or no runtime supplied; `disabled` with `models pull` guidance when the model lock has no embedding entry; provider `embed` is never called (spy) (FR-016, SC-005, research R9)
- [x] T022 [P] [US1] Write `tests/unit/test_catalog.py`: schema per contracts/catalog.md, created on first write only; `BEGIN IMMEDIATE` transactions for build start, publish, failure and recovery; `one_active` unique index; newer `user_version` → `SCHEMA_UNSUPPORTED`; corrupt file → error, never recreated (FR-011, FR-017, checklist CHK025)
- [x] T023 [P] [US1] Write `tests/unit/test_ingest_lock.py`: second `IngestLock` in another process → `BUILD_BUSY`; released on process exit including SIGKILL (FR-011)
- [x] T024 [US1] Write `tests/integration/test_build.py` using `snapshot_env` + `FakeEmbeddingProvider`: build → `validated` snapshot under `data/snapshots/<id>/` with files 0444 and exactly the contract file set; manifest counts equal DB counts; build does not activate unless `--activate`; required source `failed` or missing on disk → `REQUIRED_SOURCE_FAILED` before chunking; optional export failed → limitation; injected low free space → `DISK_INSUFFICIENT` before staging; wrong-dimension/NaN provider → build fails, snapshot `failed` (FR-009–FR-012, US1 AS1, AS7)
- [x] T025 [US1] Write `tests/integration/test_build_determinism_reuse.py`: two builds → identical `chunks` rows (all columns except rowid) and different snapshot IDs; second build makes zero provider calls and records `embedded_reused == chunks`; changing identity (digest override) → full re-embed; reuse never reads from `failed`/`deleted` snapshots; build pins reuse sources while reading (FR-005, FR-008, SC-001 logic, SC-002, research R6)
- [x] T026 [US1] Write `tests/integration/test_build_interruption.py`: for each stage (`normalizing`, `chunking`, `writing`, `embedding`, `validating`, `publishing`) inject a failure via the `BuildService` stage hook **and** run a real subprocess build that is SIGKILLed on entering the stage (hook signals via a file); afterwards the previously active snapshot's files, the active pointer and history are byte-identical; the next build removes `data/staging/build-*`, marks the stale job/snapshot `failed (interrupted)`, and deletes a published-but-unregistered directory (FR-011, SC-004, US1 AS6)
- [x] T027 [US1] Write `tests/integration/test_lock_changes.py`: lock v1 → build A; lock v2 with one file deleted and one renamed → build B; B lacks the deleted path and has the new path, while A's corpus still has the old content (SC-007, US1 AS8)
- [x] T028 [US1] Write `tests/contract/test_cli_index_build.py`: help first line per contracts/cli.md; `--json` schema; exit 0/1/2; provider unreachable → exit 1 mentioning `--lexical-only`; `--lexical-only` → `semantic: absent`, no vector files, FTS queryable; stderr progress contains no chunk text; socket guard proves no non-loopback connection (FR-009, FR-022, LOC-003, LOC-006)

### Implementation for User Story 1

- [x] T029 [US1] Implement `Chunker` in `src/score_docs_assistant/ingestion/chunking.py` (research R3 steps 1–11: block walk, need/table/code/diagram/prose rules, sentence splitting with overlap, line and row splitting, oversize fallback, prefix building with elision, IDs and hashes) — makes T015, T016 pass
- [x] T030 [US1] Implement `OllamaEmbeddingProvider` in `src/score_docs_assistant/models/ollama_embed.py` (`/api/embed` with `truncate:false`, batching, timeout from `index.embedding_timeout_seconds`, `/api/show` + `/api/tags` identity, error mapping) — makes T019 pass
- [x] T031 [P] [US1] Implement `storage/corpus_db.py`: `write_corpus(path, documents, entities, chunks)` (schema, inserts in corpus order, FTS rebuild, VACUUM, close) and `open_corpus_readonly(path)` via `open_hardened` — makes T017 pass
- [x] T032 [P] [US1] Implement `storage/vectors.py`: `write_vectors`, `open_vectors` (memmap after size check), `check_vectors` (finite, unit norm ±1e-3) — makes T018 pass
- [x] T033 [P] [US1] Implement `storage/manifest.py`: build/read `SnapshotManifest` and `EmbeddingManifest`, `hash_files(dir)`, schema gate — makes T020 pass
- [x] T034 [US1] Implement `SnapshotValidator` in `storage/validation.py` (integrity checks incl. exact `sqlite_master` comparison, semantic status vs model lock and optional runtime identity) — makes T021 pass
- [x] T035 [P] [US1] Implement `Catalog` in `storage/catalog.py` (schema, create-on-write, build-start/publish/fail/recovery transactions, queries) — makes T022 pass
- [x] T036 [P] [US1] Implement `IngestLock` in `storage/locks.py` and the pin primitives needed by the build (`Pin` shared lock on `data/pins/<id>.pin`) in `storage/pins.py` — makes T023 pass
- [x] T037 [US1] Implement `BuildService` in `storage/build.py`: lock + disk precheck, recovery, lock verification, normalization via `NormalizationService`, chunking, corpus write, reuse lookup across retained snapshots with identical identity (pinned), embedding of misses, vector/manifest/report writing, validation, fsync + chmod 0444 + `os.replace` publish, publish transaction; a stage-hook parameter for tests; logs contain IDs/counts only — makes T024–T027 pass (research R6, R7)
- [x] T038 [US1] Implement `index build` in `src/score_docs_assistant/cli/index.py` (options, progress on stderr, `--json`, `--lexical-only`, `--activate` wired after US2 — until then the option errors with exit 2 "not yet available") and register it in `cli/main.py` — makes T028 pass
- [x] T039 [US1] Add a `real_runtime` test to `tests/integration/test_real_runtime.py`: real `OllamaEmbeddingProvider` identity (dimension 768, digest = model lock); over-bound input → `EMBEDDING_INPUT_TOO_LONG`; a real build of the fixture lock validates (FR-007, SC-003)

**Checkpoint**: full local gate green; run quickstart B on the real lock and record timings,
chunk counts by kind, max `embedding_token_estimate` and reuse numbers in `verification.md`.

---

## Phase 4: User Story 2 — Activate, pin, roll back, retain (Priority: P2)

**Goal**: atomic activation and rollback with checksum re-verification, cross-process pins,
retention of snapshots and sources, and a corpus probe that reports `compatible`.

**Independent Test**: activate A, pin A in a subprocess, activate B, and retention keeps A until
the subprocess is killed; rollback twice; tampered target refused.

### Tests for User Story 2

- [x] T040 [P] [US2] Write `tests/unit/test_lifecycle.py`: activate `validated` → `active` and previous → `retired` in one transaction with a history row; `failed`/`building`/`deleted` → `NOT_ACTIVATABLE`; activating the active snapshot is a no-op; tampered file or manifest-hash mismatch → `CHECKSUM_MISMATCH` naming the file, state unchanged; rollback targets `previous_id` of the latest history row, and a second rollback returns; no history or deleted target → `NO_ROLLBACK_TARGET`; lexical-over-semantic activation returns a warning (FR-012, FR-013, US2 AS1, AS4)
- [x] T041 [P] [US2] Write `tests/integration/test_pins.py`: a subprocess pins A; retention skips A (reported "pinned"); after SIGKILL of the subprocess, retention deletes A; a pinned handle opened on A keeps returning A's manifest, FTS results and vectors after B is activated; `pin()` on a deleted snapshot → `SNAPSHOT_NOT_FOUND`; `pin_active()` retries once when its target is deleted between resolve and pin (FR-014, SC-008, research R8)
- [x] T042 [P] [US2] Write `tests/integration/test_retention.py`: with 4 snapshots and `retention_count=2`, the newest two are kept (the active one always) and older unpinned ones are deleted (row `deleted`, directory gone, pin file removed); source revisions referenced by neither retained manifests nor the current lock are deleted, referenced ones kept; `data/cache/git/<id>.git` is deleted only for source IDs absent from both; a crash mid-deletion (directory partially removed, row still `retired`) → activation refused, next retention completes; with active A (rollback target Z), newer validated B and C, activating C keeps A (C's rollback target) and deletes older ones even though B is newer (FR-015, research R12, checklist CHK023)
- [x] T043 [P] [US2] Extend `tests/unit/test_corpus_probe.py` and `tests/contract/test_health_api.py`: probe `absent` (no catalog or no active), `incompatible` (newer `user_version`, missing manifest, unsupported manifest schema), `compatible`; readiness: search unavailable with `not_implemented` when compatible, chat `not_implemented` when compatible, F001 reasons unchanged otherwise; doctor `CORPUS_ABSENT` guidance names `index build --activate` (FR-021, research R11)
- [x] T044 [US2] Write `tests/contract/test_cli_snapshots.py`: `snapshots list` table/JSON columns incl. `PINNED` and the active marker, `--all` shows deleted; `activate`/`rollback` exit codes and messages per contracts/cli.md; activation during a held ingest lock → `BUILD_BUSY`; `index build --activate` activates after validation; these commands open no sockets except the identity query (socket guard) (FR-013, FR-022)

### Implementation for User Story 2

- [x] T045 [US2] Implement `FileSnapshotStore` in `storage/snapshot_store.py` (`list`, `pin`, `pin_active`, handle exposing manifest, read-only corpus connection and lazy vector memmap) — makes the handle parts of T041 pass
- [x] T046 [US2] Implement `activate`, `rollback` and `run_retention` in `storage/lifecycle.py` (ingest lock, checksum and schema re-verification, identity query with `unverified` fallback, single transaction, history, warnings, retention order per research R12) — makes T040–T042 pass
- [x] T047 [US2] Add `CorpusState.COMPATIBLE` and catalog-based probing to `storage/corpus_probe.py`; update `readiness.py` (chat `not_implemented` when compatible) and `diagnostics/checks.py` guidance — makes T043 pass
- [x] T048 [US2] Implement `snapshots list|activate|rollback` in `src/score_docs_assistant/cli/snapshots.py`, enable `index build --activate` in `cli/index.py`, and register the commands — makes T044 pass

**Checkpoint**: full local gate green; run quickstart C and D on the real snapshots and record
the results in `verification.md`.

---

## Phase 5: User Story 3 — Validate and move snapshots as verified bundles (Priority: P3)

**Goal**: on-demand `index validate`; `bundle export|inspect|import` with full verification and
license gating.

**Independent Test**: export → inspect → import into a fresh data dir → identical identities;
hostile bundles refused with nothing registered.

### Tests for User Story 3

- [ ] T049 [P] [US3] Write `tests/contract/test_cli_index_validate.py`: help first line; exit 0 (including semantic `disabled`/`unverified`), 1 on integrity failure or unknown ID, 2 on usage error; report written to `data/reports/validate-<id>-<utc>.json`; the snapshot directory is unmodified (mtimes and hashes); runtime reachable only via identity endpoints (spy) (FR-016, FR-022, US3 AS1)
- [ ] T050 [P] [US3] Create `tests/helpers/bundles.py` (build hostile tar.gz files in `tmp_path`: tampered member, `../x`, absolute path, symlink, hardlink, device/FIFO, directory entry, duplicate name, unlisted member, missing member, member count > cap, declared size > cap, header-sum ≠ `total_size`, manifest not first, manifest > 1 MiB, newer schema) and write `tests/integration/test_bundles.py`: export → import into a fresh data dir → same manifest SHA-256, file hashes, chunk IDs and entity keys, state `validated`, not active; each hostile bundle → `BUNDLE_REJECTED` with the matching reason, nothing registered, staging removed, no file written outside staging; injected free space < total + margin → `disk_insufficient` before extraction; re-import of the same bundle → no-op; same ID with a different manifest → `id_conflict`; import of a snapshot previously `deleted` → revived (FR-019, FR-020, SC-006, contracts/bundle.md)
- [ ] T051 [P] [US3] Write `tests/integration/test_bundle_license.py`: export of a snapshot with license-review documents without acknowledgement → `LICENSE_REVIEW_REQUIRED` listing the paths; with `--acknowledge-license-review "<reason>"` the reason and files appear in `bundle-manifest.json`; export refuses `failed` snapshots and existing output paths (FR-018, US3 AS4)
- [ ] T052 [US3] Write `tests/contract/test_cli_bundle.py`: `bundle export|inspect|import` help, `--json` output, exit codes; `inspect` writes nothing and reports identity, schema, counts, embedding identity and license notes; no sockets opened (FR-019, FR-022)

### Implementation for User Story 3

- [ ] T053 [US3] Implement `index validate` in `cli/index.py` using `SnapshotValidator` (report file, text output, exit mapping) — makes T049 pass
- [ ] T054 [US3] Implement `export_bundle`, `inspect_bundle` (pass 1) and `import_bundle` (pass 1 + pass 2, validation without a runtime, registration under the ingest lock) in `storage/bundles.py` per research R10 and contracts/bundle.md, reusing `sources/paths.py` — makes T050, T051 pass
- [ ] T055 [US3] Implement `bundle export|inspect|import` in `src/score_docs_assistant/cli/bundle.py` and register them — makes T052 pass

**Checkpoint**: full local gate green; run quickstart E, F and G and record them in `verification.md`.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T056 [P] Update `README.md` and `CLAUDE.md` Commands with the new `index`/`snapshots`/`bundle` commands (global `--config` first); re-run every documented command
- [ ] T057 [P] Update `docs/BACKLOG.md` (F003 state and evidence), `docs/TRACEABILITY.md` (rows for SRC-009, SRC-010, SRC-011, RET-007, OPS-002, OPS-003, LOC-003, LOC-006, SRC-012 → FRs, tasks, tests, evidence) and `docs/ASSUMPTIONS.md` (A-019: `pretoken-v1` estimate and its adversarial limit; A-020: exports contribute entities only; A-021: activation holds the ingest lock; A-022: chat also reports `not_implemented` while a compatible corpus exists, until F005)
- [ ] T058 Run the full gate (`uv run ruff format --check . && uv run ruff check . && uv run mypy src && uv run pytest && uv run python scripts/check_licenses.py`) plus `SCORE_ASSISTANT_REAL_RUNTIME=1 uv run pytest -m real_runtime`; record commands and results in `specs/003-snapshot-index/verification.md`, separating mocked, real-runtime and real-build evidence (constitution VII)
- [ ] T059 Walk quickstart A–G end to end on the workstation; record measured SC-001 timings, snapshot size on disk, chunk counts and every deviation in `verification.md`

---

## Dependencies & Execution Order

- **Setup (Phase 1)** → **Foundational (Phase 2)** → **US1 (Phase 3)** → **US2 (Phase 4)** → **US3 (Phase 5)** → **Polish**.
- US2 needs published snapshots (US1). US3 `index validate` needs only US1's validator, and
  bundle import registration uses the US1 catalog; US3 could start after US1 in parallel with
  US2 except T048/T055 (both edit command registration in `cli/main.py`).
- Within each story: tests first (they must fail) → storage/domain → service → CLI → checkpoint.

### Parallel Opportunities

- Setup: T002, T003.
- Foundational tests T004–T007; implementations T009–T012.
- US1 tests T014–T023; implementations T031–T033, T035–T036.
- US2 tests T040–T043. US3 tests T049–T051.

## Parallel Example: User Story 1

```bash
Task: "Write tests/unit/test_chunking.py"
Task: "Write tests/unit/test_corpus_db.py"
Task: "Write tests/unit/test_vectors.py"
Task: "Write tests/unit/test_ollama_embed.py"
Task: "Write tests/unit/test_validation.py"
```

## Implementation Strategy

### MVP First

Phases 1–3 → validate with the fixture suite and a real build of the pinned lock (quickstart B)
→ then US2, US3, Polish.

### Incremental Delivery

Each story checkpoint runs the full local gate and is committed separately.

## Notes

- Mark a task `[x]` only after its verification ran and passed; record deviations in `verification.md`.
- `real_runtime` tests skipped = "not run", never "passed".
- Never execute ingested content; never enable SQLite extensions; never `extractall` a bundle.
- Keep `data/` out of git; the real snapshot is evidence recorded by hash and counts, not committed.
