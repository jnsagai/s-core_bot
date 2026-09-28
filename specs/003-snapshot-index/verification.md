# Verification Record: F003 Immutable Snapshots and Local Embedding Index

Commands actually run, with results. Categories are kept apart (constitution VII):
**mocked** (deterministic tests with `FakeEmbeddingProvider`), **real runtime** (local Ollama),
**real build** (the pinned F002 lock on the workstation). "Not run" means not run.

## Phases 1–2 (Setup, Foundational) — 2026-09-28

```text
$ uv lock && uv sync --locked                      # + numpy 2.5.3
$ uv run python scripts/check_licenses.py --write-notices
License check passed: 42 packages, all allowed or reviewed.
$ uv run ruff format --check . && uv run ruff check . && uv run mypy src
Success: no issues found in 82 source files
$ uv run pytest -q
385 passed, 3 skipped
```

- **Pre-existing test defect found and fixed**: `tests/contract/test_cli_models.py`
  `test_pull_writes_lock_and_second_run_is_already_present` and `test_pull_refuses_remote_model`
  read the workstation's real free disk space. They failed both with and without F003 changes
  (confirmed with `git stash`) once the root filesystem dropped to 4.3 GiB free, below the
  profile size. Both now patch `shutil.disk_usage` like the neighbouring disk-shortfall test does.
- **Environment note**: root filesystem free space fell from 11 GiB to 4.3 GiB (99 % used)
  during this session. This project's `data/` is 18 MB and the new dependency about 50 MB; the
  growth is elsewhere on the machine. It is a risk for real builds (the build precheck needs
  2 GiB plus the newest snapshot).

## Phase 3 (US1 — build a validated snapshot) checkpoint — 2026-09-28

### Deterministic suite (mocked provider)

```text
$ uv run ruff format --check . && uv run ruff check . && uv run mypy src
238 files already formatted / All checks passed! / Success: no issues found in 82 source files
$ uv run pytest -q
505 passed, 6 skipped (real_runtime / real_network opt-ins: not run in this invocation)
```

Covers T015–T028: chunk rules (19 tests), corpus schema/FTS, vectors, manifest gate, Ollama
provider over a mocked transport (`truncate: false` asserted), catalog, cross-process ingest
lock, 21 validator tests (one crafted defect per integrity check, semantic statuses),
build pipeline, duplicate-build identity + full reuse, and **interruption at all six stages by
both an injected exception and a real SIGKILL of a child build process**. After each case, the
active snapshot's file hashes, pointer and history are byte-identical, and the next build
recovers. The publish window (directory moved, commit missing) is covered too. T020's full
manifest-field check is in `tests/integration/test_build.py::test_build_publishes_validated_snapshot`.

### Real runtime (Ollama 0.34.0, nomic-embed-text 0a109f42…)

```text
$ SCORE_ASSISTANT_REAL_RUNTIME=1 uv run pytest -q tests/integration/test_real_runtime.py \
    -k "embedding or over_bound or fixture_build"
3 passed
```

The identity matches the model lock (dimension 768, context 2048). A 3 000-word input →
`EMBEDDING_INPUT_TOO_LONG` (no silent truncation). A real build of the synthetic fixture lock
validates.

### Real build of the pinned F002 lock (quickstart B)

```text
$ /usr/bin/time -v uv run score-assistant --config config/local.yaml index build --json
{"counts": {"chunks": 5658, "chunks_by_kind": {"code": 217, "diagram": 27, "literal": 21,
 "need": 2265, "prose": 2797, "table": 331}, "documents": 635, "embedded_new": 5658,
 "embedded_reused": 0, "entities": 4336, "relations": 9740}, "duration_seconds": 46.874,
 "semantic": "present", "snapshot_id": "20260928T135739Z-9f1f3a1a", "state": "validated", …}
Elapsed (wall clock): 0:47.38   Maximum resident set size: 318936 kB
$ … index build --json          # unchanged lock, second run
{… "embedded_new": 0, "embedded_reused": 5658, "duration_seconds": 9.393,
 "snapshot_id": "20260928T135835Z-3e756999", …}   Elapsed: 0:09.90
```

- **SC-001** (measured, reference workstation, GPU): full build 47 s (< 15 min); unchanged
  rebuild 9.9 s (< 2 min) with 0 embedding requests. 5 602 unique embedding inputs were sent
  (56 chunks share an identical input).
- **SC-002** (real): SHA-256 over all `chunks` rows (every column except rowid) is identical for
  both snapshots (`cc2095dcfcd5383e…`); `embeddings.f32` is identical too (`7a5b533a…`).
