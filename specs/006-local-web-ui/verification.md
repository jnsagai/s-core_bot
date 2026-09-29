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
