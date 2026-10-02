# Tasks: F011 Scheduled Corpus Refresh

**Input**: `specs/015-scheduled-refresh/` (spec, plan, research, data-model, contracts, quickstart)

Tests are mandatory in this project (constitution VII). `[P]` = parallelizable (different files,
no open dependency). Paths are relative to `src/score_docs_assistant/` unless they start with
`tests/`, `scripts/`, `deploy/`, `docs/` or `specs/`.

## Phase 1: Setup

- [x] T001 Create package `refresh/__init__.py` and `RefreshConfig` (`max_count_drop` 0.20 in [0,1), `check_exports` true) as `AppConfig.refresh` in `config/schema.py`; tests in `tests/unit/test_refresh_config.py` (defaults, bounds, unknown key rejected, existing configs still load)

## Phase 2: Foundational (blocks all stories)

- [x] T002 [P] Records `SourceCheck`, `GateCheck`, `RevisionChange`, `RefreshRun`, `ExportValidator`, `RefreshState` (extra=forbid, UTC datetimes) in `refresh/models.py`; tests `tests/unit/test_refresh_models.py`
- [x] T003 [P] `refresh/state.py`: `read_state(data_dir)` (missing → None, invalid → `StateInvalid` marker), `write_state` atomic temp+fsync+replace; tests `tests/unit/test_refresh_state.py` (round trip, invalid file, atomic replace leaves no temp files)
- [x] T004 [P] `SyncService(keep_unchanged_lock=...)` in `sources/sync.py`: compare new lock to current ignoring `generated_at` and `fetched_at`; when equal skip `write_lock` and `archive_lock`; `SyncOutcome.lock_changed`; `sources sync` behaviour unchanged; tests `tests/integration/test_sync_unchanged_lock.py` (file:// git fixture: second sync with flag leaves lock bytes, mtime and archive dir unchanged; without flag unchanged from F002)
- [x] T005 [P] `probe_export()` in `sources/http_fetch.py`: conditional GET (`If-None-Match`, `If-Modified-Since`), allowlist + per-hop redirect validation, registry timeouts, body never read; returns `not_modified | modified | no_validator` + new ETag/Last-Modified; tests `tests/unit/test_probe_export.py` (MockTransport: 304, 200, redirect to disallowed host refused, 5xx/timeout → FetchError)

## Phase 3: User Story 1 — one command brings the assistant up to date (P1) 🎯 MVP

**Independent test**: fixture upstream change → `refresh` activates a snapshot that finds the new text; second run `up-to-date` with no new files.

- [x] T006 [US1] `refresh/upstream.py` `UpstreamChecker`: git sources via `GitClient.resolve_ref` vs lock revision; exports via `probe_export` with stored validators (`check_exports=false` or none stored → `unknown`); registry SHA vs lock; returns list[SourceCheck] + `registry_changed`; tests `tests/unit/test_refresh_upstream.py`
- [x] T007 [US1] `refresh/service.py` `RefreshService`: refresh flock (`locks/refresh.lock`, non-blocking → `busy`), check → decide (all unchanged + registry same + active manifest `lock_sha256` == current lock SHA → `up-to-date`) → sync (`keep_unchanged_lock=True`) → decide again → build in mirrored mode (FR-016) → gate hook → activate under ingest lock (baseline re-check) → state write (not on `busy`); export validators saved only after a successful sync; injected collaborators and clock; timings per step
- [x] T008 [US1] `cli/refresh.py` `score-assistant refresh [--sources] [--profiles-dir] [--lexical-only] [--json]`, text and JSON output per `contracts/cli.md`, exit codes 0/1/3/4 (2 via common error handling); register in `cli/main.py`
- [x] T009 [US1] Integration tests `tests/integration/test_refresh_flow.py`: (a) change upstream → `activated`, new text searchable, revision_changes reported; (b) immediate rerun → `up-to-date`, no sync, and no file under data/ other than `refresh-state.json` created or modified; (c) manual sync without build → refresh builds; (d) export validator 304 + git unchanged → no sync
- [x] T010 [US1] Serve pickup test `tests/integration/test_refresh_serve_pickup.py`: a live `SearchService` answers from the new snapshot after refresh activation; a request pinned before activation keeps its snapshot (SC-004)
- [x] T011 [US1] Contract tests `tests/contract/test_cli_refresh.py`: JSON keys, exit codes per outcome, no document text in output, `network_used`

## Phase 4: User Story 2 — a bad update never replaces a good snapshot (P1)

**Independent test**: fixture update removing most documents → `held` (`coverage_drop`), previous snapshot active, candidate `validated`.

- [x] T012 [US2] `refresh/gate.py` `PromotionGate`: integrity (`verify_for_activation` + state `validated`), `exact_ids` (`exact_id_suite` on candidate), `coverage_drop` (documents, chunks, entities vs active manifest, skipped with pass detail when nothing is active), `semantic` (not lost), `required_sources` (manifest coverage); runs all checks; unit tests `tests/unit/test_refresh_gate.py` with synthetic manifests
- [x] T013 [US2] Wire gate into `RefreshService`; `held` exit 3, candidate stays `validated`; activation refuses (held) when active changed since the gate baseline
- [x] T014 [US2] Integration tests `tests/integration/test_refresh_gate_flow.py`: mass deletion → held/coverage_drop; required git source unreachable → failed, lock and active untouched (exit 1); embedding provider unavailable with semantic active → failed; `--lexical-only` with semantic active → held/semantic; held candidate activatable via `snapshots activate`

## Phase 5: User Story 3 — scheduled, opt-in (P2)

**Independent test**: units render into a temp dir and pass `systemd-analyze verify`; overlapping runs → `busy`.

- [x] T015 [P] [US3] Unit templates `deploy/systemd/score-assistant-refresh.service` (Type=oneshot, WorkingDirectory, ExecStart with uv + `--config` + `refresh`, `Nice=10`) and `.timer` (`OnBootSec=2min`, `OnUnitActiveSec=@INTERVAL@`, `RandomizedDelaySec=2min`, `Persistent=true`)
- [x] T016 [US3] `scripts/install_refresh_timer.sh` (`--config`, `--interval` default 15min, `--unit-dir`, `--no-enable`, `--uninstall`); never runs refresh itself; tests `tests/unit/test_install_refresh_timer.py` (renders into tmp, placeholders replaced, absolute paths, `systemd-analyze verify` when available else skipped, uninstall removes files; `--no-enable` never calls systemctl)
- [x] T017 [US3] Overlap test `tests/integration/test_refresh_overlap.py`: refresh lock held by another process → `busy`, exit 4, state file untouched; ingest lock held (`BUILD_BUSY`) → `busy`
- [x] T018 [US3] Static check `tests/contract/test_serve_never_refreshes.py`: `api/` and `cli/serve.py` import nothing from `refresh` or `sources.sync`/`sources.http_fetch`, and no HTTP route path contains `refresh` (FR-012, FR-017)

## Phase 6: User Story 4 — freshness visible in doctor (P3)

- [x] T019 [US4] `check_refresh_state` in `diagnostics/checks.py` + call in `diagnostics/doctor.py` (info not-run, ok, warning held/failed/invalid; never failure); tests in `tests/unit/test_checks.py` and `tests/contract/test_cli_doctor.py` (exit code unaffected)

## Phase 7: Polish & cross-cutting

- [x] T020 [P] Runbook `docs/runbooks/refresh.md` (what it does, enable/disable timer, outcomes and exit codes, gate tuning, retention warning, containers note, rollback), README "Keeping the documentation up to date" section, CLAUDE.md command list
- [x] T021 Gates: `uv run ruff format --check . && uv run ruff check .`, `uv run mypy src`, `uv run pytest`, `uv run python scripts/check_licenses.py`, `uv run python scripts/check_traceability.py`
- [x] T022 Real run per `quickstart.md` §2–§4 on a copy of `data/` in the scratchpad (network + local embedding); record commands and results in `specs/015-scheduled-refresh/verification.md`
- [x] T023 Update `docs/BACKLOG.md` (F011 row), `docs/TRACEABILITY.md` (SRC-002, SRC-009, OPS-002, LOC-003 owners + F011 FRs), `docs/ASSUMPTIONS.md`, `docs/KNOWN_LIMITATIONS.md` (containers, gate is a proxy)

## Dependencies

- T001 → T002–T005 → US1 (T006–T011) → US2 (T012–T014) → US3, US4 (independent of each other) → Polish.
- US2 extends US1's service; US3's timer only needs the CLI (T008); US4 only needs the state (T003).

## Parallel examples

- Phase 2: T002, T003, T004, T005 together.
- After T008: T015/T016 (US3) and T019 (US4) in parallel with US2.

## Implementation strategy

MVP = Phase 1–3 (manual `refresh` with up-to-date detection), immediately followed by US2 because
unattended activation without the gate is not shippable; then the timer (US3), doctor (US4), docs
and real verification.

## Phase 8: Convergence

- [x] T024 Show the candidate's state and semantic mode on the `build` line of `refresh` text output in `cli/refresh.py`, with a contract test, per contracts/cli.md (partial)
