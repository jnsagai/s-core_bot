# Overnight autonomous run — F006 Local web experience and privacy

You are running unattended overnight with nobody watching. Nothing you do here reaches the
internet, a paid API, or another person unless this file says so. When in doubt, do the safer,
more reversible thing and record why — never guess and hide it.

## Context

F001–F005 are done and merged (see `docs/BACKLOG.md`). The backend already serves:
`/health/*`, `/api/v1/capabilities`, `/api/v1/search`, `/api/v1/entities`, `/api/v1/relationships`,
`/api/v1/snapshots`, `/api/v1/sources`, `/api/v1/citations/{snapshot}/{chunk}` and
`POST /api/v1/chat` (JSON, or SSE with `Accept: text/event-stream`). Read `CLAUDE.md`,
`.specify/memory/constitution.md`, `docs/PROJECT_SPEC.md` (§11, §12, §16 F006) and the F004/F005
contracts under `specs/004-hybrid-search/contracts/` and `specs/005-grounded-chat/contracts/` first.
Owner instructions for the workflow are in `~/.claude/projects/-home-jefferson-s-core-bot/memory/`
(full autonomy: answer clarify questions yourself, label them "agent review", record them in
`docs/ASSUMPTIONS.md`).

You are on branch `006-local-web-ui`. Stay on it. Do not create or switch branches.

## Scope for tonight, in order

1. Run the Spec Kit workflow for **F006** (`specs/006-local-web-ui/`; primary requirements UX-001–
   UX-005, SEC-002, SEC-003, OPS-001): `/speckit-specify`, `/speckit-clarify` (answer yourself),
   `/speckit-plan`, `/speckit-checklist`, `/speckit-tasks`, `/speckit-analyze`,
   `/speckit-implement`, `/speckit-converge` (repeat implement/converge until it reports
   converged). Skills live in `.claude/skills/speckit-*/SKILL.md`. Set `.specify/feature.json` to
   `specs/006-local-web-ui` first.
2. Frontend per the constitution: TypeScript + React + Vite in `frontend/`, built to static files
   that the FastAPI backend serves (no separate server in production, no CDN, all assets bundled
   locally). Keep it small and dependency-light. Lock dependencies (`package-lock.json`), add the
   frontend build/test/lint to CI, and extend the license gate to frontend dependencies (same
   allowlist rules as `scripts/check_licenses.py`; record any exception with a reason).
3. Commit at each checkpoint in `tasks.md` (after the local gate passes) and push the branch.
   When converged: open a PR to `main` with `gh pr create` (description ends with the Claude Code
   attribution line). **Do not merge it** — the owner reviews it in the morning.

## The local gate (run before every commit)

```bash
uv run ruff format --check . && uv run ruff check .
uv run mypy src
uv run pytest
uv run python scripts/check_licenses.py
cd frontend && npm run lint && npm run typecheck && npm test && npm run build   # once frontend exists
```

A phase is not done until this gate passes. Fix failures; never comment out or skip a failing test
to get green. If a task cannot meet its acceptance criterion after genuine effort, leave it
unchecked, write why in `specs/006-local-web-ui/verification.md`, and move to independent tasks.

## Verification discipline (constitution VII — non-negotiable)

- Only check off a task after its verification actually ran and passed. Unrun = "not run".
- **No browser is installed** and you must not download one (no Playwright/Chromium/Puppeteer
  browser downloads). Test components with the Node test runner of your choice (e.g. Vitest +
  jsdom) and the backend with pytest/TestClient. The real "first-run-to-citation in a browser",
  keyboard-only review and automated accessibility run in a real browser are **deferred to the
  owner**: record them as "not run — no browser on this machine" in `verification.md`.
- You may run the real backend with the real local models for API-level checks (start `serve` in
  the background, `kill` its PID afterwards, never leave it running).
- Keep the security properties already in place: loopback bind, Host/Origin guard, no bodies in
  logs, sanitized rendering (no raw HTML from Markdown or sources, safe links, no remote images),
  chats only in memory (cleared on reload), exports without absolute machine paths.

## Hard rules

- Network: only `http://127.0.0.1:*`, **plus** the public npm registry for installing locked
  frontend dependencies with `npm install` / `npm ci` inside `frontend/`. Nothing else: no CDNs,
  no browser downloads, no model downloads (`models pull`, `ollama pull`), no `curl` to the
  internet, no `npx` of arbitrary packages.
- No `sudo`, no `git reset --hard`, no `git clean`, no `--force`/`--amend`, no history rewriting,
  never push to `main`, never merge PRs, never delete branches. Never touch data you did not create
  (`data/` snapshots, `~/.fabro`, other repos).
- Do not change `.claude/settings.json`, the constitution, or this file.
- **Disk**: the machine's disk is nearly full and something outside this project keeps writing to
  it. Before each phase run `df -h /`. If less than 3 GiB is free, stop: commit what is green,
  push, write a note under `## Blockers` in `specs/006-local-web-ui/verification.md`, and end the
  session. (The launcher also stops the run below 2 GiB.)
- Follow `CLAUDE.md` for everything not covered here. Commit messages end with
  `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.

## If you get stuck

If the same task fails after two genuinely different attempts, or a needed action is blocked:
stop that item, write what you tried and what a human must decide under `## Blockers` in
`specs/006-local-web-ui/verification.md`, commit what is otherwise green, and continue with the
next independent task. Do not spin, and do not silently drop a requirement.

## Stopping

Stop (everything committed and pushed, `git status --short` empty, no background processes left)
when the first of these happens: F006 converged and the PR is open; about 7 hours have passed; a
blocker stops all remaining work; free disk < 3 GiB.

End with a short summary: phases/tasks completed, last local gate result, anything under
Blockers, what was deferred to the owner (browser checks), and the PR URL if opened.
