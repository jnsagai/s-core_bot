# Feature Specification: F007 Explicit Snapshot Comparison

**Feature Branch**: `007-version-comparison`

**Created**: 2026-09-29

**Status**: Draft

**Input**: User description: "F007 from docs/PROJECT_SPEC.md §16: Explicit snapshot comparison.
Primary requirements RET-006, ANS-005, ANS-007, SRC-003. Scope: two-snapshot retrieval contract,
separately labeled evidence, missing-coverage semantics, comparison UI, ten-case comparison
benchmark. Acceptance: no implicit version mixing; deletion is not claimed when coverage is
missing; conflicting release/source metadata is visible; exports retain both snapshot identities."

**Master requirements covered**: RET-006, ANS-005, ANS-007, SRC-003 (primary); RET-005 (a
comparison is the only way to use two snapshots); master spec §10.1 (`POST /api/v1/compare` and
the comparison contract), §13 (version-comparison suite of at least 10 cases), goal G-03.
Acceptance tests AT-03, AT-10 and AT-17.

**Input from F003–F006**: immutable snapshots with per-source revisions and revision status (F003),
snapshot-pinned search and exact-ID lookup (F004), the validated answer pipeline with a single
generation slot (F005), and the local web UI with snapshot selector and export (F006).

## Clarifications

### Session 2026-09-29

Resolved autonomously by the agent (agent review, not an approval) from `docs/PROJECT_SPEC.md`
and F001–F006 precedent, at the project owner's standing instruction to be fully autonomous; see
`docs/ASSUMPTIONS.md`. The owner may override any answer.

- Q: How is a comparison answer produced — one model call over both snapshots' evidence, or
  separate per-snapshot answers plus a comparison step? → A: separate per-snapshot answers
  first, each produced by the existing validated single-snapshot pipeline on its own pinned
  snapshot, then one comparison step that sees both sides' evidence under side-namespaced IDs
  (`L1…`, `R1…`) and returns typed differences. Deterministic comparisons (snapshot metadata,
  exact requirement records) are computed without the model. Basis: master spec §10.1 requires
  `left`/`right` to be ordinary envelopes bound to their snapshots; reusing the validated pipeline
  keeps F005's guarantees, and no single envelope ever mixes versions.
- Q: May a comparison ever claim that something was removed or deleted? → A: no. When an item is
  present on one side and not found on the other, the difference is `not_established`, with the
  coverage reason (source missing from that snapshot, source failed or partial there, or simply
  not found in the retrieved evidence). Difference text that asserts removal, deletion or "no
  longer" is rejected by validation. Basis: AT-17 and the F007 acceptance "deletion is not
  claimed when coverage is missing". Retrieval cannot prove absence even when coverage is
  complete, so the rule is unconditional.
- Q: What counts as a "release label", and when may one be shown (SRC-003)? → A: the application
  shows per-source revisions (commit or export hash, with revision status) for both snapshots and
  never infers a product release label. A label is shown only when the snapshot data carries
  evidenced release metadata; no current source provides it, so none is shown and the UI says
  that per-source revisions are the identity. Metadata conflicts are surfaced, never resolved
  silently: identical revisions on both sides, a source present in only one snapshot, `unverified`
  export revisions, failed or partial sources, and different embedding or chunker identities.
- Q: Does comparison support follow-ups or conversation history (ANS-007)? → A: no. A comparison
  request is stateless and takes no history. Its result can be exported, and the chat keeps its
  own single-snapshot binding. Switching from comparison back to chat starts a new evidence
  context. Basis: bounded context and the master rule that a snapshot change starts a new
  evidence context. Multi-turn comparison is not in the F007 scope.
- Q: How are generation resources shared? → A: a comparison holds the single generation slot for
  its whole duration (both sides plus the comparison step), under one deadline that is twice the
  single-answer deadline. It uses the same bounded queue as chat, so chat and comparison can
  never run model calls in parallel.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Compare how two snapshots answer a question (Priority: P1)

