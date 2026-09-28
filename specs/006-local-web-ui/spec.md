# Feature Specification: F006 Local Web Experience and Privacy

**Feature Branch**: `006-local-web-ui`

**Created**: 2026-09-28

**Status**: Draft

**Input**: User description: "F006 from docs/PROJECT_SPEC.md §16: Local web experience and
privacy. Scope: chat/search screens, snapshot selector, evidence panel, clear states, keyboard
flow, local assets, sanitized Markdown, cancellation, Markdown/JSON export, ephemeral chat
history, safe operational logging. Acceptance: first-run-to-citation flow passes in a browser; no
CDN/analytics requests occur; malicious content is inert; reload clears conversation; exports
carry source/model identities; logs do not contain message bodies."

**Master requirements covered**: UX-001 to UX-005, SEC-002, SEC-003, OPS-001 (primary); master
spec §11 (UI specification), §12.2 (data handling), §13.1 item 4 (UI tests, accessibility, hostile
rendering fixtures), UJ-01, UJ-02, UJ-03, UJ-04, UJ-06. Acceptance tests AT-01, AT-15, AT-18
(browser-facing half).

**Input from F004/F005**: the existing `/api/v1/search`, `/api/v1/entities`,
`/api/v1/relationships`, `/api/v1/snapshots`, `/api/v1/sources`, `/api/v1/citations/{snapshot}/
{chunk}`, `/api/v1/capabilities`, `/health/*` and `POST /api/v1/chat` (JSON or SSE) contracts.
F006 builds a browser client on top of them and adds no new retrieval or generation behavior.

## Clarifications

### Session 2026-09-28

Resolved autonomously by the agent (agent review, not an approval) from `docs/PROJECT_SPEC.md`
and F001–F005 precedent, at the project owner's standing instruction to be fully autonomous; see
`docs/ASSUMPTIONS.md`. The owner may override any answer.

