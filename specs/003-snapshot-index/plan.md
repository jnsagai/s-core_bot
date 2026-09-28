# Implementation Plan: F003 Immutable Snapshots and Local Embedding Index

**Branch**: `003-snapshot-index` | **Date**: 2026-09-28 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/003-snapshot-index/spec.md`

## Summary

Turn the F002 lock plus normalization output into immutable, self-describing snapshots under
`data/snapshots/<id>/`. Each snapshot holds a structure-aware chunker's output in an SQLite
corpus with FTS5, L2-normalized float32 vectors from the local `nomic-embed-text` (reused across
builds by input hash plus exact identity, and never silently truncated), manifests with
checksums, and build reports. A catalog (`data/catalog.sqlite`) records states, the active
pointer and activation history. Builds happen only in staging behind a single-writer lock and
publish as `validated`. Activation and rollback re-verify checksums and switch in one
transaction. Readers pin snapshots with per-snapshot `flock` so retention never deletes what is
in use. Bundles move snapshots as verified tar.gz files. The F001 corpus probe learns
`compatible`.

## Technical Context

**Language/Version**: Python 3.12 (unchanged)

**Primary Dependencies**: new: **NumPy** (BSD-3-Clause; constitution baseline, research R5).
Existing: stdlib `sqlite3` (SQLite 3.53.1 with FTS5, verified), `tarfile`, `fcntl`; Pydantic,
Typer, httpx; F002 `NormalizationService`, `canonical.py`, `sources/paths.py`. External runtime:
Ollama 0.34.0 `/api/embed`, `/api/show`, `/api/tags` on loopback (build/validate/activate only).

**Storage**: files and SQLite under `data/`: `catalog.sqlite` (WAL), `snapshots/<id>/`
(manifest.json, corpus.sqlite, embeddings.f32, embedding-manifest.json, reports/),
`staging/build-<job>/`, `staging/import-<job>/`, `locks/ingest.lock`, `pins/<id>.pin`,
`reports/validate-*.json`. All of it is git-ignored.

**Testing**: pytest with the F001 loopback-only socket guard. A `FakeEmbeddingProvider`
(deterministic hash-seeded unit vectors, configurable failures: unreachable, wrong dimension,
NaN, too-long) is used via dependency injection. Fixture locks come from small synthetic RST/MD
sources plus F002 fixtures. Stage-failure injection happens via a hook in `BuildService`, plus a
real `SIGKILL` subprocess test. Cross-process pin tests use `multiprocessing`/subprocess. The
optional `real_runtime` marker covers real Ollama embedding checks (dimension, `truncate:false`
400 mapping, identity).

**Target Platform**: Linux x86-64 (unchanged; `fcntl.flock` is POSIX).

**Project Type**: single Python project, CLI + library.

**Performance Goals**: full build < 15 min, unchanged rebuild < 2 min (SC-001). Estimate:
≈ 70 embeddings/s measured (R1) → ~5 min for ~20 k chunks; normalization ≈ 7–25 s.

**Constraints**: no downloads; network only to the loopback embedding runtime; never truncate
embedding inputs (`truncate:false`); active snapshot untouched by builds; snapshots immutable;
no SQLite extensions, pickle or `.npy` object arrays; low free disk on the reference machine
(≈ 11 GiB), so the build checks free space before staging.

**Scale/Scope**: ~635 documents, ~4 300 entities (both sources + exports), an estimated
10–25 k chunks (measured count recorded at implementation). Performance budget reference
≤ 25 000 chunks (master spec §13.4).

## Constitution Check

*GATE: evaluated before Phase 0 and re-checked after Phase 1 design.*

| Principle | Status | How this plan complies |
| --- | --- | --- |
| I. Local operation | PASS | Embeddings come only from the loopback Ollama runtime. No downloads (FR-022). A lexical-only mode exists when embedding is unavailable. Serve path unchanged. |
| II. Evidence precedes assertions | PASS | Chunks keep document key, path, origin path, line span, heading path, entity keys and content hash, so F004/F005 citations can be server-assembled. Display text is verbatim, and synthetic prefixes live only in `embedding_input` (FR-004). |
| III. Snapshots explicit | PASS | The manifest records lock hash, revisions, processing and chunker hashes, token method and embedding identity. Files are 0444 and checksum-verified at validation, activation and rollback. Activation is one transaction. |
| IV. Documentation is untrusted | PASS | The corpus stores text only; parameterized SQL; no extension loading; raw float32 vectors, no pickle. Bundle import enforces path containment, regular files only, caps and hash verification before registration. |
| V. Read-only assistance | N/A (PASS) | No Q&A path. |
| VI. Modular monolith | PASS | `EmbeddingProvider` and `SnapshotStore` (master spec §5.1) are implemented as protocols. Domain records are free of SQLite/NumPy/Ollama types. No new services; NumPy is the constitution baseline, not new infrastructure. |
| VII. Honest verification | PASS | Fake-provider tests are labelled mocked, and real-runtime and real-build results are recorded separately in verification.md. Stage-kill tests are real subprocess kills. Unrun `real_runtime` tests are reported "not run". |
| VIII. Privacy | PASS | No telemetry. Build logs contain IDs, counts and timings, never chunk text. |
| IX. Spec-first | PASS | FR↔master IDs are in the spec. TRACEABILITY rows for SRC-009/010/011, RET-007, OPS-002/003, LOC-003/006, SRC-012 are updated after implementation. |
| X. Public profile separate | N/A (PASS) | No serving/bind changes. |
| XI. Licenses follow artifacts | PASS | The manifest lists license-review documents. Export refuses them without an explicit acknowledgement, which is recorded in the bundle. The nomic model license is recorded (Apache-2.0, R1). |
| XII. No implied authority | PASS | No approval semantics. "validated" means integrity-checked, not engineering approval (stated in CLI help). |

Post-design re-check (after Phase 1): **PASS**. The contracts add one loopback-only runtime
use (embed/show/tags) and one untrusted-input surface (bundle import) guarded per
[contracts/bundle.md](contracts/bundle.md). No Complexity Tracking entries.

## Project Structure

### Documentation (this feature)

```text
specs/003-snapshot-index/
├── plan.md, research.md, data-model.md, quickstart.md
├── contracts/
│   ├── cli.md              # index build|validate, snapshots list|activate|rollback, bundle export|inspect|import
│   ├── snapshot-files.md   # manifest, embedding manifest, embeddings.f32, corpus.sqlite schema
│   ├── catalog.md          # catalog schema, transactions, ingest lock, pins
│   └── bundle.md           # bundle layout, manifest, import rules
├── checklists/ requirements.md (+ checklist phase)
├── tasks.md
└── verification.md         # written during implementation
```

### Source Code (repository root)

```text
src/score_docs_assistant/
├── domain/snapshots.py         # Chunk, ChunkerConfig, EmbeddingIdentity, SnapshotManifest,
│                               # EmbeddingManifest, CorpusSnapshot, ValidationReport, BundleManifest,
│                               # SnapshotStore protocol
├── domain/errors.py            # + SnapshotError(code) family
├── config/schema.py            # + IndexConfig, BundleConfig (defaults; extra=forbid)
├── ingestion/
│   ├── tokens.py               # pretoken-v1 estimator (R2)
│   └── chunking.py             # Chunker: blocks → chunks (R3); sentence/line/row splitting
├── models/
│   ├── runtime.py              # EmbeddingProvider protocol filled in (identity(), embed())
│   └── ollama_embed.py         # OllamaEmbeddingProvider: /api/embed truncate:false, /api/show, /api/tags
├── storage/
│   ├── corpus_db.py            # write corpus.sqlite (schema, FTS), read-only open
│   ├── vectors.py              # write/read embeddings.f32 (+ shape/finite/norm checks)
│   ├── manifest.py             # manifest build/read, file hashing, schema gate
│   ├── catalog.py              # Catalog: schema, transactions, history, recovery
│   ├── locks.py                # ingest lock (flock EX|NB)
│   ├── pins.py                 # Pin / pin files (flock SH), retention probe (EX|NB)
│   ├── validation.py           # SnapshotValidator (R9)
│   ├── snapshot_store.py       # FileSnapshotStore: pin, pin_active, open handle, list
│   ├── build.py                # BuildService: staging pipeline, reuse, publish (R6, R7)
│   ├── lifecycle.py            # activate, rollback, retention (R7, R12)
│   ├── bundles.py              # export, inspect (pass 1), import (pass 2) (R10)
│   └── corpus_probe.py         # + COMPATIBLE (R11)
├── readiness.py                # chat not_implemented when corpus compatible (R11)
├── diagnostics/checks.py       # corpus guidance → new commands
└── cli/
    ├── index.py                # index build|validate
    ├── snapshots.py            # snapshots list|activate|rollback
    └── bundle.py               # bundle export|inspect|import
