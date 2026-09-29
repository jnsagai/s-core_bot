# Verification Record: F006 Local Web Experience and Privacy

Commands actually run, with results. Categories (constitution VII): **component tests** (Vitest +
jsdom + Testing Library, no real browser), **backend tests** (pytest), **real backend** (real
snapshot and local models, exercised over HTTP). **No browser exists on this machine**: every check
that needs a real browser is recorded as "not run — no browser on this machine" and is deferred to
the owner.

## Phases 1–2 and T011–T013 (overnight run, verified 2026-09-29)

The unattended overnight run (log: `overnight.log`) produced these commits and then stopped at
22:50 UTC on the account's session usage limit, before recording any verification or ticking
tasks. The work was verified the next morning:

```text
$ uv run ruff format --check . && uv run ruff check . && uv run mypy src
347 files already formatted / All checks passed! / Success: no issues found in 111 source files
$ uv run pytest -q
870 passed, 9 skipped (opt-in markers, not run)
$ cd frontend && npm ci && npm run lint && npm run typecheck && npm test && npm run build
npm ci ok; eslint: no problems; tsc --noEmit: ok
Test Files 9 passed (9)   Tests 32 passed (32)
dist/assets/index-DoNsp7ly.js 219.71 kB │ gzip: 68.62 kB   ✓ built
```

- T001–T002: scaffold with pinned versions and the lockfile; scripts `lint`, `typecheck`, `test`,
  `build`, `license-check`. Checkpoint met (`frontend/dist/index.html` + `assets/*` built).
- T003–T004, T007–T008: `client.ts` (same-origin relative paths only; error-envelope parsing) and
  the SSE parser, with tests.
- T005, T009: the guard exemption for cross-site `GET /` and `/assets/*` only, with tests. **Deviation**:
  the tests are in the existing `tests/contract/test_guard.py`, not in a new `tests/unit/test_guard.py`.
- T006, T010: static serving (CSP + no-store on `/`, 404 for unknown assets, honest 503 without a
  build; API routes take precedence), with `tests/contract/test_static_serving.py`.
- T011–T013: typed API modules, the conversation reducer and `SafeMarkdown`, with tests.
- An uncommitted `frontend/src/components/StatusBadge.tsx` (T014, unfinished) was left by the run;
  T014 completes it.

## Phases 3–8 (T014–T037), 2026-09-29

### Full gate

```text
$ uv run ruff format --check . && uv run ruff check . && uv run mypy src
348 files already formatted / All checks passed! / Success: no issues found in 111 source files
$ uv run pytest -q
873 passed, 9 skipped (opt-in markers, not run)
$ uv run python scripts/check_licenses.py
License check passed: 470 packages, all allowed or reviewed.   (42 Python + 428 npm)
$ cd frontend && npm run lint && npm run typecheck && npm test && npm run build
eslint: 0 problems; tsc: ok; Tests 60 passed (60); dist/assets/index-*.js 401.84 kB (gzip 123.50 kB)
$ npm run check-no-third-party-assets && npm run check-no-telemetry
third-party asset check passed; telemetry check passed: 23 dependencies
```

### Component tests (Vitest + jsdom, no browser)

- US1 (T014–T019): status labels and queue position; the live region announces each distinct
  state once; answer view groups claims (interpretation labelled, limitations, sources); the
  evidence dialog shows section, lines, revision, the local excerpt and a labelled upstream link
  with `rel="noopener noreferrer"`, and the local excerpt is shown without a link too; Escape closes
  it and restores focus; the header identity; tabs switch without reload; the full SSE flow queued →
  validating → ready with the exact request body and `Accept: text/event-stream`; a follow-up sends
  the previous answer as snapshot-bound history; the question length uses the server's limit.
- US2 (T020–T022): Stop aborts the request (the signal is aborted) and Retry re-issues the same
  question; an error after progress keeps the turn and shows the reason and a Retry; 429 is shown
  once with no automatic retry; chat-unavailable guidance keeps search available; an unreachable API
  on load shows Retry and **no background polling** (one call until Retry).
- US3 (T023–T027): **privacy spy** over ask → answer → export: zero `Storage.setItem`, zero cookie
  writes, no console output containing the question or answer text, and every request goes to
  `/api/v1/*` or `/health/*`; snapshot switch applies at once when empty and needs confirmation
  when not (cancel keeps, confirm clears); New conversation and remount start empty with empty
  history; Markdown/JSON exports carry question, claims, citations, snapshot and model identity,
  with no absolute path or credential-shaped strings; export only for a completed answer, via Blob.
  The telemetry check script found no analytics/telemetry SDK.