- Q: What UI framework and bundling approach? → A: TypeScript + React + Vite, built to a static
  bundle that the FastAPI backend serves from one loopback origin (constitution "Technology &
  Security Constraints"; PROJECT_SPEC.md §1.2, §14). No separate frontend dev server in
  production, no CDN-hosted dependency, no heavy component/UI framework beyond React itself.
  Basis: constitution is explicit and non-negotiable here, so this is not a real ambiguity.
- Q: How does the browser reach the backend without exposing runtime endpoints (SEC-002)? → A:
  the built frontend calls only same-origin `/api/v1/*` and `/health/*` paths; it never talks to
  Ollama or the filesystem, and no runtime base URL is configurable from the browser bundle.
  Basis: SEC-002 requires the browser to see only the application API.
- Q: What exactly gets logged for UI-triggered requests (OPS-001)? → A: F006 adds no new server
  logging path; it inherits F001's existing body-free, request-ID-tagged, rotating access log.
  This feature's job is to make sure no UI code path (export, error toast, dev console) writes
  question/answer text to a log or to `localStorage`/`sessionStorage`/cookies. Basis: OPS-001 is
  already implemented server-side (F001); F006 must not regress it from the client side.
- Q: Changing the snapshot selector mid-conversation — always confirm, always silently clear, or
  conditional? → A: conditional on whether the conversation already has turns: with an empty
  conversation the new snapshot applies immediately; with at least one turn, an explicit
  confirmation is required before clearing. Basis: master spec §11.1 offers both "start a new
  context" and "require explicit confirmation" as acceptable; conditioning on turn count satisfies
  both without extra clicks on a fresh screen.
- Q: Does the UI poll the backend in the background to detect when chat/search becomes available
  again? → A: no background polling. Readiness (`/api/v1/capabilities`, `/health/ready`) is
  fetched on initial load and re-fetched only on an explicit user action (page reload, "Retry"
  after a failure, or opening the settings/status view). Basis: constitution Principle VIII
  (privacy/minimal chatter) and OPS-006 admission bounds argue against an idle client generating
  continuous background requests; a user-triggered re-check is simpler and sufficient for a local
  single-user tool.
- Q: Where does the UI get the question-length limit for inline client-side validation
  (Edge Cases: "empty or over-long question")? → A: from `limits.question_characters` (and
  `limits.history_characters`) already returned by `/api/v1/capabilities` (see
  `specs/001-foundation/contracts/http-api.md`); the UI does not hardcode or duplicate this value,
  and the server's own validation remains authoritative regardless of what the client checked.
- Q: F001's `HostOriginGuard` (`src/score_docs_assistant/api/guard.py`) rejects every request with
  `Sec-Fetch-Site: cross-site` — including a top-level browser navigation to the app's own HTML
  page (e.g. from a bookmark saved in a browser profile that resolves it as cross-site, or a link
  typed/pasted from another origin). F001's `docs/ASSUMPTIONS.md` A-008 explicitly deferred
  deciding this to F006. Reject always, or exempt something? → A: exempt only top-level `GET`
  navigation (`Sec-Fetch-Mode: navigate`, HTML document requests) to the static frontend
  shell/assets from the cross-site check; every `/api/v1/*` and `/health/*` request keeps the
  existing strict Host/Origin/cross-site guard with no exception, matching SEC-002/SEC-004/AT-18.
  Basis: the threat this guard defends against is a hostile page's script silently calling the
  API (XHR/fetch/DNS rebinding) with the victim's loopback access — not a human deliberately
  navigating their own browser tab to a bookmarked local URL, which discloses nothing to a third
  party and changes no state. Recorded as `docs/ASSUMPTIONS.md` A-034 (resolving A-008).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ask a question and inspect its evidence in the browser (Priority: P1)

A software engineer opens the local app in a browser, sees the active documentation snapshot and
runtime readiness, types a question, watches it progress through queued/searching/generating/
validating, and receives a rendered answer with citation cards. Selecting a citation opens the
exact local excerpt (title, heading/requirement ID, revision, optional upstream link) without
leaving the page.

**Why this priority**: this is the product's core promise made usable (UJ-01, UJ-02) — F005
already produces correct cited answers; F006 is what lets a human actually use them.

**Independent Test**: with the real backend (real or stubbed model) running, a scripted browser
session (component tests + a manual/keyboard walkthrough, since no browser automation runs
unattended per the verification constraints) can go from an empty screen to an opened citation
excerpt for a covered question.

**Acceptance Scenarios**:

1. **Given** the app is loaded and a snapshot is active, **When** the user submits a question,
   **Then** the UI shows successive state labels (queued/searching/generating/validating) sourced
   from the SSE `progress` events, then renders the final answer's claims with their status
   (documented/interpretation/limitation) and inline citation markers.
2. **Given** a rendered answer, **When** the user activates a citation marker or card, **Then** an
   evidence panel opens showing the document title, heading/requirement-ID path, source revision,
   the stored excerpt, and — only when the backend supplied one — an upstream link that opens in a
   new tab with safe `rel`/`target` attributes.
3. **Given** the evidence panel is open, **When** the user closes it (click, `Escape`, or tabbing
   away) **Then** focus returns to the control that opened it.
4. **Given** the user prefers not to generate an answer, **When** they use search mode with a
   query and optional source/type filters, **Then** they see ranked results with excerpts and
   provenance directly from `/api/v1/search`, with no call to the chat/generation endpoint.
5. **Given** more than one snapshot is queryable, **When** the user opens the snapshot selector,
   **Then** they see the available snapshots and can select one; the header always shows which
   snapshot the current conversation is bound to.

---

### User Story 2 - See clear states and recover from failures without losing trust (Priority: P2)

A user's model is not installed, the network between browser and backend hiccups, or a request is
slow. The UI never looks stuck or silently wrong: it shows a specific, distinguishable state for
each situation and offers a next action.

**Why this priority**: UX-003 and the master spec's failure-message table (§11.3) — a confusing
or misleadingly "done" UI would undermine the honesty the rest of the system works hard to
provide.

**Independent Test**: drive the UI against fixture/mocked backend responses for each documented
capability/readiness/error combination and assert the exact state shown and the recovery action
offered, without needing a real model or network fault.

**Acceptance Scenarios**:

1. **Given** `/api/v1/capabilities` reports chat unavailable (model missing) but search available,
   **When** the app loads, **Then** the UI shows a specific "generation unavailable" state with
   guidance, keeps the question input for search, and does not offer a chat button that silently
   fails.
2. **Given** a chat request is in flight, **When** the user clicks "Stop", **Then** the browser
   aborts the underlying fetch/EventSource, the UI shows a cancelled state distinct from
   "failed", and the input is immediately re-enabled.
3. **Given** a request ends in a typed error (busy, deadline, generation unavailable, invalid
   request), **When** the error arrives, **Then** the UI shows the specific reason from the error
   envelope (never a generic "something went wrong") and an explicit "Retry" action that re-sends
   the same question.
4. **Given** no corpus/snapshot exists yet, **When** the app loads, **Then** the UI shows setup
   guidance instead of an empty chat box that implies the assistant is ready.
5. **Given** the SSE stream ends with an `error` event after `progress` events were already shown,
   **When** this happens, **Then** the UI shows the failure state (not a silently blank or frozen
   "generating" state) and preserves the already-rendered progress history for that turn.

---

### User Story 3 - Keep the session private and export a shareable answer (Priority: P2)

A user reloads the page, opens a new conversation, or closes the tab: nothing about their
questions or answers persists anywhere the application controls. When they want to keep an
answer, they explicitly export it as Markdown or JSON, and that export is self-contained and
free of machine-specific details.

**Why this priority**: UX-004, UX-005, SEC-002, SEC-003 — privacy-by-default is a constitution
invariant (Principle VIII), not a nice-to-have.

**Independent Test**: component/unit tests assert that (a) no chat or answer content is written
to any Web Storage/cookie/log call, (b) reload or "New conversation" clears in-memory state, and
(c) a generated export file's content matches a snapshot fixture with no absolute filesystem path
or secret-shaped string.

**Acceptance Scenarios**:

1. **Given** an active conversation, **When** the user reloads the page or clicks "New
   conversation", **Then** the visible history is cleared and no prior turn is sent as context to
   the next request.
2. **Given** a completed answer, **When** the user chooses "Export Markdown" or "Export JSON",
   **Then** the downloaded file contains the question, claims, citations, snapshot ID and model
   identity, and contains no absolute local filesystem path, environment variable, or credential.
3. **Given** rendered Markdown from an answer or a search excerpt, **When** it contains raw HTML,
   a `javascript:`/`data:` URL, or a remote `<img>` reference, **Then** the raw HTML is not
   executed, the unsafe URL is neutralized (not clickable as a navigation target), and no network
   request is made to load a remote image.
4. **Given** the browser developer console or network tab is inspected during ordinary use,
   **When** the user asks questions or searches, **Then** the only requests are same-origin calls
   to this application's own `/api/v1/*`/`/health/*` paths — no request to a CDN, analytics, font,
   or third-party host of any kind.
5. **Given** the app's HTML/JS/CSS bundle, **When** it is inspected, **Then** every script,
   stylesheet, font and icon it uses is bundled locally; none is fetched from a public CDN at
   runtime.

---

### User Story 4 - Operate the whole flow by keyboard and screen reader (Priority: P3)

A user who cannot or prefers not to use a mouse completes the primary flow — ask, read progress,
open a citation, export — using only the keyboard, with a screen reader announcing state changes
without repeating the entire answer on every update.

**Why this priority**: UX-001 and master spec §11.2; accessibility is a stated requirement, not
an afterthought, though the deepest verification (real browser + real screen reader) is deferred
to the owner per this run's constraints.

**Independent Test**: static/automated accessibility checks runnable without a browser (e.g. a
jsdom-based axe/testing-library run over rendered component trees) plus a recorded manual
keyboard walkthrough checklist; the real-browser keyboard-only session itself is deferred to the
owner.

**Acceptance Scenarios**:

1. **Given** any interactive control (question input, snapshot selector, citation card, stop/
   retry/export buttons, search filters), **When** navigating with `Tab`/`Shift+Tab`, **Then**
   every control is reachable in a logical order with a visible focus indicator.
2. **Given** a state change (queued → searching → generating → validating → ready/degraded/
   failed), **When** it happens, **Then** an ARIA live region announces the new state once, without
   re-announcing the full answer text on every subsequent update.
3. **Given** the evidence panel or any modal-like overlay is open, **When** the user presses
   `Escape` or tabs through it, **Then** focus stays trapped inside it until closed, then returns
   to the triggering control.
4. **Given** automated static accessibility checks run over the main screen's rendered markup,
   **When** they run in CI, **Then** they report no critical violations (missing labels, missing
   roles, insufficient contrast in the default theme).

---

### Edge Cases

- Backend becomes unreachable mid-session (server restarted) → UI shows a distinct "disconnected/
  degraded" state on the next request rather than hanging indefinitely; existing rendered history
  is preserved.
- User submits an empty question, or one exceeding `limits.question_characters` from
  `/api/v1/capabilities`, or history exceeding `limits.history_characters` → inline validation
  before any request is sent using the server-reported limits (never a hardcoded duplicate); no
  round trip wasted. The server's own validation remains authoritative if the two ever disagree.
- User switches the snapshot selector mid-conversation → with an empty conversation the switch is
  immediate; with existing turns, the UI requires an explicit confirmation (per master spec §11.1)
  before clearing the current context; no prior answer is presented as evidence for the new
  snapshot.
- Two answers are open in two browser tabs against the same backend → each tab's cancel/export/
  state is independent; cancelling in one tab does not affect the other.
- A citation's upstream link cannot be proven current (`revision_match` not `exact`) → the UI
  labels the link accordingly instead of presenting it as equally authoritative to the local
  excerpt.
- Export requested while a request is still generating → export is only offered for a completed
  (validated) answer, never for in-flight or partial-stream content.
- A very long answer or many citations → the evidence panel and answer list scroll and remain
  keyboard-navigable; nothing is clipped without a way to reach it.
- JavaScript disabled or the static bundle fails to load → the backend still serves a minimal
  honest message (not a blank white page) explaining the app needs JavaScript, sourced from
  server-rendered HTML shell, not from the failed bundle.
- Browser opens the app's HTML page via a cross-site top-level navigation (e.g. a bookmark or an
  external link) → the page loads (FR-011a); any subsequent API call it makes is still fully
  Host/Origin/cross-site guarded like every other request.

