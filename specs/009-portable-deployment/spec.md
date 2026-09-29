# Feature Specification: F009 Portable Local Release and Hosting Preparation

**Feature Branch**: `009-portable-deployment`

**Created**: 2026-09-29

**Status**: Draft

**Input**: User description: "F009 from docs/PROJECT_SPEC.md §16: Portable local release and
hosting preparation. Primary requirements LOC-001 through LOC-007, OPS-001 through OPS-006,
SEC-001 through SEC-005. Scope: container image, local Compose profile, CPU/NVIDIA instructions,
prepared offline bundle procedure, fresh installation/restore exercises, runbooks, resource caps,
same API contracts across native/container execution. Acceptance: a clean prepared machine can run
the app; container ports expose only loopback locally; model service has no public host port;
restored corpus retains citations; the local v1.0 release report is complete."

**Master requirements covered**: LOC-001–LOC-007, OPS-001–OPS-006, SEC-001–SEC-005 (release-level
re-verification); master §17.1–§17.2 (native and container deployment), §18.1 (release contents:
locks, container digest, model record, corpus identity, notices, evaluation, hardware matrix,
limitations), §18.3 (local v1.0 gate), AT-16.

## Clarifications

### Session 2026-09-29

Resolved autonomously by the agent (agent review, not an approval) from `docs/PROJECT_SPEC.md`
§17–§18 and F001–F008 precedent; recorded in `docs/ASSUMPTIONS.md`. The owner may override any
answer.

- Q: How do the containers reach the model runtime without exposing it? → A: the portable default
  profile (`bundled`, CPU) runs the application and a runtime container on a private Compose network
  with no host port for the runtime; only the application port is published, to `127.0.0.1`. The
  runtime container mounts an already-prepared models directory read-only, so running never
  downloads models. A Linux-only `host-runtime` profile runs the application container on the host
  network and uses the host's loopback runtime, keeping the loopback bind unchanged.
- Q: The application enforces a loopback bind and a loopback runtime URL; how does the bundled
  profile work? → A: a new explicit `deployment.mode: container` allows binding `0.0.0.0` and naming
  runtime hosts from `deployment.runtime_private_hosts` (for example `ollama`). It is accepted only
  when the process really runs in the application image (the image sets
  `SCORE_ASSISTANT_CONTAINER=1`); otherwise configuration validation fails. The native default is
  unchanged. Host/Origin validation stays on and still admits only `localhost`/`127.0.0.1`. The
  loopback-only host port is enforced by the committed Compose file, a test that parses it, and a
  runtime check of the published ports.
- Q: GPU in containers? → A: CPU is the portable default. NVIDIA acceleration is documented as a
  Compose override that needs the NVIDIA container toolkit on the host. The toolkit is not installed
  on the reference machine, and installing system packages is outside this project's authority, so
  the GPU container path is recorded as "not run". Native NVIDIA operation was qualified in F008.
- Q: Log rotation and retention (OPS-001)? → A: logs stay body-free JSON on stderr by default. The
  Compose profile caps them with the container log driver (size and file count). Natively, an
  optional `logging.file` writes a daily-rotated file with `logging.retention_days` backups (default
  7, configurable shorter, at most 7).
- Q: What makes the local v1.0 release report "complete"? → A: every gate — including new F009
  gates (container loopback ports, private runtime, fresh install, offline bundle restore with
  citations retained, SBOM, log retention, same API contract native/container) — has a status from
  recorded evidence. None is `not run` except explicitly deferred public-profile items. The verdict
  may remain `blocked` by the human-review items, which the report states.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run the assistant from containers, reachable only locally (Priority: P1)

A user with Docker runs one Compose command on a prepared machine and uses the assistant at
`http://127.0.0.1:8080/`. The model runtime has no host port, and the app port is bound to loopback
only.

**Why this priority**: the core F009 deliverable and two acceptance items.

**Independent Test**: bring the bundled profile up and check the published ports: the app is on
`127.0.0.1:8080` only, the runtime has none, and health, search and a cited answer work through
it.

**Acceptance Scenarios**:

1. **Given** a prepared machine (images present, models directory prepared, data directory with an
   active snapshot), **When** `docker compose --profile bundled up` runs, **Then** the app answers on
   `127.0.0.1:8080`, and `docker port` shows no other published port.
2. **Given** the running stack, **When** the runtime container is inspected, **Then** it publishes no
   host port and is attached only to the private network.
3. **Given** the app container, **When** inspected, **Then** it runs as a non-root user with a
   read-only root filesystem, no added capabilities, `no-new-privileges`, and memory, CPU and PID
   limits.
4. **Given** the running stack with network egress blocked for the containers (internal network),
   **When** a covered question is asked, **Then** a cited answer is returned (no runtime download).

---

### User Story 2 - Prepare offline, then install and restore on a clean machine (Priority: P1)

