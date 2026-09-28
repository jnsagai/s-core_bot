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
| SRC-001 | F002 | F002 FR-001 | F002 T006, T011, T018 | `config/sources.yaml`, `sources/registry.py` | `tests/unit/test_registry.py` | specs/002-source-ingestion/verification.md (real sync + inspect of both S-CORE sources) | verified |
| SRC-002 | F002 | F002 FR-003, FR-008 | F002 T023, T025, T026, T028, T030, T031 | `sources/git_client.py`, `sources/sync.py`, `sources/lock.py` | `tests/unit/test_git_client.py`, `tests/integration/test_sync_git.py`, `tests/integration/test_sync_failure.py` | specs/002-source-ingestion/verification.md (real sync + inspect of both S-CORE sources) | verified |
| SRC-003 | F002, F007 | F002 FR-004 | F002 T025, T031 | `sources/sync.py` (`release_mapping: null`, per-source revisions) | `tests/integration/test_sync_git.py` | specs/002-source-ingestion/verification.md (real sync + inspect of both S-CORE sources) | verified |
| SRC-004 | F002 | F002 FR-016 | F002 T038, T045, T046, T048 | `ingestion/rst/parser.py`, `ingestion/markdown.py`, `ingestion/normalize.py` | `tests/unit/test_line_spans.py`, `tests/unit/test_markdown_parser.py`, `tests/unit/test_rst_include.py` | specs/002-source-ingestion/verification.md (real sync + inspect of both S-CORE sources) | verified |
| SRC-005 | F002 | F002 FR-010, FR-011, FR-012 | F002 T034, T037, T039, T043, T045, T046 | `ingestion/rst/*`, `ingestion/markdown.py` (incl. MyST), `ingestion/entities.py`, `config/parser-profiles/s-core.yaml` | `tests/unit/test_rst_parser.py`, `tests/unit/test_markdown_parser.py`, `tests/integration/test_upstream_golden.py` | specs/002-source-ingestion/verification.md (real sync + inspect of both S-CORE sources) | verified |
| SRC-006 | F002 | F002 FR-005, FR-013, FR-014 | F002 T023, T025, T035, T043, T045 | `sources/git_client.py` (no checkout, hardened env), `ingestion/rst/directives.py`, `ingestion/rst/roles.py`, `ingestion/rst/settings.py` | `tests/unit/test_rst_safety.py`, `tests/integration/test_sync_git.py` (mutation-checked) | specs/002-source-ingestion/verification.md (real sync + inspect of both S-CORE sources) | verified |
| SRC-007 | F002 | F002 FR-015 | F002 T036, T043 | `ingestion/rst/directives.py` (`SafeInclude`) | `tests/unit/test_rst_include.py` | specs/002-source-ingestion/verification.md (real sync + inspect of both S-CORE sources) | verified |
| SRC-008 | F002 | F002 FR-019, FR-020 | F002 T051–T054 | `ingestion/needs_export.py`, `sources/http_fetch.py` | `tests/unit/test_needs_export.py`, `tests/integration/test_sync_inspect_export.py` | specs/002-source-ingestion/verification.md (real sync + inspect of both S-CORE sources) | verified |
| SRC-009 | F003 | — | — | — | — | — | open |
| SRC-010 | F002, F003 | F002 FR-017 | F002 T013, T020, T040 | `ingestion/canonical.py` | `tests/unit/test_canonical.py`, `tests/integration/test_inspect.py` | specs/002-source-ingestion/verification.md (real sync + inspect of both S-CORE sources) | verified (F002; F003 part pending) |
| SRC-011 | F002, F003 | F002 FR-012, FR-023 | F002 T034, T040, T049 | `ingestion/report.py` | `tests/integration/test_inspect.py`, `tests/contract/test_cli_inspect.py` | specs/002-source-ingestion/verification.md (real sync + inspect of both S-CORE sources) | verified (F002; F003 part pending) |
| SRC-012 | F002 (F001 notices framework) | F001 FR-017; F002 FR-021, FR-022 | T006, T056, T057; F002 T014, T021, T025 | `NOTICE`, `THIRD_PARTY_NOTICES.md`, `scripts/check_licenses.py`, `ingestion/licenses.py`, `sources/sync.py` (LICENSE/NOTICE acquisition) | `tests/unit/test_check_licenses.py`, `tests/unit/test_decode_and_license.py`, `tests/integration/test_inspect.py` | specs/002-source-ingestion/verification.md (real sync + inspect of both S-CORE sources) (3 CC-BY-SA-4.0 files flagged) | verified |
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
| SEC-005 | F002, F009 | F002 FR-002, FR-006, FR-007 | F002 T010, T011, T017, T023–T026, T029, T031 | `sources/registry.py` (`url_problem`), `sources/paths.py`, `sources/http_fetch.py`, `sources/sync.py` | `tests/unit/test_safe_paths.py`, `tests/unit/test_registry.py`, `tests/unit/test_http_fetch.py`, `tests/integration/test_sync_git.py` | specs/002-source-ingestion/verification.md (real sync + inspect of both S-CORE sources) | verified for F002 (F009 re-checks container/host setup) |
| OPS-001 | F006, F009 | — | — | — | — | — | open |
| OPS-002 | F003, F009 | — | — | — | — | — | open |
| OPS-003 | F003, F009 | — | — | — | — | — | open |
| OPS-004 | F001, F009 | F001 FR-015, FR-016 | T020, T021, T022 | `config/schema.py`, `config/loader.py`, `config/redact.py` | `tests/unit/test_config_schema.py`, `tests/unit/test_config_loader.py`, `tests/unit/test_redact.py` | verification.md Phase 1/2 checkpoint | verified |
| OPS-005 | F001, F009 | F001 FR-017, FR-019 | T001, T003, T055–T058 | `pyproject.toml`, `uv.lock`, `NOTICE`, `THIRD_PARTY_NOTICES.md`, `scripts/check_licenses.py`, `.github/workflows/ci.yml` | `tests/unit/test_check_licenses.py` | verification.md Phase 6 checkpoint | verified locally and in CI (run 36391821731); gap found 2026-09-28 (mixed permissive+copyleft strings auto-passed) — **fixed** in F002 FR-025 (T002–T004); docutils passes via an agent-reviewed exception pending owner confirmation |
| OPS-006 | F005, F009 | — | — | — | — | — | open |
| PUB-001 – PUB-008 | F010 (deferred) | — | — | — | — | — | open (deferred) |

Grouped rows (ANS, UX, PUB) are expanded to one row per ID when their owning feature is specified.
Unprefixed task IDs refer to F001's `tasks.md`; other features prefix task IDs with the feature (e.g. `F002 T031`).
