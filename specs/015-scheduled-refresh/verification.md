# Verification: F011 Scheduled Corpus Refresh

Reference machine: the owner's Linux laptop (RTX 4070, Ollama 0.34.0, `qwen3:4b-instruct` +
`nomic-embed-text`). Categories follow constitution VII: **mocked** (deterministic tests),
**real** (real network + local runtime), **not run**.

## Deterministic tests (mocked) — 2026-10-02

Fixture upstream: bare git repositories over `file://`, needs exports through an httpx
`MockTransport` honouring `If-None-Match`, the fake embedding provider, socket guard active.

| Command | Result |
| --- | --- |
| `uv run pytest tests/unit/test_refresh_*.py tests/unit/test_probe_export.py tests/unit/test_install_refresh_timer.py tests/integration/test_refresh_*.py tests/integration/test_sync_unchanged_lock.py tests/contract/test_cli_refresh.py tests/contract/test_serve_never_refreshes.py tests/contract/test_cli_doctor.py` | all passed |
| `uv run pytest` (full suite, at implementation checkpoint 1f44369) | 1224 passed, 10 skipped (opt-in real runtime/network), 355.65 s |
| `uv run ruff format --check . && uv run ruff check .` | clean |
| `uv run mypy src` | no issues in 147 source files |
| `uv run python scripts/check_licenses.py` | passed (470 packages) |
| `uv run python scripts/check_traceability.py` | passed |
| `systemd-analyze verify --user` on units rendered by `scripts/install_refresh_timer.sh --no-enable` | exit 0 |

Final gate rerun after docs: see "Final gates" below.

## Real run against upstream S-CORE (real) — 2026-10-02, on a scratch copy of `data/`

`cp -a data <scratch>/refresh-data`; config = `config/local.yaml` with `data_dir` set to the copy.

| Step | Command | Result |
| --- | --- | --- |
| 1 | `refresh` (08:20:17Z) | `activated 20261002T082027Z-edd42609` (previous `20260928T140548Z-7c6a05b3`), exit 0, wall 24.45 s. Checks: score-platform `e2373d8 → 4e8b93a`, score-process `66321fe → d0f9291`, both exports `unknown` (no stored validator). Build 13.7 s. Gate: integrity pass; exact_ids 2177/2177; coverage documents 635→635, chunks 5658→5684, entities 4336→4354; semantic present; 2 required sources. |
| 2 | `refresh` again | `up-to-date: no upstream change`, exit 0, wall 2.43 s; git `unchanged`, exports `304 not modified`; no sync |
| 3 | `refresh --json` + `find -newer` marker | `up-to-date`, `synced: false`, timings `{check: 1.45}`, wall 2.00 s; the only file changed under the data copy: `refresh-state.json` (**SC-002 met**) |
| 4 | `doctor` | `[OK] corpus.refresh: Last refresh 2026-10-02T08:21:09Z: up-to-date.`, exit 0 |
| 5 | `search "How do I build the documentation?"` | answered from `20261002T082027Z-edd42609`, hybrid, 8 results |
| 6 | `refresh &` then `refresh` | second run `busy: another refresh is running`, exit 4 |
| 7 | `serve` running (one process, never restarted); `POST /api/v1/search` → `snapshots rollback` → search → `refresh` → search | served `082027Z` → `140548Z` → `20261002T082739Z-2a39f1f7` (refresh rebuilt because the rolled-back snapshot was not built from the current lock); **FR-012/SC-004 real** |

SC-005 met (active moved to current upstream commits; immediate rerun `up-to-date`). SC-001: one
run made the upstream change searchable; trailing bound = timer interval + ~25 s.

Retention on step 1 deleted, in the copy, the unactivated comparison baseline
`20260929T075830Z-9135a190` and two keyword-only snapshots, as documented (runbook "Before you
enable it: retention").

## Incident: real `data/` modified during verification (agent error) — 2026-10-02

The first attempt of step 7 started `serve` with `S=<scratch> && … serve &`; the variable was
assigned only in the backgrounded subshell, so the following `snapshots rollback` and `refresh`
received `--config /refresh.yaml`. A missing `--config` file falls back to defaults
(`data_dir: data`, F001 loader behaviour), so both commands ran on the owner's real `data/`:

- rollback switched active `20260928T140548Z-7c6a05b3` → `20260928T141225Z-648207dd`
  (keyword-only); retention deleted `20260929T075830Z-9135a190` (comparison baseline),
  `20260928T141254Z-c181820c` (keyword-only) and later `20260928T140548Z-7c6a05b3`;
- refresh (mirroring the keyword-only active snapshot) built and activated
  `20261002T082154Z-14627e78` (keyword-only) and rewrote `data/source-lock.json`.

Recovery, with the owner's choice ("Restore old active", "Rebuild it now"):

1. `bundle export --snapshot 20260928T140548Z-7c6a05b3` from the scratch copy (byte-intact,
   `index validate`: integrity ok, semantic enabled) → `bundle import` into `data/` →
   `snapshots activate 20260928T140548Z-7c6a05b3` (retention then removed `141225Z`).
2. `data/source-lock.json` restored from the content-addressed archive
   `data/source-locks/f5c6a38f….json`; SHA-256 `f5c6a38f…` equals the active manifest's
   `lock_sha256`. The accidental `data/refresh-state.json` was removed.
3. Comparison baseline rebuilt: `sources sync --config config/sources-baseline.yaml` into a scratch
   data dir (pinned commits `ba13d82`, `82bca16`), the two revision directories copied into
   `data/sources/`, then `index build --source-lock data/source-lock-baseline.json` (build verifies
   every file hash against that lock) → `20261002T082618Z-1359115c`, validated, semantic, 6084
   chunks (same count as the lost baseline). `eval/comparison-dev.yaml` `left_snapshot` updated.
4. Checked: `snapshots list` (active `140548Z`), `index validate` (integrity ok, semantic
   enabled), `doctor` exit 0, `search` answered from `140548Z`, `snapshots diff` baseline vs active.

Not recovered (no unique content): the two keyword-only builds `141254Z` and `141225Z` of the
same lock as the active snapshot (rebuild with `index build --lexical-only` if wanted). Remaining in
`data/`: `20261002T082154Z-14627e78` (retired, keyword-only, current upstream; the rollback
target), its source revisions and lock archive entry. Activation history timestamps changed.
Recorded as A-058; agent memory updated to use literal absolute `--config` paths.

## Not run

- Enabling the timer on the owner's machine (`scripts/install_refresh_timer.sh` without
  `--no-enable`): the owner decides; only rendering + `systemd-analyze verify` ran.
- Refresh inside containers: out of scope (A-057).
- A real upstream change that the gate holds: not available upstream; covered by mocked tests only.

## Final gates (T021 rerun after documentation) — 2026-10-02

| Command | Result |
| --- | --- |
| `uv run ruff format --check .` | 501 files already formatted |
| `uv run ruff check .` | all checks passed |
| `uv run mypy src` | no issues in 147 source files |
| `uv run pytest` | 1224 passed, 10 skipped (opt-in), 322.42 s; after convergence task T024: 1224 passed, 10 skipped, 318.97 s |
| `uv run python scripts/check_licenses.py` | passed (470 packages) |
| `uv run python scripts/check_traceability.py` | passed |

CI on the pull request is recorded in the PR checks.