## Requirements *(mandatory)*

### Functional Requirements

**Screens and navigation (UX-001, §11.1)**

- **FR-001**: The UI MUST provide, from one loopback origin served by the backend's static build:
  a chat/question screen, a search screen, a snapshot selector, a source/evidence inspection view,
  and a runtime-readiness/settings view, all reachable without a full page reload.
- **FR-002**: The header MUST display the community-project label, the currently bound snapshot,
  and a "runs on this computer" local-mode indicator (master spec §11.1).
- **FR-003**: Every interactive control MUST be reachable and operable via keyboard alone, with a
  visible focus indicator and a screen-reader-accessible name/role.

**Progress and state (UX-003)**

- **FR-004**: The UI MUST visually and programmatically (ARIA live region) distinguish at least
  these states for a chat/search request: loading (initial app load), queued, searching,
  generating, validating, ready (answer/results shown), degraded (partial capability, e.g.
  lexical-only search or chat unavailable), and failed (with the specific typed reason).
  Live-region announcements fire once per state transition, not once per rendered token/claim.
- **FR-005**: The UI MUST provide a control to stop an in-flight chat generation; stopping MUST
  abort the underlying HTTP request/EventSource client-side and immediately return the input to a
  ready state.
- **FR-006**: After any failed request, the UI MUST offer an explicit retry action that re-issues
  the same request; it MUST NOT auto-retry silently in a loop.
