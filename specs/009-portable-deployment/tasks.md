---

description: "Task list for F009 Portable Local Release and Hosting Preparation"
---

# Tasks: F009 Portable Local Release and Hosting Preparation

**Tests**: MANDATORY (constitution VII). Real container/install runs are recorded in `verification.md`.

## Phase 1: Configuration and logging (foundational)

- [ ] T001 `DeploymentConfig` + `LoggingConfig` in `config/schema.py`; loopback rules moved to an `AppConfig` validator with the container exception (R3); tests `tests/unit/test_deployment_config.py`
- [ ] T002 Providers take `allowed_hosts` from `cli/runtime_factory.py` (loopback + private hosts in container mode); provider tests updated
- [ ] T003 Rotating file log (`logging.file`, `retention_days`) in `api/logging.py`/`cli/serve.py`; `tests/unit/test_log_retention.py`; `doctor` shows deployment mode and log settings

## Phase 2: US1 Containers (P1)

- [ ] T004 `Dockerfile` (pinned base digests), `.dockerignore`, `config/container.yaml`
- [ ] T005 `compose.yaml` (`bundled`, `host-runtime`), `compose.nvidia.yaml`; `tests/unit/test_compose_policy.py` (loopback-only ports, no runtime ports, hardening, internal network, read-only models)
- [ ] T006 `scripts/container_check.sh` (up → inspect → probe → down → `container-*.json`)

## Phase 3: US2 Package, install, restore (P1)

- [ ] T007 `qualification/restore.py` (snapshot/chunk/citation comparison) + CLI entry; `tests/integration/test_restore_check.py` (identical, and a tampered restore detected)
- [ ] T008 `scripts/prepare_package.sh` and `scripts/fresh_install.sh` (namespace, offline)

## Phase 4: US3 Contract parity (P2)

- [ ] T009 `qualification/contract.py` (probe, signature, compare, CLI); `tests/unit/test_contract_probe.py`

## Phase 5: US4 Operations (P2)

- [ ] T010 `scripts/sbom.py` (CycloneDX 1.5) + `tests/unit/test_sbom.py`
- [ ] T011 `release assemble` (`qualification/release.py`) + `tests/unit/test_release_assembly.py`
- [ ] T012 Runbooks `docs/runbooks/` (install, offline-preparation, backup-restore, upgrade-rollback, troubleshooting, logs), `docs/quality/hardware-matrix.md`, `docs/KNOWN_LIMITATIONS.md`

## Phase 6: US5 Gates

- [ ] T013 F009 gates in `eval/release-gates.yaml` + gate-file test update

## Phase 7: Real runs

- [ ] T014 Build/pull images; run `container_check.sh`; record
- [ ] T015 Package + fresh install + restore (offline namespace); record
- [ ] T016 Contract parity native vs container; record
- [ ] T017 SBOM, release assemble, pytest/vitest JUnit, release report (zero non-deferred `not run`); commit report copy

## Phase 8: Polish

- [ ] T018 README/CLAUDE.md, BACKLOG, TRACEABILITY (LOC/OPS/SEC F009 parts), ASSUMPTIONS (A-050+), verification, quickstart walk
