# Quickstart / Validation Guide: F006

Starting point: F005 done, an active snapshot exists, and (for section C) Ollama on loopback with
the locked models. `C=config/local.yaml`. Contract: [contracts/ui-contract.md](contracts/ui-contract.md).

## A. Frontend deterministic checks (no backend needed)

```bash
cd frontend
npm ci
npm run lint
npm run typecheck
npm test
npm run build          # emits frontend/dist/
```

Expected: all pass; `frontend/dist/index.html` and hashed `frontend/dist/assets/*` exist.

## B. Backend deterministic checks

```bash
uv run ruff format --check . && uv run ruff check . && uv run mypy src
uv run pytest tests/contract/test_guard.py tests/contract/test_static_serving.py
uv run pytest
uv run python scripts/check_licenses.py
```

Expected: the guard tests show the static-GET exemption applies only to `/` and `/assets/*`, and
that `/api/v1/*`/`/health/*` reject `Sec-Fetch-Site: cross-site` exactly as before (AT-18
unchanged). `check_licenses.py` reports both the Python and (once `frontend/package-lock.json`
exists) the npm inventory.

## C. Real end-to-end walkthrough (manual — no browser automation available)

```bash
uv run score-assistant --config $C serve &
```

Open `http://127.0.0.1:8080/` in an actual browser (this step is performed by the project owner —
no browser may be installed in this development environment) and walk through:

1. Ask a covered question → observe queued/searching/generating/validating states, then a
   rendered answer with citation markers (User Story 1, SC-001).
2. Open a citation → evidence panel shows title/heading/revision/excerpt; `Escape` closes it and
   returns focus (FR-007, FR-008).
3. Reload the page → conversation is empty; open browser dev tools → Application → Storage:
   `localStorage`/`sessionStorage`/cookies contain nothing chat-related (FR-013, SC-004).
4. Export the answer as Markdown and as JSON → both files contain the question, claims, citations,
   snapshot ID and model identity, and no absolute path (FR-016, SC-005).
5. Open the browser's Network tab while repeating steps 1–4 → every request targets
   `127.0.0.1:8080`; zero requests to any other host (SC-002).
6. Disconnect the generation model (stop Ollama) and reload → chat shows "generation unavailable"
   with guidance; search still returns results (FR-004, User Story 2).
7. Tab through the entire flow using only the keyboard, including opening/closing the evidence
   panel and the snapshot selector (User Story 4).

Record the actual outcome of C in `verification.md`, honestly, as either "run by the owner on
<date>, passed/failed" or "not run — deferred to the owner" per constitution Principle VII. This
run's own agent session cannot execute section C because no browser is installed here.

## D. Hostile rendering fixtures (automated, section A's `npm test`)

`test/components/SafeMarkdown.test.tsx` feeds fixture Markdown containing raw `<script>`/`<img
onerror=...>` HTML, a `javascript:` link, a `data:text/html` link, and a remote `<img>`
reference, and asserts: no script executes (jsdom would throw/record if it tried), no `<img>` DOM
node is ever created, and the unsafe links render as inert text or a neutralized `href`.

## E. Snapshot-switch confirmation (automated)

`test/components/search-snapshot-export.test.tsx` (SnapshotSelector cases) asserts: switching snapshots with zero turns applies
immediately (no dialog); switching with ≥ 1 turn shows a confirmation dialog, and only confirming
clears the conversation and applies the new snapshot (FR-017, A-035).
