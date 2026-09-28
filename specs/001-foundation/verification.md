# Verification: F001 Foundation and Local Runtime Contract

Real commands and results, recorded as run. "Not run" is recorded explicitly with a reason
(constitution VII) — it is never reported as passed.

## Phase 1 (Setup) + Phase 2 (Foundational) checkpoint — 2026-09-27

Commands actually run, in order, from the repository root:

```
$ uv lock
Resolved 42 packages in 677ms

$ uv sync --locked
... (42 packages installed; versions match research.md R2 exactly — recorded in docs/toolchain.md)

$ uv run ruff format --check .
79 files already formatted

$ uv run ruff check .
All checks passed!

$ uv run mypy src
Success: no issues found in 21 source files

$ uv run pytest tests/unit -q
50 passed in 0.16s
```

`scripts/check_licenses.py` does not exist yet (created in T056, Phase 6) — not run this checkpoint,
per tasks.md.

### Notes

- Local workstation sources `/opt/ros/iron/setup.bash`, which adds ROS's Python 3.10 site-packages
  to `PYTHONPATH`. pytest's setuptools entry-point scan discovered ROS's `pytest11` plugins and
  crashed importing Python-3.10-only modules under our Python 3.12 venv. Fixed by blocking those
  plugin names in `pyproject.toml`'s pytest `addopts` (see `docs/ASSUMPTIONS.md` A-009); harmless
  no-op on machines without ROS installed (including CI).
- Tasks T001–T028 (Phase 1 Setup, Phase 2 Foundational) are checked off in `tasks.md`. Tests and
  implementation for each module were written together in this checkpoint (not strict red-then-
  green per task); the first `uv run pytest` run against the completed pair caught two real bugs
  (a userinfo-detection logic error in `runtime.base_url` validation, and a `redact_text` regex
  that stopped at the first token instead of the whole value) — both are fixed and covered by the
  fixtures that caught them.
- No `real_runtime` tests exist yet at this checkpoint (they arrive with US3, Phase 5).

## Phase 3 (User Story 1 — `doctor`, MVP) checkpoint — 2026-09-27

```
$ uv run ruff format --check . && uv run ruff check .
89 files already formatted; All checks passed!

$ uv run mypy src
Success: no issues found in 26 source files

$ uv run pytest -q
72 passed in 3.48s
```

### Real end-to-end run (quickstart.md scenario C, runtime already running — not stopped/started
since `sudo` is unavailable tonight)

```
$ uv run score-assistant --config config/local.yaml doctor
[OK] config.valid: Configuration is valid.
[INFO] app.version: score-assistant 0.1.0
[INFO] platform: Linux x86_64, 32 CPU threads.
[INFO] memory: 13848829952 bytes available of 33337810944 total.
[INFO] gpu: Detected: NVIDIA GeForce RTX 4070 Laptop GPU.
[OK] disk.data: 18170785792 bytes free at /home/jefferson/s-core_bot/data.
[OK] disk.models: 18170785792 bytes free at /var/snap/ollama/common/models.
[WARNING] data_dir.writable: /home/jefferson/s-core_bot/data does not exist yet.
  → It is created automatically on first use, or create it yourself.
[OK] runtime.reachable: Ollama 0.34.0 reachable at http://127.0.0.1:11434.
[INFO] runtime.cloud: Cannot verify from this client whether Ollama cloud features are disabled on the runtime host.
  → Set OLLAMA_NO_CLOUD=1 or "disable_ollama_cloud": true in ~/.ollama/server.json on the machine running Ollama.
[WARNING] model.generation: qwen3:4b-instruct is not installed.
  → Run `score-assistant models pull --profile local-small`.
[WARNING] model.embedding: nomic-embed-text:latest is not installed.
  → Run `score-assistant models pull --profile local-small`.
[WARNING] model.lock: One or more configured models are not locked.
  → Run `models pull` to (re)lock installed models.
[WARNING] corpus.state: No document corpus is installed yet.
  → Corpus ingestion is not implemented in F001; see F002+.
```

This matches quickstart.md scenario C exactly (real Ollama 0.34.0, both models correctly reported
missing with the exact `models pull --profile local-small` command, no download occurred).

Config-error path also verified for real (quickstart scenario E, first command only):

