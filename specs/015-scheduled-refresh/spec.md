# Feature Specification: F011 Scheduled Corpus Refresh

**Feature Branch**: `015-scheduled-refresh`

**Created**: 2026-10-02

**Status**: Draft

**Input**: User description: "F011 — Scheduled corpus refresh. Keep the active documentation
snapshot close to upstream S-CORE without manual steps. Add a one-shot, operator-invoked
`score-assistant refresh` command that (1) performs a cheap upstream change check and stops when
nothing changed, (2) otherwise runs the existing source sync, (3) builds a new snapshot only when the
synced source revisions differ from the active snapshot, (4) applies a promotion gate and (5)
activates the new snapshot atomically only when the gate passes, otherwise keeps the current
snapshot and reports why. The serve path stays network-free; scheduling is done by operator-installed
timer units shipped in the repository (opt-in). Polling must not accumulate files, overlapping runs
must be refused, and the last refresh outcome must be visible in `doctor`. Running `serve` instances
pick up the new snapshot without restart. Containers are out of scope for automatic refresh."

Owner request (2026-10-02): "how to guarantee that the local model always are updated with the
latest s-core documentation in real-time?" → agent proposal (scheduled refresh as a spec-first
feature) → owner: "do it".

**Master requirements covered**: SRC-002 (refs resolved to commits before ingestion), SRC-009
(failed update leaves the active snapshot untouched), OPS-002 (atomic activation, request pinning),
LOC-003 (network only in explicit, operator-invoked preparation), SRC-001 and SEC-005 (only
allowlisted sources and URL limits, reused unchanged). Feature ID F011 is new: it is not in
`docs/PROJECT_SPEC.md` §16 and is added at the owner's request as an operational follow-up to
F002/F003 (it does not change F010, which stays deferred).

## Clarifications

### Session 2026-10-02

Resolved autonomously by the agent (agent review, not an approval) at the owner's standing request
for full autonomy; recorded in `docs/ASSUMPTIONS.md` (A-057). The owner may override any answer.

- Q: Should the promotion gate include the retrieval or answer evaluation suites? → A: No. The gate
  is integrity, exact-ID lookup, coverage-drop and semantic-availability checks plus required
  sources. Development eval cases are tied to specific documents and legitimately shift when
  upstream changes, so they would hold good updates; they stay a manual `eval` step.
- Q: Which exit codes does refresh use? → A: 0 `up-to-date` or `activated`; 1 `failed`; 2
  configuration/usage error (as every other command); 3 `held`; 4 `busy`. Distinct codes let a
  scheduler or script tell "needs attention" (3) from "try later" (4).
- Q: Does refresh build semantic or keyword-only snapshots? → A: It mirrors the active snapshot:
  semantic when the active snapshot has semantic search (and fails, never downgrades, if the
  embedding runtime is unavailable); keyword-only when the active snapshot is keyword-only. With no
  active snapshot it builds semantic. `--lexical-only` forces keyword-only, and the gate then still
  refuses to replace a semantic active snapshot.
- Q: Is refresh status exposed in the HTTP API or web UI? → A: Not in this feature. Status is in
  `refresh --json`, the state file and `doctor`; the UI already shows which snapshot answers. A UI
  indicator can be specified later.
- Q: What if a git source changed but its needs export has not been republished yet? → A: Refresh
  builds and activates as soon as the git change passes the gate; when the export is republished,
  the next run sees its validator change and refreshes again. No waiting or pairing logic.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - One command brings the assistant up to date (Priority: P1)

An operator runs a single refresh command. If upstream S-CORE documentation changed since the active
snapshot, the assistant downloads the change, builds and checks a new snapshot, and starts serving
it. If nothing changed, the command says so quickly and changes nothing.

**Why this priority**: this is the whole value: the assistant answers from current documentation
without the operator remembering four separate commands and their order.

