<!--
Sync Impact Report
- Version change: template (unversioned) → 1.0.0
- Rationale: initial ratification; all principles derived from docs/PROJECT_SPEC.md §3.
- Principles defined (12):
  I. Local Operation Is a Product Invariant
  II. Evidence Precedes Assertions
  III. Snapshots Are Explicit
  IV. Documentation Is Untrusted Input
  V. Read-Only Assistance
  VI. Modular Monolith First
  VII. Honest Verification
  VIII. Privacy by Default
  IX. Spec-First Increments
  X. Public Deployment Is a Separate Operating Profile
  XI. Licenses Follow Artifacts
  XII. No Implied Authority
- Added sections: Technology & Security Constraints; Development Workflow & Quality Gates; Governance
- Removed sections: none (template placeholders replaced)
- Templates:
  ✅ .specify/templates/plan-template.md — generic "Constitution Check" gate; no edit required,
     plans MUST enumerate principles I–XII (see Governance).
  ✅ .specify/templates/spec-template.md — compatible; master requirement IDs are carried in
     functional requirements (see Development Workflow).
  ✅ .specify/templates/tasks-template.md — compatible; test tasks are mandatory for this project
     per Principle VII (overrides the template's "tests optional" note).
  ✅ .claude/skills/speckit-*/SKILL.md — no outdated agent-specific references requiring change.
  ✅ CLAUDE.md / AGENTS.md — created referencing this constitution.
- Deferred TODOs: none.
-->

# S-CORE Docs Assistant Constitution

## Core Principles

### I. Local Operation Is a Product Invariant

Required runtime functionality (search, chat, source inspection, export) MUST NOT depend on
a paid service, API key, vendor login, or cloud inference. A cloud or paid provider MUST NEVER
appear in a fallback chain. Network access is permitted only for operator-invoked preparation
(install, model acquisition, source sync); the serve path MUST make no external calls.

*Rationale*: the product promise is a free, offline-capable local assistant.

### II. Evidence Precedes Assertions

Every S-CORE factual assertion MUST cite evidence from the selected corpus snapshot. Citations
and URLs MUST be assembled from stored provenance, never from model output. "Insufficient
evidence", "partial" and "clarification needed" are valid, first-class results. The system MUST
NOT substitute general model knowledge for missing evidence.

### III. Snapshots Are Explicit

Every answer is bound to exactly one snapshot unless comparison mode is explicitly requested.
Source commit SHAs, content hashes, parser/chunker versions and embedding model identities
MUST be recorded and validated. Snapshots are immutable once validated; activation and rollback
are atomic.

### IV. Documentation Is Untrusted Input

Source content MUST NEVER be executed, imported as configuration, rendered as raw HTML, or
promoted to a privileged prompt. Ingestion MUST NOT run repository scripts, Sphinx `conf.py`,
directives, Git hooks, or template expressions. Path containment, size limits and include-depth
limits are mandatory.

### V. Read-Only Assistance

The question-answering path MUST NOT run commands, edit repositories, install dependencies,
change settings, or approve engineering work. No tools or function-execution capabilities are
passed to the model. Commands found in documentation remain inert text.

### VI. Modular Monolith First

Responsibilities are separated by explicit interfaces (`SourceAdapter`, `DocumentParser`,
`EmbeddingProvider`, `GenerationProvider`, `SearchIndex`, `SnapshotStore`) inside one deployable
application. Domain records MUST NOT depend on FastAPI or Ollama types. New infrastructure
(queues, vector databases, orchestration, extra services) requires an ADR with measured evidence.

### VII. Honest Verification

Mocked tests, real-model evaluation, human review and measured benchmarks MUST be reported as
distinct categories. An unrun check is "not run", never "passed". Every feature ships with
automated tests for its externally observable behavior and failure modes; tests are not optional.
Thresholds MUST NOT be lowered silently; a miss requires improvement or a recorded scoped decision.

### VIII. Privacy by Default

No telemetry, analytics, crash upload, or remote inference. Question/answer bodies MUST NOT be
logged by default. Chats are held in client memory only; persistence and exports are explicit
user actions. Diagnostic output MUST redact secrets.

### IX. Spec-First Increments

Every feature has a spec, plan, tasks, and traceable verification before it is declared complete.
Master requirement IDs (e.g. `LOC-001`) MUST be preserved in feature artifacts and in
`docs/TRACEABILITY.md`; no requirement may disappear when features are split.

### X. Public Deployment Is a Separate Operating Profile

The default profile binds to loopback and validates Host/Origin. Any remote-exposed mode MUST be
rejected unless the public profile and its access-control, quota and capacity gates are
configured and passed. Local v1.0 does not imply public readiness.

### XI. Licenses Follow Artifacts

Provenance, copyright notices and license records for source documents, models and dependencies
MUST be preserved. Unknown licensing blocks redistribution of the affected artifact.

### XII. No Implied Authority

The assistant is a community tool. It MUST NOT claim Eclipse/S-CORE endorsement, ISO 26262
qualification, certification, release approval, or exhaustive work-product coverage. It MUST NOT
offer approval buttons, ASIL assignment, or automatic sign-off.

## Technology & Security Constraints

- Backend: Python 3.12, FastAPI, Pydantic. Frontend: TypeScript, React, Vite, served as a static
  build by the backend. Local inference: Ollama. Retrieval: SQLite FTS5 plus NumPy exact cosine.
  Changes to these baseline decisions require an ADR under `docs/adr/`.
- Default bind is `127.0.0.1`; Host and Origin validation, strict CORS, and cross-origin protection
  for costly/state-changing requests are mandatory in every profile.
- Configuration is schema-validated, rejects unknown keys, and follows precedence: built-in safe
  defaults < config file < documented environment overrides < CLI flags.
- Dependencies (Python and frontend) are locked and checked in CI. No runtime asset is fetched from
  a public CDN. No pickle or other executable deserialization of corpus data.
- Concurrency, queue size, request size and deadlines are bounded in every profile.

## Development Workflow & Quality Gates

- Workflow per feature (Spec Kit 0.14.0, Claude integration): specify → clarify → plan →
  checklist → tasks → analyze → implement → converge. Agent-performed requirement reviews MUST be
  labelled as agent reviews and MUST NOT masquerade as human approval.
- A task is complete only when its verification has actually run and passed; planned checks do not
  count.
- Definition of done (per feature): artifacts consistent; every assigned requirement verified or
  explicitly open; no open critical security, provenance, snapshot-isolation or fabricated-citation
  issue; docs and quickstart match real commands; traceability and backlog updated; converge clean.
- CI on every change: format, lint, type check, deterministic tests, contract tests, frontend build
  (when present), dependency/license checks. CI MUST NOT require paid APIs or large model downloads.
- Real-model evaluation runs only on a documented prepared environment; missing GPU means "not run".

## Governance

This constitution supersedes other practices in this repository. `docs/PROJECT_SPEC.md` is the
product baseline; where it and this constitution conflict, the constitution wins until amended.

- **Amendments**: proposed via a pull request that edits this file, states the rationale, updates
  the Sync Impact Report, and updates dependent templates, `CLAUDE.md`, and affected feature
  artifacts. Changes affecting local-only behavior, source authority, privacy, citation integrity,
  external services, or public exposure require explicit project-owner approval.
- **Versioning**: semantic versioning. MAJOR for removing or redefining a principle; MINOR for a
  new principle or materially expanded guidance; PATCH for clarifications.
- **Compliance review**: every `plan.md` includes a Constitution Check listing principles I–XII
  with pass/violation status; violations require a Complexity Tracking justification. Every
  `/speckit-analyze` run treats constitution conflicts as CRITICAL. Runtime guidance for coding
  agents lives in `CLAUDE.md` (with `AGENTS.md` as a pointer for other agents).

**Version**: 1.0.0 | **Ratified**: 2026-09-27 | **Last Amended**: 2026-09-27
