# Verification Record: F003 Immutable Snapshots and Local Embedding Index

Commands actually run, with results. Categories are kept apart (constitution VII):
**mocked** (deterministic tests with `FakeEmbeddingProvider`), **real runtime** (local Ollama),
**real build** (the pinned F002 lock on the workstation). "Not run" means not run.

## Phases 1–2 (Setup, Foundational) — 2026-09-28

```text
$ uv lock && uv sync --locked                      # + numpy 2.5.3
$ uv run python scripts/check_licenses.py --write-notices
License check passed: 42 packages, all allowed or reviewed.
$ uv run ruff format --check . && uv run ruff check . && uv run mypy src
Success: no issues found in 82 source files
$ uv run pytest -q
385 passed, 3 skipped
```

- **Pre-existing test defect found and fixed**: `tests/contract/test_cli_models.py`
  `test_pull_writes_lock_and_second_run_is_already_present` and `test_pull_refuses_remote_model`
  read the workstation's real free disk space. They failed both with and without F003 changes
  (confirmed with `git stash`) once the root filesystem dropped to 4.3 GiB free, below the
  profile size. Both now patch `shutil.disk_usage` like the neighbouring disk-shortfall test does.
- **Environment note**: root filesystem free space fell from 11 GiB to 4.3 GiB (99 % used)
  during this session. This project's `data/` is 18 MB and the new dependency about 50 MB; the
  growth is elsewhere on the machine. It is a risk for real builds (the build precheck needs
  2 GiB plus the newest snapshot).
