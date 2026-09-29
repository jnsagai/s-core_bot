---

description: "Task list for F006 Local Web Experience and Privacy"
---

# Tasks: F006 Local Web Experience and Privacy

**Input**: Design documents from `specs/006-local-web-ui/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/ui-contract.md,
quickstart.md, checklists/requirements.md, checklists/privacy-rendering.md

**Tests**: MANDATORY (constitution VII). Frontend tests use Vitest + jsdom + Testing Library (no
real browser available in this environment). Real-browser, keyboard-only and screen-reader checks
are out of scope for this run and are recorded as "not run — no browser on this machine" in
`verification.md`, never marked passed.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelizable (different files, no dependency on incomplete tasks)
- **[Story]**: US1 (ask + inspect evidence), US2 (clear states, recover from failure), US3
  (privacy + export), US4 (keyboard + screen reader)
- Frontend paths are relative to `frontend/`; backend paths are relative to
  `src/score_docs_assistant/`

---

## Phase 1: Setup

- [x] T001 [P] Scaffold `frontend/` project: `package.json` (pinned versions from research.md R1),
  `package-lock.json` (via `npm install`), `tsconfig.json` (strict mode), `vite.config.ts`
  (`publicDir: false` per research.md R4), `.eslintrc.cjs`, `index.html` (with a `<noscript>`
  fallback message), `src/main.tsx` placeholder, `test/setup.ts` (jsdom + Testing Library +
  axe-core wiring)
- [x] T002 [P] Add npm scripts to `frontend/package.json`: `lint`, `typecheck` (`tsc --noEmit`),
  `test` (`vitest run`), `build` (`vite build`), `license-check`
  (`license-checker-rseidelsohn --json`)

**Checkpoint**: `npm ci && npm run lint && npm run typecheck && npm test && npm run build`
succeeds on a placeholder app (empty `<div/>`), emitting `frontend/dist/index.html` and
`frontend/dist/assets/*`.

---

## Phase 2: Foundational (blocking)

### Tests

- [x] T003 [P] Write `frontend/test/api/client.test.ts`: every exported call builds a relative,
  same-origin URL (`/api/v1/...` or `/health/...`); there is no configurable base URL anywhere in
  the module; error responses are parsed into the F001 error envelope shape (FR-011,
  contracts/ui-contract.md §1)
- [x] T004 [P] Write `frontend/test/api/chat-stream.test.ts`: `parseChatStream` on a scripted
  `ReadableStream` yields `progress`/`answer`/`error`/`done` events with increasing IDs in order;
  aborting the underlying `AbortController` stops iteration with no further events and no retry
  (contracts/ui-contract.md §3, research.md R3)
- [x] T005 [P] Write `tests/unit/test_guard.py::TestStaticExemption` (extends F001's guard test
  module): `GET /` and `GET /assets/anything.js` with `Sec-Fetch-Site: cross-site` pass through to
  the app; `POST /api/v1/chat`, `GET /api/v1/capabilities`, and `GET /health/ready` with the same
  header are still rejected with `403 CROSS_SITE_REQUEST`; a bad `Host` header is rejected on
  every path including `/` (FR-011a, research.md R5)
- [x] T006 [P] Write `tests/contract/test_static_serving.py`: `GET /` returns `index.html` with
  the FR-010a Content-Security-Policy header and `cache-control: no-store`; `GET /assets/<real
  hashed file>` returns 200 with a long-lived cache header; `GET /assets/does-not-exist.js`
  returns 404 (never `index.html`); when `frontend/dist/` is absent, `GET /` returns 503 with a
  plain message, not a stack trace (contracts/ui-contract.md §2)

### Implementation

- [x] T007 [P] Implement `frontend/src/api/client.ts` (fetch wrapper, same-origin paths only,
  F001 error-envelope parsing) — makes T003 pass
- [x] T008 [P] Implement `frontend/src/api/chat.ts` (`parseChatStream`) — makes T004 pass
- [x] T009 Implement the static-GET exemption in `api/guard.py` (`static_get_paths` predicate) —
  makes T005 pass
- [x] T010 Implement `api/static_routes.py` (mounts `frontend/dist`, CSP + cache headers, 503 when
  absent) and wire it into `api/app.py` after all `/api/v1/*`/`/health/*` routers — makes T006 pass

**Checkpoint**: gate green (backend `uv run pytest`/`ruff`/`mypy`; frontend
`npm run lint && npm run typecheck && npm test`). Commit.

---

## Phase 3: User Story 1 — Ask a question and inspect its evidence (P1) 🎯 MVP

- [x] T011 [P] [US1] Implement `frontend/src/api/capabilities.ts`, `snapshots.ts`, `search.ts`,
  `citations.ts` (typed calls matching contracts/ui-contract.md §1) with
  `frontend/test/api/*.test.ts` per module (request shape, response typing, error passthrough)
- [x] T012 [P] [US1] Implement `frontend/src/state/conversation.ts` (reducer: add user turn, start
  assistant turn with status, apply progress/answer/error, clear) with
  `frontend/test/state/conversation.test.ts` (data-model.md ConversationTurn)
- [x] T013 [P] [US1] Implement `frontend/src/components/SafeMarkdown.tsx` (react-markdown +
  remark-gfm, no `rehype-raw`, custom `a`/`img` renderers per research.md R2) with
  `frontend/test/components/SafeMarkdown.test.tsx` (safe link renders, unsafe scheme neutralized,
  no `<img>` ever created, code blocks get copy control and no run control) (FR-009, FR-010)
- [x] T014 [P] [US1] Implement `frontend/src/components/StatusBadge.tsx` and
  `frontend/src/components/LiveRegion.tsx` (one shared `aria-live` region, de-duplicated
  announcements) with `frontend/test/components/StatusBadge.test.tsx` (FR-004)
- [x] T015 [US1] Implement `frontend/src/components/AnswerView.tsx` (claims grouped by kind,
  citation markers) and `frontend/src/components/EvidencePanel.tsx` (focus-trapped, `Escape`
  closes and restores focus) with `frontend/test/components/EvidencePanel.test.tsx` (FR-007,
  FR-008)
- [x] T016 [US1] Implement `frontend/src/components/ChatPanel.tsx` (question input, submit via
  `chat.ts`, renders `AnswerView`, wires `StatusBadge`/`LiveRegion`) with
  `frontend/test/components/ChatPanel.test.tsx` (scripted SSE fixture drives
  queued→searching→generating→validating→ready; renders claims and citation markers) (US1 AS1,
  AS2)
- [x] T017 [P] [US1] Implement `frontend/src/components/SearchPanel.tsx` (query + source/kind
  filters, result list, never calls chat) with `frontend/test/components/SearchPanel.test.tsx`
  (FR-018, US1 AS4)
- [x] T018 [US1] Implement `frontend/src/components/SnapshotSelector.tsx` (basic: list + select,
  confirmation logic deferred to T024) and `frontend/src/components/Header.tsx` with
  `frontend/test/components/Header.test.tsx` (FR-001, FR-002, US1 AS5)
- [x] T019 [US1] Implement `frontend/src/App.tsx` and `frontend/src/main.tsx` (tab shell wiring
  Header/ChatPanel/SearchPanel/SnapshotSelector, no router) with
  `frontend/test/App.test.tsx` (tab switching without reload)

**Checkpoint**: gate green. Manual walkthrough against the real backend (quickstart.md §C steps
1–2) attempted by the agent for smoke purposes; full recorded confirmation deferred to the owner
per constitution VII.

---

## Phase 4: User Story 2 — Clear states, recover from failure (P2)

- [x] T020 [P] [US2] Implement `frontend/src/state/readiness.ts` (fetch on load; explicit
  re-fetch only — no timer) with `frontend/test/state/readiness.test.ts` (A-036, FR-006a)
- [x] T021 [US2] Extend `ChatPanel.tsx`/`App.tsx`: readiness-derived degraded/unavailable messages
  (chat unavailable but search available; no corpus), Stop control aborting the in-flight
  request, Retry re-issuing the same request, with
  `frontend/test/components/ChatPanel.test.tsx` additions (FR-005, FR-006, US2 AS1–AS4)
- [x] T022 [US2] Handle the SSE `error`-after-`progress` case in `ChatPanel.tsx`: preserve
  rendered progress history for the turn, show the failure state, with a test case in
  `ChatPanel.test.tsx` (US2 AS5)

**Checkpoint**: gate green. Commit.

---

## Phase 5: User Story 3 — Privacy and export (P2)

- [x] T023 [P] [US3] Write `frontend/test/privacy/no-storage-writes.test.ts`: spies on
  `localStorage.setItem`, `sessionStorage.setItem`, `document.cookie` setter, and
  `console.log`/`console.error`/`console.warn` across a full mounted-app ask→answer→export flow;
  asserts zero storage/cookie calls and that no console call's arguments contain the literal
  question or answer text used in the test (FR-013, FR-014, FR-015, SC-004)
- [x] T024 [US3] Extend `SnapshotSelector.tsx`: switching with an empty conversation applies
  immediately; switching with ≥ 1 turn opens a focus-trapped confirmation dialog, only confirming
  clears and applies (FR-017, A-035) with `frontend/test/components/SnapshotSelector.test.tsx`
  (quickstart.md §E)
- [x] T025 [US3] Wire "New conversation" and reload-clears-state into `App.tsx`/
  `conversation.ts` with a test asserting no prior turn is sent as history after either action
  (US3 AS1)
- [x] T026 [P] [US3] Implement `frontend/src/components/ExportMenu.tsx` (`buildMarkdownExport`,
  `buildJsonExport` per data-model.md ExportDocument, Blob + temporary `<a download>`) with
  `frontend/test/components/ExportMenu.test.tsx` (required identities present, no absolute path
  or credential-shaped string, export disabled until the answer is validated/complete) (FR-016,
  SC-005)
- [x] T027 [US3] Confirm no analytics/telemetry import exists: add a CI-time dependency-graph
  check (`npm ls` based, or a simple grep over `frontend/src` for known SDK import names) recorded
  in `frontend/package.json`'s scripts, with a passing run (FR-015)

**Checkpoint**: gate green; the storage-write spy (T023) and export fixtures (T026) are the
closest thing to SC-002/SC-004/SC-005 evidence this environment can produce without a browser.
Commit.

---

## Phase 6: User Story 4 — Keyboard and screen reader (P3)

- [x] T028 [P] [US4] Write `frontend/test/a11y/main-screen.a11y.test.tsx`: render `<App/>` under
  jsdom, run `axe-core` restricted to rules that do not require real layout/paint (documented
  explicitly in the test file per research.md R6), assert zero violations
- [x] T029 [US4] Verify and fix, via Testing Library's `tab()`/keyboard helpers, that every
  interactive control in `ChatPanel`, `SearchPanel`, `SnapshotSelector`, `EvidencePanel`, and
  `ExportMenu` is reachable in a logical order with an accessible name/role
  (`frontend/test/a11y/keyboard-order.test.tsx`) (FR-003, US4 AS1)
- [x] T030 [US4] Verify `LiveRegion` announces each state transition exactly once (no
  re-announcement on every rendered token/claim) with a dedicated assertion in
  `frontend/test/components/StatusBadge.test.tsx` (FR-004, US4 AS2)
- [x] T031 [US4] Verify focus-trap and restore-on-close behaviour for `EvidencePanel` and the
  `SnapshotSelector` confirmation dialog under simulated `Escape`/Tab-cycling
  (`frontend/test/a11y/focus-trap.test.tsx`) (US4 AS3)

**Checkpoint**: gate green; `verification.md` records exactly which a11y rules were checked under
jsdom and which (color contrast, real focus-order rendering, screen reader) are "not run — no
browser on this machine."

---

## Phase 7: Cross-cutting: CI and license gate

- [x] T032 [P] Extend `scripts/check_licenses.py` with `run_npm_licenses()` (research.md R7):
  invoked only when `frontend/package-lock.json` exists; reuses `evaluate()`/`is_allowed()`/
  `is_copyleft()` and `config/license-exceptions.yaml`; add `tests/unit/test_check_licenses.py`
  cases for the npm inventory path (mocked `npm run license-check` output)
- [x] T033 Run `uv run python scripts/check_licenses.py` against the real
  `frontend/package-lock.json` inventory; record any exception in
  `config/license-exceptions.yaml` with a reason, or confirm zero violations
- [x] T034 [P] Extend `.github/workflows/ci.yml` with a frontend job: `npm ci`,
  `npm run lint`, `npm run typecheck`, `npm test`, `npm run build`, running on the same triggers as
  the Python job; confirm the workflow YAML is valid (`actionlint`-equivalent or a dry parse) and
  the frontend job is required for the branch's merge gate
- [x] T034a Add a build-time check (script or CI step) that greps every built
  `frontend/dist/index.html` and `frontend/dist/assets/*` file for an `http://`/`https://`
  reference to any host other than none (the build must contain zero absolute third-party URLs —
  same-origin relative paths only); wire it into T034's CI job and into `frontend/package.json`
  as a script runnable locally (FR-012, SC-002)

**Checkpoint**: gate green including the extended license check. Commit and push.

---

## Phase 8: Polish

- [x] T035 [P] Update `README.md`/`CLAUDE.md`/`docs/user/` with the frontend build/serve commands
  and the "no browser installed here" verification caveat
- [x] T036 [P] Update `docs/BACKLOG.md`, `docs/TRACEABILITY.md` (UX-001–UX-005, SEC-002, SEC-003,
  OPS-001), `docs/ASSUMPTIONS.md` (already updated during clarify — confirm no further gaps)
- [x] T037 Run the full local gate (backend + frontend) and record commands/results in
  `specs/006-local-web-ui/verification.md`
- [ ] T038 Walk quickstart.md §A, §B, §D, §E and record real results; record §C as "not run — no
  browser on this machine, deferred to the owner" per constitution VII

---

## Dependencies & Execution Order

Setup → Foundational → US1 → US2 → US3 → US4 → Cross-cutting → Polish. US2 extends US1's
`ChatPanel`; US3's export needs a completed US1 answer; US4 audits components built in US1–US3
rather than adding new ones.

### Parallel Opportunities

T001–T002; T003–T006; T007–T008 with T009–T010; T011–T014, T017; T020, T023, T026, T028; T032,
T034, T035, T036.

## Implementation Strategy

MVP = Phases 1–3 (ask a question, see progress, open a citation, search directly). Then failure
states, privacy/export, accessibility audit, cross-cutting CI/license, polish; commit per
checkpoint and push per this run's instructions.

## Notes

- Mark a task `[x]` only after its verification ran and passed (constitution VII). A frontend
  test that cannot run without a real browser stays unchecked with the reason recorded, not
  skipped silently.
- Never write conversation content to Web Storage, a cookie, or a log line, even in a test helper
  used only for assertions.