- **SC-003** (real): the build succeeded with `truncate:false`, so every one of the 5 602 inputs
  fit the 2048-token runtime bound. Max `embedding_token_estimate` = 923 (cap 1 800); max display
  chunk = 816 estimated tokens (a unit allowed over `max_tokens` because it fits the cap).
- Snapshot size on disk: 39 MB. Measured chunk count 5 658 is below the plan's 10–25 k estimate
  (recorded; prose sections in these sources are short, median 135 estimated tokens).
- All 2 168 git-source need entities have need chunks (2 265 need chunks including continuations).
- **Deviation**: quickstart B used the `sqlite3` CLI, which is not installed on the workstation;
  the quickstart now uses a `uv run python` one-liner.

## Phase 4 (US2 — activate, pin, roll back, retain) checkpoint — 2026-09-28

```text
$ uv run ruff format --check . && uv run ruff check . && uv run mypy src && uv run pytest -q
533 passed, 6 skipped
```

Mocked-provider coverage: activation/rollback transitions, history and double rollback,
no-op re-activation, `NOT_ACTIVATABLE`, checksum/manifest tamper refusal with the active
snapshot unchanged, lexical-over-semantic warning, semantic `disabled`/`unverified` warnings;
**cross-process pins with a real child process** (retention skips the pinned snapshot, SIGKILL
releases it, and the next retention deletes it); a pinned handle keeps reading the original
manifest, FTS and vectors after another snapshot is activated; `pin_active` retry; retention
keeps active plus rollback target even when newer validated snapshots exist; source and git-cache
pruning; crash mid-deletion completed by the next retention; probe `absent|incompatible|
compatible`; readiness keeps search and chat `not_implemented` with a compatible corpus;
`snapshots` CLI exit codes, `BUILD_BUSY` during a held ingest lock, and no foreign sockets.

- Test-design correction: the first retention tests built several snapshots before activating
  the oldest, and retention (correctly, research R12) deleted the newer validated ones. The
  tests now build and activate one at a time.

### Real run on the workstation (quickstart C)

```text
$ score-assistant --config config/local.yaml snapshots activate 20260928T135739Z-9f1f3a1a
activated 20260928T135739Z-9f1f3a1a
$ score-assistant --config config/local.yaml doctor | grep corpus
[OK] corpus.state: An active, compatible corpus snapshot is installed.
(background reader holding flock(LOCK_SH) on data/pins/20260928T135739Z-9f1f3a1a.pin)
$ … snapshots activate 20260928T135835Z-3e756999
activated 20260928T135835Z-3e756999 (previous: 20260928T135739Z-9f1f3a1a)
$ … index build --activate --json          # 9.4 s, embedded_reused 5658, new 0
activated 20260928T140548Z-7c6a05b3 (previous: 20260928T135835Z-3e756999)
retention: kept 20260928T135739Z-9f1f3a1a (pinned by a reader)
(reader process killed)
$ … snapshots rollback
rolled back to 20260928T135835Z-3e756999 (previous: 20260928T140548Z-7c6a05b3)
retention: deleted 20260928T135739Z-9f1f3a1a
$ … snapshots rollback
rolled back to 20260928T140548Z-7c6a05b3 (previous: 20260928T135835Z-3e756999)
```

All four locked source revisions and both git caches were kept (all referenced by the lock).
Operator note: the reader was killed together with the agent's shell (a `pkill -f` pattern
matched the shell's own command line), which is still a kill of the pin holder; its pin was
released as designed.

## Phase 5 (US3 — validate and bundles) checkpoint and Phase 6 polish — 2026-09-28

### Full gate

```text
$ uv run ruff format --check . && uv run ruff check . && uv run mypy src
248 files already formatted / All checks passed! / Success: no issues found in 82 source files
$ uv run pytest -q
566 passed, 6 skipped (opt-in markers; not run in this invocation)
$ SCORE_ASSISTANT_REAL_RUNTIME=1 uv run pytest -q -m real_runtime
4 passed, 1 skipped (real model pull, separate opt-in: not run)
$ uv run python scripts/check_licenses.py
License check passed: 42 packages, all allowed or reviewed.
```

