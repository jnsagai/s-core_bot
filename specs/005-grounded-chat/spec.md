# Feature Specification: F005 Grounded Local Answers

**Feature Branch**: `005-grounded-chat`

**Created**: 2026-09-28

**Status**: Draft

**Input**: User description: "F005 from docs/PROJECT_SPEC.md §16: Grounded local answers. Scope:
local chat adapter, capability/model identity checks, bounded context, structured claims,
citations, conflict/abstention behavior, request queue, deadlines, cancellation, follow-ups,
progress stream, no cloud fallback. Acceptance: real local runtime answers covered questions; fake
citations and malformed results fail safely; blocked-egress run succeeds; model outage preserves
search; injection fixtures do not override policy; factual quality is measured, not inferred from
valid JSON."

**Master requirements covered**: ANS-001 to ANS-012, RET-005, LOC-002, SEC-001, OPS-006
(primary); OPS-001 (no answer bodies in logs), UJ-02, UJ-04, UJ-06 (JSON export of an answer),
master spec §5.2 serving sequence, §7.2 context budget, §7.3 answer schema, §10.1 chat contract
and SSE framing, §13.3 citation integrity, safe handling of unsupported cases, injection resistance.
Acceptance tests AT-01, AT-02 (search when generation is unavailable), AT-05, AT-06, AT-09, AT-10,
AT-12 (answer level), AT-14.

**Input from F004**: `SearchService` evidence (pinned snapshot, ranked chunks with provenance,
degraded-mode reasons) and the evidence endpoints. F005 adds generation on top and never changes
retrieval or snapshots.

## Clarifications

### Session 2026-09-28

Resolved autonomously by the agent (agent review, not an approval) from `docs/PROJECT_SPEC.md` and
F001–F004 precedent at the project owner's request ("be fully autonomous"); see
`docs/ASSUMPTIONS.md` A-029. The owner may override any answer.

- Q: When the model output fails validation twice, typed failure or extractive fallback? → A:
  extractive fallback whenever at least one evidence item exists (status `partial`, origin
  `extractive_fallback`, verbatim excerpts, warning). A typed `answer_invalid` error only when no
  fallback can be built. Basis: §5.2 step 9, §7.3; the fallback is honest and still useful.
- Q: How does a client choose streaming? → A: `Accept: text/event-stream` gets SSE; any other
  Accept gets one JSON body. Basis: §10.1 "fetch-readable server-sent-event framing over POST".
- Q: What query is used for retrieval on a follow-up? → A: the new question plus the most recent
  prior *user* turn (never assistant text), bounded by the question character limit. Basis:
  ANS-007; assistant text is model output and must not steer evidence selection.
- Q: What bounds history, and how is its snapshot binding known? → A: at most 10 turns and the
  existing `limits.history_characters` (12 000). Assistant turns carry the `snapshot_id` they were
  answered from; an assistant turn without it, or with a different one, is excluded together with
  the user turn it answered, and the new-evidence-context warning is given. Basis: ANS-007
  (fail-safe when binding is unknown).
- Q: What does the quoted-string consistency check cover? → A: text inside double quotes or
  backticks of at least 12 characters must appear verbatim (after whitespace normalization) in at
  least one excerpt cited by that claim. Shorter quotes are not checked. Basis: §7.3; avoids false
  failures on short tokens like `"id"`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ask a documentation question and get a cited answer (Priority: P1)