A contributor wants to know how guidance on a topic differs between two documentation snapshots
(for example, an older and a newer revision of the process description). They pick two snapshots
explicitly, ask one question, and see two clearly labelled answers, one per snapshot, each with
its own citations, plus a list of typed differences that point to evidence on each side.

**Why this priority**: this is the core of the feature and the only sanctioned way to use more
than one snapshot (RET-005, RET-006).

**Independent Test**: with two fixture snapshots whose content differs, one comparison request
returns a left answer citing only left-snapshot chunks, a right answer citing only right-snapshot
chunks, and differences whose evidence IDs resolve to the correct side.

**Acceptance Scenarios**:

1. **Given** two queryable snapshots with different content for a topic, **When** the user
   compares them for a question on that topic, **Then** the result contains a left answer bound
   to the left snapshot, a right answer bound to the right snapshot, and at least one `changed`
   difference with evidence IDs from both sides.
2. **Given** the same comparison, **When** any citation is inspected, **Then** it carries its
   own snapshot ID, and no left citation references a right-snapshot chunk or the reverse (AT-03).
3. **Given** a comparison request naming the same snapshot twice, or only one snapshot, **When**
   it is submitted, **Then** it is rejected as invalid; a comparison always names exactly two
   different snapshots.
4. **Given** a snapshot is activated or retired while a comparison runs, **When** it finishes,
   **Then** both sides still use the snapshots named in the request (both stay pinned).

---

### User Story 2 - Missing coverage is reported as unknown, never as deletion (Priority: P1)

A reviewer compares an older snapshot that lacks a source (or where a source failed) with a newer
one. For content that exists only on one side, they need an honest "not established" statement
with the reason, not a false claim that the content was removed or added.

**Why this priority**: a false deletion claim is the most harmful comparison error (AT-17), and
missing coverage is common (optional export sources, failed syncs, different selectors).

**Independent Test**: a fixture where the left snapshot lacks a source that the right has: the
comparison reports `not_established` with a coverage reason for right-only content, and no
difference text contains removal or deletion wording.

**Acceptance Scenarios**:

1. **Given** the left snapshot lacks source S and the right snapshot has it, **When** the user
   asks about content from S, **Then** the difference is `not_established` with the reason
   "source S is not in the left snapshot".
