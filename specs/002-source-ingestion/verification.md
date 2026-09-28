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

## Phase 3 (User Story 1 — acquisition, MVP) checkpoint — 2026-09-28

```
$ uv run ruff format --check . && uv run ruff check .   → 155 files formatted; All checks passed!
$ uv run mypy src                                        → Success: no issues found in 51 source files
$ uv run pytest -q                                       → 268 passed, 2 skipped (real_runtime)
```

### Mutation check: the "global git config ignored" test was initially insensitive

`test_hooks_filters_lfs_and_global_config_never_execute` first passed even against a deliberately
weakened client (no `core.hooksPath` override, global gitconfig honoured): our flow (`init
--bare`, fetch-by-SHA, `ls-tree`, `cat-file`) never checks out and never updates a ref, so no
hook event fires — the override is defense in depth, and the test proved nothing. Fixed by adding
a vector that *does* apply: for `file://` fetches git runs `upload-pack` locally, which honours a
**global** `uploadpack.packObjectsHook` (program execution). Re-run of the mutation check:

```
hardened: exit=0 marker created = False
weakened (global config honoured): exit=0 marker created = True
```

The test now fails if the environment hardening is removed.

### Real sync against GitHub / GitHub Pages (quickstart B)

```
$ uv run score-assistant sources validate --config config/sources.yaml     → valid (4 sources), exit 0
$ /usr/bin/time uv run score-assistant sources sync --config config/sources.yaml --json
score-platform: resolved main -> e2373d822fc2f6e9a3f8a0538904f3faa39309ea
score-platform: extracted 319 files, skipped 0
score-platform-needs: downloaded 718776 bytes
score-process: resolved main -> 66321fe6bd131eae58fbd6395b0f0b92d63e00f5
score-process: extracted 314 files, skipped 0
score-process-needs: downloaded 1236569 bytes
wall=6.01s   exit 0
```

- SC-005 (sync < 5 min): **6.0 s**.
- Resolved SHAs equal the commits sampled in research R1.
- Lock: git sources `pinned`, LICENSE + NOTICE in `notice_files` (outside the selectors),
  `excluded_by_selector` 157 / 75; exports `unverified` with `docs_root` `docs` / `process`;
  `release_mapping: null` everywhere.
- On disk: 0 files not mode 0444, 0 symlinks, 0 staging leftovers; 7.7 MB sources, 9.5 MB git cache.
- Re-sync: identical revisions and file lists (revision directories reused).

## Blockers

(none)