```
$ uv run score-assistant --config tests/fixtures/config/unknown_nested_key.yaml doctor
server.hots: Extra inputs are not permitted
(exit code 2)
```

### Notes

- Scenario B (stop Ollama, `sudo snap stop ollama`) was **not run**: `sudo` is unavailable tonight
  per the overnight policy. `RUNTIME_UNREACHABLE`/`RUNTIME_TIMEOUT` paths are instead covered by
  `tests/unit/test_checks.py`, `tests/contract/test_cli_doctor.py`, and the real-socket integration
  test `tests/integration/test_doctor_timing.py` (a loopback port that accepts but never responds).
- Fixed two bugs surfaced by the first `--json` contract-test run: `probe_hardware` crashed with
  `FileNotFoundError` when `data_dir` did not exist yet (now falls back to the nearest existing
  ancestor, matching `check_disk`'s existing behavior); and `SECRET_KEY_PATTERN`/`_KV_RE` matched
  "token" as a substring of the legitimate config key `runtime.context_tokens`, silently masking it
  in `doctor --json` output — fixed with lookaround word boundaries so the keyword must not be
  directly adjoined by another letter (`tests/unit/test_redact.py::test_redact_does_not_mask_words_merely_containing_token`
  guards this).

## Phase 4 (User Story 2 — `serve`) checkpoint — 2026-09-27

```
$ uv run ruff format --check . && uv run ruff check .
102 files already formatted; All checks passed!

$ uv run mypy src
Success: no issues found in 34 source files

$ uv run pytest -q
102 passed (101 + 1 real subprocess integration test, `test_serve_loopback.py`, run separately
to isolate its ~1s subprocess startup)
```

### Real end-to-end run (quickstart.md scenario F, against the workstation's real Ollama 0.34.0)

```
$ uv run score-assistant --config config/local.yaml serve &
$ curl -s -i http://127.0.0.1:8080/health/live
HTTP/1.1 200 OK ... {"status":"alive"}
$ curl -s -i http://127.0.0.1:8080/health/ready
HTTP/1.1 503 ... {"ready":false,"capabilities":{"search":{"available":false,"reasons":["corpus_missing"]},
  "chat":{"available":false,"reasons":["corpus_missing","generation_model_missing"]},
  "compare":{"available":false,"reasons":["not_implemented"]}}}
$ curl -s http://127.0.0.1:8080/api/v1/capabilities
{"schema_version":1,"app":{"name":"S-CORE Docs Assistant — Community Project","version":"0.1.0"},
  "profile":"local","runs_locally":true, ... "models":{"generation":"qwen3:4b-instruct","embedding":"nomic-embed-text"}, ...}
$ curl -s -i -H 'Origin: https://evil.example' http://127.0.0.1:8080/api/v1/capabilities
HTTP/1.1 403 Forbidden ... {"error":{"code":"ORIGIN_NOT_ALLOWED", ...}}
$ curl -s -i -H 'Host: attacker.example' http://127.0.0.1:8080/health/live
HTTP/1.1 400 Bad Request ... {"error":{"code":"HOST_NOT_ALLOWED", ...}}
$ ss -ltnp | grep 8080
LISTEN 0 2048  127.0.0.1:8080  0.0.0.0:*  users:(("score-assistant",pid=654419,fd=6))
$ kill 654419   # confirmed stopped (exit 143) before moving on
```

Matches quickstart.md scenario F exactly: listening on `127.0.0.1` only (never `0.0.0.0`), correct
status codes and reason codes, guard rejects both the hostile Host and the disallowed Origin.

### Notes

- Fixed one circular-import bug the first `pytest` collection run caught: `doctor.py` and
  `serve.py` both need a `profiles_path_for` helper, but `doctor.py` originally defined it while
  also being imported by `serve.py`, and both are imported by `main.py` to register their
  commands — a three-way cycle. Moved the helper to a dependency-free `cli/config_paths.py`.
- The integration test (`test_serve_loopback.py`) starts a real `score-assistant serve`
  subprocess against a real (fake) loopback Ollama HTTP server, confirms the listening socket is
  127.0.0.1-only via `psutil`, and confirms readiness reasons change from not including
  `runtime_unreachable` to including it after the fake runtime is shut down — passed on first real
  run (1.08s).

## Phase 5 (User Story 3 — `models inspect`/`models pull`) checkpoint — 2026-09-27

```
$ uv run ruff format --check . && uv run ruff check .
107 files already formatted; All checks passed!

$ uv run mypy src
Success: no issues found in 35 source files

$ uv run pytest -q
118 passed, 2 skipped in 4.95s
```

The 2 skipped are `tests/integration/test_real_runtime.py` (marked `real_runtime`) — reported as
**skipped, not passed**, since `SCORE_ASSISTANT_REAL_RUNTIME=1` was not set this run.

### Real end-to-end run (quickstart.md scenario C, `models inspect` half)

```
$ uv run score-assistant --config config/local.yaml models inspect
generation: qwen3:4b-instruct (missing, lock=not_locked)
embedding: nomic-embed-text:latest (missing, lock=not_locked)
```

Matches quickstart.md scenario C exactly (real Ollama 0.34.0, both models correctly reported
missing). `models pull` was **not run for real**: it is denied by `.claude/settings.json`
(`*models*pull*` is on the deny list) and the overnight policy separately forbids any real model
download tonight (disk ~95% full). `models pull` is instead verified entirely against the fake
Ollama transport in `tests/contract/test_cli_models.py` (writes the lock with digests from
`/api/tags`, idempotent second run, disk-shortfall/unknown-size/remote-model refusals) and the
atomic-write/interrupted-write guarantees in `tests/unit/test_model_lock.py`.

### Notes

- Fixed two test bugs the first run caught (both in the test file, not the implementation):
  `--help` output always starts with a Click "Usage: ..." line before the command's own
  description, so the network-use sentence is the *second* non-blank line, not the first; and
  Typer's `CliRunner` mixes stdout and stderr by default, so a test parsing `result.output` as JSON
  must take the *last* line (the final JSON result), since `models pull`'s stderr progress lines
  are interleaved into the same captured stream.

## Phase 6 (User Story 4 — license gate, CI) checkpoint — 2026-09-28

```
$ uv run ruff format --check . && uv run ruff check .
111 files already formatted; All checks passed!

$ uv run mypy src
Success: no issues found in 35 source files

$ uv run pytest -q
127 passed, 2 skipped in 3.09s

$ uv run python scripts/check_licenses.py --write-notices
Wrote /home/jefferson/s-core_bot/THIRD_PARTY_NOTICES.md (39 packages).
License check passed: 39 packages, all allowed or reviewed.
```

The 2 skipped are `real_runtime` (opt-in, not run — reported skipped, not passed).

### Real environment finding: `pip-licenses` sees ROS packages without a PYTHONPATH fix

The same ROS `PYTHONPATH` contamination noted in the Phase 1/2 checkpoint (A-009) affects
`pip-licenses` too: run naively, it reported on packages from `/opt/ros/iron/lib/python3.10/
site-packages` (dozens of `UNKNOWN`-licensed ROS packages) instead of only this project's synced
venv. Confirmed by comparing `uv run pip-licenses --format=json` (picks up ROS packages) against
the same command with `PYTHONPATH=` cleared (exactly the 39 real locked dependencies). Fixed by
having `run_pip_licenses()` in `scripts/check_licenses.py` strip `PYTHONPATH` from the subprocess
environment before invoking `pip-licenses`. Real run against the actual synced environment: **all
39 locked dependencies pass** (MIT, BSD-2/3-Clause, Apache-2.0, MPL-2.0, ISC, PSF-2.0) — no
exceptions were needed in `config/license-exceptions.yaml`. This resolves `docs/ASSUMPTIONS.md`
A-005's open dependency-license review.

`.github/workflows/ci.yml` created with `actions/checkout` and `astral-sh/setup-uv` pinned by
commit SHA (resolved from each action's latest release tag via the GitHub API on 2026-09-28:
checkout v7.0.1 → `3d3c42e5aac5ba805825da76410c181273ba90b1`; setup-uv v10.2.0 →
`c18668ad3cf93ea998bef934396af7bb5c839dc7`). Not run in a real GitHub Actions environment tonight
(no CI trigger available from this workstation); YAML syntax validated locally with
`yaml.safe_load`. First real CI run should be checked after this branch is pushed.

## Phase 7 (Polish) — quickstart.md scenarios A–F — 2026-09-28

Full local gate re-confirmed at the point all 63 tasks are checked off:

```
$ uv run ruff format --check . && uv run ruff check .
111 files already formatted; All checks passed!

$ uv run mypy src
Success: no issues found in 35 source files

$ uv run pytest -q
127 passed, 2 skipped in 3.09s

$ uv run python scripts/check_licenses.py
License check passed: 39 packages, all allowed or reviewed.
```

### Scenario A — install and deterministic checks (SC-001, SC-004)

Measured for real from a **fresh clone in a new directory** (`git clone -b 001-foundation
/home/jefferson/s-core_bot`, not the working tree), to give SC-001 an honest clone-to-diagnostic
measurement rather than reusing an already-installed environment:

```
$ time (git clone -q -b 001-foundation <repo> repo && cd repo && uv sync --locked && \
        uv run score-assistant --config config/local.yaml doctor)
real  0m1.382s
```

**1.4 seconds**, comfortably under the 10-minute SC-001 target — but this benefits from `uv`'s
local package cache already being warm from earlier checkpoints tonight; a genuinely first-ever
run on a machine with no cache would additionally pay for downloading ~43 packages from PyPI
(a few seconds to low minutes depending on connection, not model-sized). No model download is
included either way, per SC-001's own exclusion. `doctor` exited 0 (warnings only: empty corpus,
absent models, not-yet-created data dir — all correct for a fresh install) matching quickstart
scenario C's warning set.

