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

## Phases 4–5 (User Stories 2 and 3 — normalization, inspect, exports) checkpoint — 2026-09-28

```
$ uv run ruff format --check . && uv run ruff check .   → 179 files formatted; All checks passed!
$ uv run mypy src                                        → Success: no issues found in 62 source files
$ uv run pytest -q                                       → 348 passed, 2 skipped (real_runtime)
$ uv run python scripts/check_licenses.py                → 41 packages, all allowed or reviewed
```

**Task-order deviation (recorded):** the export importer (US3: T051, T053) was implemented before
`NormalizationService` (T048) so normalization was written once with export support instead of a
throwaway "exports unsupported" branch. Dependencies allowed it; all US2/US3 tests ran in order.

### Prototype findings before writing the parser (research R2, now verified)

docutils line numbers are exact for paragraphs/list items/directives (section titles report the
underline line — corrected); an empty permissive option mapping is falsy and makes docutils swallow
`:id:` into the title (must define `__bool__`); `role` is both a docutils directive and an S-CORE
need type; `' .. document::` parses as a definition-list term.

### Real inspect over both sources — and what it found

First real run (before fixes): 918 vs 908 needs in `score-platform`, 8 `PARSE_ERROR`s. Each was
investigated rather than accepted:

1. **Real scope gap — MyST directives in Markdown.** The 10 needs present in the official export
   but not in our parse were all `dec_rec` needs in `DR-*.md` using MyST backtick directives.
   Implemented MyST fenced directives with the same profile semantics as RST (shared
   `ingestion/entities.py`), spec FR-010 extended, research R1 corrected.
2. **Directives inside grid-table cells** (`| .. centered:: …`) were not seen by the prescan →
   "Unknown directive" errors and lost text. Prescan now also matches after `|`.