**Independent Test**: with fixture sources, change one upstream file and run refresh: a new
snapshot is active and a search finds the new text. Run refresh again: it reports "up to date",
writes no new snapshot, lock or report.

**Acceptance Scenarios**:

1. **Given** an active snapshot and an upstream commit that changes a document, **When** the
   operator runs refresh, **Then** a new snapshot built from the new commit is active and the
   outcome reports the old and new snapshot and the changed sources.
2. **Given** upstream is unchanged since the last refresh, **When** refresh runs, **Then** it ends
   with outcome "up to date", downloads no source content, builds nothing and leaves the source lock,
   lock archive, reports and snapshots byte-for-byte unchanged.
3. **Given** a running `serve` process, **When** refresh activates a new snapshot, **Then** the next
   request is answered from the new snapshot without restarting `serve`, and a request already in
   progress keeps citing its original snapshot.
4. **Given** the operator already synced manually but did not build, **When** refresh runs, **Then**
   it builds and activates from the current lock even if the upstream check finds nothing new.

---

### User Story 2 - A bad update never replaces a good snapshot (Priority: P1)

Upstream changes can be broken (a parser regression, a half-published requirement export, a mass
deletion). Refresh checks the new snapshot against a promotion gate and activates it only if it
passes. Otherwise the current snapshot keeps serving and the operator sees why.

**Why this priority**: unattended activation is only acceptable if it cannot make the assistant
worse without a visible reason; it shares P1 with Story 1.

**Independent Test**: make a fixture update that removes most documents; refresh ends "held", the
previous snapshot stays active, the new one stays `validated` (inspectable, activatable by hand),
and the reason names the failed gate check.

**Acceptance Scenarios**:

1. **Given** a new snapshot whose document, chunk or entity count dropped by more than the allowed fraction
   compared with the active snapshot, **When** refresh runs, **Then** the outcome is "held" with the
   check `coverage_drop` and the active snapshot is unchanged.
2. **Given** the active snapshot has semantic search and the new one does not (embedding runtime
   unavailable, or `--lexical-only` given), **When** refresh runs, **Then** no keyword-only snapshot
   is activated: outcome `failed` (runtime unavailable) or `held` with the check `semantic`.
3. **Given** any requirement ID in the new snapshot is not returned first by exact lookup, **When**
   refresh runs, **Then** the outcome is "held" with the check `exact_ids`.
4. **Given** a sync failure of a required source, **When** refresh runs, **Then** the outcome is
   "failed", the previous lock and active snapshot are untouched, and the exit code is non-zero.
5. **Given** a held snapshot, **When** the operator inspects it and activates it by hand, **Then**
   the existing activation command works on it unchanged.

---

### User Story 3 - Refresh runs on a schedule, opt-in (Priority: P2)

The operator enables a provided timer so that refresh runs every 15 minutes (configurable) in the
background on their machine, and can disable it again with one command.

**Why this priority**: scheduling turns Story 1 into "always close to upstream"; it is valuable but
only after Story 1 and 2 are safe.

**Independent Test**: install the units into a temporary user unit directory, check that they are
syntactically valid, that the service runs the refresh command with the operator's config, and that
two overlapping refresh runs are refused (the second reports "busy").

**Acceptance Scenarios**:

1. **Given** the shipped timer is not installed, **When** the assistant runs, **Then** no refresh or
   network access ever happens on its own.
2. **Given** a refresh is already running, **When** a second refresh starts, **Then** it exits at
   once with outcome "busy" and changes nothing.
3. **Given** the timer is enabled, **When** an interval elapses, **Then** one refresh runs and its
   outcome is recorded.

---

### User Story 4 - The operator can see how fresh the assistant is (Priority: P3)

`doctor` shows when refresh last ran, its outcome, and the active snapshot, so the operator notices a
refresh that keeps failing or holding.

**Why this priority**: observability for an unattended job; useful but not required for correctness.

