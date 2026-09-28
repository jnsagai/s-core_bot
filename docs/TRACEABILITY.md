# Requirements traceability

One row per normative requirement from `docs/PROJECT_SPEC.md` §4. Many-to-many mapping is
allowed; no requirement may be dropped. Status: open → implemented → verified (with evidence).
"Feature FR" is the requirement ID inside the owning feature's `spec.md`.

| Req | Owning feature(s) | Feature FR | Tasks | Implementation | Tests / evaluation | Evidence | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| LOC-001 | F001, F009 | F001 FR-001, FR-002 | T009, T020 | `config/schema.py` (RuntimeConfig: provider="ollama" only, cloud_fallback must be false) | `tests/unit/test_config_schema.py` | verification.md Phase 1/2 checkpoint | verified |
| LOC-002 | F005, F009 | — | — | — | — | — | open |
| LOC-003 | F001 (install, acquire-models, serve), F002 (sync-sources), F003 (build-index), F009 | F001 FR-003, FR-004, FR-023 | T028, T036, T047, T053, T054 | `cli/main.py`, `cli/doctor.py`, `cli/serve.py`, `cli/models.py` | `tests/contract/test_cli_doctor.py`, `tests/contract/test_cli_serve.py`, `tests/contract/test_cli_models.py`, `tests/contract/test_no_pull_outside_models_pull.py` | verification.md Phase 3/4/5 checkpoints | verified (F001 scope: install/doctor/serve/models only; sync-sources and build-index are F002/F003) |
| LOC-004 | F001, F009 | F001 FR-010, FR-011, FR-020 | T020, T040, T041, T046, T047 | `config/schema.py` (loopback validation), `cli/serve.py`, `api/app.py`, `api/routes.py` | `tests/contract/test_cli_serve.py`, `tests/integration/test_serve_loopback.py`, `tests/contract/test_health_api.py` | verification.md Phase 4 checkpoint; Phase 7 scenario E (real non-loopback refusal) | verified |
| LOC-005 | F001, F009 | F001 FR-005–FR-008, FR-022, FR-024 | T029–T036 | `diagnostics/checks.py`, `diagnostics/doctor.py`, `diagnostics/hardware.py`, `config/redact.py`, `storage/corpus_probe.py`, `models/lock.py` | `tests/unit/test_checks.py`, `tests/unit/test_hardware.py`, `tests/unit/test_redact.py`, `tests/unit/test_corpus_probe.py`, `tests/contract/test_cli_doctor.py`, `tests/contract/test_doctor_redaction_and_network.py` | verification.md Phase 3 checkpoint (real `doctor` run against live Ollama) | verified |
| LOC-006 | F004 (F001 reports readiness) | F001 FR-009 | T018, T039, T042 | `domain/readiness.py`, `readiness.py` (ReadinessService) | `tests/unit/test_readiness.py`, `tests/contract/test_health_api.py` | verification.md Phase 4 checkpoint | verified for F001 scope (readiness modelling and degraded-state reporting); `search`/`chat` becoming actually available is F004/F005 |
| LOC-007 | F001, F009 | F001 FR-018 | T013, T026, T058 | `diagnostics/hardware.py` (GPU detection optional, never required) | `tests/unit/test_hardware.py`; `.github/workflows/ci.yml` runs on `ubuntu-latest` with no GPU | verification.md — all checkpoints run on Linux x86-64, CPU-only doctor/serve/test runs | verified locally; first real GitHub Actions run still pending (not yet pushed) |
| SRC-001 | F002 | — | — | — | — | — | open |
| SRC-002 | F002 | — | — | — | — | — | open |
| SRC-003 | F002, F007 | — | — | — | — | — | open |
| SRC-004 | F002 | — | — | — | — | — | open |
| SRC-005 | F002 | — | — | — | — | — | open |
| SRC-006 | F002 | — | — | — | — | — | open |
| SRC-007 | F002 | — | — | — | — | — | open |
| SRC-008 | F002 | — | — | — | — | — | open |
| SRC-009 | F003 | — | — | — | — | — | open |
| SRC-010 | F002, F003 | — | — | — | — | — | open |
| SRC-011 | F002, F003 | — | — | — | — | — | open |
| SRC-012 | F002 (F001 notices framework) | F001 FR-017 | T006, T056, T057 | `NOTICE`, `THIRD_PARTY_NOTICES.md`, `scripts/check_licenses.py` | `tests/unit/test_check_licenses.py` | verification.md Phase 6 checkpoint | verified for F001's dependency-notices framework; per-ingested-source attribution is F002 scope |
| RET-001 | F004 | — | — | — | — | — | open |
| RET-002 | F004 | — | — | — | — | — | open |
| RET-003 | F004 | — | — | — | — | — | open |
| RET-004 | F004 | — | — | — | — | — | open |
| RET-005 | F005 | — | — | — | — | — | open |
| RET-006 | F007 | — | — | — | — | — | open |
| RET-007 | F003 | — | — | — | — | — | open |
| RET-008 | F004 | — | — | — | — | — | open |
| ANS-001 – ANS-012 | F005 (ANS-005, ANS-007 also F007) | — | — | — | — | — | open |
| UX-001 – UX-005 | F006 | — | — | — | — | — | open |
| SEC-001 | F005, F009 | — | — | — | — | — | open |
| SEC-002 | F006, F009 | — | — | — | — | — | open |
| SEC-003 | F006, F009 | — | — | — | — | — | open |
| SEC-004 | F001, F009 | F001 FR-012–FR-014 | T044 | `api/guard.py` | `tests/contract/test_guard.py` | verification.md Phase 4 checkpoint (real hostile-Host/Origin curl requests rejected) | verified |
| SEC-005 | F002, F009 | — | — | — | — | — | open |
| OPS-001 | F006, F009 | — | — | — | — | — | open |
| OPS-002 | F003, F009 | — | — | — | — | — | open |
| OPS-003 | F003, F009 | — | — | — | — | — | open |
| OPS-004 | F001, F009 | F001 FR-015, FR-016 | T020, T021, T022 | `config/schema.py`, `config/loader.py`, `config/redact.py` | `tests/unit/test_config_schema.py`, `tests/unit/test_config_loader.py`, `tests/unit/test_redact.py` | verification.md Phase 1/2 checkpoint | verified |
| OPS-005 | F001, F009 | F001 FR-017, FR-019 | T001, T003, T055–T058 | `pyproject.toml`, `uv.lock`, `NOTICE`, `THIRD_PARTY_NOTICES.md`, `scripts/check_licenses.py`, `.github/workflows/ci.yml` | `tests/unit/test_check_licenses.py` | verification.md Phase 6 checkpoint | verified locally; first real GitHub Actions run still pending (not yet pushed) |
| OPS-006 | F005, F009 | — | — | — | — | — | open |
| PUB-001 – PUB-008 | F010 (deferred) | — | — | — | — | — | open (deferred) |

Grouped rows (ANS, UX, PUB) are expanded to one row per ID when their owning feature is specified.