config/model-profiles.yaml      # nomic-embed-text license: Apache-2.0 (R1)
tests/
├── helpers/fake_embedding.py   # FakeEmbeddingProvider
├── fixtures/snapshot/          # synthetic lock + sources (SYNTHETIC header), hostile bundles built in tmp
├── unit/        # tokens, chunking (golden), manifest, vectors, catalog, pins, validation, config
├── contract/    # CLI exit codes/help/JSON, network confinement, readiness/doctor
└── integration/ # build pipeline, kill-at-stage, reuse, rename/delete, activation+pins, bundles, real_runtime
```

**Structure Decision**: follows master spec §14. Chunking lives in `ingestion/` (spec §14:
"normalization, chunking"), persistence and lifecycle in `storage/`, and the embedding provider
in `models/`. `SnapshotStore` is the master-spec §5.1 interface that F004 will consume for pinned
read access.

## Key Design Decisions

1. **Never silently truncate** (R1): `truncate:false` on every embed call. HTTP 400 context
   errors fail the build naming the chunk. The conservative `pretoken-v1` estimate (R2) keeps
   real inputs well below the bound, and the runtime check is the hard guarantee.
2. **Structure-first chunking** (R3): needs, tables, code and diagrams are their own chunks. Prose
   accumulates only within one heading path. Splits happen at child, sentence, line or row
   boundaries with continuation labels. Oversize is allowed only up to the embedding cap,
   otherwise the build fails.
3. **Exports: entities only** (R3): no duplicate need chunks from unverified exports.
4. **Staging → validate → publish → (opt-in) activate** (R7): only the publish transaction and
   activation touch catalog state that readers use. Recovery happens on the next build under
   the ingest lock.
5. **Pins via `flock`** (R8): kernel-released on any process exit. Retention probes with
   `LOCK_EX|LOCK_NB` and deletes while holding the exclusive lock. Readers re-check after pinning.
6. **Reuse only from retained snapshots with an identical identity** (R6). The build pins its
   reuse sources.
7. **Validation separates integrity from semantic status** (R9). Identity is checked against the
   model lock always and the runtime when reachable, and never by embedding.
8. **Bundles: two-pass import** (R10): the whole archive is checked before any write, and the
   full validator runs before registration.
9. **Deterministic chunk records**: sources by ID, documents by path, blocks in order, and IDs
   from canonical hashes. The snapshot ID and timestamps are the only per-build values, and they
   are outside chunk records.

## Verification Strategy

| Requirement | Verification (layer) |
| --- | --- |
| FR-001, FR-002 | unit/golden: fixture docs → chunk kinds, section boundaries, need = one chunk, long need continuations, table header repetition + row ranges, code line splits, sentence overlap 50–100, no text loss (reconstruction test) |
| FR-003, SC-003 | unit: `pretoken-v1` table cases; property test on generated text: every `embedding_token_estimate ≤ cap`; unsplittable over cap → `CHUNK_UNSPLITTABLE`; real_runtime: over-bound input → 400 → `EMBEDDING_INPUT_TOO_LONG`; real build success recorded |
| FR-004, FR-005, SC-002 | unit: chunk ID derivation; display text has no prefix; integration: build twice → identical chunk rows; ID changes when chunker config changes |
| FR-006 | unit: corpus schema, `user_version`, FTS query for `feat_req__…` and `MLE.3.BP1` tokens, export entities `unverified`, one relation row per link; no `enable_load_extension` (grep test) |
| FR-007 | unit: vector file layout/size, re-normalization, NaN/wrong-dim → failure; fake provider records `truncate` flag false |
| FR-008, SC-001 | integration: second build → 0 provider calls; identity field change → full re-embed; real timings in verification.md |
| FR-009 | integration: provider unreachable → exit 1; `--lexical-only` → `semantic: absent`, no vectors, FTS works |
| FR-010 | unit: manifest fields/order/checksums; license_review populated from F002 records |
| FR-011, SC-004 | integration: failure injected at each stage + real SIGKILL subprocess at each stage → active pointer/catalog/active files unchanged; next build recovers staging and marks `failed`; concurrent build → `BUILD_BUSY` |
| FR-012 | integration: required source failed/missing → exit 1 before chunking; optional export failed → limitation in manifest |
| FR-013 | integration: activate/rollback transitions, history, double rollback, no-op re-activate, checksum tamper refusal, lexical-over-semantic warning, `failed` not activatable |
| FR-014, SC-008 | integration: subprocess pin → retention skips; SIGKILL → retention deletes; pinned handle reads A after activating B (metadata, FTS, vectors) |
| FR-015 | integration: retention count, unreferenced source revisions and git caches deleted, referenced kept |
| FR-016, SC-005 | unit: each integrity check fails on a crafted defect; digest/dimension/preprocessing mismatch → `disabled`; runtime unreachable → `unverified`; exit codes; no embed calls (spy) |
| FR-017 | unit: newer `user_version`/`schema_version` in catalog, corpus, manifest, bundle → refused before other reads |
| FR-018–FR-020, SC-006 | integration: export → import into fresh data dir → identical hashes/IDs; hostile bundles (tamper, `..`, absolute, symlink, hardlink, device, duplicate, over-count, over-size, disk check via injected free-space function) → rejected, nothing registered; license acknowledgement flow |
| FR-021 | contract: probe states absent/incompatible/compatible; readiness search `not_implemented`, chat `not_implemented`; doctor guidance text |
| FR-022 | contract: help texts; socket guard + provider spy prove only loopback embedding in build and only identity queries in validate/activate; `bundle`/`snapshots list` open no sockets |
| SC-007 | integration: lock v1 → lock v2 with deleted and renamed files → new snapshot paths correct, old snapshot unchanged |

## Complexity Tracking

No constitution violations; section intentionally empty.