- **FR-006a**: The UI MUST fetch `/api/v1/capabilities` and `/health/ready` on initial page load
  to derive readiness, and MUST re-fetch them only on an explicit user action (page reload, an
  error-state "Retry", or opening the settings/status view) — never on a background timer/poll.

**Evidence and citations (UX-002)**

- **FR-007**: Selecting a citation MUST open a panel/view showing, at minimum, the document title,
  heading or requirement-ID path, source revision, and the stored excerpt, fetched from
  `/api/v1/citations/{snapshot_id}/{chunk_id}` or from data already present in the answer envelope.
  When the backend supplies an upstream URL, it is shown as an optional link labelled with its
  `revision_match` status; its absence never blocks viewing the local excerpt.
- **FR-008**: The evidence panel MUST be reachable, closeable, and focus-managed by keyboard
  (`Escape` closes it; focus returns to the triggering control).

**Rendering safety (SEC-003)**

- **FR-009**: Answer and search-excerpt Markdown MUST be rendered through a sanitizing pipeline
  that disables raw HTML execution, strips or neutralizes `javascript:`/`data:`/other
  non-`http(s)` URL schemes in links, and does not auto-load remote images. External links MUST
  open with safe attributes (`rel="noopener noreferrer"`, explicit `target` only for genuine
  external navigation).
