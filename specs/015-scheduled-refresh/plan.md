# Implementation Plan: F011 Scheduled Corpus Refresh

**Branch**: `015-scheduled-refresh` | **Date**: 2026-10-02 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/015-scheduled-refresh/spec.md`

## Summary

Add a one-shot `score-assistant refresh` command that chains the existing F002/F003 operations
with two new pieces: a cheap **upstream check** (git `ls-remote` per git source, conditional HTTP
GET with stored ETag/Last-Modified per needs export) and a **promotion gate** (integrity re-check,
exact-ID suite, coverage-drop guard, semantic not lost, required sources present). Sync is taught to
leave an unchanged lock untouched so frequent polling creates no files. Activation reuses the
existing atomic activation; `serve` already pins the active snapshot per request, so it picks up a
new snapshot without restart. Scheduling is an opt-in systemd user timer installed by a script;
`serve` never refreshes. `doctor` reports the last outcome from a single replaced state file.

## Technical Context

**Language/Version**: Python 3.12 (uv-managed), unchanged.

**Primary Dependencies**: existing only — Typer (CLI), Pydantic (state/config models), httpx
(conditional export request), system `git` ≥ 2.34 via the hardened `GitClient`. No new packages.

**Storage**: files under `data/`: `source-lock.json` (unchanged format), new
`refresh-state.json` (atomic replace), new `locks/refresh.lock` (flock). Snapshot catalog and
layout unchanged.

**Testing**: pytest; local bare git repositories over `file://` (existing `tests/helpers/git_repos.py`
pattern with `allowed_protocols={"file"}`), httpx `MockTransport` for exports, the fake embedding
provider, the existing socket guard (no real network). Opt-in real-network run recorded in
`verification.md`.

**Target Platform**: Linux x86-64 with systemd user sessions (timer); the command itself runs on
any platform the CLI runs on.

**Project Type**: CLI + local service (modular monolith).

**Performance Goals**: unchanged run < 10 s on the reference machine (SC-002); changed run =
sync + build time (F003 measured: full build 47 s, unchanged-content rebuild 9.9 s with embedding
reuse) + gate (exact-ID suite over ~2 200 IDs, seconds).

**Constraints**: no network in `serve`; network only to registry-allowlisted hosts; no new file
per unchanged run; single-writer ingest lock respected; no document text in logs/output.