**Independent Test**: after one successful and one failed refresh, `doctor` shows the latest outcome
with its time and reason; with no refresh ever run, it says refresh has not run.

**Acceptance Scenarios**:

1. **Given** no refresh has run, **When** `doctor` runs, **Then** it reports refresh as "not run"
   (informational, never a failure).
2. **Given** the last refresh was "held" or "failed", **When** `doctor` runs, **Then** it reports a
   warning with the reason and the time of the last successful refresh.

### Edge Cases

- The upstream check itself fails (offline, DNS, HTTP 5xx): outcome "failed" with the reason; nothing
  else runs; the previous state is kept. A transient failure must not delete anything.
- A needs export changes without a git commit (S-CORE's documentation build publishes after the
  commit): the export check detects it and triggers a refresh. A git change that arrives before its
  export is republished is activated on its own; the later export change triggers another refresh.
- The export server gives no validator (no ETag/Last-Modified): the check cannot prove "unchanged",
  so refresh proceeds to sync; sync then finds identical content and refresh ends "up to date" with
  no new files.
- The source registry (`config/sources.yaml`) changed since the lock: refresh syncs even if upstream
  heads are unchanged.
- Build interrupted (power loss, Ctrl-C): the existing build recovery applies; the active snapshot
  is untouched; the next refresh retries.
- A manual `index build` or `snapshots activate` runs during refresh: the existing single-writer
  lock makes one of them fail with "busy"; refresh reports "busy" and changes nothing.
- Activation applies retention: snapshots beyond the retention count (default 2) that are not active,
  not the rollback target and not pinned by a reader are deleted, including an unactivated comparison
  baseline. Documented; the operator raises `index.retention_count` to keep more.
- Not enough disk for a new snapshot: the existing build disk check fails the build; outcome
  `failed`, nothing deleted to make room.
- The state file is missing, unreadable or invalid: refresh treats it as absent (all exports
  `unknown`, so it syncs) and replaces it at the end; `doctor` warns about an invalid file.
- The embedding runtime is down during a semantic refresh: outcome `failed` with the runtime
  reason; refresh never silently downgrades an active semantic snapshot (FR-016).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a one-shot `refresh` command that, in one run, checks upstream,
  syncs when needed, builds when needed, gates, and activates when the gate passes.
- **FR-002**: The upstream check MUST use only the allowlisted sources of the registry and MUST
  download no file content for git sources (reference resolution only) and MUST use conditional
  requests (stored validators) for exports where the server supports them. It MUST apply the
  registry's host allowlist, redirect validation and connect/read timeouts, exactly as sync does.
- **FR-003**: When the check proves every source unchanged relative to the recorded state, and the
  current lock is the one the active snapshot was built from, refresh MUST end "up to date" without
  syncing or building.
- **FR-004**: When a sync finds the same source revisions and registry as the current lock, the
  current lock file and the lock archive MUST NOT be rewritten.
- **FR-005**: A new snapshot MUST be built only when the current lock differs from the lock the active
  snapshot was built from (or no snapshot is active).
- **FR-006**: The promotion gate MUST check, for the new snapshot: integrity validation passes;
  every requirement ID is returned first by exact lookup; chunk, document and entity counts each
  dropped by no more than a configurable fraction (default 20 %) against the active snapshot;
  semantic search is not lost when the active snapshot has it; every required source is present.
- **FR-007**: Only a snapshot that passes the gate MUST be activated, through the existing atomic
  activation (which also applies retention). A gate failure MUST leave the new snapshot `validated`
  and the active snapshot unchanged.
- **FR-008**: Each run MUST end with exactly one outcome: `up-to-date`, `activated`, `held`, `failed`
  or `busy`, with exit code 0 for `up-to-date` and `activated`, 1 for `failed`, 3 for `held` and 4
  for `busy` (2 stays reserved for configuration/usage errors); `--json` MUST print the outcome,
  the snapshots involved, per-source revision changes, gate results and timings.