A maintainer prepares a transferable package: images, models, corpus bundle, source code with
locks. They then install it into a fresh directory and data location, with no network use during
installation or serving, and the restored corpus answers with the same citations.

**Why this priority**: "a clean prepared machine can run the app" and "restored corpus retains
citations" (AT-16).

**Independent Test**: export a bundle from the active snapshot, import it into a new empty data
directory, then ask the same question and look up the same chunk on both. The snapshot ID, chunk
IDs, excerpts and revisions match.

**Acceptance Scenarios**:

1. **Given** the reference data, **When** the preparation procedure runs, **Then** it produces a corpus
   bundle, saved image archives, the models directory reference and a manifest with SHA-256
   hashes, without including secrets.
2. **Given** a fresh clone and an empty data directory, **When** the install procedure runs offline
   (locked dependencies from cache, bundle import, model lock copied), **Then** `doctor` reports
   ready and `serve` answers.
3. **Given** the restored data directory, **When** the citation for a fixed chunk and a fixed question
   is compared with the original, **Then** the snapshot ID, chunk ID, excerpt text and revision are
   identical.

---

### User Story 3 - Same API contract natively and in containers (Priority: P2)

A maintainer runs one contract check against the native server and the container server and gets
identical response shapes for health, capabilities, snapshots, search, citation, chat and compare.

**Why this priority**: explicit scope item; it prevents container drift.

**Independent Test**: the contract probe produces a JSON shape signature per endpoint; the two
signatures are equal.

**Acceptance Scenarios**:

1. **Given** both deployments serving the same snapshot, **When** the probe runs, **Then** every
   endpoint's key structure and status codes are equal, and any difference is listed.

---

### User Story 4 - Operate: runbooks, logs, SBOM, limitations (Priority: P2)

An operator has runbooks for install, preparation, backup/restore, upgrade/rollback, troubleshooting
and log retention. Logs rotate within the retention limit. Every release carries an SBOM, the locks,
the model record, the corpus identity, license notices, evaluation results, a hardware/OS matrix and
known limitations.

**Why this priority**: OPS-001 and OPS-005 release obligations and master §18.1.

**Independent Test**: the file log handler rotates daily and keeps at most N files; the SBOM
generator lists every locked Python and npm package with its version and license; the release
bundle manifest lists every required artifact.

**Acceptance Scenarios**:

1. **Given** `logging.file` and `retention_days: 3`, **When** the log rolls over repeatedly, **Then** at
   most three rotated files remain and no question/answer text is written.
2. **Given** the locks, **When** the SBOM is generated, **Then** it is a CycloneDX 1.5 JSON with every
   locked package (Python and npm), its version, license and purl.
3. **Given** a release is assembled, **When** its manifest is checked, **Then** it contains locks,
   the SBOM, notices, the model qualification record, the corpus manifest identity, the latest
   evaluation and release reports, the hardware/OS matrix and known limitations.

---

### User Story 5 - The local v1.0 release report is complete (Priority: P1)

The release report covers all local baseline requirements and F009's deployment gates, with a
status from recorded evidence for every one. Only public-profile items are deferred.

**Why this priority**: F009 acceptance.

**Independent Test**: after the F009 runs, `release report` shows zero `not run` gates apart from
deferred ones.

**Acceptance Scenarios**:

1. **Given** the F009 evidence, **When** the report is generated, **Then** container, restore,
   contract, SBOM and log-retention gates have evidence, and the report lists the hardware matrix
   (native NVIDIA qualified; container CPU qualified; container NVIDIA not run; WSL2 not
   validated).

---

### Edge Cases

- `deployment.mode: container` outside the image → configuration error naming the missing marker.
- A runtime private host that is not listed → configuration error.
- A Compose file edited to publish on `0.0.0.0` → the Compose test fails.
- Models directory missing or empty in the bundled profile → readiness reports chat unavailable
  with guidance; search still works; nothing is downloaded.
- The data directory is not writable by the container user → `doctor` reports it with the fix.
- An old image with a different application version → `doctor` shows both versions; snapshot
  compatibility is checked as usual.
- Disk space below the bundle size on import → the existing F003 disk check refuses.
- The NVIDIA toolkit is absent → the GPU override fails fast with documented guidance, and the
  failure is recorded as "not run".

## Requirements *(mandatory)*

### Functional Requirements

**Containers (§17.2, LOC-004, SEC-001, SEC-002, SEC-005, OPS-006)**

- **FR-001**: The project MUST provide an application image built from locked dependencies
  (frontend built in a separate stage) that runs as a non-root user, works with a read-only root
  filesystem (writable data volume and tmpfs only), exposes a health check, and contains no
  secrets or corpus data.
