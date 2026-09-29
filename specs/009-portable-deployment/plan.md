# Implementation Plan: F009 Portable Local Release and Hosting Preparation

**Branch**: `009-portable-deployment` | **Date**: 2026-09-29 | **Spec**: [spec.md](spec.md)

## Summary

Package the assistant for portable local use:
- a hardened non-root application image and a Compose file (`bundled` CPU profile with a private
  runtime and an app port published only on `127.0.0.1`; a Linux `host-runtime` profile; an NVIDIA
  override documented);
- an explicit, image-only `deployment.mode: container` that is the sole exception to the loopback
  rules;
- optional rotating file logs with ≤ 7 days retention;
- scripted preparation, offline fresh install and restore with a citation-identity check (run inside
  the F008 loopback-only namespace);
- a native/container contract-parity probe, a CycloneDX SBOM and release assembly;
- runbooks, a hardware matrix and known limitations;
- new release gates so the local v1.0 report is complete.

## Technical Context

**Language/Version**: Python 3.12, Bash, Dockerfile/Compose; frontend unchanged

**Primary Dependencies**: none new (stdlib `tomllib`, `logging.handlers`); Docker Engine + Compose
v2 as external tools

**Storage**: `data/` volume; packages and releases under user-chosen paths and `data/releases/`

**Testing**: pytest (config validation, providers, log rotation, SBOM, contract comparison, restore
comparison over fixture snapshots, Compose file policy parsed as YAML); real runs of the container
check, fresh install and restore, recorded in verification

**Target Platform**: Linux x86-64 (reference RTX 4070 laptop); CPU containers as the portable
default

**Constraints**: no downloads while serving; runtime without a host port; loopback-only
publishing; no secrets in images or packages; no redistribution of weights/corpus by default

## Constitution Check

| Principle | Status | Note |
| --- | --- | --- |
| I Local operation | PASS | Prepared deployments run without fetching; image pulls are preparation only; offline install exercised in a namespace. |
| II Evidence | PASS | Restore check compares citations by identity. |
| III Snapshots explicit | PASS | Bundles keep snapshot identity; restore verified. |
| IV Untrusted docs | PASS | No change. |
| V Read-only | PASS | No change. |
| VI Modular monolith | PASS | One app image + runtime; no orchestration beyond Compose; no Kubernetes. |
| VII Honest verification | PASS | GPU containers and a second physical machine recorded "not run"/not available. |
| VIII Privacy | PASS | Body-free logs; retention ≤ 7 days. |
| IX Spec-first | PASS | Traceability updated for LOC/OPS/SEC. |
| X Public profile separate | PASS | Container mode is loopback-published only; public hosting remains F010. |
| XI Licenses | PASS | SBOM + notices in releases; weights/bundles excluded by default. |
| XII No implied authority | PASS | Report verdict remains blocked by human items. |

## Project Structure

```text
Dockerfile, .dockerignore, compose.yaml, compose.nvidia.yaml, config/container.yaml
scripts/prepare_package.sh, fresh_install.sh, container_check.sh, sbom.py
src/score_docs_assistant/config/schema.py        # DeploymentConfig, LoggingConfig, loopback rules
src/score_docs_assistant/cli/runtime_factory.py  # allowed runtime hosts
src/score_docs_assistant/models/ollama*.py       # allowed_hosts parameter
src/score_docs_assistant/api/logging.py, cli/serve.py  # rotating file log
src/score_docs_assistant/qualification/restore.py, contract.py, release.py
src/score_docs_assistant/cli/qualify.py          # release assemble
docs/runbooks/*.md, docs/quality/hardware-matrix.md, docs/KNOWN_LIMITATIONS.md
tests/unit/test_deployment_config.py, test_log_retention.py, test_sbom.py, test_contract_probe.py,
      test_compose_policy.py, test_release_assembly.py; tests/integration/test_restore_check.py
```

## Verification Strategy

| Requirement | Verification |
| --- | --- |
| FR-001–FR-003, SC-001 | unit: config rules + Compose policy test; real: `container_check.sh` report |
| FR-004 | docs; GPU override "not run" recorded |
| FR-005–FR-007, SC-002, SC-003 | integration: restore comparison on fixtures; real: package + fresh install + restore in a namespace |
| FR-008, SC-004 | unit: signature/compare; real: native vs container probes |
| FR-009 | unit: rotation with retention |
| FR-010, SC-005 | unit: SBOM counts equal lock counts |
| FR-011 | unit: manifest, exclusions; real: assembled release |
| FR-012 | runbooks reviewed against commands (quickstart walk) |
| FR-013, SC-006 | gate-file test; real report with zero non-deferred `not run` |

## Complexity Tracking

None.