- **FR-010**: Code blocks copied from evidence or answers MUST render as inert text with a copy
  control; the UI MUST NOT provide a "run" action for any code or command text.
- **FR-010a**: The backend MUST send a strict Content-Security-Policy header on the served HTML
  document (`default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src
  'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'`,
  exact directive set finalized during implementation) so that even a defect in the sanitizing
  renderer cannot load a remote script/style/connection, and so the page cannot be framed by
  another origin (master spec §12.1: "sanitized rendering, strict content-security policy, no
  remote auto-loads"). This is defense-in-depth on top of, not instead of, FR-009's rendering-time
  sanitization.

**Backend-only communication (SEC-002)**

- **FR-011**: The built frontend MUST call only same-origin `/api/v1/*` and `/health/*` paths. No
  code path may construct a request to the local model runtime, a filesystem path, or any
  non-configured host. There is no user- or build-time-configurable "backend URL" that could point
  the browser elsewhere in the shipped static build.
- **FR-011a**: The backend's Host/Origin/cross-site guard MUST exempt only top-level `GET`
  navigation to the static frontend document/asset routes (exactly `/` and everything under
  `/assets/`, the complete and only set of paths the frontend build emits — enforced by keeping
  Vite's `publicDir` empty so no unhashed top-level file such as a favicon exists outside that
  set) from the `Sec-Fetch-Site: cross-site` rejection, so a user can open/bookmark the app in a
  browser. Every `/api/v1/*` and `/health/*` request, regardless of method, keeps the full
  existing Host/Origin/cross-site check with no exception (resolves `docs/ASSUMPTIONS.md` A-008 as
  A-034). This exemption governs only the cross-site *header* check; it does not by itself permit
  framing (see FR-010a's `frame-ancestors 'none'`).
- **FR-012**: The production build MUST NOT load any script, stylesheet, font, icon, or image from
  a public CDN or other third-party host at runtime; all such assets are bundled and served
  locally by the backend.

**Privacy and ephemeral state (UX-005, OPS-001)**

- **FR-013**: Conversation history MUST be held only in browser memory (in-process JS state), never
  written to `localStorage`, `sessionStorage`, `IndexedDB`, or a cookie, and MUST be cleared on
  page reload and on an explicit "new conversation" action.
- **FR-014**: No UI code path (including error reporting, analytics, or debug logging) MAY write
  question or answer text to the browser console in production builds or to any server-side log;
  this feature adds no new server logging surface and MUST NOT bypass F001's existing body-free
  access log.
- **FR-015**: The UI MUST NOT embed any analytics, crash-reporting, or telemetry SDK; it makes no
  network request other than to this application's own API.

**Export (UX-004)**

- **FR-016**: The UI MUST offer Markdown and JSON export of a completed answer, each containing the
  question, claims (with kind and evidence IDs), citations, snapshot ID, and generation model
  identity, as already supplied in the F005 answer envelope. Exports MUST NOT contain any
  machine-specific absolute filesystem path, environment variable value, or credential.
  Export is only available for a validated, completed answer.

**Snapshot handling (§11.1, ANS-007 interaction)**

- **FR-017**: The snapshot selector MUST list queryable snapshots from `/api/v1/snapshots` and let
  the user pick one. With an empty conversation, selecting a different snapshot applies
  immediately. With at least one turn already in the conversation, changing the snapshot MUST
  prompt for explicit confirmation before clearing it. No prior turn's evidence is ever presented
  as belonging to the newly selected snapshot.

**Search screen (UX-001)**

- **FR-018**: The search screen MUST let the user query `/api/v1/search` directly (no generation
  call), with optional source/kind filters exposed from the search response's own vocabulary, and
  MUST render each result's excerpt, provenance, and (when present) exact-match/entity indicator
  without requiring the user to open chat mode.

**Build and dependency hygiene (constitution, OPS-005)**

- **FR-019**: The frontend MUST be built with TypeScript, React, and Vite, producing a static
  bundle that the backend serves; it MUST have no runtime dependency on a separately running
  Node.js server in production. Frontend dependencies MUST be locked (`package-lock.json`) and
  checked into the repository.
- **FR-020**: Frontend dependency licenses MUST be checked by an extension of the project's
  license gate (`scripts/check_licenses.py` or an equivalent frontend-aware check), using the same
  allow/deny philosophy as the Python gate; any exception MUST be recorded with a reason.

### Key Entities

- **AppReadinessState**: derived client-side from `/api/v1/capabilities` and `/health/ready` —
  which of chat/search is available, and why not when unavailable.
- **ConversationTurn** (client-only, in memory): role, text, snapshot ID (for assistant turns),
  timestamp; never persisted.
- **AnswerViewModel**: the rendered form of an F005 `AnswerEnvelope` — claims grouped by kind,
  citation markers linked to citation cards.
- **CitationViewModel**: the rendered form of an F005 `Citation`/F004 `CitationRecord` — title,
  heading path, revision, excerpt, optional labelled upstream link.
- **ExportDocument**: Markdown or JSON representation of one answer turn, self-contained, with no
  machine-specific paths.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: From an empty screen, a user can submit a covered question and open its first
  citation's local excerpt using only the documented UI flow, with no manual API calls, in
  component-level and manual verification (real-browser timing is deferred to the owner per this
  run's constraints).
- **SC-002**: 100% of network requests observed while using chat/search/citation/export in the
  built production bundle target this application's own same-origin `/api/v1/*` or `/health/*`
  paths; zero requests to any third-party host.
- **SC-003**: 100% of hostile-Markdown/rendering fixture cases (raw HTML, unsafe URL schemes,
  remote image references) render with no script execution, no unsafe navigation target, and no
  remote image request.
- **SC-004**: Reloading the page or starting a new conversation clears 100% of visible prior
  turns in every tested case, and no chat/answer text is ever found in `localStorage`,
  `sessionStorage`, cookies, or the access log across the test suite.
- **SC-005**: 100% of exported Markdown/JSON fixtures contain the required identities (question,
  snapshot ID, model identity, citations) and zero absolute local filesystem paths or
  credential-shaped strings.
- **SC-006**: Automated static accessibility checks over the main screen's rendered markup report
  zero critical violations; a recorded manual keyboard-only walkthrough completes the ask →
  citation → export flow without a mouse (real-browser/screen-reader confirmation deferred to the
  owner).

## Assumptions

- The frontend is TypeScript + React + Vite per the constitution's fixed technology constraint;
  this is not an open design choice for this feature.
- No browser automation tool (Playwright/Chromium/Puppeteer) may be installed or run in this
  environment; component tests use a Node-based DOM (e.g. Vitest + jsdom/Testing Library), and the
  real first-run-to-citation browser flow, full keyboard-only review, and automated
  in-browser accessibility run are recorded as "not run — no browser on this machine" and deferred
  to the owner, per constitution Principle VII (honest verification).
- F006 introduces no new backend endpoints, retrieval, or generation behavior; it consumes F004/
  F005 contracts as they exist today. Any backend gap discovered while building the UI (e.g. a
  field genuinely missing from an envelope) is raised as a scoped follow-up, not silently patched
  into F006's scope without a recorded decision.
- Snapshot comparison UI (F007) and any multi-user/public concerns (F010) are out of scope; the
  single-user local browser session is the only supported mode.
- OPS-001 (log rotation, 7-day retention, body-free logging) is already implemented server-side by
  F001; F006's OPS-001 obligation is limited to not regressing it from new UI-triggered code paths
  and to documenting that no new log surface was added.

## Out of Scope

Snapshot comparison UI (F007), quality/evaluation UI (F008), authentication or multi-user
isolation (F010), any new retrieval/generation/backend capability beyond what F004/F005 already
expose, real-browser and real-screen-reader verification (deferred to the owner), token-level
streaming of provisional claim text (F005 already excludes this), server-side chat persistence.
