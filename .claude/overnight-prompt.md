# Overnight autonomous run — F001 implementation

You are running unattended overnight with nobody watching. Nothing you do here reaches the
internet, a paid API, or another person unless this file says so. When in doubt, do the safer,
more reversible thing and record why in the log — never guess and hide it.

## Scope for tonight, in order

1. **Implement F001** by working `specs/001-foundation/tasks.md` top to bottom, exactly as
   `.claude/skills/speckit-implement/SKILL.md` describes (respect `[P]` parallel markers within a
   phase; do not start a later phase before its dependencies checkpoint).
2. After each of these checkpoints, stop implementing, run the full local gate, and commit before
   continuing to the next phase:
   - Phase 2 (Foundational) — checkpoint at tasks.md:72
   - Phase 3 (User Story 1 / MVP) — checkpoint at tasks.md:96
   - Phase 4 (User Story 2) — checkpoint at tasks.md:123
   - Phase 5 (User Story 3) — checkpoint at tasks.md:146
   - Phase 6 (User Story 4) — checkpoint at tasks.md:166
   - Phase 7 (Polish) — after T063
3. Once `tasks.md` is fully checked off and the local gate is green, run `/speckit-converge`
   (`.claude/skills/speckit-converge/SKILL.md`). If it appends a Convergence phase, implement those
   tasks too (same commit discipline), then run `/speckit-converge` again. Stop once it reports
   "✅ Converged".
4. If F001 converges with time and budget left (see Budget below), and only then: run
   `/speckit-specify`, `/speckit-clarify`, `/speckit-plan`, `/speckit-checklist`, `/speckit-tasks`,
   `/speckit-analyze` for **F002 Source registry and safe document normalization**
   (`docs/PROJECT_SPEC.md` §16 F002; directory `specs/002-source-ingestion/`), the same way F001's
   artifacts were produced. **Do not run `/speckit-implement` for F002.** Leave it for human review
   in the morning.

## The local gate (run before every commit in step 2)

```bash
uv run ruff format --check . && uv run ruff check .
uv run mypy src
uv run pytest
uv run python scripts/check_licenses.py   # once it exists (after T056)
```

A phase is not done until this gate passes. Fix failures before moving on; do not comment out or
skip a failing test to get green. If a task's own acceptance criterion (in tasks.md or spec.md)
cannot be met after genuine effort, stop implementing that one task, leave it unchecked, write why
in `specs/001-foundation/verification.md`, and move on to independent tasks — do not silently mark
it done.

## Commit steps (repeat at each stopping point above)

```bash
git status --short          # review what changed
git add -A
git commit -m "<type>(f001): <what this phase/task group delivers>

<1-3 lines: which tasks (Txxx-Txxx), what the local gate showed>

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

Use `feat` for new functionality, `test` for test-only commits, `docs` for traceability/backlog
updates, `chore` for tooling. One commit per checkpoint is fine; smaller commits within a phase are
also fine if a natural boundary appears (e.g. tests-red before implementation-green). Never use
`--amend` or `--force`, never rewrite history, never touch a commit made before tonight.
Push the feature branch after each checkpoint commit (see Hard rules).

## Verification discipline (constitution VII — non-negotiable)

- Only check off a `tasks.md` item after its test(s) actually ran and passed. An unrun check is
  "not run", never "passed".
- Two `quickstart.md` scenarios cannot run unattended tonight:
  - **Scenario B** needs `sudo snap stop ollama` — sudo is unavailable to you tonight.
  - **Scenario D** downloads real models (`models pull`) — disabled tonight (disk is ~95% full and
    this must never happen without a human watching).
  Record both as "not run — requires sudo / disk headroom, deferred to human review" in
  `specs/001-foundation/verification.md`, with the reason. Everything else in quickstart.md that
  does not need those two things should actually be run and its real output recorded.
- The `real_runtime` and any real-pull-gated tests stay opt-in and skipped, exactly as tasks.md
  specifies; report them as skipped, not passed.
- Update `docs/TRACEABILITY.md` and `docs/BACKLOG.md` (F001 → in-progress, then verified/done) as
  part of the Phase 7 / converge commit, not before.

## Hard rules

- No `sudo`, no `git reset --hard`/`git clean`, no model downloads (`models pull`,
  `ollama pull`), no starting/stopping the Ollama service. These are blocked by
  `.claude/settings.json`; do not look for a workaround if one is blocked — that block is
  intentional, not a bug to fix.
- Pushing is allowed only for the current feature branch, after a checkpoint commit whose local
  gate passed (`git push -u origin <feature-branch>`). Never force-push, never delete remote
  branches, never push to `main` (all blocked by `.claude/settings.json`). After pushing, check the
  CI run with `gh run list` / `gh run view --log-failed` and fix real failures.
- No network access except to `http://127.0.0.1:*` (the local runtime and the service you start
  for integration tests). If a task seems to need anything else, stop that task, note it, move on.
- Follow `CLAUDE.md` and `.specify/memory/constitution.md` for everything not covered above.
- Stay on branch `001-foundation`. Do not create or switch branches.
- Kill any `serve` process you start for a test before moving on (`kill` the PID); do not leave
  background servers running between phases.

## If you get stuck

If the same task fails after two genuinely different fix attempts, or you hit a blocked action
with no safe alternative: stop working on that item, write a clear note (what you tried, what
failed, what a human needs to decide) at the top of `specs/001-foundation/verification.md` under
a `## Blockers` heading, commit what is otherwise in good shape, and move on to the next
independent task. Do not spin retrying the same thing, and do not silently drop the requirement.

## Budget and stopping

Work steadily; there is no fixed task quota. Stop the whole run (leave everything committed and
clean, `git status --short` empty) when any of these happens first:
- F001 has converged and, if time remains, F002 is specified/planned/tasked/analyzed (not
  implemented) as described in step 4.
- You have been running for about 7 hours.
- You hit a blocker that stops all remaining independent tasks (write it under `## Blockers` as
  above).

End the session with a short final message summarizing: which phases/tasks completed, the local
gate's last result, anything recorded under Blockers, and the exact next command a human should
run (e.g. `/speckit-implement` to resume, or review `specs/002-source-ingestion/` if reached).
