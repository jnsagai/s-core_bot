# Implementation Plan: F006 Local Web Experience and Privacy

**Branch**: `006-local-web-ui` | **Date**: 2026-09-28 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/006-local-web-ui/spec.md`

## Summary

Add a small TypeScript + React + Vite single-page app under `frontend/`, built to a static bundle
that FastAPI serves from the existing loopback origin. No client-side router: the app is one HTML
document with in-memory view state (chat / search / settings tabs) — no deep links are required
by the spec, and this avoids an SPA-fallback route and a router dependency. The app talks only to
the existing `/api/v1/*` and `/health/*` endpoints (F001/F004/F005); it adds no backend business
logic. It renders answers/excerpts through `react-markdown` with no raw-HTML plugin and a custom
link/image renderer (no auto-loaded remote images, safe external links), parses the chat SSE
stream itself over `fetch()` (`EventSource` cannot POST), keeps all conversation state in React
state only (cleared on reload/new-conversation, never written to Web Storage), and exports answers
client-side as downloaded Markdown/JSON files built from data already in the answer envelope. The
one backend change is a narrow exemption in `HostOriginGuard` so a top-level `GET` document/asset
request can load the app even when browser-reported as cross-site (resolves `docs/ASSUMPTIONS.md`
A-008 as A-034); every `/api/v1/*`/`/health/*` request keeps the unmodified guard. Frontend
dependencies are locked (`package-lock.json`) and license-checked by extending
`scripts/check_licenses.py` with an npm-inventory pass using the same allow/deny policy.

## Technical Context

**Language/Version**: TypeScript (frontend, strict mode), Python 3.12 (backend, one guard change).

**Primary Dependencies**: `react`, `react-dom`, `react-markdown` + `remark-gfm` (no `rehype-raw`),
`vite`, `@vitejs/plugin-react`, `typescript`. Dev/test only: `vitest`, `@testing-library/react`,
`@testing-library/user-event`, `jsdom`, `axe-core` (static accessibility checks under jsdom),
`eslint` + `@typescript-eslint/*`, `license-checker-rseidelsohn` (frontend license inventory). No
UI component framework, no state-management library, no router, no CSS framework — plain CSS
modules or a single stylesheet.

**Storage**: none new. The frontend keeps conversation state only in React state (memory);
nothing is written to `localStorage`/`sessionStorage`/`IndexedDB`/cookies (FR-013).

**Testing**: Vitest + jsdom + Testing Library for components (no real browser available in this
environment — Playwright/Chromium/Puppeteer downloads are forbidden by this run's constraints).
`axe-core` runs against jsdom-rendered trees for the static-checkable accessibility rules (missing
labels/roles/landmarks); rules that need real layout/paint (color contrast, visible focus order)
are out of scope for jsdom and are recorded as "not run — no browser on this machine" per
constitution Principle VII. Backend guard change is tested with pytest/TestClient like the rest of
F001's guard suite.

**Target Platform**: any modern desktop browser reachable at `http://127.0.0.1:<port>`; Linux
x86-64 development/CI machine (no browser installed).

**Project Type**: web application — existing Python backend + new frontend, built and served
together as one deployable unit (constitution "Technology & Security Constraints").

**Performance Goals**: not a new measured budget for this feature; the app must not add
noticeably to perceived latency over the existing F004/F005 p95 targets. Static bundle stays
small (no heavy framework) so first load is fast on loopback.

**Constraints**: no CDN/runtime fetch of any third-party asset (FR-012); no analytics/telemetry
SDK (FR-015); browser talks only to same-origin `/api/v1/*`/`/health/*` (FR-011); no background
polling (A-036); Markdown rendering never executes raw HTML or loads a remote image (FR-009).

**Scale/Scope**: one user, one browser tab at a time is the primary case; the spec explicitly
requires two independent tabs not to interfere (edge case), which the stateless-per-request
backend already guarantees — no new multi-tab coordination code is needed.

## Constitution Check

*GATE: evaluated before Phase 0 and re-checked after Phase 1 design.*

| Principle | Status | How this plan complies |
| --- | --- | --- |
| I. Local operation | PASS | Frontend is static, served by the same backend; it calls no cloud service; nothing in this feature adds a runtime network dependency. |
| II. Evidence precedes assertions | PASS | The UI only renders claims/citations already validated by F005; it invents no evidence and adds no new generation path. |
| III. Snapshots explicit | PASS | Header always shows the bound snapshot (FR-002); snapshot switch mid-conversation requires confirmation once turns exist (FR-017, A-035); no client-side merging of evidence across snapshots. |
| IV. Documentation untrusted | PASS | Markdown/excerpt rendering never executes raw HTML, never treats source content as navigable script, and neutralizes unsafe URL schemes (FR-009); a strict CSP is defense-in-depth against a rendering defect (FR-010a). |
| V. Read-only assistance | PASS | No "run" action for code/commands (FR-010); the UI cannot call any endpoint beyond the existing read/answer contracts. |
| VI. Modular monolith | PASS | Frontend is a separate build artifact, not a separate service; it is served by the existing FastAPI app via one new static-files mount. No new backend service, queue, or database. |
| VII. Honest verification | PASS | Real-browser, keyboard-only, and screen-reader checks are explicitly recorded as "not run — no browser on this machine" (spec Assumptions); component/static checks are labelled for what they actually cover. |
| VIII. Privacy by default | PASS | No telemetry SDK; no Web Storage/cookie writes; chat memory-only, cleared on reload (FR-013, FR-015); no new server logging surface (FR-014). |
| IX. Spec-first | PASS | UX-001–005, SEC-002, SEC-003, OPS-001 mapped to FRs; `docs/TRACEABILITY.md` updated at convergence. |
| X. Public profile separate | PASS | The guard change (FR-011a) narrows an exemption to unauthenticated static GETs only; it does not touch the local-profile Host/Origin/CORS logic for any state-changing or API route, and has no effect on the (deferred) public profile. |
| XI. Licenses follow artifacts | PASS | `package-lock.json` committed; frontend dependency licenses checked by an extension of `scripts/check_licenses.py` using the existing allow/deny policy (FR-020). |
| XII. No implied authority | PASS | The UI renders F005's own claim kinds/labels; it adds no certification/approval affordance. |

Post-design re-check: **PASS**. No Complexity Tracking entries.

## Project Structure

### Documentation (this feature)

```text
specs/006-local-web-ui/
├── plan.md, research.md, data-model.md, quickstart.md
├── contracts/ ui-contract.md
├── checklists/ requirements.md (+ checklist phase)
├── tasks.md
└── verification.md
```

### Source Code (repository root)

```text
frontend/
├── package.json, package-lock.json, tsconfig.json, vite.config.ts, .eslintrc.cjs
├── index.html
├── src/
│   ├── main.tsx                     # mounts <App/>
│   ├── App.tsx                      # tab shell: header, snapshot selector, chat/search/settings
│   ├── api/
│   │   ├── client.ts                # fetch wrapper: same-origin only, JSON error envelope parsing
│   │   ├── capabilities.ts          # GET /api/v1/capabilities, /health/ready types + calls
│   │   ├── search.ts                # POST /api/v1/search
│   │   ├── chat.ts                  # POST /api/v1/chat (JSON) + parseChatStream (SSE-over-fetch)
│   │   ├── citations.ts             # GET /api/v1/citations/{snapshot}/{chunk}
│   │   └── snapshots.ts             # GET /api/v1/snapshots, /api/v1/sources
│   ├── state/
│   │   ├── conversation.ts          # in-memory turn list, reducer, "new conversation"/reload clear
│   │   └── readiness.ts             # capabilities/readiness state, explicit re-check triggers
│   ├── components/
│   │   ├── Header.tsx               # project label, snapshot indicator, "runs on this computer"
│   │   ├── SnapshotSelector.tsx     # FR-017, confirmation dialog when turns exist
│   │   ├── ChatPanel.tsx            # question input, turn list, stop/retry controls
│   │   ├── StatusBadge.tsx          # loading/queued/searching/generating/validating/ready/degraded/failed
│   │   ├── LiveRegion.tsx           # one shared aria-live region, de-duplicated announcements
│   │   ├── AnswerView.tsx           # claims by kind, citation markers
│   │   ├── SearchPanel.tsx          # query + source/kind filters, result list
│   │   ├── EvidencePanel.tsx        # focus-trapped citation detail (title, heading, revision, excerpt, link)
│   │   ├── SafeMarkdown.tsx         # react-markdown wrapper: no raw HTML, safe link/image renderers
│   │   ├── ExportMenu.tsx           # Markdown/JSON export via Blob + temporary <a download>
│   │   └── SettingsView.tsx         # model/runtime readiness, source list, coverage
│   ├── noscript-fallback (index.html <noscript> block, no separate file)
│   └── styles/ (single stylesheet, no CSS framework)
└── test/
    ├── setup.ts                     # jsdom + axe matchers
    ├── api/ client.test.ts, chat-stream.test.ts
    ├── components/ ChatPanel.test.tsx, SnapshotSelector.test.tsx, SafeMarkdown.test.tsx,
    │               EvidencePanel.test.tsx, ExportMenu.test.tsx, StatusBadge.test.tsx
    ├── state/ conversation.test.ts, readiness.test.ts
    └── a11y/ main-screen.a11y.test.tsx   # static axe-core pass over rendered App

src/score_docs_assistant/
├── api/static_routes.py             # mounts frontend/dist as StaticFiles, serves index.html,
│                                     # exempts static GETs in the guard call path
├── api/guard.py                     # + is_static_get() exemption (FR-011a / A-034)
└── api/app.py                       # wires static_routes when frontend/dist exists

scripts/check_licenses.py            # + run_npm_licenses(), evaluated against the same policy
frontend/package.json                # "license-check": "license-checker-rseidelsohn --json"

tests/
├── unit/test_guard.py               # extended: static GET cross-site exemption, API routes unaffected
└── contract/test_static_serving.py  # index.html served, unknown asset 404, security headers present

.github/workflows/ci.yml             # + frontend install/lint/typecheck/test/build job
```

**Structure Decision**: master spec §14 already reserves `frontend/` for "TypeScript UI and
frontend tests." The one backend touch point (`static_routes.py`, `guard.py`) stays inside the
existing `api/` package rather than a new module, since it is a routing/guard concern, not a new
domain capability.

## Key Design Decisions

1. **No client-side router** (spec has no deep-link requirement): fewer dependencies, no SPA
   fallback route needed, and it sidesteps the guard question for anything beyond `GET /` and the
   fixed set of built asset paths.
2. **SSE-over-fetch, not `EventSource`** (master spec §10.1 "fetch-readable... over POST"):
   `EventSource` cannot send a POST body, so `chat.ts` reads `response.body` as a stream and parses
   `id:`/`event:`/`data:` frames itself, matching F005's contract exactly.
3. **`react-markdown` without `rehype-raw`, custom `a`/`img` renderers** (FR-009): the library
   never parses embedded raw HTML into DOM without that plugin, so leaving it out is the sanitizer,
   not an afterthought bolted on. Links get `rel="noopener noreferrer"` and a scheme allowlist
   (`http`/`https` only); images are never fetched — rendered as a plain "image reference" link
   the user can choose to open, never an auto-loading `<img>`.
4. **Export is 100% client-side** (FR-016): the completed answer envelope already has everything
   required (question, claims, citations, snapshot ID, model identity); building the file client
   from that JSON avoids a new backend endpoint and guarantees no server path or credential can
   leak in, because the browser never had them to begin with.
5. **No background polling** (A-036): readiness is refetched only on load or an explicit user
   action, keeping the "no new log/network chatter" property visibly true rather than merely
   asserted.
6. **Guard exemption is narrow and route-shaped, not header-shaped** (A-034): rather than trusting
   a client-controllable header combination to decide "this is safe," the exemption is keyed on
   the server's own route table (is this a static GET the app intentionally serves publicly?) — an
   attacker cannot expand what a "cross-site" request is allowed to reach by sending different
   headers, because API routes never consult the exemption at all.
7. **License gate reuses one policy, two inventories**: `scripts/check_licenses.py` gains a second
   `run_npm_licenses()` collector; both Python and npm inventories are evaluated by the same
   `evaluate()`/`is_allowed()`/`is_copyleft()` functions and the same `config/license-exceptions.yaml`,
   so there is one allowlist to maintain, not two.

## Verification Strategy

| Requirement | Verification (layer) |
| --- | --- |
| FR-001–FR-003 | component: tab navigation, header content, full keyboard tab order over the main screen's controls |
| FR-004, FR-006, FR-006a | component: state-badge transitions from scripted capability/SSE fixtures; live-region fires once per transition; retry re-issues the same request; capabilities fetched once on load and again only after an explicit action |
| FR-005 | component: Stop aborts the fetch/stream (mocked `AbortController`), input re-enabled immediately |
| FR-007, FR-008 | component: citation activation opens panel with required fields; `Escape` closes and restores focus |
| FR-009, FR-010, SC-003 | component: hostile-Markdown fixture table (raw HTML, `javascript:`/`data:` links, remote `<img>`) renders inert; code blocks have copy, never a run control |
| FR-010a | contract: `GET /` response carries the exact CSP directive set incl. `frame-ancestors 'none'`; static asset responses need no CSP (not documents) |
| FR-011, FR-011a, SC-002 | unit: `client.ts` only ever builds same-origin `/api/v1/*`/`/health/*` URLs (no configurable base); pytest: guard exempts `GET /` and built asset paths, still rejects cross-site `POST /api/v1/*` |
| FR-012 | build-time check: bundle/asset URLs are all relative/same-origin (grep the built `index.html`/`assets/*` for any `http(s)://` third-party reference in CI) |
| FR-013, FR-014, FR-015, SC-004 | component: reload/new-conversation clears state; a storage-writing spy on `localStorage`/`sessionStorage`/`document.cookie` stays empty across a full ask→answer→export flow; no telemetry import exists in the dependency graph |
| FR-016, SC-005 | component: export produces the expected Markdown/JSON fixture with required identities and no absolute-path/credential-shaped string |
| FR-017 | component: snapshot switch with empty vs. non-empty conversation |
| FR-018 | component: search screen calls only `/api/v1/search`, never chat |
| FR-019, FR-020 | CI: `npm run build` succeeds and is deterministic given the lock; `check_licenses.py` covers the npm inventory with zero unresolved violations |
| SC-001 | manual recorded walkthrough (ask → citation) against the real backend; real-browser timing deferred to the owner |
| SC-006 | `axe-core` static pass in CI (zero violations for the rules it can evaluate under jsdom); manual keyboard-only walkthrough recorded; real screen reader deferred to the owner |

## Complexity Tracking

No constitution violations; section intentionally empty.