- **FR-002**: A Compose file MUST provide a `bundled` profile (app + runtime on an internal network,
  runtime with no host port and a read-only models mount, app published to `127.0.0.1` only) and a
  Linux `host-runtime` profile (app on the host network using the host loopback runtime). It MUST
  set resource caps (memory, CPUs, PIDs), drop all capabilities, set `no-new-privileges`, and cap
  the container logs.
- **FR-003**: `deployment.mode: container` MUST be the only way to allow a non-loopback bind
  (`0.0.0.0`) or a non-loopback runtime host (only names in `deployment.runtime_private_hosts`), and
  MUST be rejected unless `SCORE_ASSISTANT_CONTAINER=1` is set, which the image does. Host/Origin
  validation MUST remain unchanged.
- **FR-004**: An NVIDIA Compose override and CPU/NVIDIA instructions MUST be documented, stating
  the prerequisites and what was and was not run.

**Preparation, install, restore (§17.1, LOC-002, LOC-003, OPS-002, OPS-003, AT-16)**

- **FR-005**: A preparation procedure MUST produce, from a prepared machine: a corpus bundle
  (existing `bundle export`), image archives (`docker save`), a copy or reference of the models
  directory, and a manifest with SHA-256 hashes. It MUST NOT include secrets, caches or logs.
- **FR-006**: A fresh-install exercise MUST install into a new directory and data location without
  network access during install and serving (dependencies from the locked cache, bundle import),
  and confirm `doctor` ready, `serve` health, search and a cited answer.
- **FR-007**: A restore check MUST compare, between the original and the restored data directory,
  the snapshot ID, a fixed set of chunk IDs with their excerpts and revisions, and the citations of a
  fixed question; any difference fails.

**Contract parity (scope item)**

- **FR-008**: A contract probe MUST record the response shape (keys, types, status codes) of health,
  readiness, capabilities, snapshots, search, citation, chat (JSON) and compare-diff for a base URL.
  Comparing a native and a container probe MUST list any difference.

**Operations (OPS-001, OPS-004, OPS-005)**

- **FR-009**: Optional file logging MUST rotate daily and keep at most `logging.retention_days`
  (default 7, allowed 1–7) rotated files, writing the same body-free records as stderr.
- **FR-010**: An SBOM generator MUST produce CycloneDX 1.5 JSON from `uv.lock` and
  `frontend/package-lock.json` (name, version, purl, license where known, scope), with no new
  dependency and no network.
- **FR-011**: A release-assembly command MUST collect the release contents of master §18.1 into
  `data/releases/<version>-<utc>/` with a manifest of hashes, and MUST refuse to include model
  weights or corpus bundles unless explicitly requested (redistribution conditions are unchecked).
- **FR-012**: Runbooks MUST cover install (native, containers), offline preparation and transfer,
  backup/restore, upgrade and rollback (application and snapshot), troubleshooting (doctor output
  meanings), log retention, and the hardware/OS matrix with what was actually qualified.

**Release report (§18.3)**

- **FR-013**: The release gates MUST add F009 gates: container loopback-only publishing, runtime
  without a host port, container hardening, fresh install, restore retains citations, contract
  parity, SBOM present, log retention and the hardware matrix. After the F009 runs no gate MUST be
  `not run` except deferred public-profile gates.

### Key Entities

- **DeploymentConfig**: mode (`native` | `container`), runtime_private_hosts.
- **LoggingConfig**: file (optional path), retention_days (1–7).
- **PreparedPackage manifest**: items (path, kind, sha256, size), app version, snapshot ID, model
  digests, image digests, created_at.
- **ContractSignature**: per endpoint: status, key tree with types.
- **RestoreReport**: original/restored snapshot IDs, compared chunks, citation comparison, status.
- **ReleaseManifest**: version, items with hashes, excluded items with reasons.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With the bundled profile running, 100% of published host ports are bound to
  `127.0.0.1`, and the runtime container has zero published ports (checked on the running stack).
- **SC-002**: A fresh install from the prepared package into an empty directory reaches a cited
  answer with no network access during install and serving.
- **SC-003**: The restored corpus has the same snapshot ID and identical excerpts and revisions for
  100% of compared chunks and citations.
- **SC-004**: The native and container contract signatures are identical for every probed
  endpoint.
- **SC-005**: The SBOM lists 100% of locked packages (Python and npm).
- **SC-006**: The local v1.0 release report has zero `not run` gates except deferred public-profile
  gates.

## Assumptions

- Docker Engine and Compose v2 are installed on the reference machine (29.8 / v5.5); image pulls
  (python, node, ollama) are preparation steps that use the network once, and the images are then
  saved for offline transfer.
- The bundled runtime image is pinned to the locked runtime version (Ollama 0.34.0) by digest.
- The "clean machine" exercise uses a fresh clone and data directory on the reference machine; a
  second physical machine is not available, which is recorded.
- Model weights and corpus bundles are not redistributed; the package references them for the
  owner's own transfer.
