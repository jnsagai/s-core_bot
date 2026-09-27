# Implementation Plan: F001 Foundation and Local Runtime Contract

**Branch**: `001-foundation` | **Date**: 2026-09-27 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-foundation/spec.md`

## Summary

Create the Python 3.12 project skeleton with validated configuration, an Ollama runtime provider
behind an interface, hardware and corpus probes, a `score-assistant` CLI (`doctor`,
`models inspect`, `models pull`, `serve`), and a loopback-only FastAPI service exposing liveness,
readiness and capabilities behind a Host/Origin guard. Add locks, license/notice framework, CI,
and a network-isolated deterministic test suite. No ingestion, search, chat, or UI.

## Technical Context

**Language/Version**: Python 3.12 (uv-managed 3.12.14)

**Primary Dependencies**: FastAPI 0.141, uvicorn 0.54, Pydantic 2.13, Typer 0.27, httpx 0.28,
PyYAML 6.0 (`safe_load` only), psutil 7.2 — see [research.md](research.md) R2

**Storage**: Files only: YAML config (`config/`), `<data_dir>/model-lock.json`. No database in F001
(corpus catalog is only probed for existence, R-clarification 5).

**Testing**: pytest with an autouse loopback-only socket guard; `httpx.MockTransport` fake runtime;
FastAPI `TestClient`; optional `real_runtime` marker for live Ollama checks.

**Target Platform**: Linux x86-64, CPU-only supported; NVIDIA GPU detected when present.

**Project Type**: single Python project (CLI + local web service); frontend arrives in F006.

**Performance Goals**: `doctor` < 10 s with runtime absent (SC-002); readiness reflects runtime
changes within one query after a ≤ 2 s cache (SC-007).

**Constraints**: no outbound network except the loopback runtime and the explicit `models pull`;
bind loopback only; unknown config keys are errors; no secrets in output.

**Scale/Scope**: ~15 source modules, ~4 CLI commands, 3 HTTP endpoints.

## Constitution Check

*GATE: evaluated before Phase 0 and re-checked after Phase 1 design.*

| Principle | Status | How this plan complies |
| --- | --- | --- |
| I. Local operation | PASS | Only `ollama` provider accepted; `cloud_fallback` must be `false`; runtime URL must be loopback; remote-proxied models fail `doctor`; only `models pull` uses network. |
| II. Evidence precedes assertions | N/A (PASS) | No answers in F001; FR-021 forbids placeholder chat. |
| III. Snapshots explicit | PASS | Corpus probe never opens an unknown/incompatible catalog; model identities recorded by digest in the model lock. |
| IV. Untrusted documentation | N/A (PASS) | No ingestion. YAML parsed with `safe_load`; no executable deserialization. |
| V. Read-only assistance | PASS | No model tools; service has no state-changing endpoints in F001. |
| VI. Modular monolith | PASS | `GenerationProvider`/`EmbeddingProvider` share an Ollama runtime client behind a `ModelRuntime` protocol; domain types free of FastAPI/httpx. No new infrastructure. |
| VII. Honest verification | PASS | Tests mandatory; `real_runtime` tests reported "not run" when skipped; `verification.md` records actual results. |
| VIII. Privacy by default | PASS | No telemetry; logs contain request id, method, path, status, duration only; redaction utility applied to all diagnostic output. |
| IX. Spec-first increments | PASS | FR↔master IDs mapped; traceability updated in Polish phase. |
| X. Public profile separate | PASS | `profile` accepts only `local`; non-loopback bind refused (exit 2); Host/Origin guard always on. |
| XI. Licenses follow artifacts | PASS | License allowlist check, NOTICE, THIRD_PARTY_NOTICES; model licenses recorded in profile file. |
| XII. No implied authority | PASS | README and capabilities carry the community-project label; no approval features. |

Post-design re-check (after Phase 1): **PASS** — contracts add no network paths, no persistence
of user data, and no non-loopback exposure. No Complexity Tracking entries required.

## Project Structure

### Documentation (this feature)

```text
specs/001-foundation/
├── plan.md              # this file
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/
│   ├── cli.md           # CLI commands, flags, exit codes, JSON output
│   ├── http-api.md      # /health/live, /health/ready, /api/v1/capabilities, error envelope
│   └── config.md        # configuration schema, env overrides, precedence
├── checklists/
│   ├── requirements.md  # spec quality (agent review)
│   └── security.md      # security requirements quality (agent review)
├── tasks.md             # /speckit-tasks
└── verification.md      # written during implementation with real results
```

### Source Code (repository root)

```text
pyproject.toml                 # project metadata, deps, ruff/mypy/pytest config, console script
uv.lock
.python-version                # 3.12
NOTICE
THIRD_PARTY_NOTICES.md
README.md                      # community label, quickstart, limits
config/
├── local.yaml                 # default local profile (matches built-in defaults)
├── model-profiles.yaml        # local-small: tags, roles, approx sizes, source/date, licenses
└── license-exceptions.yaml    # reviewed license exceptions (initially empty)
scripts/
└── check_licenses.py
src/score_docs_assistant/
├── __init__.py                # __version__
├── domain/
│   ├── errors.py              # typed exceptions with stable codes
│   ├── diagnostics.py         # CheckResult, DiagnosticReport, CheckStatus
│   ├── readiness.py           # Capability, CapabilityState, Readiness
│   └── models.py              # ModelProfile, ModelIdentity, ModelLock
├── config/
│   ├── schema.py              # AppConfig and sections (extra="forbid")
│   ├── loader.py              # defaults < file < env < CLI, source tracking
│   └── redact.py              # secret redaction
├── models/
│   ├── runtime.py             # ModelRuntime protocol, RuntimeInfo, InstalledModel
│   ├── ollama.py              # OllamaRuntime (httpx), pull streaming
│   ├── profiles.py            # load model-profiles.yaml
│   └── lock.py                # read/write/compare model-lock.json (atomic write)
├── storage/
│   └── corpus_probe.py        # CorpusProbe protocol + F001 implementation (absent/incompatible)
├── diagnostics/
│   ├── hardware.py            # RAM, disk, GPU (nvidia-smi), platform
│   ├── checks.py              # individual checks → CheckResult
│   └── doctor.py              # orchestrates checks, computes exit code, renders text/JSON
├── readiness.py               # ReadinessService (cached, bounded probes)
├── api/
│   ├── app.py                 # create_app(config, services)
│   ├── guard.py               # Host/Origin/cross-site ASGI middleware + CORS
│   ├── routes.py              # health + capabilities
│   ├── schemas.py             # response models, error envelope
│   └── logging.py             # request-id middleware, body-free access log
└── cli/
    ├── main.py                # Typer app, global --config/--json, exit codes
    ├── doctor.py
    ├── models.py              # inspect, pull
    └── serve.py               # validated bind, uvicorn.run