3. **Card headings inside unknown directives** (sphinx-design `grid-item-card` with a `^^^`
   heading) were rejected by docutils (first as "unexpected section title", then as a title-level
   skip) → heading text lost. Generic bodies now parse with `match_titles` and a fresh title-style
   memo (Sphinx's `nested_parse_with_titles` technique).
4. **57 unresolved links are legitimate:** all are `:need:` references to `tool_req__docs_*` (and
   one `gd_req`) defined in a repository not yet ingested; none exists in either repo or either
   official export.

Mutation checks: the first regression test for (3) still passed with the fix removed (its snippet
did not reproduce a level skip); rewritten to mirror `docs/users_guide/index.rst`, it now fails
without the fix and passes with it. The test for (2) likewise fails without the fix.

### Final real results (quickstart C, D)

```
$ /usr/bin/time uv run score-assistant sources inspect --lock data/source-lock.json
score-platform @ e2373d8  selected 319  included 319  partial 0  failed 0  entities 918
  export consistency vs score-platform: matched 918  id-only 0  missing in source 0  missing in export 0
score-process @ 66321fe  selected 314  included 314  partial 0  failed 0  entities 1250
  export consistency vs score-process: matched 1250  id-only 0  missing in source 0  missing in export 0
wall ≈ 7 s
```

- **Need-set parity with the official Sphinx builds**: 918/918 and 1250/1250 matched by ID *and*
  file path, zero missing in either direction (SC-001 at corpus scale; the statistic never
  changes the exports' `unverified` status).
- SC-002: every selected file classified (`selected == included + partial + failed` in all
  sources); 0 `PARSE_ERROR`; all dynamic/unknown constructs carry diagnostics
  (`DYNAMIC_NOT_EVALUATED`, `UNKNOWN_DIRECTIVE`, `EXTERNAL_RESOURCE_NOT_READ`).
- SC-004: two real runs → byte-identical `documents.jsonl` (14 022 243 B) and `entities.jsonl`
  (6 936 671 B).
- SC-005: inspect ≈ 7 s (< 2 min).
- SC-006: all 2 168 export entities `unverified`.
- SC-007: 0 entities with `<` in their ID (code-block templates stayed inert).
- `requires review`: exactly the 3 CC-BY-SA-4.0 files in `score-process` (research R1).
- `ambiguous`: 0 (consistent with the corrected research finding).
- **Offline guarantee (quickstart D), proven for real**: inspect run inside a network namespace
  with no interfaces (`unshare -rn`) → exit 0, same results.

## Phase 6 (Polish) — 2026-09-28

Final local gate (T055): ruff format/check clean, mypy clean (62 source files),
`348 passed, 3 skipped` (2 `real_runtime`, 1 `real_network` — not run by default),
license check 41 packages allowed or reviewed.

- **T056 opt-in real-network test**: skipped by default ("contacts GitHub … not run"); with
  `SCORE_ASSISTANT_REAL_NETWORK=1` it performed a real sync of `score-process` from GitHub —
  `1 passed in 1.96s`. The socket guard is lifted only for tests carrying that marker.
  Caveat recorded honestly: the in-process socket guard cannot observe network use by the `git`
  subprocess; the default suite is offline because every git test uses `file://` fixtures and the
  offline commands (`validate`, `inspect`) are proven by tests that forbid subprocesses entirely.
- **T057 quickstart A–E on the workstation**: A (gate above); B real sync (Phase 3); C real inspect
  and D offline inspect in a network namespace (Phases 4–5); E failure safety, real:

  ```
  $ sed 's#eclipse-score/score.git#eclipse-score/does-not-exist-xyz.git#' config/sources.yaml > /tmp/broken.yaml
  $ uv run score-assistant sources sync --config /tmp/broken.yaml
  score-process: resolved main -> 66321fe…; extracted 314 files; score-process-needs: downloaded …
  Sync failed; previous lock left unchanged.            exit=1
  $ cmp data/source-lock.json /tmp/lock.before          → LOCK-UNCHANGED
  $ ls data/staging | wc -l                             → 0
  ```

  SC-003 tally: every hostile-fixture test (traversal/absolute/NUL/backslash paths, symlinked
  parents and leaves, symlink and gitlink tree entries, oversize file, include escape/absolute/
  missing/unselected/URL/standard/cycle/depth, non-HTTPS/credential/port/off-allowlist URLs,
  off-allowlist and non-HTTPS redirects, hooks + attribute filters + LFS pointer, malicious global
  gitconfig with an executable `packObjectsHook`) passes: 0 files outside the source root,
  0 requests to non-allowlisted hosts, 0 executions of repository or user-config content.
- **T058/T059 docs**: traceability rows for SRC-001–008, SRC-010–012, SEC-005 filled with real
  paths/tests/evidence; backlog, assumptions (A-013 fixed pending owner confirmation of the
  docutils exception; A-016 MyST; A-017), toolchain, README and CLAUDE.md updated.
  **Doc defect found in F001:** README and CLAUDE.md documented `doctor --config …` and
  `serve --config …`, which fail with "No such option: --config" (the global option goes before
  the subcommand). Corrected, and every documented command was re-run: `doctor` 0,
  `sources validate` 0, `sources inspect` 0, `serve` started (stopped by timeout, port 8080 free
  afterwards).

## `/speckit-converge` — 2026-09-28

First pass (independent re-read of 25 FRs, 7 SCs, acceptance scenarios, edge cases, plan
decisions, contracts, constitution) found **5 gaps**, appended as Phase 7:

| ID | Gap | Severity | Fix (task) |
| --- | --- | --- | --- |
| F1 | `SourceAdapter` protocol declared but not implemented (plan + constitution VI) | HIGH | `sources/adapters.py`: `GitSourceAdapter`, `ExportSourceAdapter`; `SyncService` now orchestrates only (T061); mypy statically checks protocol conformance |
| F2 | Report counted partially-parsed files but did not list them (FR-023) | MEDIUM | `partial_files` with warning codes in JSON and text (T062) |
| F3 | `HASH_MISMATCH` only a source-level string, no per-file diagnostics (contract) | LOW | one error diagnostic per file, also listed under `failed` (T063) |
| F4 | `UNSUPPORTED_FILE_TYPE` emitted but absent from the contract catalogue | LOW | contract updated (T064) |
| F5 | Malformed `:need:` role targets produced no `MALFORMED_LINK` diagnostic | LOW | emitted in `rst/roles.py` (T065) |

Each code fix went test-first (confirmed red, then green). After the adapter refactor, a real
re-sync against GitHub produced a lock identical to the previous one except timestamps and the
`required` field (absent in the older lock, now correct), and real inspect results were unchanged
(918/918, 1250/1250 parity).

Follow-up pass: **0 findings — ✅ Converged.** `tasks.md` unchanged by the second pass.

```
$ uv run ruff format --check . && uv run ruff check .   → 182 files formatted; All checks passed!
$ uv run mypy src                                        → Success: no issues found in 63 source files
$ uv run pytest -q                                       → 350 passed, 3 skipped (opt-in: 2 real_runtime, 1 real_network)
```

## Project-owner decision — 2026-09-28

The docutils license exception (agent review, research R3) was **accepted by the project owner**,
who asked the agent to record it; `config/license-exceptions.yaml` and `docs/ASSUMPTIONS.md` A-013
now say so. This was the last open F002 item.

## Blockers

(none)
