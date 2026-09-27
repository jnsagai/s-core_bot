# Feature Specification: F001 Foundation and Local Runtime Contract

**Feature Branch**: `001-foundation`

**Created**: 2026-09-27

**Status**: Draft

**Input**: User description: "Specify F001 Foundation and local runtime contract from docs/PROJECT_SPEC.md. The user must be able to install the project, inspect configuration/runtime readiness, and start a loopback-only service that accurately reports missing models or corpus. No paid account or external inference is required. Preserve LOC-001, LOC-003, LOC-004, LOC-005, LOC-007, OPS-004, OPS-005, and SEC-004. Do not implement ingestion, chat generation, or a decorative fake chatbot yet. Include failure behavior, security defaults, observable acceptance scenarios, and the verification needed to move to F002."

**Master requirements covered**: LOC-001, LOC-003, LOC-004, LOC-005, LOC-007, OPS-004, OPS-005,
SEC-004 (primary); LOC-006 readiness reporting and SRC-012 notices framework (supporting).

## Clarifications

### Session 2026-09-27

Resolved autonomously by the agent from `docs/PROJECT_SPEC.md` at the project owner's request
("proceed without stopping"); see `docs/ASSUMPTIONS.md` A-007. The owner may override any answer.

- Q: What exit codes does the diagnostic use, and does "corpus not prepared" count as failure? →
  A: `0` = no failures (warnings allowed, including not-yet-prepared corpus/models); `1` = one or
  more failures (runtime unreachable/incompatible, model identity mismatch, data dir unwritable,
  incompatible corpus); `2` = configuration or usage error (nothing else is checked). Basis:
  §10.2 "document their exit codes", §11.3 "messages must give a next action"; a fresh install
  is expected to be unprepared, so that state is a warning, not a failure.
- Q: What HTTP status does readiness return when some capabilities are unavailable? →
  A: `/health/ready` returns 200 when search is available (chat may be listed as degraded) and 503
  when search is unavailable; the body contains only capability states and reason codes. The
  capabilities endpoint always returns 200 while live. Basis: LOC-006 (search survives generation
  loss), §10.1 "minimal public detail". In F001 readiness is therefore always 503.
- Q: Are state-changing requests without an `Origin` header (non-browser clients) allowed? →
  A: Yes, if the `Host` header is allowed and the request carries no browser cross-site indicator
  (`Sec-Fetch-Site: cross-site`). Requests with a disallowed `Origin` are always rejected with 403.
  Basis: SEC-004 targets browser-originated abuse; §10.2 requires CLI/local clients to work.
- Q: How is free disk space checked before model acquisition? →
  A: Required free space = sum of the profile's known download sizes + a configurable safety margin
  (default 2 GiB). If a size is unknown, acquisition warns and requires `--allow-unknown-size`.
  Basis: §8.2 "setup must check rather than assume a fixed universal capacity"; workstation has
  14 GiB free (docs/toolchain.md).
- Q: How does F001 determine corpus state before the corpus format exists (F003)? →
  A: Corpus state is `absent` when the data directory has no snapshot catalog; any existing catalog
  is reported `incompatible` ("no supported corpus schema in this release") and never opened. The
  probe is an interface that F003 replaces. Basis: §9.2 layout; §9.2 "a newer incompatible corpus
  schema must fail clearly rather than be partially opened".

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Diagnose local readiness after installation (Priority: P1)

A new contributor clones the repository, installs it with the documented steps, and runs a single
diagnostic command. The diagnostic tells them, in plain language, whether the local model runtime
is reachable, which configured models are present and with what identity, how much memory, GPU
memory and disk space are available, whether a documentation corpus exists and is compatible, and
what to do next for every problem found. It never asks for an account, key, or payment.

**Why this priority**: every later feature depends on a user being able to install the project
and learn honestly what is missing. It delivers value on its own as an environment checker.