tests/
├── conftest.py                # socket guard, fake runtime fixtures, tmp config/data dirs
├── fixtures/                  # config fixtures (valid, unknown key, bad types, secrets, ...)
├── unit/                      # config, redact, lock, profiles, hardware, corpus probe, checks
├── contract/                  # CLI exit codes/JSON shape, HTTP responses/error envelope
└── integration/               # serve on loopback with fake runtime; real_runtime (opt-in)
.github/workflows/ci.yml
```

**Structure Decision**: single project under `src/score_docs_assistant/` following master spec
§14. `config/` and `diagnostics/` packages and `readiness.py` are F001 additions not listed in §14;
they hold cross-cutting responsibilities (configuration, doctor) that §14 assigns implicitly to
`cli/` and `api/`. `frontend/` is not created until F006.

## Key Design Decisions

1. **Single runtime client, two provider roles**: `OllamaRuntime` implements `ModelRuntime`
   (version, list models, pull). Generation/embedding provider interfaces are declared in
   `models/runtime.py` as protocols only, without implementations (F003/F005 implement them) — this
   satisfies the §5.1 interface requirement without fake behavior.
2. **Checks are pure functions** of (config, runtime client, probes) → `CheckResult`, so each is
   unit-testable with fakes; `doctor` only orders them and derives the exit code (0/1/2).
3. **Config errors short-circuit**: loader raises `ConfigError` with a list of `(path, reason)`;
   CLI maps to exit 2 before touching the runtime (US1 AS3).
4. **Serve startup**: load + validate config → verify bind is loopback → build app → `uvicorn.run`
   with `host` from config, `proxy_headers=False`, `server_header=False`,
   `forwarded_allow_ips=None`. Port in use → exit 1 with `BIND_FAILED`.
5. **Readiness**: `ReadinessService` computes capability states from runtime reachability, model
   presence, and corpus probe; `search` requires a compatible corpus (never true in F001), `chat`
   requires search + generation model. Cached ≤ 2 s (configurable, 0 in tests).
6. **Logging**: stdlib `logging` with a JSON formatter to stderr; access log fields: request_id,
   method, path (no query string), status, duration_ms. Uvicorn access log disabled in favour of it.
7. **Atomic lock write**: write to temp file in same dir, `fsync`, `os.replace`.

## Verification Strategy

| Requirement | Verification (layer) |
| --- | --- |
| FR-001, FR-002 | unit: schema rejects provider≠ollama, cloud_fallback=true, secret-like keys absent; contract: `doctor --json` has no key/token fields |
| FR-003, FR-004 | contract: CLI command list exact; socket guard + pull-spy asserting `serve`/`doctor`/`inspect` never call pull; help text of `models pull` mentions network |
| FR-005 – FR-008, FR-022, FR-024 | unit per check with fake runtime/probes; contract: text vs JSON parity, exit codes 0/1/2; redaction fixtures (SC-006) |
| FR-009, FR-020, FR-021 | contract: readiness 503 + reason codes, liveness minimal, capabilities shape; route inventory test (no chat routes) |
| FR-010, FR-011 | unit: bind validation matrix (127.0.0.1, ::1, localhost ok; 0.0.0.0, LAN IP, hostname rejected); integration: `serve` actually listens on 127.0.0.1 |
| FR-012 – FR-014 | contract: hostile fixture matrix (SC-003) |
| FR-015, FR-016 | unit: precedence matrix, unknown file key, unknown env var, relative path resolution (SC-005) |
| FR-017, FR-019 | CI run; `scripts/check_licenses.py` unit test with fake inventory |
| FR-018 | CI on ubuntu x86-64 without GPU; hardware probe tests with nvidia-smi absent |
| FR-023 | unit: disk shortfall aborts before request; unknown size requires override; interruption leaves lock untouched |
| SC-001 | manual timed run recorded in verification.md (H) |
| SC-002 | test with runtime connect timeout; asserts wall time < 10 s |
| SC-004 | socket guard active for the entire suite; CI job runs with it |
| SC-007 | integration: stop fake runtime → readiness changes on next query |
| Real Ollama | `real_runtime` tests: version, tags, identity, optional real `models pull` (network, manual) — reported "not run" if skipped |

## Complexity Tracking

No constitution violations; section intentionally empty.