Mocked-provider coverage for US3: `index validate` exit codes (semantic `disabled`/`unverified`
exit 0, integrity failure exit 1 naming the file, unknown ID exit 1, usage exit 2), report written
to `data/reports/`, snapshot directory mtimes unchanged; bundle round trip on a fresh data dir;
**18 hostile bundles** (tampered, same-size byte flip, `..`, absolute, outside prefix, backslash,
symlink, hardlink, device, FIFO, directory entry, duplicate, unlisted, missing member, manifest not
first, manifest > 1 MiB, newer schema, wrong declared total), each rejected with its own reason,
nothing registered and staging removed; entry-count and size caps; disk check before extraction;
same-ID no-op, `id_conflict`, revival of a deleted ID; the license-review gate and recorded
acknowledgement; bundle commands proven socket-free.

### Real runs on the workstation

**Quickstart D (integrity)**: `index validate` on retired `20260928T135835Z-3e756999` → exit 0.
After appending to its `reports/coverage.json`:
`FAIL file:reports/coverage.json: reports/coverage.json: checksum mismatch`, exit 1.
`snapshots activate` → `CHECKSUM_MISMATCH: … reports/coverage.json changed or missing`, exit 1,
active unchanged.

**Quickstart E (runtime unavailable)**: stopping the snap-managed Ollama needs sudo, which the
agent does not have. Instead, a config copy pointed `runtime.base_url` at `http://127.0.0.1:9`
(nothing listening), which the client sees exactly as a stopped runtime:
`index build` → `EMBEDDING_UNAVAILABLE: no embedding runtime at http://127.0.0.1:9: [Errno 111]
Connection refused (use --lexical-only …)`, exit 1; `index build --lexical-only` → validated,
`semantic: absent`, 5 658 chunks, `network_used: none`; `index validate` → `semantic: unverified`,
exit 0. **Deviation**: the literal `snap stop ollama` step was not run.

**Quickstart F (bundles)**: export without acknowledgement → `LICENSE_REVIEW_REQUIRED` listing the
3 CC-BY-SA-4.0 `score-process` files; with `--acknowledge-license-review "local verification only;
not redistributed"` → 20.4 MB bundle (40.5 MB uncompressed, 7 entries) in 1.6 s; `bundle inspect`
shows identity, counts, embedding, revisions, license notes and the acknowledgement; import into a
fresh data dir in 1.3 s → `validated`, not active. **SC-006**: `sha256sum` of all 6 snapshot files
is identical between the original and the imported snapshot. In the fresh data dir (no model lock),
`index validate` reports integrity ok and semantic `disabled` with `models pull` guidance.

**Quickstart G (offline, `unshare -rn`, no network at all, not even loopback to Ollama)**:
`index validate` (exit 0, semantic `unverified`: "Network is unreachable"), `snapshots list`,
`bundle inspect`, `snapshots activate` of a lexical-only snapshot (with the
lexical-over-semantic warning; retention deleted the tampered snapshot), `snapshots rollback`,
`index build --lexical-only`, and `bundle import` into another fresh data dir all succeeded.

### Polish

- README Status/Scope/Quickstart and CLAUDE.md Commands list the new commands; the documented
  offline commands were re-run (`sources validate`, `doctor` → `[OK] corpus.state`, `snapshots
  list`, `index validate`, `bundle *`).
- `docs/TRACEABILITY.md`: SRC-009, RET-007, OPS-002, OPS-003 → verified (F003 scope); SRC-010,
  SRC-011 F003 parts verified; LOC-003, LOC-006, SRC-012 notes extended.
- `docs/ASSUMPTIONS.md`: A-019 to A-023 added. `docs/BACKLOG.md`: F003 implemented at this
  checkpoint (set to done after convergence, below).
- Environment: root filesystem still 99 % used (≈ 4.2 GiB free) at the end of the session.

## Phase 7 (Convergence) — 2026-09-28

The first converge pass (22 FRs, 8 SCs, 16 acceptance scenarios, 18 edge cases, plan decisions,
constitution I–XII) found 3 partial gaps, appended as T060–T062 and implemented:

- T060 (FR-012): the validator now fails `manifest.sources` when a required source is not `ok`
  and `manifest.coverage` when the coverage report is absent. A crafted, consistently re-hashed
  bundle claiming a failed required source is rejected at import (`validation_failed:
  manifest.sources…`). The real active snapshot still validates (integrity ok, semantic enabled).
- T061 (edge case "zero chunkable text"): `counts.documents_without_chunks` in the manifest,
  tested with a document containing only a `needtable`. Older manifests parse (default 0).
- T062 (contracts/cli.md): `snapshots list` shows the `ACTIVATED` column.

```text
$ uv run ruff format --check . && uv run ruff check . && uv run mypy src && uv run pytest -q
570 passed, 6 skipped
```

The second converge assessment found no remaining gaps: **converged**. Agent review, not a human
approval.