**Independent Test**: on a machine with no model runtime and no corpus, install the project and run
the diagnostic; it completes, lists each missing component with a next action, and exits with the
documented status. Repeat with the runtime running and models present; the report changes
accordingly.

**Acceptance Scenarios**:

1. **Given** a fresh installation and no local model runtime running, **When** the user runs the
   diagnostic, **Then** it reports the runtime as unreachable with the configured address and a
   next action, reports corpus as "not prepared", and still reports memory and disk information.
2. **Given** the runtime is running but a configured model is absent, **When** the user runs the
   diagnostic, **Then** that model is reported missing with the exact acquisition command, and
   present models are reported with their resolved identity (digest).
3. **Given** a configuration file with a misspelled key or an out-of-range value, **When** the user
   runs the diagnostic, **Then** it reports the exact key/path and reason, and exits with the
   configuration-error status without contacting the runtime.
4. **Given** a configuration containing a credential-like value (e.g. in a URL userinfo or an
   environment override), **When** the diagnostic prints configuration, **Then** the value is
   redacted.
5. **Given** a machine without an NVIDIA GPU, **When** the diagnostic runs, **Then** it reports
   CPU-only operation as supported and GPU memory as "not detected", not as an error.
6. **Given** any diagnostic run, **When** it completes, **Then** no network request has been made
   to any host other than the configured local runtime address.

---

### User Story 2 - Start a loopback-only service that reports readiness honestly (Priority: P2)

The user starts the application service. It listens only on the local machine, answers liveness
and readiness checks, and publishes its capabilities. Because no corpus and no answering exist
yet, it states that search and chat are unavailable and why. It never pretends to be a working
chatbot. Requests from other websites or with unexpected host names are rejected.

**Why this priority**: establishes the serving contract and security defaults every later API
depends on. Requires the configuration and readiness model from US1.

**Independent Test**: start the service with default configuration; query liveness, readiness and
capabilities from the same machine; send requests with a hostile Origin and a rebinding Host
header; attempt to start with a non-loopback address.

**Acceptance Scenarios**:

1. **Given** default configuration, **When** the service starts, **Then** it listens on
   `127.0.0.1` only and reports the address it bound.
2. **Given** a running service with no corpus, **When** the readiness check is queried, **Then** it
   reports "not ready" with minimal, non-sensitive reasons (e.g. `corpus_missing`,
   `generation_model_missing`) and the capabilities endpoint reports search and chat unavailable.
3. **Given** a running service, **When** the liveness check is queried, **Then** it reports alive
   without runtime, path, or configuration details.
4. **Given** configuration requesting a non-loopback bind address (e.g. `0.0.0.0` or a LAN IP),
   **When** the service is started, **Then** it refuses to start with an explanation that remote
   exposure requires the public profile, which is not available in this release.
5. **Given** a request whose `Host` header is not in the allowed list, **When** it reaches the
   service, **Then** it is rejected before any application logic runs.
6. **Given** a request carrying an `Origin` not in the allowed list, or marked as a cross-site
   browser request, **When** it reaches the service, **Then** it is rejected and no CORS permission
   is granted.
7. **Given** the model runtime is stopped while the service is running, **When** readiness is
   queried again, **Then** the change is reflected without restarting the service.

---

### User Story 3 - Acquire and inspect local models explicitly (Priority: P3)

An operator explicitly acquires the configured model profile with a dedicated preparation command
that states it uses the network and shows the known download size. A separate inspection command
shows installed model identities without downloading anything. The resolved identities are
recorded in a model lock so later runs detect silent model changes. Serving never downloads.

**Why this priority**: separates preparation from operation (LOC-003) and records model identity
for later qualification; useful only after US1 exists.

**Independent Test**: run inspect with the runtime up and models absent (reports absent, no
download); run acquire for the profile (downloads, writes lock); run inspect again (matches lock);
start the service and confirm no pull was requested.

**Acceptance Scenarios**:

1. **Given** the runtime is running, **When** the operator runs model inspection, **Then** it lists
   each profile model as present/absent with digest, size and family where available, and makes no
   download request.