**Scale/Scope**: 4 sources today (2 git, 2 needs exports); ~6 000 chunks per snapshot; timer
default every 15 min (96 checks/day ≈ 4 tiny requests each when unchanged).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
| --- | --- | --- |
| I. Local operation | pass | Network only in the operator-invoked `refresh` (or the timer the operator installs); `serve` gains no network path. Same allowlist and limits as `sources sync`. A-057. |
| II. Evidence precedes assertions | pass | Answer path unchanged; citations still from stored provenance of the pinned snapshot. |
| III. Snapshots explicit | pass | New snapshot built through F003 (recorded revisions, hashes); activation atomic via existing lifecycle; requests stay pinned. |
| IV. Documentation untrusted | pass | Reuses hardened git (no checkout) and export fetch; the check reads only refs and HTTP headers. |
| V. Read-only assistance | pass | Q&A path untouched; refresh is not reachable from the model or API. |
| VI. Modular monolith | pass | New `refresh/` module in the same app; no daemon, queue or scheduler service (systemd timer is the OS's, opt-in). |
| VII. Honest verification | pass | Tests for every outcome and gate check; real upstream run recorded separately; timer install verified with `systemd-analyze verify`, enabling it on the owner's machine is reported as not done unless done. |
| VIII. Privacy | pass | Output and state carry IDs, revisions, counts, reasons only. |
| IX. Spec-first | pass | This spec/plan/tasks; master IDs SRC-002, SRC-009, OPS-002, LOC-003 traced. |
| X. Public deployment separate | pass | No new listener; loopback default untouched; webhooks explicitly rejected (F010 deferred). |
| XI. Licenses follow artifacts | pass | Sync's license handling reused unchanged; no new dependency. |
| XII. No implied authority | pass | Auto-activation documented as operational, not an engineering review; `held` never claims approval. |

No violations; Complexity Tracking empty.

## Project Structure

### Documentation (this feature)

```text
specs/015-scheduled-refresh/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── cli.md            # `refresh` command, outcomes, exit codes, JSON
│   └── state-file.md     # data/refresh-state.json
├── checklists/
└── tasks.md
```

### Source Code (repository root)

```text
src/score_docs_assistant/
├── refresh/                 # NEW
│   ├── __init__.py
│   ├── models.py            # RefreshOutcome, SourceCheck, GateCheck, RefreshState (Pydantic)
│   ├── state.py             # read/write data/refresh-state.json (atomic replace)
│   ├── upstream.py          # UpstreamChecker: ls-remote + conditional export probe
│   ├── gate.py              # PromotionGate
│   └── service.py           # RefreshService: lock → check → sync → build → gate → activate
├── sources/
│   ├── sync.py              # + keep unchanged lock (no rewrite/archive), outcome.lock_changed
│   └── http_fetch.py        # + probe_export(): conditional GET, headers only, redirect-validated
├── config/schema.py         # + RefreshConfig (max_count_drop, check_exports)
├── diagnostics/checks.py    # + check_refresh_state
├── diagnostics/doctor.py    # + refresh line
└── cli/refresh.py           # NEW `score-assistant refresh`

scripts/install_refresh_timer.sh   # NEW: write/enable/disable systemd user units
deploy/systemd/                    # NEW: unit templates (service + timer)
docs/runbooks/refresh.md           # NEW runbook
tests/unit/test_refresh_*.py, tests/integration/test_refresh_*.py, tests/contract/test_cli_refresh.py
```

**Structure Decision**: single project, new `refresh` package beside `sources` and `storage`,
depending on them through their existing services (SyncService, BuildService, lifecycle,
SearchService) injected into `RefreshService` for tests.

## Key Design

1. **Order**: acquire `locks/refresh.lock` (flock, non-blocking → `busy`) → upstream check →
   decide → sync (if needed) → decide → build (if needed, in mirrored mode) → gate → activate under
   the ingest lock (re-checking the active snapshot is still the gate's baseline) → write state.
2. **"Built from current lock"**: the active snapshot's manifest `lock_sha256` equals the SHA-256 of
   `data/source-lock.json`. Combined with sync not rewriting an unchanged lock, this makes the
   decision exact and repeatable.
3. **Unchanged sync**: compare the new lock with the current one ignoring `generated_at` and
   per-source `fetched_at`; if equal, do not write the lock or its archive.
4. **Upstream check** returns per source `unchanged | changed | unknown`; refresh skips sync only
   if every source is `unchanged`, the registry SHA matches the lock, and the active snapshot was
   built from the current lock. Any `unknown` (no validator, first run) → sync. A check error → `failed`.
5. **Gate**: integrity (`verify_for_activation` + build state `validated`), `exact_ids`
   (`exact_id_suite` on the candidate, all first), `coverage_drop` (documents, chunks, entities vs
   active, ≤ `max_count_drop`), `semantic` (not lost), `required_sources` (every required lock
   source `ok` in the candidate coverage). All checks run and are reported, even after a failure.
6. **State**: one JSON file replaced atomically per run (also on `up-to-date`), holding the latest
   run, `last_success_at` and export validators (saved only after a successful sync).
7. **Exit codes**: 0 up-to-date/activated, 1 failed, 2 config/usage, 3 held, 4 busy.
8. **Timer**: `scripts/install_refresh_timer.sh` renders the unit templates with the repo path,
   `uv` path and config into `~/.config/systemd/user/` (or `--unit-dir`), then `systemctl --user
   daemon-reload && enable --now`; `--uninstall` disables and removes. `Persistent=true`,
   `RandomizedDelaySec=2min`, `--interval` default `15min`.

## Complexity Tracking

None.