- **FR-009**: Overlapping refresh runs MUST be refused at once (outcome `busy`), and refresh MUST
  respect the existing single-writer ingest lock.
- **FR-010**: Refresh MUST record its latest outcome (time, outcome, reason, snapshot IDs, export
  validators, time of the last successful refresh) in one small state file that is replaced, not
  appended, on every run except `busy` (which writes nothing, so it cannot hide the running job's
  result); an unchanged run MUST NOT create any other new file.
- **FR-011**: `doctor` MUST report the latest refresh outcome: "not run" as information, `held` or
  `failed` as a warning, never as a failure that changes `doctor`'s exit code.
- **FR-012**: `serve` MUST NOT start, schedule or perform refresh or any upstream network access;
  a running server MUST serve a newly activated snapshot from the next request on, without restart.
- **FR-013**: The repository MUST ship opt-in user-level timer units (default interval 15 minutes
  with a small randomized delay) and documented install/enable/disable steps; nothing is installed
  or enabled automatically.
- **FR-014**: Refresh MUST NOT log question/answer bodies or document text; its output carries
  source IDs, revisions, counts and reasons only.
- **FR-015**: Gate thresholds and the export check MUST be configurable through the schema-validated
  app configuration with safe defaults; unknown keys are rejected.
- **FR-016**: Refresh MUST build in the active snapshot's mode (semantic or keyword-only; semantic
  when nothing is active); `--lexical-only` forces keyword-only. An unavailable embedding runtime
  during a semantic refresh MUST end `failed`, not in a keyword-only activation.
- **FR-017**: The promotion gate MUST NOT run the retrieval, answer or comparison evaluation suites
  (they remain manual); refresh status MUST NOT be added to the HTTP API or web UI in this feature.

### Key Entities

- **Refresh run**: one execution; outcome, start/end time, per-step timings, reason.
- **Refresh state**: the latest run's outcome plus export validators (ETag/Last-Modified per export
  source), the last successful refresh time and the active snapshot at that time.
- **Upstream check result**: per source: unchanged / changed / unknown, with the resolved commit or
  validator.
- **Gate result**: per check: pass/fail with measured values and thresholds.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After an upstream documentation change, one refresh run makes the change searchable;
  with the timer enabled at its default interval, the active snapshot trails upstream by at most one
  interval plus one build time.
- **SC-002**: An unchanged refresh run completes in under 10 seconds on the reference machine and
  creates no new files other than replacing the state file.
- **SC-003**: In fixture tests, 100 % of the gate-failing updates (coverage drop, exact-ID miss, lost
  semantic search, required source failure) leave the previous snapshot active.
- **SC-004**: Requests served during an activation by refresh cite only their original snapshot
  (0 isolation violations in the concurrency test).
- **SC-005**: A real refresh against upstream S-CORE on the reference machine moves the active
  snapshot to the current upstream commits, and an immediate second run reports "up to date".

## Assumptions

- Refresh is "operator-invoked preparation" under constitution Principle I: the operator runs it by
  hand or explicitly installs and enables the timer; `serve` never does it. No constitution amendment
  is needed.
- "Real time" is not achievable without a public webhook endpoint, which conflicts with the loopback
  default and the deferred public profile (F010); periodic polling is the accepted approximation.
- Automatic activation is an operational convenience, not an engineering review or approval
  (Principle XII). The gate detects broken builds, not subtle content changes; every answer still
  names its snapshot, and rollback stays available.
- Containers: the app image has no git and the bundled runtime has no host port, so automatic
  refresh in containers is out of scope. Operators refresh natively and restart/re-point the
  containers' data directory, or wait for a later feature.
- Linux with systemd user sessions is the documented scheduler; cron is mentioned as an
  alternative but not tested.
- Retention behaviour on activation is unchanged (F003); refresh does not add new deletion rules.