2. **Given** the operator runs model acquisition for the `local-small` profile, **When** it
   completes, **Then** each model is present, its identity is written to the model lock, and the
   output states that network was used.
3. **Given** a model lock exists and the installed model digest differs, **When** the diagnostic
   runs, **Then** it reports an identity mismatch requiring explicit requalification, not "ok".
4. **Given** configured models are missing, **When** the service or any query command starts,
   **Then** no download is triggered and the missing models are reported.
5. **Given** free disk space below the profile's known download size plus a safety margin, **When**
   acquisition is requested, **Then** it stops before downloading and reports the shortfall.

---

### User Story 4 - Contributor verification baseline (Priority: P3)

A contributor can run the same formatting, lint, type, and deterministic test checks locally that
continuous integration runs, without internet access to model registries and without downloading
models. Dependency versions are locked, licensing and third-party notices exist, and the exact
toolchain versions are recorded.

**Why this priority**: required by the constitution for every later feature, but produces no
end-user behavior by itself.

**Independent Test**: on a prepared checkout with network to model registries blocked, run the
documented check command; all checks run and pass. Inspect the repository for lock files, license,
notices, and toolchain record.

**Acceptance Scenarios**:

1. **Given** a checkout with locked dependencies installed, **When** the contributor runs the
   documented check command with external network blocked, **Then** format, lint, type and tests
   run to completion and no test contacts a model runtime or the internet.
2. **Given** a pull request, **When** continuous integration runs, **Then** it executes the same
   checks plus a dependency-license check and fails on any failure.
3. **Given** the repository, **When** a reviewer inspects it, **Then** `LICENSE`, `NOTICE`,
   `THIRD_PARTY_NOTICES.md`, the dependency lock, and the recorded toolchain versions are present.

---

### Edge Cases

- Runtime address reachable but not an Ollama-compatible runtime (unexpected response) →
  reported as "incompatible runtime", not "missing model".
- Runtime responds slowly → diagnostic and readiness checks time out within a bounded deadline and
  report "timeout" rather than hanging.
- Configuration file missing → built-in safe defaults are used and the report states so.
- Configuration file unreadable or not valid YAML → configuration error with file and line.
- Configured runtime address is non-loopback in the local profile → configuration error (the local
  profile may only use a loopback runtime).
- Environment override with an unknown variable name under the project prefix → reported as an
  error, like unknown file keys.
- Data directory absent → reported as "not prepared" with next action; not created by read-only
  diagnostics.
- Data directory not writable → reported by the diagnostic as a failure with the path.
- GPU tooling present but no GPU visible → "not detected", with a note.
- Requested port already in use → service exits with a clear error and non-zero status.
- IPv6 loopback (`::1`) requested → accepted as loopback.
- Request without an `Origin` header (non-browser local client, e.g. CLI or curl) → allowed if the
  Host header is valid.
- Corpus directory exists from a newer, incompatible schema → reported "incompatible corpus";
  service does not open it.
- Browser cross-site request without an `Origin` header but with `Sec-Fetch-Site: cross-site` →
  rejected with 403.
- Disk space unknown for the model store (runtime reports no path) → check falls back to the data
  directory filesystem and says so.
- Diagnostic run on a freshly installed, unprepared machine → exit code 0 with warnings.

## Requirements *(mandatory)*

### Functional Requirements

**Local operation and separation of operations**

- **FR-001** (LOC-001): The installation, diagnostic, model inspection, and service MUST operate
  without any API key, vendor login, or paid endpoint; no such setting exists in configuration.
- **FR-002** (LOC-001): Configuration MUST reject any runtime provider other than the local Ollama
  provider and any attempt to enable a cloud fallback.
- **FR-003** (LOC-003): The command-line tool MUST expose preparation and operation as separate
  commands: diagnose (`doctor`), model inspection (`models inspect`), model acquisition
  (`models pull --profile <name>`), and service start (`serve`). Source sync and index build are
  reserved for F002/F003 and MUST NOT be present as non-functional placeholders.