Deterministic checks (`ruff format --check`, `ruff check`, `mypy`, `pytest`, `check_licenses.py`)
were run with external network blocked implicitly: none of the fixtures, the socket guard
(`tests/conftest.py`), or the tools above make any non-loopback connection during the run (the
`real_runtime` tests that would need one are marked and skipped). SC-004 holds.

### Scenario B — diagnose with runtime stopped

**Not run** tonight: requires `sudo snap stop ollama`, and `sudo` is denied by
`.claude/settings.json` for the unattended/agent-run policy in effect this session. Recorded
already at the Phase 3 checkpoint above. The `RUNTIME_UNREACHABLE`/`RUNTIME_TIMEOUT` code paths
this scenario would exercise are covered instead by `tests/unit/test_checks.py`,
`tests/contract/test_cli_doctor.py`, and the real-socket `tests/integration/test_doctor_timing.py`
(a loopback port that accepts but never responds, confirming the < 10 s bound, SC-002).

### Scenario C — diagnose with runtime running, models absent

Already run for real at the Phase 3 checkpoint (`doctor`) and Phase 5 checkpoint (`models
inspect`) above, against the workstation's live Ollama 0.34.0. Not repeated here; both halves
match the scenario exactly.

### Scenario D — acquire models

**Not run**: `models pull` is denied by `.claude/settings.json` (`*models pull*`,
`score-assistant models pull:*`) and would download ~2.8 GB on a disk that was ~95% full when
recorded (`docs/toolchain.md`). Verified instead against the fake Ollama transport in
`tests/contract/test_cli_models.py` (writes the lock, idempotent re-run, disk-shortfall and
unknown-size refusals, remote-model rejection) and `tests/unit/test_model_lock.py` (atomic write,
interrupted-write safety). A human should run this scenario for real once disk space allows,
before F001 is treated as fully field-verified.

### Scenario E — configuration errors (SC-005)

Both commands run for real just now:

```
$ printf 'schema_version: 1\nserver:\n  hots: 127.0.0.1\n' > /tmp/bad.yaml
$ uv run score-assistant --config /tmp/bad.yaml doctor
server.hots: Extra inputs are not permitted
(exit code 2)

$ SCORE_ASSISTANT_SERVER__HOST=0.0.0.0 uv run score-assistant --config config/local.yaml serve
server.host: Remote exposure requires the public profile, which is not available in this release.
(exit code 2)
```

Both match quickstart.md exactly: unknown key rejected with its dotted path, non-loopback bind
refused with the public-profile message, both exit 2.

### Scenario F — service contract and guard (SC-003)

Already run for real at the Phase 4 checkpoint above, against the workstation's live Ollama.
Not repeated here.

## Blockers

(none)