2. **Given** both snapshots include S but a requirement ID is found only on the right, **When**
   the user asks about that ID, **Then** the difference is `not_established` ("not found in the
   left snapshot's records"), never "added" or "removed".
3. **Given** the model drafts a difference saying an item "was removed", **When** it is validated,
   **Then** the draft is rejected and the item is reported as `not_established`.
4. **Given** one side has no evidence at all for the question, **When** the comparison completes,
   **Then** that side's answer is `insufficient_evidence` and every difference is
   `not_established`.

---

### User Story 3 - Snapshot identity and metadata conflicts are visible (Priority: P2)

Before trusting a comparison, a user wants to see exactly what is being compared: per-source
revisions of both snapshots, which sources differ, which are unchanged, which are missing on a
side, and which revisions are unverified, without any invented release label.

**Why this priority**: SRC-003 and the acceptance "conflicting release/source metadata is
visible". It also explains many `unchanged` or `not_established` results.

**Independent Test**: comparing two fixture snapshots returns a metadata comparison listing each
source as `same`, `different`, `left_only` or `right_only`, with revisions and statuses, plus a
warning when every revision is identical.

**Acceptance Scenarios**:

1. **Given** two snapshots, **When** compared, **Then** a per-source table shows both revisions,
   both revision statuses and a relation (`same`, `different`, `left_only`, `right_only`).
2. **Given** all source revisions are identical, **When** compared, **Then** the result warns that
   the documentation content is the same and that differences can only come from processing or
   retrieval, and it shows no `changed` difference unless it cites differing evidence.
3. **Given** a source whose revision is `unverified` (an export without a commit identity),
   **When** compared, **Then** it is flagged as unverified and not presented as pinned.
4. **Given** no release label is evidenced, **When** the comparison is shown, **Then** no product
   release name appears; identity is given by per-source revisions only.

---

### User Story 4 - Compare in the web UI and export with both identities (Priority: P2)

A contributor uses a Compare screen in the local web UI: two snapshot pickers, a question field,
progress, stop, two side-by-side labelled answers, differences with type labels and per-side
citations, the metadata table, and Markdown/JSON export that retains both snapshot identities.

**Why this priority**: the comparison UI and export are in F007 scope; the backend is usable from
the CLI without it.

**Independent Test**: component tests drive the Compare screen with a mocked comparison stream
and verify labelling, keyboard access, citation opening per side, and export content.

**Acceptance Scenarios**:

1. **Given** the Compare screen, **When** the user picks the same snapshot on both sides, **Then**
   submission is disabled with an explanation.
2. **Given** a completed comparison, **When** rendered, **Then** each answer is headed with its
   side and snapshot ID, and each difference shows its type and evidence links opening the
   correct side's excerpt.
3. **Given** a completed comparison, **When** exported as Markdown or JSON, **Then** the export
   contains the question, both snapshot IDs, per-source revisions, both answers, all differences
   with side-labelled evidence, the model identity, and no absolute local path.
4. **Given** a running comparison, **When** the user presses Stop, **Then** the request is
   aborted and the generation slot is released.

---

### User Story 5 - Measure comparison quality on ten cases (Priority: P3)

A maintainer runs a comparison benchmark of at least ten cases over two real snapshots and gets a
report of difference-type agreement, side isolation, citation integrity and forbidden deletion
claims. It is labelled a development measurement until the cases are reviewed.

**Why this priority**: the master spec requires a version-comparison suite by this milestone, but
the feature is usable before the suite is measured.

**Independent Test**: running the evaluation with a fake generation provider over fixture
snapshots produces a report with all metrics; a real run over two real snapshots is recorded in
`verification.md`.

**Acceptance Scenarios**:

1. **Given** a case file with ≥ 10 cases (including missing-coverage and unchanged cases),
   **When** the evaluation runs, **Then** the report lists per-case expected and observed
   difference types, side-isolation violations (must be 0), citation integrity, and deletion-claim
   count (must be 0).
2. **Given** the case file is not marked reviewed, **When** the report is produced, **Then** it is
   labelled "development measurement, not release evidence".

---

### Edge Cases

- Either snapshot is unknown, failed, deleted or not queryable → 404/409 before any model call.
- Snapshots have incompatible embedding identities → each side degrades to keyword search
  independently, with a per-side warning; the comparison still runs.
- The generation model is unavailable → the comparison endpoint returns `GENERATION_UNAVAILABLE`
  like chat; the metadata comparison stays available separately without generation (a
  snapshot-diff endpoint and CLI), so users can still see both identities.
- The comparison step's output fails validation and its one repair fails → differences fall back
  to deterministic observations only (metadata, exact records, per-side evidence presence), with
  a warning. No unvalidated difference is ever returned.
- One side's answer uses the extractive fallback → the comparison still runs on that side's
  evidence and labels the side as fallback.
- The question contains a requirement ID → exact records are compared deterministically: same
  content → `unchanged`, different content → `changed` with both records cited, present on one
  side only → `not_established` with the coverage reason.
- Evidence text on either side contains injection → the F005 injection handling applies per side,
  and the comparison step applies the same policy rules to both evidence sets.
- The request is cancelled or the client disconnects → the slot is released within 2 s, as for
  chat.
- The queue is full → 429, as for chat.

## Requirements *(mandatory)*

### Functional Requirements

**Comparison contract (RET-005, RET-006, master §10.1)**

- **FR-001**: The system MUST accept a comparison request naming exactly two different snapshot
  IDs (`left_snapshot_id`, `right_snapshot_id`) and a question, and MUST reject requests with a
  missing, identical or unqueryable snapshot, history, or unknown fields.
- **FR-002**: Both snapshots MUST be pinned for the whole request; activation, retirement or
  deletion during the request MUST NOT change which snapshot either side uses.
- **FR-003**: The response MUST contain `left` and `right` answer envelopes, each an ordinary
  single-snapshot envelope bound to its own snapshot, with citations only from that snapshot.
  A mixed-version answer MUST NOT appear inside a single-snapshot envelope.
- **FR-004**: The response MUST contain `differences`, each with a type from {`changed`,
  `unchanged`, `conflicting`, `not_established`}, a statement, `left_evidence_ids` and
  `right_evidence_ids` that resolve to the corresponding side's citations, and an origin
  (`model`, `exact_record`, `coverage`).
- **FR-005**: `changed`, `unchanged` and `conflicting` differences MUST cite evidence on both
  sides. A `not_established` difference MUST state the coverage reason: source absent from a
  snapshot, source failed or partial in a snapshot, record not found, or no evidence retrieved.
- **FR-006**: No difference statement MAY assert removal, deletion, or addition as a fact about
  the documentation. Validation MUST reject such wording, and absence on one side MUST be
  reported as `not_established`. The rule applies to differences only; each side's own answer
  follows F005 rules and may quote documentation that uses such words.
- **FR-007**: Conflicting evidence (ANS-005) — excerpts on the two sides whose guidance on the
  same point is mutually exclusive (one requires what the other forbids or replaces) — MUST be
  reported as `conflicting` with both sides' evidence, without choosing which is correct or
  current. Any other difference in content is `changed`. Neither type implies which snapshot is
  newer or authoritative; the UI shows each snapshot's creation time and revisions instead.
- **FR-008**: The comparison step MUST see both sides' evidence only under side-namespaced IDs
  (`L1…`, `R1…`) in separately delimited blocks, under the same untrusted-data policy as F005, and
  its output MUST be validated (schema, evidence membership per side, type/evidence rules,
  forbidden wording) with at most one repair. If the repaired output is still invalid but
  structurally sound, only the differences that individually pass every check are kept and the
  number dropped is reported in a warning; otherwise only deterministic differences are returned,
  with a warning. (Amended after the first real runs, A-043.)

**Deterministic comparisons (SRC-003, RET-006)**

- **FR-009**: The response MUST include a snapshot metadata comparison: for each source in
  either snapshot, both revisions, both revision statuses and statuses, and a relation (`same`,
  `different`, `left_only`, `right_only`), plus differing processing identities (chunker,
  embedding model). No product release label MAY be inferred.
- **FR-010**: The response MUST warn when all shared source revisions are identical, when a
  source is present on only one side, and when a compared revision is `unverified`.
- **FR-011**: When the question names requirement IDs that exact lookup recognizes, the system
  MUST compare those records across the two snapshots deterministically and report each as
  `unchanged`, `changed` or `not_established` with its coverage reason.
- **FR-012**: A snapshot metadata comparison MUST be available without generation, over HTTP
  and the CLI, so identities can be inspected while the model is unavailable.

**Execution (F005 parity)**

- **FR-013**: A comparison MUST hold the single generation slot for its whole duration, use the
  shared bounded queue (429 when full), run under one deadline, and release its slot within 2 s of
  cancellation or client disconnect.
- **FR-014**: The comparison endpoint MUST support a JSON response and an SSE stream with
  `progress` (stage and side), `comparison`, `error` and `done` events; no claim or difference
  text is sent before validation completes.
- **FR-015**: Comparison requests MUST be stateless and take no history (ANS-007). The chat's
  single-snapshot binding MUST remain unchanged by comparisons.
- **FR-016**: Question and answer text MUST NOT be logged; the existing guard, loopback-only
  runtime and no-download rules apply unchanged.

**CLI and UI (UX, F006 parity)**

- **FR-017**: The CLI MUST offer `compare "QUESTION" --left ID --right ID [--json]
  [--show-evidence]` and `snapshots diff LEFT RIGHT [--json]` (metadata only, no model).
- **FR-018**: The web UI MUST offer a Compare screen with two snapshot pickers listing the
  queryable snapshots (defaults: right = the active snapshot, left = the most recently created
  other queryable snapshot; the same snapshot on both sides is not allowed; with fewer than two
  queryable snapshots the screen explains how to build one), progress with side, Stop, side-labelled answers, differences
  with type labels and evidence links that open the correct side's excerpt, the metadata table,
  and keyboard and screen-reader access equivalent to F006.
- **FR-019**: Comparison export (Markdown and JSON) MUST retain the question, both snapshot IDs,
  per-source revisions of both sides, both answers, all differences with side-labelled evidence,
  and the model identity, and MUST NOT contain absolute local paths or credentials.

**Evaluation (master §13)**

- **FR-020**: The system MUST provide `eval comparison --cases FILE --left ID --right ID` over a
  committed case file of ≥ 10 cases, including ≥ 2 missing-coverage cases, ≥ 2 unchanged cases
  and ≥ 1 exact-ID case. The report MUST include difference-type agreement, side-isolation
  violations, citation integrity and deletion-claim count, and MUST be labelled a development
  measurement unless the case file is marked reviewed.

### Key Entities

- **ComparisonRequest**: question, left snapshot ID, right snapshot ID, response language.
- **ComparisonResult**: request ID, question, left and right answer envelopes, differences,
  metadata comparison, model identity, warnings, timings, schema version.
- **Difference**: type, statement, left evidence IDs, right evidence IDs, origin, coverage reason.
- **SnapshotDiff**: left and right snapshot IDs, per-source relation rows, processing identity
  differences, warnings.
- **ComparisonCase**: ID, question, category, expected difference types, expected coverage
  reason (optional), reviewed flag at file level.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In 100% of comparison test cases, every left citation references a left-snapshot
  chunk and every right citation a right-snapshot chunk (zero side-isolation violations), in both
  fixture tests and the real benchmark.
- **SC-002**: In 100% of missing-coverage fixture and benchmark cases, no difference statement
  asserts removal, deletion or addition; the relevant items are `not_established` with a reason.
- **SC-003**: 100% of comparison exports contain both snapshot IDs, per-source revisions of both
  sides and the model identity, and zero absolute local paths.
- **SC-004**: The metadata comparison reports every source present in either snapshot with the
  correct relation in 100% of fixture cases, including identical, left-only, right-only and
  unverified revisions.
- **SC-005**: A benchmark of ≥ 10 comparison cases over two real snapshots is run and its
  difference-type agreement, citation integrity, isolation and deletion-claim results are
  recorded (development measurement until reviewed).
- **SC-006**: A warm comparison of one question over two snapshots completes within 3× the
  measured single-answer time on the reference workstation, and within the comparison deadline.

## Assumptions

- Two real snapshots with different content are needed for the benchmark. The current local
  snapshots all share the same revisions, so an older baseline snapshot is built from pinned
  older upstream commits with `sources sync` (network, allowed outside the serve path) and
  `index build` (not activated). Published needs exports exist only for `main`, so the baseline
  omits them. This produces a real missing-coverage case for requirement records.
- The existing snapshot retention rules still apply; building a baseline snapshot must not
  delete the active snapshot or its rollback target (A-023), which is checked before building.
- The comparison deadline defaults to 2 × the single-answer deadline; it is a configuration value.
- F006's snapshot selector and chat remain single-snapshot. The Compare screen is a separate tab.
- The benchmark cases are authored by the agent from the two real snapshots and are unreviewed
  (development measurement) until the owner reviews them.
