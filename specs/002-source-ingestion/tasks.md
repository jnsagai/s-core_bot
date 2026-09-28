---

description: "Task list for F002 Source Registry and Safe Document Normalization"
---

# Tasks: F002 Source Registry and Safe Document Normalization

**Input**: Design documents from `specs/002-source-ingestion/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: MANDATORY (constitution VII). Within each story, write tests first and confirm they
fail before implementing. Fixture files are created by the test task that first needs them;
synthetic fixtures carry a `SYNTHETIC — not S-CORE guidance` comment.

**Organization**: grouped by user story; each task lists the requirement IDs it serves.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on incomplete tasks)
- **[Story]**: US1–US3 from spec.md
- Paths are repository-relative (package root `src/score_docs_assistant/`)

---

## Phase 1: Setup (Shared Infrastructure)

- [ ] T001 Add `docutils>=0.23` and `markdown-it-py>=4.2.0` to `[project].dependencies` in `pyproject.toml`; run `uv lock` and `uv sync --locked`; record resolved versions in `docs/toolchain.md` (FR-025, research R2, R4)
- [ ] T002 Extend `tests/unit/test_check_licenses.py`: a string naming a permissive and a copyleft license (e.g. `BSD License; GNU General Public License (GPL); Public Domain`) fails without an exception; passes with a reviewed exception; `Apache-2.0 OR BSD-2-Clause` still passes; `LGPL`, `AGPL`, `CC-BY-SA` variants fail (FR-025)
- [ ] T003 Implement the copyleft rule in `scripts/check_licenses.py` (copyleft identifiers override permissive keywords unless the package has a reviewed exception) — makes T002 pass (FR-025, research R3)
- [ ] T004 Add a reviewed `docutils` entry to `config/license-exceptions.yaml` citing research.md R3 (only GPL file `tools/editors/emacs/rst.el` is not in the wheel); regenerate `THIRD_PARTY_NOTICES.md` via `uv run python scripts/check_licenses.py --write-notices` (FR-025, SRC-012)
- [ ] T005 [P] Create `config/parser-profiles/s-core.yaml` exactly per contracts/registry.md, with a provenance comment citing research.md R1 and commits `e2373d8`/`66321fe` (FR-011, FR-013)
- [ ] T006 [P] Create `config/sources.yaml` exactly per contracts/registry.md (4 sources, allowlist, limits) (FR-001, FR-002, FR-007)
- [ ] T007 [P] Create packages `src/score_docs_assistant/sources/__init__.py`, `src/score_docs_assistant/ingestion/__init__.py`, `src/score_docs_assistant/ingestion/rst/__init__.py`, and `tests/helpers/__init__.py`
- [ ] T008 [P] Create `tests/fixtures/upstream/` with ≥ 10 Apache-2.0 excerpts copied verbatim from `eclipse-score/score@e2373d8` and `eclipse-score/process_description@66321fe` (a `feat_req` with version-qualified links; a `std_req` with nested `note`; the `dd_sta` template inside `code-block:: rst`; a `needextend`; a `needtable`; an `:ndf:` role; a `list-table`; a `toctree`; a `raw:: html`; a tab-indented file; both `doc__platform_mgt_plan` definitions; one `DR-*.md`), each file keeping its SPDX header, plus `tests/fixtures/upstream/NOTICE` recording repo, commit, original path and license per file; no CC-BY-SA-4.0 files (SC-001, SRC-012)

---

## Phase 2: Foundational (Blocking Prerequisites)

**⚠️ CRITICAL**: no user story work can begin until this phase is complete

### Tests for Foundational

- [ ] T009 [P] Write `tests/unit/test_selectors.py`: `**` zero/many segments, `*` never crosses `/`, `?`, literal dots, `.git/**` always excluded, include/exclude precedence, rejected syntax (`[…]`, leading `/`, `..`) (FR-001, research R8)
- [ ] T010 [P] Write `tests/unit/test_safe_paths.py`: absolute, `..`, `.`/empty segments, NUL, backslash, trailing slash, over-long names, symlinked parent directory → rejected; normal nested paths accepted; `resolve()` containment enforced (FR-006, SC-003)
- [ ] T011 [P] Write `tests/unit/test_registry.py` with fixtures under `tests/fixtures/registry/`: valid file (the committed `config/sources.yaml`), unknown key at each level, `http://`/`ssh://`/`file://`/`git@` URLs, userinfo, query/fragment, non-443 port, host off allowlist, duplicate `source_id`, bad glob, empty include, `associated_source` pointing to a non-git or missing source, `associated_source` without `docs_root`, abbreviated SHA `ref`, full SHA `ref` accepted, non-positive limits (FR-001, FR-002)
- [ ] T012 [P] Write `tests/unit/test_parser_profile.py`: committed profile loads; duplicate entries, a name in two lists, invalid names, unknown keys rejected; `profile_hash` stable across loads and changes when any entry changes (FR-011, FR-017)
- [ ] T013 [P] Write `tests/unit/test_canonical.py`: canonical JSON byte form, key ordering, non-ASCII preserved, floats rejected; `processing_hash` includes profile, `PARSER_VERSION`, docutils and markdown-it-py versions; document key identical for identical inputs and different when any input differs (FR-017, research R9)
- [ ] T014 [P] Write `tests/unit/test_decode_and_license.py`: strict UTF-8 success, BOM stripped, invalid bytes → `ENCODING_ERROR`, empty → `EMPTY_DOCUMENT`; SPDX in RST comment, in Markdown HTML comment, absent (→ `inherited` from `repository_license`), absent with no repository license (→ `unknown` + `LICENSE_UNKNOWN`), `CC-BY-SA-4.0` → `declared` + `requires_review`, `Apache-2.0` → `allowed` (FR-021)

### Implementation for Foundational

- [ ] T015 [P] Implement all records in `src/score_docs_assistant/domain/ingestion.py` per data-model.md (frozen Pydantic, `extra="forbid"`, no floats), plus the `SourceAdapter` and `DocumentParser` protocols (master spec §5.1, plan Structure Decision)
- [ ] T016 [P] Implement glob compilation and matching in `src/score_docs_assistant/sources/selectors.py` — makes T009 pass
- [ ] T017 [P] Implement `safe_relative_path()` and `ensure_within()` in `src/score_docs_assistant/sources/paths.py` — makes T010 pass
- [ ] T018 Implement registry loading/validation in `src/score_docs_assistant/sources/registry.py` (uses T015, T016) — makes T011 pass
- [ ] T019 [P] Implement profile loading, validation and `profile_hash` in `src/score_docs_assistant/sources/profile.py` — makes T012 pass
- [ ] T020 [P] Implement canonical JSON, hashes, `PARSER_VERSION`, `processing_hash`, document keys in `src/score_docs_assistant/ingestion/canonical.py` — makes T013 pass
- [ ] T021 [P] Implement `src/score_docs_assistant/ingestion/decode.py` and `src/score_docs_assistant/ingestion/licenses.py` — makes T014 pass
- [ ] T022 Implement `tests/helpers/git_repos.py`: builders for local fixture repositories (plain docs repo with LICENSE/NOTICE; repo with a symlink; repo with a submodule gitlink via `git update-index --cacheinfo 160000,…`; repo with a hook, `.gitattributes` filter and an LFS pointer whose execution would create a marker file; repo with an oversize file; repo with two branches and a tag), each returning its `file://` URL and head SHA

**Checkpoint**: `uv run pytest tests/unit` passes; foundation ready.

---

## Phase 3: User Story 1 - Acquire pinned documentation sources safely (Priority: P1) 🎯 MVP

**Goal**: `sources validate` and `sources sync` produce a correct lock and read-only acquired trees without executing anything from the repositories.

**Independent Test**: quickstart.md scenarios B and E (against fixtures in the suite; against GitHub in the real run).

### Tests for User Story 1

- [ ] T023 [P] [US1] Write `tests/unit/test_git_client.py`: argv and environment of every git invocation contain the hardening flags and variables from research R5 and never `shell=True`; production `GitClient()` refuses `file://` and `http://` URLs; `GitClient(allowed_protocols={"file"})` against T022 repos: ls-remote resolves branch and tag, ambiguous name and missing ref error, 40-hex ref skips ls-remote; `ls-tree` parsing of modes/sizes/paths with `-z`; `cat-file --batch` returns exact bytes; git binary absent from PATH → clear `GIT_NOT_FOUND` error naming the prerequisite (FR-003, FR-005, SC-003)
- [ ] T024 [P] [US1] Write `tests/unit/test_http_fetch.py` with `httpx.MockTransport`: success returns bytes + SHA-256 + size; body over cap fails without partial write; redirect to allowlisted HTTPS host followed; redirect to non-allowlisted host, to `http://`, or a 4th hop refused; timeout surfaces as failure (FR-007, SC-003, research R7)
- [ ] T025 [P] [US1] Write `tests/integration/test_sync_git.py`: sync of T022 plain repo writes lock with 40-hex `revision`, `ref`, `fetched_at`, `selector_sha256`, per-file SHA-256/size, `release_mapping: null`, `revision_status: pinned`; LICENSE/NOTICE in `notice_files` although not selected; acquired files are mode 0444 and byte-identical to the commit; symlink, submodule and oversize entries appear in `skipped` with reasons and nothing exists outside `data/sources/<id>/<rev>/`; hook/filter/LFS repo leaves the marker file absent and stores raw pointer bytes; re-sync of the same commit reuses the revision directory (FR-003, FR-004, FR-005, FR-006, FR-007, FR-022, SC-003)
- [ ] T026 [P] [US1] Write `tests/integration/test_sync_failure.py`: a required source that fails after another succeeded → exit status 1, previous lock and existing revision directories byte-identical (tree hash before/after), `data/staging/` empty; an optional source failure → lock written with that entry `status: failed`; `KeyboardInterrupt` during fetch → staging removed, lock unchanged; total-size cap exceeded → source failed (FR-007, FR-008)
- [ ] T027 [P] [US1] Write `tests/contract/test_cli_sources_validate_sync.py`: `sources validate` exit 0/2 with `<dotted.path>: <reason>` lines; `sources sync --help` second non-blank line states network use; `sources sync --json` shape per contracts/cli.md; `sources validate` spawns no subprocess and opens no socket (subprocess and socket spies) (FR-009, FR-024)

### Implementation for User Story 1

- [ ] T028 [US1] Implement `GitClient` in `src/score_docs_assistant/sources/git_client.py` (fixed argv, sanitized env, `resolve_ref`, `fetch_commit` into bare cache, `list_tree`, `read_blobs` via `--batch`) — makes T023 pass (FR-003, FR-005)
- [ ] T029 [US1] Implement export download in `src/score_docs_assistant/sources/http_fetch.py` — makes T024 pass (FR-007)
- [ ] T030 [US1] Implement lock read/write/verify in `src/score_docs_assistant/sources/lock.py` (atomic write; unknown fields rejected; `verify_files()` → `HASH_MISMATCH`) (FR-003, FR-008)
- [ ] T031 [US1] Implement `SyncService` in `src/score_docs_assistant/sources/sync.py` (staging dir, selector filtering, mode-based skipping, path safety, caps, notice files, read-only placement via `os.replace`, reuse of identical revisions, lock write only when all required sources ok, staging cleanup on every exit path) — makes T025, T026 pass (FR-004–FR-008, FR-022)
- [ ] T032 [US1] Implement `sources validate` and `sources sync` in `src/score_docs_assistant/cli/sources.py` and register the `sources` command group in `src/score_docs_assistant/cli/main.py` — makes T027 pass (FR-009, FR-024)

**Checkpoint**: US1 independently testable; MVP complete.

---

## Phase 4: User Story 2 - Normalize documents and inspect coverage (Priority: P2)

**Goal**: `sources inspect` produces normalized documents, entities, resolved relationships and an honest coverage report, offline and deterministically.

**Independent Test**: quickstart.md scenarios C and D.

### Tests for User Story 2

- [ ] T033 [P] [US2] Write `tests/unit/test_links.py`: grammar `ID[qualifier]`, commas inside brackets not split, surrounding whitespace, empty item and unbalanced bracket → `malformed` with raw kept; resolution same-source, unique other source, ambiguous (lists candidates), unresolved; export namespace isolation (FR-011, FR-018)
- [ ] T034 [P] [US2] Write `tests/unit/test_rst_parser.py` with synthetic fixtures in `tests/fixtures/rst/`: section heading paths, bullet/enumerated/definition/field lists, grid/simple/list/csv tables with header rows, code-block language, admonitions, toctree entries, need entity with all options raw and parsed links, nested `note` inside need, need without `:id:` (`NEED_WITHOUT_ID`), duplicate ID (`DUPLICATE_ID_IN_SOURCE`, `#2` key), unknown directive (generic, content parsed, `UNKNOWN_DIRECTIVE`), unknown directive with `:id:` (`POSSIBLE_UNCONFIGURED_NEED`, no entity), unknown role, tab-indented content (FR-010, FR-011, FR-012)
- [ ] T035 [P] [US2] Write `tests/unit/test_rst_safety.py`: need syntax inside `code-block:: rst` creates no entity; `needextend`/`needtable`/`needpie` and `:ndf:` produce `dynamic_view`/inert text + `DYNAMIC_NOT_EVALUATED` with filter expression kept verbatim; `raw:: html` excluded (`RAW_EXCLUDED`); `image`/`figure`/`csv-table :file:`/`:url:` never open files or sockets (spies on `open`, `socket`, `httpx`) and emit `EXTERNAL_RESOURCE_NOT_READ`; no `conf.py`/`docutils.conf` read; docutils directive and role registries identical before and after a parse (FR-013, FR-014, SC-003)
- [ ] T036 [P] [US2] Write `tests/unit/test_rst_include.py` with an acquired-tree fixture: valid relative include inserts content with `origin_path` of the included file and its own line numbers; absolute path, `..` escape, missing file, unselected file, `:url:`, `<standard>` include, depth 9, and a cycle each yield `INCLUDE_UNRESOLVED` and no inserted content; `literalinclude` yields a literal block (FR-015, SC-003)
- [ ] T037 [P] [US2] Write `tests/unit/test_markdown_parser.py` with fixtures in `tests/fixtures/md/`: heading paths, lists, fenced code language, indented code, tables with header, block quotes, `html_block`/`html_inline` excluded with `RAW_EXCLUDED`, 1-based spans from token maps (FR-010, FR-013, FR-016)
- [ ] T038 [P] [US2] Write `tests/unit/test_line_spans.py`: for fixtures with known line numbers, `need`, `section` and directive blocks report exact `line_start`/`line_end`; paragraphs and list items report the documented best-available line (assert the rule chosen after inspecting docutils behavior); every block has `raw_sha256` and `origin_path` (FR-016, research R2)
- [ ] T039 [P] [US2] Write `tests/integration/test_upstream_golden.py` over `tests/fixtures/upstream/`: expected need IDs (exact case), types, raw options, link targets and qualifiers, list-table rows, code-block content; zero entity IDs containing `<`; `doc__platform_mgt_plan` defined in both sources and a reference to it from a third fixture source reported `ambiguous` with both keys (FR-011, FR-014, FR-018, SC-001, SC-007)
- [ ] T040 [P] [US2] Write `tests/integration/test_inspect.py` on a lock produced by T031 from fixture repos: report invariant `selected == included + partial + failed` per git source; tampered acquired file → `HASH_MISMATCH`, source failed; two runs with `--output` produce byte-identical JSONL; changing the profile changes `processing_hash` and document keys; report JSON validates against contracts/normalized-output.md shape (FR-016, FR-017, FR-023, SC-002, SC-004)
- [ ] T041 [P] [US2] Write `tests/contract/test_cli_inspect.py`: exit 0 on healthy lock, 1 when a required source is failed/missing/tampered, 2 on invalid lock; `--json` shape; text summary lines per contracts/cli.md; `--output` creates `documents.jsonl` and `entities.jsonl`; inspect spawns no subprocess and opens no socket (FR-009, FR-023, FR-024)

### Implementation for User Story 2

- [ ] T042 [US2] Implement hardened settings in `src/score_docs_assistant/ingestion/rst/settings.py` per research R2 (FR-013)
- [ ] T043 [US2] Implement `NeedDirective` (permissive option mapping), `DynamicDirective`, `LiteralDirective`, `RawExcludedDirective`, `GenericDirective`, `SafeImage`/`SafeFigure`, `SafeCsvTable` and `SafeInclude`/`SafeLiteralInclude` in `src/score_docs_assistant/ingestion/rst/directives.py` (FR-011–FR-015)
- [ ] T044 [US2] Implement reference roles, dynamic roles and `GenericRole` in `src/score_docs_assistant/ingestion/rst/roles.py` (FR-012, FR-013, FR-018)
- [ ] T045 [US2] Implement `RstParser` in `src/score_docs_assistant/ingestion/rst/parser.py`: prescan of directive/role names, registry context manager under a module lock, `publish_doctree`, doctree visitor → `Block`/`Entity`, system messages → diagnostics — makes T034, T035, T036, T038 pass (FR-010–FR-016)
- [ ] T046 [P] [US2] Implement `MarkdownParser` in `src/score_docs_assistant/ingestion/markdown.py` — makes T037 pass (FR-010, FR-013, FR-016)
- [ ] T047 [US2] Implement link parsing and cross-source resolution in `src/score_docs_assistant/ingestion/links.py` — makes T033 pass (FR-011, FR-018)
- [ ] T048 [US2] Implement `NormalizationService` in `src/score_docs_assistant/ingestion/normalize.py` (verify hashes via `sources/lock.py`, decode, license, parse by extension, resolve links, classify documents, deterministic ordering) — makes T039, T040 pass (FR-016, FR-017, FR-021)
- [ ] T049 [US2] Implement coverage report building and text/JSON rendering in `src/score_docs_assistant/ingestion/report.py` (FR-023)
- [ ] T050 [US2] Implement `sources inspect` in `src/score_docs_assistant/cli/sources.py` (report file under `data/reports/`, `--json`, `--output`) — makes T041 pass (FR-023, FR-024)

**Checkpoint**: US1 and US2 work independently.

---

## Phase 5: User Story 3 - Import a published Sphinx-Needs export (Priority: P3)

**Goal**: exports are downloaded, validated, and exposed as `unverified` entities in their own namespace with a consistency statistic.

**Independent Test**: quickstart.md scenario B (export entries) and C (export checks).

### Tests for User Story 3

- [ ] T051 [P] [US3] Write `tests/unit/test_needs_export.py` with fixtures in `tests/fixtures/needs_export/` (a trimmed real export shape plus hostile variants): valid → entities keyed `<export_id>:<need_id>` with `tags`, `fulfils_back` and all other raw fields in `export_fields`, `revision_status: unverified`; invalid JSON, missing `id`/`type`/`title`/`docname`, a string field over 1 MiB, over 200 000 needs, missing `current_version` key → `EXPORT_INVALID` and no entities; consistency counts against a parsed associated source using `docs_root` path mapping (`matched`, `id_only_matched`, `missing_in_source`, `missing_in_export`); the statistic never changes `revision_status` (FR-019, FR-020, SC-006)
- [ ] T052 [P] [US3] Write `tests/integration/test_sync_inspect_export.py` (MockTransport + fixture repo): export synced into the lock with `revision` = SHA-256 and `unverified`; optional export failure → sync exit 0 with `status: failed` entry and a coverage limitation in inspect; export links resolve only within the export (FR-018, FR-019, FR-020)

### Implementation for User Story 3

- [ ] T053 [US3] Implement export validation, entity mapping and consistency statistic in `src/score_docs_assistant/ingestion/needs_export.py` — makes T051 pass (FR-019, FR-020)
- [ ] T054 [US3] Wire `needs-export` sources into `src/score_docs_assistant/sources/sync.py`, `src/score_docs_assistant/ingestion/normalize.py` and `src/score_docs_assistant/ingestion/report.py` — makes T052 pass (FR-019, FR-020, FR-023)

**Checkpoint**: all stories complete.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T055 Run the full local gate `uv run ruff format --check . && uv run ruff check . && uv run mypy src && uv run pytest && uv run python scripts/check_licenses.py`; fix all failures (constitution VII)
- [ ] T056 [P] Register the `real_network` marker in `pyproject.toml` and make the socket guard in `tests/conftest.py` allow non-loopback connections only for tests carrying that marker when `SCORE_ASSISTANT_REAL_NETWORK=1`; write `tests/integration/test_real_network_sync.py` (skipped otherwise): validate + sync of `score-process` from GitHub, assert 40-hex revision and non-empty file list (FR-003)
- [ ] T057 Execute quickstart.md scenarios A–E on the workstation (real GitHub and GitHub Pages); record resolved SHAs, file/entity/link counts, diagnostics summary, timings (SC-002, SC-005, SC-006, SC-007), a tally of hostile-fixture tests passed (SC-003), determinism result (SC-004) and any "not run" items with reasons in `specs/002-source-ingestion/verification.md`
- [ ] T058 [P] Update `docs/TRACEABILITY.md`: one row each for SRC-001–SRC-008, SRC-010–SRC-012 and SEC-005 with F002 FR IDs, task IDs, implementation paths, tests and evidence; note SRC-009 remains F003 (constitution IX)
- [ ] T059 [P] Update `docs/BACKLOG.md` (F002 state), `docs/ASSUMPTIONS.md` (docutils license review; exports unverified by construction; git ≥ 2.34 prerequisite for sync), `docs/toolchain.md` (docutils, markdown-it-py, git), `README.md` and `CLAUDE.md` command lists (`sources validate|sync|inspect`)
- [ ] T060 Run `/speckit-converge` and complete any appended tasks before declaring F002 done

---

## Dependencies & Execution Order

### Phase Dependencies

- Setup (T001–T008) → Foundational (T009–T022) → US1 (T023–T032) → US2 (T033–T050) → US3 (T051–T054) → Polish (T055–T060).
- US2 needs a lock and acquired trees: its integration tests (T040, T041) use `SyncService` from US1 against fixture repos; its unit tests (T033–T039) need only Foundational.
- US3 extends `sync.py` (US1) and `normalize.py`/`report.py` (US2).
- T002–T004 (license gate) must complete before T055, because T001 adds docutils.

### Within Each Story

Tests first (must fail) → domain/services → CLI wiring → checkpoint running the full local gate.

### Parallel Opportunities

- Setup: T005, T006, T007, T008 (T002–T004 are sequential).
- Foundational tests T009–T014; implementations T015–T017, T019–T021.
- US1 tests T023–T027; US2 tests T033–T041; US3 tests T051–T052; T046 alongside T042–T045.

## Parallel Example: User Story 2

```bash
Task: "Write tests/unit/test_links.py"
Task: "Write tests/unit/test_rst_parser.py"
Task: "Write tests/unit/test_rst_safety.py"
Task: "Write tests/unit/test_markdown_parser.py"
```

## Implementation Strategy

### MVP First

Phases 1–3 → validate with the fixture-repo suite and a real `sources sync` → then US2, US3, Polish.

### Incremental Delivery

Each story checkpoint runs the full local gate before continuing; commit per checkpoint.

## Notes

- Mark a task `[x]` only after its verification ran and passed; record deviations in `verification.md`.
- `real_network` tests skipped = "not run", never "passed".
- Never run upstream `conf.py`, Sphinx, or any upstream script — not even "just to compare".
