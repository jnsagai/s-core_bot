# Verification: F009 Portable Local Release and Hosting Preparation

Commands and results as actually run on 2026-09-29 (reference machine: Linux x86-64, RTX 4070
Laptop, Docker 29.8 / Compose v5.5, no NVIDIA container toolkit).

## Deterministic

```text
$ uv run ruff format --check . && uv run ruff check . && uv run mypy src
460 files already formatted / All checks passed! / Success: no issues found in 140 source files
$ uv run pytest -q --junitxml=data/reports/pytest-<utc>.xml
1117 passed, 10 skipped (opt-in)
$ uv run python scripts/check_traceability.py
Traceability check passed: every local requirement is mapped; PUB deferred.
```

New tests:
- **Container mode** (`test_deployment_config.py`, 13 tests):
  - the native defaults are unchanged;
  - container mode is refused without the image marker, and the marker alone opens nothing;
  - unlisted runtime hosts, invalid labels, and private hosts in native mode are refused;
  - providers refuse non-loopback hosts unless allowed;
  - the committed `config/container.yaml` loads only inside the image.
- **Compose and image policy** (`test_compose_policy.py`): the runtime has no ports, only the
  internal network, read-only models, a digest-pinned image and `OLLAMA_NOPRUNE`; the app is
  published on 127.0.0.1 only; both app services are hardened; the host-runtime profile uses the
  native loopback config; every Dockerfile base is digest-pinned, runs non-root with the marker,
  uses `--frozen`, and `.dockerignore` excludes data and venvs.
- **Log retention** (`test_log_retention.py`): body-free file records; after 5 forced rollovers at
  most 3 rotated files remain (retention 3).
- **Container report** (`test_container_report.py`): each failure mode is named.
- **Restore** (`test_restore_check.py`): a real bundle round trip passes, a different corpus is
  detected, and an empty restore fails.
- **Contract** (`test_contract_probe.py`): the shape ignores values and lengths, and differences
  are listed.
- **SBOM** (`test_sbom.py`): every uv.lock package and every distinct npm name@version is listed
  once, with scopes.
- **Release assembly** (`test_release_assembly.py`): a complete manifest; missing items listed;
  weights and bundles excluded; operator documents present.
- **Gates** (`test_gates.py`): F009 references covered.
- **Finding:** an existing test pinned the startup-log keys; the new `deployment`/`log_file` keys
  (configuration only) were added to its allow-list.

## Real runs

### Image and containers (T014)

```text
$ docker build -t score-docs-assistant:0.1.0 .          → 368 MB, sha256:ea4feb27e01e… (final)
$ docker compose --profile bundled pull ollama          → ollama/ollama:0.34.0@sha256:684d8674…, 5.5 GB
$ scripts/container_check.sh                            → data/reports/container-20260929T132833Z.json
container check: pass — loopback-only app port, private runtime, hardened, cited answer
published ports: app ["127.0.0.1:8080->8080/tcp"], runtime []; runtime networks internal: true
app: user 1000:1000, read_only true, cap_drop [ALL], no-new-privileges, memory 2 GiB, 2 CPUs, pids 256
probe: chat ready, search 8 results, answer HTTP 200 answered with 2 citations, digest 0edcdef34593… (lock)
```

CPU inference in the container took about 60 s for the first answer, including the model load.
After the run, the stack was down and port 8080 was free.

### Package, fresh install, restore (T015; all offline in a loopback-only namespace)

```text
$ scripts/prepare_package.sh <scratch>/package --acknowledge-license-review "not redistributed: …"
139M  (app-image 123 MB, corpus bundle 20 MB, source git bundle 1.3 MB, frontend 127 KB, model lock, manifest)
$ scripts/fresh_install.sh <scratch>/package <scratch>/fresh    → fresh-install-20260929T133023Z.json
external egress blocked            ok  DNS lookup failed as expected
clone source from the package      ok
install locked dependencies offline ok (uv sync --frozen --offline --no-dev)
install built frontend             ok
import corpus bundle               ok
activate restored snapshot         ok  20260928T140548Z-7c6a05b3
doctor                             ok
serve: cited answer, excerpt, search, UI  ok  (offline check pass)
restore keeps citations            ok  snapshot identical; chunks 50 (0 mismatches); citations 23 (0 mismatches)
fresh install: pass
```

- The first attempt failed one step: `tar` tried to chown inside the user namespace. It was
  fixed with `--no-same-owner`.
- The export needed a license-review reason for 3 flagged documents; the reason given is scoped to
  this local exercise (A-052). The package and the fresh install were deleted afterwards.

### Contract parity (T016)

```text
native (config/local.yaml) vs container (bundled): contract parity: pass (10 endpoints) []
endpoints: health_live, health_ready, capabilities, snapshots, search, citation, entities,
           chat_json, chat_invalid (422), snapshot_diff
```

### SBOM, release assembly, report (T017)

```text
$ uv run python scripts/sbom.py --out data/reports/sbom-20260929T131920Z.cdx.json
SBOM: 498 components (45 Python, 453 npm); 1 without license data
$ uv run score-assistant --config config/local.yaml release report
verdict: blocked  gates: {'blocked': 7, 'pass': 35, 'not run': 1}
$ uv run score-assistant --config config/local.yaml release assemble
release 0.1.0: 17 items → data/releases/0.1.0-<utc>   (complete: true; weights and bundles excluded)
```

- **Report copy:** `docs/quality/release-report-local-v1.0-2026-09-29.md`.
- **Not run (1):** only the deferred public profile, so SC-006 is met.
- **Blocked (7):** all human-dependent (suite review, human-judged metrics, held-out gates on
  unreviewed cases, the browser walkthrough).

### Not run

- GPU in containers: the NVIDIA toolkit is not installed, and installing system packages is out
  of scope.
- The `host-runtime` profile end-to-end: only its policy is tested.
- A second physical machine: not available (A-053).
- WSL2 and macOS: not validated.

## Quickstart walk (T018)

| Section | Result |
| --- | --- |
| A deterministic | above |
| B containers | build, pull, container check pass |
| C package/fresh install/restore | pass |
| D contract parity | pass |
| E SBOM/assemble/report | done (report complete, verdict blocked by human items only) |

## Convergence (agent review)

- Checked against the code and tests: FR-001–FR-013, SC-001–SC-006 and constitution I–XII. No
  missing or contradicting items; no Convergence phase appended.
- FR-004's GPU container path is documented and recorded as not run, as the spec allows.
- Open owner items: A-052 (license review before any real transfer), A-040, A-044, A-045/A-048.