- **FR-004** (LOC-003): Only the model acquisition command may cause downloads. Service start and
  all diagnostics MUST NOT request model pulls or contact any network host other than the
  configured local runtime. Help text of network-using commands MUST state that they use the
  network.

**Diagnostics**

- **FR-005** (LOC-005): The diagnostic MUST report: application version; configuration source(s)
  and validation result; runtime reachability and version; each configured model's presence and
  resolved identity (digest); model-lock agreement; total/available RAM; GPU name and total/free
  GPU memory where detectable; free disk space at the data directory; corpus presence and schema
  compatibility.
- **FR-006** (LOC-005): Every reported failure or warning MUST include a stable code, a
  human-readable explanation, and a concrete next action.
- **FR-007** (LOC-005): The diagnostic MUST provide human-readable output and a machine-readable
  output (`--json`) with the same content, and MUST exit `0` when no check failed (warnings
  allowed), `1` when at least one check failed, and `2` on configuration or usage error. A
  not-yet-prepared corpus or missing model is a warning, not a failure.
- **FR-008** (LOC-005, OPS-004): Diagnostic and log output MUST redact secrets: URL userinfo,
  values of keys or environment variables whose names indicate secrets, and authorization headers.
- **FR-009** (LOC-006): Readiness MUST be modelled per capability (search, chat) with explicit
  reasons, so later features can report degraded operation; in F001 both capabilities report
  "unavailable" with reason codes because no corpus or answering exists.

**Service and network exposure**

- **FR-010** (LOC-004): The service MUST bind to a loopback address by default (`127.0.0.1`).
- **FR-011** (LOC-004): The service MUST refuse to start when configured to bind to a non-loopback
  address unless the public profile is selected; in F001 the public profile does not exist, so
  any non-loopback bind MUST be refused with an explanation.
- **FR-012** (SEC-004): The service MUST reject requests whose `Host` header does not match the
  configured allowed hosts (with port), protecting against DNS rebinding.
- **FR-013** (SEC-004): The service MUST reject requests with an `Origin` header not in the
  configured allowed origins, and requests marked by the browser as cross-site; CORS permissions
  MUST be granted only to allowed origins. Rejections use HTTP 403 (Origin/cross-site) or 400
  (Host) with a stable error code and no application processing.
- **FR-014** (SEC-004): Requests using state-changing methods (anything other than GET, HEAD,
  OPTIONS) without an `Origin` header MUST be accepted only when the `Host` is allowed and no
  browser cross-site indicator is present; this protection applies to every current and future
  route by default.
- **FR-020**: The service MUST expose liveness (`/health/live`), readiness (`/health/ready`), and
  capabilities (`/api/v1/capabilities`) endpoints. Liveness exposes no details; readiness returns
  200 when search is available and 503 otherwise, exposing only capability states and reason codes;
  capabilities (always 200 while live) exposes modes, limits, model label, and per-capability
  readiness.
- **FR-021**: The service MUST NOT present any chat or answer functionality, placeholder answers,
  or simulated responses.

**Configuration**

- **FR-015** (OPS-004): Configuration MUST be schema-validated with a declared `schema_version`,
  MUST reject unknown keys, and MUST report every invalid value with its path and reason.
- **FR-016** (OPS-004): Configuration precedence MUST be: built-in safe defaults < selected
  configuration file < documented environment overrides < explicit command-line flags. Relative
  paths resolve against the configuration file's directory.

**Dependencies, licensing, platform, CI**

- **FR-017** (OPS-005, SRC-012): The repository MUST contain locked Python dependencies, `LICENSE`,
  `NOTICE`, `THIRD_PARTY_NOTICES.md`, and a recorded toolchain; a check MUST fail when a locked
  dependency's license is not on the approved list or unknown.
- **FR-018** (LOC-007): The project MUST install and pass its deterministic checks on Linux x86-64
  without a GPU. GPU detection is optional and MUST NOT be required.
