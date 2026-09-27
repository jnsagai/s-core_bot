# Verification: F001 Foundation and Local Runtime Contract

Real commands and results, recorded as run. "Not run" is recorded explicitly with a reason
(constitution VII) — it is never reported as passed.

## Phase 1 (Setup) + Phase 2 (Foundational) checkpoint — 2026-09-27

Commands actually run, in order, from the repository root:

```
$ uv lock
Resolved 42 packages in 677ms

$ uv sync --locked
... (42 packages installed; versions match research.md R2 exactly — recorded in docs/toolchain.md)

$ uv run ruff format --check .
79 files already formatted

$ uv run ruff check .
All checks passed!

$ uv run mypy src
Success: no issues found in 21 source files

$ uv run pytest tests/unit -q
50 passed in 0.16s
```

`scripts/check_licenses.py` does not exist yet (created in T056, Phase 6) — not run this checkpoint,
per tasks.md.

### Notes

- Local workstation sources `/opt/ros/iron/setup.bash`, which adds ROS's Python 3.10 site-packages
  to `PYTHONPATH`. pytest's setuptools entry-point scan discovered ROS's `pytest11` plugins and
  crashed importing Python-3.10-only modules under our Python 3.12 venv. Fixed by blocking those
  plugin names in `pyproject.toml`'s pytest `addopts` (see `docs/ASSUMPTIONS.md` A-009); harmless
  no-op on machines without ROS installed (including CI).
- Tasks T001–T028 (Phase 1 Setup, Phase 2 Foundational) are checked off in `tasks.md`. Tests and
  implementation for each module were written together in this checkpoint (not strict red-then-
  green per task); the first `uv run pytest` run against the completed pair caught two real bugs
  (a userinfo-detection logic error in `runtime.base_url` validation, and a `redact_text` regex
  that stopped at the first token instead of the whole value) — both are fixed and covered by the
  fixtures that caught them.
- No `real_runtime` tests exist yet at this checkpoint (they arrive with US3, Phase 5).

## Blockers

(none yet)