- US4 (T028–T031): **axe-core** on the main screen with an answer and on the evidence dialog: 0
  violations. Rules run: all axe rules except `color-contrast` and `scrollable-region-focusable`,
  which need real layout/paint (**not run — no browser on this machine**). Keyboard: every
  control is reachable by Tab with an accessible name, in the order snapshot → New conversation →
  tabs → answer controls → question. Focus trap: Tab and Shift+Tab cycle inside dialogs, and Escape
  restores focus (evidence dialog and snapshot confirmation).

### License gate and CI (T032–T034a)

- The npm inventory now includes dev dependencies, and SPDX expressions are evaluated strictly.
  **Defect found and fixed**: the allow keyword `UNLICENSE` substring-matched npm's `UNLICENSED`
  ("no license granted"). BlueOak-1.0.0 and CC0-1.0 were added to the allowlist, and three dev-only
  CC-BY data packages pass via reviewed exceptions (A-038). Unit tests cover all of this.
- `check-no-third-party-assets` was shown to fail on a planted `https://cdn.example.com/x.js` in a
  built asset (exit 1) and to pass after rebuilding.
- CI: new `frontend` job (npm ci, lint, typecheck, test, build, asset and telemetry checks, using the
  runner's preinstalled Node), plus `npm ci` before the license check in the Python job. Making the
  job a *required* status check is a GitHub branch-protection setting, which the agent does not
  change: **left to the owner**. Merges already wait for all checks to be green.

### Real backend over HTTP (no browser)

```text
GET /                      → 200 text/html, CSP "default-src 'self'; …; frame-ancestors 'none'; …", no-store
GET /assets/index-*.js     → 200 text/javascript
GET / (Sec-Fetch-Site: cross-site)                    → 200   (static exemption)
GET /api/v1/capabilities (Sec-Fetch-Site: cross-site) → 403   (API unchanged)
GET /assets/nope.js        → 404 (never index.html)
UI calls: capabilities → search/chat available, question limit 4000; snapshots → active + 3;
SSE chat (same-origin headers) → progress ×3, answer, done; question text in server log: 0
```

### Not run (deferred to the owner, A-040)

Quickstart §C in a real browser: the first-run-to-citation walkthrough, the Network-tab proof that
no request leaves 127.0.0.1, the storage inspector after reload, keyboard-only review, colour
contrast and screen reader.

## Quickstart walk (T038), 2026-09-29

| Section | Result |
| --- | --- |
| A. Frontend checks | lint 0 problems; typecheck ok; `vitest run` 13 files / 60 tests passed; build emits `dist/index.html` + `dist/assets/index-DJTwm2Gf.js` (401.84 kB, gzip 123.50 kB); asset and telemetry checks passed |
| B. Backend checks | ruff format (349 files) + ruff check + mypy (111 files) clean; `pytest tests/contract/test_guard.py tests/contract/test_static_serving.py` 24 passed; full `pytest` 873 passed, 9 skipped (opt-in); license check 470 packages OK (Python + npm) |
| C. Real browser walkthrough | **not run — no browser on this machine, deferred to the owner** (A-040). The HTTP-level substitute above (real server: CSP, static exemption, SSE flow, no question text in log) was run |
| D. Hostile rendering | `SafeMarkdown.test.tsx` passed (raw `<script>`/`<img onerror>` inert, `javascript:`/`data:` links neutralized, no `<img>` node created) |
| E. Snapshot-switch confirmation | SnapshotSelector cases in `search-snapshot-export.test.tsx` passed (D + E files: 16 tests) |

## Convergence (agent review), 2026-09-29

✅ Converged — FR-001–FR-020 (incl. FR-006a, FR-010a, FR-011a), SC-001–SC-006, the plan's decisions
and constitution I–XII checked against the code; no missing, partial or contradicting items, so no
Convergence phase was appended to `tasks.md`. The real-browser parts of SC-001, SC-002 and SC-006
remain deferred to the owner (A-040).

Deviation (file layout only): the planned per-component test files were consolidated.
`test/components/components.test.tsx` covers StatusBadge/LiveRegion, AnswerView/EvidencePanel,
Header/App/ChatPanel and readiness (no polling), and `test/components/search-snapshot-export.test.tsx`
covers SearchPanel, SnapshotSelector, New conversation and Export. `test/a11y/accessibility.test.tsx`
covers axe, keyboard order and focus trap, and `test/privacy/no-storage-writes.test.tsx` covers
privacy. Each `describe` block names its task ID.