- **FR-019** (OPS-005): Continuous integration MUST run format, lint, type check, deterministic
  tests, and the license check on every change, without paid APIs or model downloads.

**Model identity**

- **FR-022** (LOC-005, LOC-003): Model acquisition MUST write a model lock recording, per model:
  configured tag, resolved digest, size, runtime version, and acquisition time (UTC). Diagnostics
  MUST compare installed identities with the lock and report mismatches.
- **FR-023** (LOC-003): Model acquisition MUST require free disk space at the runtime's model
  storage location (or, if not determinable, the data directory) of at least the profile's known
  download size plus a configurable safety margin (default 2 GiB) before starting; unknown sizes
  require an explicit override flag. It MUST support clean interruption and idempotent re-runs.
- **FR-024** (LOC-005): Corpus state MUST be reported as `absent` (no snapshot catalog in the data
  directory) or `incompatible` (a catalog exists but its schema is not supported by this release);
  an incompatible corpus MUST NOT be opened. F003 extends this with `compatible`.

### Key Entities

- **AppConfig**: validated configuration (schema version, profile, server bind/allowed hosts/
  origins, data directory, runtime provider/address/models/context limits, limits, privacy flags);
  records the source of each effective value.
- **ModelProfile**: named set of models (e.g. `local-small`: generation + embedding) with known
  approximate download sizes.
- **ModelLock**: recorded identities of acquired models (tag, digest, size, runtime version, time).
- **DiagnosticReport**: ordered set of checks, each with id, status (ok/warning/failure/not
  applicable), code, message, next action, and redacted details; plus overall status and exit code.
- **Readiness**: per-capability (search, chat) availability with reason codes; derived from runtime
  state, model presence, and corpus state.
- **HardwareInfo**: RAM, GPU (if detectable), disk, CPU architecture/OS.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A contributor on a prepared Linux x86-64 machine (tools installed) goes from clone to
  a completed diagnostic report in under 10 minutes, excluding model downloads.
- **SC-002**: With the model runtime absent or unresponsive, the diagnostic completes in under
  10 seconds and every failure line includes a next action (100 % of failure lines).
- **SC-003**: 100 % of the hostile-request fixtures (foreign Origin, cross-site marker, rebinding
  Host, non-loopback bind attempt) are rejected in the automated suite.
- **SC-004**: The full deterministic check suite completes with external network blocked, with
  zero outbound connections other than to the loopback interface.
- **SC-005**: 100 % of seeded misconfiguration fixtures (unknown key, wrong type, out-of-range value,
  non-loopback runtime, cloud fallback) are reported with the exact key path.
- **SC-006**: 0 secrets from the redaction fixtures appear in diagnostic, JSON, or log output.
- **SC-007**: Readiness reflects a runtime stop or start within one readiness query (no restart).

## Assumptions

- Target platform for this feature is Linux x86-64; Windows/WSL2 and macOS are documented later
  (LOC-007) and not tested here.
- The local model runtime is Ollama installed by the user; the project does not install or
  update it, GPU drivers, or system packages.
- The `local-small` profile uses the master-spec candidate models (`qwen3:4b-instruct`,
  `nomic-embed-text`); qualification of those models is out of scope (F005/F008).
- The web user interface is out of scope (F006); the service exposes only JSON endpoints.
- Corpus schema compatibility checking in F001 only recognises "absent", "present-compatible", and
  "present-incompatible" using a manifest version marker; the corpus format itself is defined in
  F003.
- Tests use a fake runtime; real-runtime checks are optional integration tests marked as such and
  reported "not run" when the runtime is unavailable.

## Out of Scope

Source acquisition, ingestion, indexing, search, chat generation, UI, container packaging, public
profile, authentication, rate limiting beyond request size bounds.

## Exit Criteria to Move to F002

All FR verified by automated tests; SC-002 to SC-007 measured in the suite; SC-001 measured once
and recorded; `docs/TRACEABILITY.md` updated; converge reports no remaining work.
