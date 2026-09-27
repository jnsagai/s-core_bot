---

description: "Task list for F001 Foundation and Local Runtime Contract"
---

# Tasks: F001 Foundation and Local Runtime Contract

**Input**: Design documents from `specs/001-foundation/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: MANDATORY for this project (constitution VII). Within each story, write the tests
first and confirm they fail before implementing.

**Organization**: grouped by user story; each task lists the requirement IDs it serves.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on incomplete tasks)
- **[Story]**: US1–US4 from spec.md
- Paths are repository-relative (single project, `src/score_docs_assistant/`)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: project initialisation and tooling

- [x] T001 Create `pyproject.toml` (name `s-core-docs-assistant`, package `score_docs_assistant`, `requires-python = ">=3.12,<3.13"`, hatchling backend, console script `score-assistant = score_docs_assistant.cli.main:app`, runtime and dev dependencies with minimum versions from research.md R2, ruff/mypy(strict)/pytest config incl. `real_runtime` marker) and `.python-version` = `3.12` (FR-017, FR-018)
- [x] T002 Create package skeleton with `__init__.py` files for `src/score_docs_assistant/{domain,config,models,storage,diagnostics,api,cli}/` and `__version__ = "0.1.0"` in `src/score_docs_assistant/__init__.py`; create `tests/{unit,contract,integration,fixtures}/` (plan: Project Structure)
- [x] T003 Run `uv lock` and `uv sync --locked` with Python 3.12 to produce `uv.lock`; record exact resolved versions of runtime deps in `docs/toolchain.md` (FR-017, OPS-005)
- [x] T004 [P] Create `config/local.yaml` mirroring contracts/config.md defaults with `data_dir: ../data` (FR-015, FR-016)
- [x] T005 [P] Create `config/model-profiles.yaml` with profile `local-small` (qwen3:4b-instruct ≈2.5 GB Apache-2.0; nomic-embed-text ≈274 MB license "to confirm"), each with `size_source` and date per research.md R6 (FR-022, FR-023)
- [x] T006 [P] Create `NOTICE` (project name, Apache-2.0, community-project/no-endorsement statement) and placeholder-free `README.md` with community label, scope, prerequisites, and F001 quickstart commands (FR-017, constitution XII)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: configuration, domain types, runtime client, probes, and the test harness needed by every story

**⚠️ CRITICAL**: no user story work can begin until this phase is complete

### Tests for Foundational

- [x] T007 Implement autouse network guard in `tests/conftest.py` that patches `socket.socket.connect`/`connect_ex` to allow only loopback and AF_UNIX, plus fixtures: `tmp_config_dir`, `tmp_data_dir`, `fake_runtime` (httpx.MockTransport serving `/api/version`, `/api/tags`, `/api/pull` from scenario dicts), and skip logic for `real_runtime` unless `SCORE_ASSISTANT_REAL_RUNTIME=1` (SC-004, research R12)
- [x] T008 [P] Add config fixtures in `tests/fixtures/config/` (valid, unknown top-level key, unknown nested key, wrong type, out-of-range port, non-loopback `server.host` variants incl. `0.0.0.0`/`192.168.1.10`/`example.com`, `::1` valid, off-host `runtime.base_url`, `https` base_url, userinfo in base_url, `cloud_fallback: true`, provider `openai`, `telemetry: true`, profile `public`, invalid YAML) (SC-005)
- [x] T009 [P] Write `tests/unit/test_config_schema.py` covering every fixture in T008 with the expected dotted error path and reason (FR-001, FR-002, FR-010, FR-011, FR-015)
- [x] T010 [P] Write `tests/unit/test_config_loader.py`: precedence matrix default<file<env<cli with per-key source tracking, `SCORE_ASSISTANT_CONFIG`, unknown `SCORE_ASSISTANT_*` env → `CONFIG_UNKNOWN_ENV`, relative path resolution against config dir and CWD, missing file → defaults notice (FR-016)
- [x] T011 [P] Write `tests/unit/test_redact.py`: URL userinfo, secret-named keys/env vars, nested dicts, strings quoting input; assert no fixture secret survives (FR-008, SC-006)
- [x] T012 [P] Write `tests/unit/test_ollama_runtime.py` using `fake_runtime`: version parse, tags parse into `InstalledModel` (`:latest` normalisation, `is_remote` from `remote_model`/`remote_host`), connect refused → `RuntimeUnreachable`, timeout → `RuntimeTimeout`, non-JSON/unexpected shape → `RuntimeIncompatible` (FR-005, research R3)
- [x] T013 [P] Write `tests/unit/test_hardware.py`: psutil values mapped; `nvidia-smi` absent, timeout, malformed output, and valid CSV (monkeypatched `subprocess.run`) → `not_detected`/`error`/`detected` (FR-005, FR-018)
- [x] T014 [P] Write `tests/unit/test_corpus_probe.py`: no catalog → `absent`; catalog file present → `incompatible` and file is never opened (patch `open`/`sqlite3.connect` to fail if called) (FR-024)
- [x] T015 [P] Write `tests/unit/test_profiles.py`: load `config/model-profiles.yaml`, unknown profile error, exactly one generation + one embedding role enforced, unknown size → `None` (FR-022, FR-023)

### Implementation for Foundational

- [x] T016 [P] Implement typed errors with stable codes in `src/score_docs_assistant/domain/errors.py` (`ConfigError` carrying `[(path, reason)]`, `RuntimeUnreachable`, `RuntimeTimeout`, `RuntimeIncompatible`, `BindNotLoopback`, `DiskInsufficient`, `ProfileNotFound`) (FR-006)
- [x] T017 [P] Implement `CheckResult`, `CheckStatus`, `DiagnosticReport` with the exit-code invariant in `src/score_docs_assistant/domain/diagnostics.py` (FR-006, FR-007; data-model.md)
- [x] T018 [P] Implement `Capability`, `ReasonCode`, `CapabilityState`, `Readiness` in `src/score_docs_assistant/domain/readiness.py` (FR-009)
- [x] T019 [P] Implement `ModelProfile`, `ProfileModel`, `ModelLock`, `ModelLockEntry`, `InstalledModel`, `RuntimeInfo` in `src/score_docs_assistant/domain/models.py` (FR-022)
- [x] T020 Implement `AppConfig` and section models with `extra="forbid"` and all constraints from contracts/config.md (loopback validation per research R9) in `src/score_docs_assistant/config/schema.py` (FR-001, FR-002, FR-010, FR-011, FR-015) — makes T009 pass
- [x] T021 Implement loader (YAML `safe_load`, env parsing, CLI overrides, source tracking, path resolution, `EffectiveConfig`) in `src/score_docs_assistant/config/loader.py` (FR-016) — makes T010 pass
- [x] T022 [P] Implement redaction in `src/score_docs_assistant/config/redact.py` (FR-008) — makes T011 pass
- [x] T023 Implement `ModelRuntime` protocol plus `GenerationProvider` and `EmbeddingProvider` protocols (declarations only, no implementations) in `src/score_docs_assistant/models/runtime.py` (plan Key Design 1, constitution VI)
- [x] T024 Implement `OllamaRuntime` (httpx client with configured timeouts; `version()`, `list_models()`; `pull()` streaming generator) in `src/score_docs_assistant/models/ollama.py` (FR-005) — makes T012 pass
- [x] T025 [P] Implement profile loading in `src/score_docs_assistant/models/profiles.py` (FR-022) — makes T015 pass
- [x] T026 [P] Implement hardware probe in `src/score_docs_assistant/diagnostics/hardware.py` (research R11) — makes T013 pass
- [x] T027 [P] Implement `CorpusProbe` protocol and F001 `FileCorpusProbe` in `src/score_docs_assistant/storage/corpus_probe.py` (FR-024) — makes T014 pass
- [x] T028 Create Typer app skeleton with global `--config`, `--version`, SIGINT → exit 130, and `ConfigError` → exit 2 mapping in `src/score_docs_assistant/cli/main.py` (FR-003, FR-007)

**Checkpoint**: `uv run pytest tests/unit` passes; foundation ready.

---

## Phase 3: User Story 1 - Diagnose local readiness after installation (Priority: P1) 🎯 MVP

**Goal**: `score-assistant doctor [--json]` reports every check with codes, next actions and exit codes 0/1/2.

**Independent Test**: quickstart.md scenarios B, C, E (doctor parts).

### Tests for User Story 1

- [x] T029 [P] [US1] Write `tests/unit/test_checks.py`: each check in contracts/cli.md order returns the specified status/code for its scenarios (runtime unreachable/timeout/incompatible, model missing/present/remote, lock match/mismatch/not locked, data dir missing/not writable, disk low, GPU not detected, corpus absent/incompatible), and every warning/failure has a `next_action` (FR-005, FR-006, FR-022, FR-024)
- [x] T030 [P] [US1] Write `tests/contract/test_cli_doctor.py` using Typer `CliRunner` + `fake_runtime`: exit 0 on unprepared-but-healthy machine, exit 1 on runtime unreachable, exit 2 on each config-error fixture with no runtime call made; `--json` schema matches contracts/cli.md; text and JSON contain the same check ids/statuses; no key/token fields present (FR-001, FR-007, US1 AS1–AS6)
- [x] T031 [P] [US1] Write `tests/contract/test_doctor_redaction_and_network.py`: userinfo/secret env fixtures never appear in text, JSON, or captured logs; doctor makes no pull request and no non-loopback connection (FR-004, FR-008, SC-006)
- [x] T032 [P] [US1] Write `tests/integration/test_doctor_timing.py`: runtime pointing at a loopback port that accepts but never responds; doctor completes in < 10 s and reports `RUNTIME_TIMEOUT` with next action (SC-002)

### Implementation for User Story 1

- [x] T033 [P] [US1] Implement model-lock read/compare (read-only part) in `src/score_docs_assistant/models/lock.py` (FR-022)
- [x] T034 [US1] Implement checks as pure functions in `src/score_docs_assistant/diagnostics/checks.py`, including `runtime.cloud` info check with `OLLAMA_NO_CLOUD` guidance (research R4) and model-store disk path resolution (research R5) (FR-005, FR-006, FR-022, FR-024)
- [x] T035 [US1] Implement `run_doctor()` ordering, exit-code derivation, text and JSON rendering (all via redaction) in `src/score_docs_assistant/diagnostics/doctor.py` (FR-005–FR-008)
- [x] T036 [US1] Implement `doctor` command wiring in `src/score_docs_assistant/cli/doctor.py` and register it in `cli/main.py` (FR-003, FR-007)

**Checkpoint**: US1 independently testable; MVP complete.

---

## Phase 4: User Story 2 - Loopback-only service with honest readiness (Priority: P2)

**Goal**: `score-assistant serve` exposes `/health/live`, `/health/ready`, `/api/v1/capabilities` behind the Host/Origin guard; refuses non-loopback binds.

**Independent Test**: quickstart.md scenario F and the `serve` part of scenario E.

### Tests for User Story 2

- [ ] T037 [P] [US2] Write `tests/contract/test_guard.py` hostile matrix with `TestClient`: disallowed Host (incl. `attacker.example`, `localhost:9999` when bound to 8080, `127.0.0.1.nip.io`) → 400; disallowed Origin, `Origin: null`, and `Sec-Fetch-Site: cross-site` without Origin → 403 for GET, POST, and OPTIONS; allowed origin gets exact ACAO + `Vary: Origin`, never `*`; no-Origin CLI request allowed; error envelope shape (FR-012, FR-013, FR-014, SC-003)
- [ ] T038 [P] [US2] Write `tests/contract/test_health_api.py`: liveness body exactly `{"status":"alive"}`; readiness 503 with reason codes and no paths/URLs/versions; capabilities 200 shape per contracts/http-api.md; `Cache-Control: no-store`, `X-Request-ID`, no `Server` header; route inventory equals exactly the three routes and `/docs`, `/redoc`, `/openapi.json` return 404 (FR-009, FR-020, FR-021)
- [ ] T039 [P] [US2] Write `tests/unit/test_readiness.py`: capability derivation table from data-model.md; cache TTL honoured; runtime stop→start reflected on next query with TTL 0 (FR-009, SC-007)
- [ ] T040 [P] [US2] Write `tests/contract/test_cli_serve.py`: non-loopback host via file, env, and `--host` → exit 2 `BIND_NOT_LOOPBACK` with public-profile message, uvicorn never started (spy); port in use → exit 1 `BIND_FAILED` (FR-010, FR-011)
- [ ] T041 [P] [US2] Write `tests/integration/test_serve_loopback.py`: start `serve` in a subprocess on a free loopback port with a loopback fake runtime; assert listening socket is bound to 127.0.0.1 only (psutil), endpoints respond, access log lines contain only request_id/method/path/status/duration_ms; stop fake runtime → readiness reasons change (FR-010, FR-020, SC-007, constitution VIII)

### Implementation for User Story 2

- [ ] T042 [US2] Implement `ReadinessService` (cached, bounded probes) in `src/score_docs_assistant/readiness.py` (FR-009) — makes T039 pass
- [ ] T043 [P] [US2] Implement response/error schemas in `src/score_docs_assistant/api/schemas.py` (contracts/http-api.md)
- [ ] T044 [US2] Implement Host/Origin/cross-site guard + CORS as pure ASGI middleware in `src/score_docs_assistant/api/guard.py` (FR-012–FR-014, research R8) — makes T037 pass
- [ ] T045 [P] [US2] Implement request-id and body-free JSON access logging middleware in `src/score_docs_assistant/api/logging.py` (constitution VIII)
- [ ] T046 [US2] Implement routes in `src/score_docs_assistant/api/routes.py` and `create_app()` in `src/score_docs_assistant/api/app.py` (docs/redoc/openapi routes disabled, exception handlers returning the error envelope, no-store headers) (FR-020, FR-021) — makes T038 pass
- [ ] T047 [US2] Implement `serve` command in `src/score_docs_assistant/cli/serve.py` (bind validation before uvicorn, `proxy_headers=False`, `server_header=False`, uvicorn access log off, `BIND_FAILED` mapping) and register in `cli/main.py` (FR-004, FR-010, FR-011) — makes T040, T041 pass

**Checkpoint**: US1 and US2 work independently.

---

## Phase 5: User Story 3 - Acquire and inspect local models explicitly (Priority: P3)

**Goal**: `models inspect` (no download) and `models pull --profile` (network, disk-checked, writes lock).

**Independent Test**: quickstart.md scenarios C (inspect) and D (pull, optional/network).

### Tests for User Story 3

- [ ] T048 [P] [US3] Write `tests/contract/test_cli_models.py` with `fake_runtime`: `inspect` lists roles/presence/digests/lock status and never calls `/api/pull`; `pull` help text first line states network use; unknown profile → exit 2; disk shortfall → exit 1 `DISK_INSUFFICIENT` with no pull request sent; unknown size without `--allow-unknown-size` → refused; successful pull writes lock with digests from `/api/tags`; second run → `already_present`, no pull; remote model in tags → failure (FR-003, FR-004, FR-022, FR-023, US3 AS1–AS5)
- [ ] T049 [P] [US3] Write `tests/unit/test_model_lock.py`: atomic write (temp + replace), unknown fields rejected, interrupted pull (generator raises `KeyboardInterrupt`) leaves previous lock byte-identical, compare outcomes `match|mismatch|missing_installed|not_locked` (FR-022, FR-023)
- [ ] T050 [P] [US3] Write `tests/contract/test_no_pull_outside_models_pull.py`: spy on `OllamaRuntime.pull`; run `doctor`, `models inspect`, `serve` startup + all endpoints; assert zero pull calls (FR-004, US3 AS4)
- [ ] T051 [P] [US3] Write `tests/integration/test_real_runtime.py` marked `real_runtime`: real `/api/version`, `/api/tags`, identity parsing; optional real pull gated by `SCORE_ASSISTANT_REAL_PULL=1` that verifies `/api/pull` stream fields (`status`, `digest`, `total`, `completed`) on Ollama 0.34.0 (research R3 verification item)

### Implementation for User Story 3

- [ ] T052 [US3] Add atomic lock write and compare to `src/score_docs_assistant/models/lock.py` (FR-022) — makes T049 pass
- [ ] T053 [US3] Add `required_free_bytes(profile, margin)` to `src/score_docs_assistant/diagnostics/checks.py`, reusing the model-store path resolver created in T034 (no second resolver), for use by pull (FR-023, research R5)
- [ ] T054 [US3] Implement `models inspect` and `models pull` in `src/score_docs_assistant/cli/models.py` (progress to stderr, JSON result, SIGINT handling, idempotency) and register in `cli/main.py` (FR-003, FR-004, FR-022, FR-023) — makes T048, T050 pass

**Checkpoint**: US1–US3 work independently.

---

## Phase 6: User Story 4 - Contributor verification baseline (Priority: P3)

**Goal**: same checks locally and in CI; locked deps; license gate; notices.

**Independent Test**: quickstart.md scenario A.

### Tests for User Story 4

- [ ] T055 [P] [US4] Write `tests/unit/test_check_licenses.py`: fake `pip-licenses` JSON inventory → allowed pass, unknown/unlisted license fails naming the package, reviewed exception honoured (FR-017)

### Implementation for User Story 4

- [ ] T056 [US4] Implement `scripts/check_licenses.py` (allowlist per research R13, `config/license-exceptions.yaml`, `--write-notices` generating `THIRD_PARTY_NOTICES.md`) and create `config/license-exceptions.yaml` (empty list) (FR-017, OPS-005) — makes T055 pass
- [ ] T057 [US4] Generate `THIRD_PARTY_NOTICES.md` from the synced environment via `uv run python scripts/check_licenses.py --write-notices`; review and resolve any failing package (FR-017, SRC-012)
- [ ] T058 [US4] Create `.github/workflows/ci.yml` (ubuntu-latest x86-64, `astral-sh/setup-uv` pinned by commit SHA, `uv sync --locked`, `ruff format --check`, `ruff check`, `mypy src`, `pytest`, license check; no Ollama, no model download) (FR-018, FR-019)

**Checkpoint**: all stories complete.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T059 Run full local gate `uv run ruff format --check . && uv run ruff check . && uv run mypy src && uv run pytest && uv run python scripts/check_licenses.py`; fix all failures (constitution VII)
- [ ] T060 Execute quickstart.md scenarios A–F on the workstation; record commands, redacted outputs, timings (SC-001, SC-002), environment, and any "not run" items with reasons in `specs/001-foundation/verification.md`
- [ ] T061 [P] Update `docs/TRACEABILITY.md` rows LOC-001, LOC-003, LOC-004, LOC-005, LOC-006, LOC-007, OPS-004, OPS-005, SEC-004, SRC-012 with task IDs, implementation paths, test files, evidence link, and status (constitution IX)
- [ ] T062 [P] Update `docs/BACKLOG.md` F001 state and `docs/ASSUMPTIONS.md` (record the T057 dependency license check outcome under A-005) and `docs/toolchain.md` with final pins
- [ ] T063 Run `/speckit-converge` and complete any appended tasks before declaring F001 done

---

## Dependencies & Execution Order

### Phase Dependencies

- Setup (Phase 1) → Foundational (Phase 2) → US1 (P1) → US2 (P2) / US3 (P3) / US4 (P3) → Polish.
- US2 depends on Foundational plus T033 (lock read/compare, needed for the
  `model_identity_mismatch` reason). `ReadinessService` uses `OllamaRuntime`, `CorpusProbe` and
  `lock.py` directly — it does not import `diagnostics/checks.py`.
- US3 depends on T033 (extended by T052) and on T034's model-store path resolver (used by T053).
- US4 (T055–T058) can run in parallel with US2/US3 after Phase 1 (only needs `uv.lock`).

### Within Each Story

Tests first (must fail) → domain/services → CLI/API wiring → story checkpoint.

### Parallel Opportunities

- Phase 1: T004, T005, T006.
- Phase 2 tests: T008–T015; implementations T016–T019, T022, T025–T027.
- US1 tests T029–T032; US2 tests T037–T041; US3 tests T048–T051; US4 can proceed alongside.

## Parallel Example: User Story 2

```bash
Task: "Write tests/contract/test_guard.py hostile matrix"
Task: "Write tests/contract/test_health_api.py"
Task: "Write tests/unit/test_readiness.py"
Task: "Write tests/contract/test_cli_serve.py"
```

## Implementation Strategy

### MVP First

Phases 1–3 → validate `doctor` with quickstart B/C/E → then US2, US3, US4, Polish.

### Incremental Delivery

Each story checkpoint runs the full local gate (T059 command) before continuing.

## Notes

- Mark a task `[x]` only after its verification ran and passed; record deviations in
  `verification.md`.
- `real_runtime` tests skipped = "not run", never "passed".