A developer asks a question about S-CORE ("Which work products does the architecture process
require?"). The assistant retrieves evidence from one selected snapshot, asks the local model for
a structured answer, checks it, and returns short statements. Each statement is labelled as
documented fact, interpretation or limitation, and every documented statement carries citations.
Each citation opens the exact stored excerpt with source, file, revision, lines and, where it can
be proven, an immutable upstream link. The response names the snapshot, the generation model and
its digest, the answer status and any warnings.

**Why this priority**: this is the product's core promise (UJ-02). Everything else in F005
protects or operates it.

**Independent Test**: with a fake generation provider returning scripted structured outputs,
covered questions produce `answered` responses whose citations all resolve to the pinned
snapshot's stored excerpts. With the real local model, a set of covered questions produces cited
answers (measured, not assumed).

**Acceptance Scenarios**:

1. **Given** an active snapshot and a running generation model, **When** the user asks a covered
   question, **Then** the response has status `answered`, at least one `documented` claim, every
   documented claim cites one or more evidence IDs from the evidence supplied for this request,
   and every citation includes snapshot, chunk, source, revision, path, lines and the stored
   excerpt.
2. **Given** a git source at a pinned revision, **When** a citation is built, **Then** its immutable
   link points to that exact revision and file (with line anchors when lines are known). An export
   source, or any source whose revision cannot be proven, gets no immutable link and is labelled
   `unverified`.
3. **Given** a claim that paraphrases a documented obligation, an example or a proposal, **When** it
   is returned, **Then** the kind shows whether it is documented fact, the assistant's
   interpretation or a limitation, and interpretations cite the evidence they rest on.
4. **Given** evidence containing commands or code, **When** the answer quotes it, **Then** it is
   returned as inert text with its applicability context (file, section), and nothing is executed.
5. **Given** a completed answer, **When** the user requests it as JSON, **Then** the export contains
   the question, claims, citations, snapshot ID and model identity, and no machine-specific
   absolute paths or credentials.

---

### User Story 2 - Get honest results when evidence is weak, conflicting, hostile or the model misbehaves (Priority: P2)

A user asks something the documentation does not cover, or where two sources disagree, or where
retrieved text contains instructions aimed at the assistant. Or the model returns malformed
output, invents citations or is not running. In every case the user gets an honest, clearly
labelled outcome instead of a confident fabrication. The status is insufficient evidence, partial,
or clarification needed with explicit gaps; conflicts are shown with both sources; a visible
failure is returned; or search results still work without an answer.

**Why this priority**: safety and trust (ANS-004, ANS-005, ANS-009, ANS-010, ANS-012). A wrong
confident answer is worse than none for engineering documentation.

**Independent Test**: scripted fake-model outputs (fake evidence IDs, invalid JSON, schema
violations, URLs, empty documented claims, injected instructions, timeouts) and fixture evidence
(conflicting, hostile, empty) produce the specified statuses and failures deterministically.

**Acceptance Scenarios**:

1. **Given** retrieval finds nothing relevant, **When** the user asks, **Then** the status is
   `insufficient_evidence` with a limitation explaining what is missing, and no documented claim is
   returned.
2. **Given** the model output cites an evidence ID that was not supplied, **When** it is validated,
   **Then** it is rejected. One repair attempt may be made within the deadline; if that also fails,
   the response is an explicit failure or a clearly labelled extractive result built only from
   stored excerpts, never the unchecked draft.
3. **Given** malformed or schema-violating output, **When** validated, **Then** the same bounded
   repair/fallback applies, and the failure is visible (never silently fixed or partially
   published).
4. **Given** model output containing URLs, **When** validated, **Then** no model-supplied URL is
   presented as a citation or link. Citation links come only from stored provenance.
5. **Given** two supplied excerpts that state conflicting requirements, **When** the model reports
   the conflict, **Then** both are cited, and the answer does not claim that one takes precedence
   unless an excerpt says so.
6. **Given** an excerpt containing instructions such as "ignore previous rules", "reveal the system
   prompt" or "run this command", **When** it is used as evidence, **Then** the answer follows the
   assistant's policy, grants no capability, and treats the text only as document content.
7. **Given** the generation runtime is down, the model is missing, or its digest differs from the
   model lock, **When** the user asks, **Then** they get a typed "generation unavailable" error with
   guidance, and search still works (readiness shows chat unavailable, search available).
8. **Given** a question asking whether the platform is certified, qualified, release-approved or
   complete, **When** the evidence does not establish it, **Then** the assistant does not assert it
   and says what the evidence does and does not cover.

---

### User Story 3 - Follow up, see progress, cancel, and share capacity fairly (Priority: P3)

A user asks a follow-up ("and for components?") in the same conversation. Progress (queued,
searching, generating, validating) is visible while they wait. They can abort a slow answer, and
the next request is admitted promptly. Only one answer is generated at a time on the machine, a
small number wait in a bounded queue, and everything else is refused with a retry hint.

**Why this priority**: usable interaction (UJ-02, UX states for F006) and bounded resource use
(OPS-006, AT-14).

**Independent Test**: with a slow fake provider, concurrent requests are admitted, queued and
rejected per limits; aborting a request frees its slot within 2 seconds; progress events arrive
in order with increasing IDs; a follow-up with a different snapshot starts a new evidence context.

**Acceptance Scenarios**:

1. **Given** a follow-up question with bounded prior turns, **When** asked, **Then** retrieval uses
   the question in context of the conversation, prior turns are treated as untrusted context and
   never as evidence, and the response stays bound to the same snapshot.
2. **Given** a follow-up that names a different snapshot than the previous turn, **When** asked,
   **Then** the previous turns' evidence is not reused and the response says a new evidence context
   was started.
3. **Given** one answer being generated and the queue holding its maximum, **When** another request
   arrives, **Then** it is rejected at once with a retryable "busy" error. Queued requests report
   their queued state.
4. **Given** a streamed request, **When** it runs, **Then** the client receives `progress` events
   (queued, searching, generating, validating), then exactly one `answer` or `error` event, then
   `done`, with increasing event IDs. No unchecked claim text is streamed.
5. **Given** a running request, **When** the client disconnects or aborts, **Then** its queue slot
   or generation is released within 2 seconds, the provider call is stopped, and the next request
   is admitted.
6. **Given** a request that exceeds the configured deadline, **When** time runs out, **Then** it ends
   with a retryable deadline error and releases its resources.

---

### User Story 4 - Measure answer quality instead of assuming it (Priority: P4)

A maintainer runs an answer evaluation on a case file against the real local model. They get,
per case and in aggregate, the status (compared with the expected status), citation integrity
(every citation resolves to the snapshot and its stored excerpt), whether cited evidence overlaps
the expected evidence, timing, and a review sheet listing every claim with its cited excerpts for
human support review. Human-judged metrics (factual support precision, required-fact coverage) are
reported as "not run" until a human fills in the review.

**Why this priority**: the backlog acceptance says factual quality must be measured, not
inferred from valid JSON. The release-grade reviewed evaluation is F008.

**Independent Test**: on fixture cases with a fake provider the report is deterministic; with the
real model the report is produced and recorded; human-review fields stay "not run" until filled.

**Acceptance Scenarios**:

1. **Given** a case file with expected statuses and evidence, **When** the evaluation runs, **Then**
   the report lists per case the returned status, the expected status, citation-integrity result,
   cited-evidence overlap with the expected evidence, latency and warnings, plus totals with counts
   by category.
2. **Given** unanswerable cases, **When** evaluated, **Then** the report counts how many were safely
   handled (insufficient evidence, partial with gaps, or clarification) versus answered.
3. **Given** a completed run, **When** the review sheet is produced, **Then** it lists each claim,
   its kind and its cited excerpts, with empty reviewer fields. Human-judged metrics are reported
   as "not run" until those fields are filled.

---

### Edge Cases

- Empty or over-long question (over the configured character limit) → validation error, nothing
  generated.
- History longer than the configured character/turn limit → rejected, not silently truncated.
- Unsupported `response_language` (anything other than `en`) → clear unsupported-language error.
- Retrieval degraded to keyword-only → answer still possible; the degradation appears as a warning,
  not as an answer status.
- Evidence exceeding the evidence budget → fewer or shorter excerpts are supplied (whole excerpts
  dropped from the lowest rank first), never a truncated prompt; the dropped count is reported.
- Model returns valid JSON with zero documented claims but status `answered` → invalid (repair or
  fallback).
- Model returns a documented claim without evidence IDs → invalid.
- Model cites an evidence ID twice or cites the same ID for unrelated claims → allowed (membership
  is checked, not uniqueness).
- Model quotes text in quotation marks that does not appear in any cited excerpt → the quote fails
  the quoted-string consistency check (repair or fallback).
- Model output exceeds the output-token budget → the runtime stops it; the result is malformed
  (repair or fallback), never a partially published answer.
- Model includes hidden-thought content → stripped/refused. Thinking is disabled when the model
  supports turning it off.
- Snapshot activated while an answer is generated → the answer and all citations stay on the
  pinned snapshot.
- Generation model digest differs from the model lock → generation refused as unavailable
  (identity mismatch) with guidance; search unaffected.
- Client sends a chat request from a foreign origin → rejected by the existing guard.
- Two browser tabs streaming at once → each counted separately against the queue.
- Question in the history role "system" or containing a fake system prompt → history is plain
  untrusted text; roles other than user/assistant are rejected.

## Requirements *(mandatory)*

### Functional Requirements

**Answer flow and envelope (ANS-001, ANS-008, RET-005, §5.2)**

- **FR-001**: The system MUST answer a question by: validating the request; resolving and pinning
  one snapshot; retrieving evidence with F004 search (question plus bounded conversation context);
  selecting evidence within the budget; generating a structured draft with the local model;
  validating it; and returning a validated answer envelope. No step may use another snapshot.
- **FR-002**: The answer envelope MUST contain schema version, request ID, status (`answered`,
  `partial`, `insufficient_evidence`, `clarification_needed`), claims, limitations, citations,
  snapshot ID, generation model identity (provider, model tag, digest), retrieval mode and
  warnings, answer origin (`model` or `extractive_fallback`), and timings. Operational failures are
  typed errors, not statuses.
- **FR-003**: Each claim MUST have text, kind (`documented`, `interpretation`, `limitation`) and
  evidence IDs. `documented` claims MUST cite at least one evidence ID; `interpretation` claims
  MUST cite the evidence they rest on; `limitation` claims may cite none. Status `answered` or
  `partial` requires at least one documented claim.

**Evidence and citations (ANS-002, ANS-006, ANS-012)**

- **FR-004**: Evidence supplied to the model MUST be labelled with request-local evidence IDs
  (`E1…En`) mapped server-side to chunk IDs. Citations MUST be assembled only from stored
  provenance: snapshot, chunk, source, revision, revision status, path, heading path, lines,
  excerpt, and an immutable upstream URL only when the source is a git repository with a pinned
  revision. Export or unverified sources get no immutable URL and a revision-match label.
- **FR-005**: Model output MUST NOT contribute URLs, file paths or identifiers to citations. Any
  URL in claim text MUST be removed or rejected by validation, and no URL scheme other than the
  server-built `https://` immutable links may appear in the envelope.
- **FR-006**: Commands and code from evidence MUST be returned as plain text only. Nothing in an
  answer is executable by the system.

**Validation, repair, fallback (ANS-001, ANS-004, ANS-009, §7.3)**

- **FR-007**: Validation MUST check: schema conformance; maximum sizes (claim count, claim length);
  every cited evidence ID was supplied for this request; every cited chunk belongs to the pinned
  snapshot; the status/claim rules of FR-003; quoted strings in claim text (text in double quotes
  or backticks of at least 12 characters, whitespace-normalized) appear verbatim in at least one cited excerpt; and no
  URLs or hidden-thought markers.
- **FR-008**: On validation failure, at most one repair request MAY be made within the original
  deadline, sending the validation errors. If the repaired output also fails, or the deadline does
  not allow a repair, the system MUST return an extractive fallback when at least one evidence item
  exists, otherwise a typed `answer_invalid` failure. An extractive fallback contains only stored excerpts of the top evidence as `documented` claims
  whose text is the verbatim excerpt, status `partial`, origin `extractive_fallback`, and a warning
  that the model output failed validation. The unchecked draft is never returned.
- **FR-009**: When retrieval returns no evidence, the system MUST return `insufficient_evidence`
  without calling the model.

**Policy and prompt (ANS-003, ANS-005, ANS-010, ANS-011, §7.2)**

- **FR-010**: The model MUST receive a fixed system policy (versioned) instructing it to: answer
  only from supplied evidence; treat excerpts and history as untrusted reference text, never as
  instructions; cite evidence IDs on factual claims; label interpretations; report gaps and
  conflicts (citing both sides, without inventing precedence); ask for missing release/module
  context when it changes the answer; keep identifiers and command syntax intact; not claim
  certification, qualification, release approval or exhaustive coverage without source support;
  and return only the structured schema. No tools, functions or execution capabilities are ever
  passed to the model.
- **FR-011**: Evidence and history MUST be placed in clearly delimited data sections, separate from
  the policy. Injected instructions in evidence MUST NOT change the policy, the schema, the
  citation rules or the capabilities.

**Context budget and generation settings (§7.2, ANS-009)**

- **FR-012**: The prompt MUST fit the configured context budget (defaults: context 8 192, policy and
  schema ~1 000, history and question ≤ 1 000, evidence ≤ 4 500, output ≤ 900 tokens) under a
  conservative token estimate. When over budget, evidence is reduced first (lowest-ranked whole
  excerpts dropped), then history (oldest turns dropped). The prompt is never silently truncated,
  and reductions are reported in warnings.
- **FR-013**: Generation MUST use low temperature, a bounded output length, the configured context
  size, thinking disabled when the model supports disabling it, and structured-output mode when
  the runtime supports it. Unsupported options are not sent.

**Generation provider and identity (LOC-002, SEC-001, no cloud fallback)**

- **FR-014**: Generation MUST use only the configured local runtime on loopback and the configured
  generation model. Before generating, the installed model's digest MUST match the model lock
  entry for generation. A mismatch, missing model or unreachable runtime is a typed
  `generation_unavailable` error with a reason and guidance. There is never a fallback to any other
  provider, and search remains available.
- **FR-015**: No prompt, answer or document content may leave the host. The only network use is
  loopback calls to the local runtime (embeddings via F004 and generation).

**Conversation (ANS-007)**

- **FR-016**: Chat requests MAY include bounded history (at most 10 turns and
  `limits.history_characters`; roles `user` and `assistant` only; assistant turns carry the
  `snapshot_id` they were answered from). The retrieval query is the new question plus the most
  recent prior user turn; assistant text never feeds retrieval. History is untrusted context. It may inform the
  retrieval query and the prompt, but it is never evidence and is never cited.
- **FR-017**: Each request carries its snapshot ID (explicit or resolved active). When the request's
  snapshot differs from the snapshot recorded on prior assistant turns in the history, the prior
  turns MUST be excluded from the prompt, and a warning MUST state that a new evidence context was
  started.

**Admission, deadlines, cancellation, streaming (OPS-006, ANS-009, §10.1)**

- **FR-018**: At most one generation MAY run at a time (`limits.active_generations`, 1). At most
  `limits.queued_generations` requests (default 4) MAY wait. Further requests MUST be rejected
  immediately with a retryable busy error (HTTP 429).
- **FR-019**: Every chat request MUST finish within `limits.request_deadline_seconds` (default 120),
  including queueing, retrieval, generation and at most one repair. On expiry it MUST end with a
  retryable deadline error (HTTP 504) and release its resources.
- **FR-020**: Cancellation (client disconnect or abort) MUST release the queue slot or stop the
  provider call and release the generation slot within 2 seconds.
- **FR-021**: `POST /api/v1/chat` MUST return the validated envelope as JSON, or, when the client
  asks for a stream, server-sent events over the POST response: `progress` (stage: `queued`,
  `searching`, `generating`, `validating`, with queue position when queued), exactly one `answer`
  or `error`, then `done`, with increasing event IDs. Clients select streaming with
  `Accept: text/event-stream`. Unchecked claim text is never streamed.
- **FR-022**: Chat requests MUST pass F001's Host/Origin/cross-site protection, reject unknown
  fields (URLs, model names, system prompts, runtime options), and never log question, history or
  answer text.

**Readiness and CLI (LOC-006, §10.2)**

- **FR-023**: Readiness MUST report chat available only when a compatible active snapshot exists
  and the generation model is installed with a digest matching the lock. Otherwise chat is
  unavailable with a reason (the F003/F004 `not_implemented` reason is removed), while search is
  reported independently.
- **FR-024**: The CLI MUST provide `ask "question" [--snapshot ID] [--json] [--show-evidence]` with
  exit codes 0 (an answer envelope of any status), 1 (generation unavailable, deadline, busy, no
  snapshot), 2 (usage error). `ask` never downloads anything.

**Evaluation (§13.3, backlog acceptance)**

- **FR-025**: The CLI MUST provide `eval answers --cases FILE [--snapshot ID]` producing a report per
  case (status vs expected, citation integrity, cited-evidence overlap with expected evidence,
  latency, warnings, answer origin) and aggregates by category with counts. It also produces a
  review sheet (every claim, kind and cited excerpts) with empty reviewer fields. Factual support
  precision and required-fact coverage are reported as "not run" unless the review sheet is
  filled in by a human.
- **FR-026**: An initial answer case file of at least 20 cases MUST be committed, including at least
  5 unanswerable or out-of-scope cases and at least 3 cases whose retrieved evidence contains
  injected instructions (synthetic fixture content in a test snapshot, marked SYNTHETIC). Review
  status is `unreviewed (agent-authored)`.

### Key Entities

- **ChatRequest**: question, snapshot ID (optional), history (bounded turns), response language,
  stream flag.
- **EvidenceItem**: request-local evidence ID mapped to a chunk and its stored provenance/excerpt.
- **Claim**: text, kind, evidence IDs.
- **Citation**: evidence ID plus stored provenance, excerpt, immutable URL (when provable) and
  revision-match label.
- **AnswerEnvelope**: FR-002 fields.
- **GenerationIdentity**: provider, model tag, digest, runtime version.
- **AnswerCase / AnswerReport / ReviewSheet**: evaluation records (FR-025).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100 % of citations in all returned envelopes (deterministic tests and real-model runs)
  resolve to the pinned snapshot and to the exact stored excerpt (citation integrity).
- **SC-002**: 100 % of scripted invalid model outputs (fake evidence IDs, malformed JSON, schema
  violations, URLs, unsupported quotes, answered-without-documented-claim) end in a validated
  repair, an explicit failure or a labelled extractive fallback, and never in an unchecked draft.
- **SC-003**: With the generation runtime stopped or mismatched, 100 % of chat requests return the
  typed unavailable error while search keeps returning evidence.
- **SC-004**: Zero policy overrides in the injection fixture suite. No tool/command action is taken,
  no system-prompt disclosure occurs, and no injected assertion appears as a documented claim
  unless it is the actual cited document content.
- **SC-005**: Aborting a request releases its slot and admits the next request within 2 seconds in
  100 % of tests.
- **SC-006**: A real-model run of the answer case file completes on the reference workstation. The
  report states, with counts, how many covered cases were answered with valid citations and how
  many unanswerable cases were safely handled. Human-judged metrics are "not run" until reviewed.
- **SC-007**: With external network egress blocked (loopback only), asking a covered question
  returns a cited answer (AT-01).

## Assumptions

- The generation model is the locked `qwen3:4b-instruct` served by the local Ollama runtime. Its
  structured-output support, thinking control, context limits and real prompt-token counts are
  verified against the runtime during research, not assumed.
- F006 renders Markdown from claims and handles HTML sanitization. F005 returns structured claims
  and a plain-text/Markdown rendering for the CLI only.
- Answers are English only in v1 (`response_language: en`).
- Chats are not persisted on the server (stateless; the client sends bounded history).
- The answer-quality release thresholds (factual support precision ≥ 95 %, required-fact coverage
  ≥ 85 %) are F008 gates; F005 builds the measurement and reports it honestly.

## Out of Scope

UI (F006), snapshot comparison (F007), release-grade reviewed evaluation (F008), containers (F009),
public hosting (F010), token-level streaming of provisional text, chat persistence, multi-language
answers, any remote or paid provider.
