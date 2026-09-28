# Verification: F002 Source Registry and Safe Document Normalization

Real commands and results, recorded as run. "Not run" is recorded explicitly with a reason
(constitution VII) — it is never reported as passed.

## Phase 1 (Setup) + Phase 2 (Foundational) checkpoint — 2026-09-28

```
$ uv lock && uv sync --locked            # + docutils 0.23, markdown-it-py 4.2.0, types-docutils
$ uv run ruff format --check . && uv run ruff check .
143 files already formatted; All checks passed!
$ uv run mypy src
Success: no issues found in 46 source files
$ uv run pytest -q
234 passed, 2 skipped (real_runtime, not run)
$ uv run python scripts/check_licenses.py
License check passed: 41 packages, all allowed or reviewed.
```

### Findings during this checkpoint

1. **F001 license-gate defect confirmed with real data (A-013).** Before the fix, the gate
   reported `41 packages, all allowed` with docutils present, although pip-licenses reports
   docutils as `BSD License; GNU General Public License (GPL); Public Domain`. After T003 the same
   run fails naming docutils; it passes again only through the `config/license-exceptions.yaml`
   entry, which is labelled **agent review, pending project-owner confirmation** — not presented
   as a human review.
2. **Research R1 claim corrected.** While selecting fixtures (T008), the claimed cross-repository
   ID collision (`doc__platform_mgt_plan` in both repos) turned out to be an artifact of the naive
   grep used for sampling: in `process_description` the ID follows `' .. document::` (leading
   apostrophe → plain paragraph) or is template text. Both published exports were checked: they
   share **0** IDs. Spec, research, tasks, quickstart and contracts were corrected; the quoted
   pseudo-directive became a golden test case. Namespaced keys remain (master spec §9.1).
3. **Design gap fixed: the lock is now self-contained for source facts.** `sources inspect` takes
   only `--lock`, but needs `parser_profile`, `repository_license`, the redistribution allowlist,
   `associated_source` and `docs_root`. Re-reading `config/sources.yaml` at inspect time could mix
   a newer registry with an older sync, so these are recorded in the lock (contracts/lock.md,
   data-model.md, contracts/cli.md `--profiles-dir`).
4. New real construct added to tests: link values continued over several indented lines
   (`:complies:` spanning 9 lines upstream).

## Blockers

(none)
