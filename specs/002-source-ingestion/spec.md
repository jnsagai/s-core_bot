# Feature Specification: F002 Source Registry and Safe Document Normalization

**Feature Branch**: `002-source-ingestion`

**Created**: 2026-09-28

**Status**: Draft

**Input**: User description: "F002 from docs/PROJECT_SPEC.md §16: initial approved repositories,
revision lock, source acquisition, Markdown/RST safe subset, source locations, include handling,
source notices, needs-export importer, coverage reports. Sample actual upstream constructs before
finalizing parser behavior."

**Master requirements covered**: SRC-001 – SRC-008, SRC-010 – SRC-012, SEC-005 (primary);
LOC-003 (sync is a separate, network-using operation), RET-003 (namespaced entity keys needed by
F004), OPS-005 (new dependencies pass the license gate) (supporting).

**Evidence base**: behaviour below is derived from sampling the real upstream sources at
`eclipse-score/score@e2373d8` and `eclipse-score/process_description@66321fe` (both 2026-09-25)
and their published `needs.json` exports — see [research.md](research.md) R1.

## Clarifications

### Session 2026-09-28

Resolved autonomously by the agent from `docs/PROJECT_SPEC.md` and the upstream sampling evidence,
following the same owner-authorised procedure as F001 (`docs/ASSUMPTIONS.md` A-007). The owner may
override any answer.

- Q: Master spec §10.2 lists `sources validate` and `sources sync` but no command to inspect
  normalization results before an index exists. Add one? → A: Yes, `sources inspect` (offline).
  Basis: UJ-05 "inspect changes and ingestion failures", SRC-011 reports, persona *Maintainer*;
  F003's `index build` reuses the same normalization library, so no duplicate logic.
- Q: Since upstream `conf.py` (which defines need types and link options) may not be executed,
  where does that knowledge come from? → A: A versioned, repository-committed parser profile
  derived from observed usage (41 need types, 22 link options); unconfigured directives that look
  like needs get `POSSIBLE_UNCONFIGURED_NEED` instead of guessing. Basis: SRC-005 "configured need
  directives", SRC-006, ADR-005.
- Q: The same need ID could appear in two repositories (a naive grep suggested
  `doc__platform_mgt_plan`; corrected in research R1 — the current pair shares no IDs). Which
  wins? → A: Neither; keys are `<source_id>:<need_id>` and cross-source references resolve only
  when unambiguous, otherwise reported `ambiguous`. Basis: §9.1 "requirement IDs alone are not
  globally unique", RET-003.
- Q: Should the published `needs.json` exports be required sources? → A: No — registered as
  `required: false` supplementary sources with `unverified` revision status; a failed export
  download is a coverage limitation, not a sync failure. Basis: SRC-008, §6.3 "index it as a
  separately identified artifact".
- Q: Files declaring CC-BY-SA-4.0 (observed: 3 in `process_description`) — ingest or exclude? →
  A: Ingest for local use; record the declared license; flag `redistribution: requires_review`
  so bundle export (F003) is blocked for them until reviewed. Basis: SRC-012 "unknown licensing
  shall block redistribution", §1.1 model/corpus licensing recorded separately.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Acquire pinned documentation sources safely (Priority: P1)

A maintainer lists the approved documentation repositories in a registry, validates it, and runs
one explicit sync command. The sync resolves each moving reference (e.g. `main`) to an exact
commit, downloads only the selected documentation files for that commit, stores them read-only
under the data directory together with the repository's license and notice files, and writes a
lock file recording exactly what was acquired. Nothing from the repositories is executed, and a
failed sync leaves the previous lock and files untouched.

**Why this priority**: every later feature (index, search, answers) consumes the pinned files
and the lock. Without trustworthy acquisition there is no corpus.

**Independent Test**: with a local fixture repository standing in for GitHub, run validate and
sync; inspect the lock (commit SHA, per-file hashes) and the acquired tree. Repeat with hostile
fixture repositories (symlinks, traversal paths, submodules, hooks, oversized files).

**Acceptance Scenarios**:

1. **Given** a valid registry with source `ref: main`, **When** the maintainer runs sync,
   **Then** the lock records the 40-character commit SHA `main` resolved to, the retrieval time
   (UTC), a hash of the source's include/exclude selectors, a hash of every acquired file, and
   hashes of its license and notice files.
2. **Given** a registry entry with an `http://`, `ssh://`, `file://` URL, embedded credentials, or
   a host not on the registry's allowlist, **When** validate or sync runs, **Then** it is rejected
   with the entry's path and reason and no network request is made.
3. **Given** a repository containing a symlink, a submodule, a path with `..`, or a file above the
   size cap among the selected paths, **When** sync runs, **Then** those entries are skipped with a
   diagnostic, and no file is written outside `data/sources/<source-id>/<revision>/`.
4. **Given** a repository that ships git hooks, `.gitattributes` filters, or LFS pointers, **When**
   sync runs, **Then** no hook, filter, or LFS download is executed; files are stored as their raw
   committed bytes.
5. **Given** a required source whose fetch fails mid-sync, **When** sync ends, **Then** it exits
   non-zero, the previous lock file and previously acquired revisions are byte-identical to before,
   and no partially written revision directory remains in place of a complete one.
6. **Given** an optional source that fails, **When** sync ends, **Then** the lock is written with
   that source marked failed and the failure is reported as a coverage limitation.
7. **Given** validate or inspect is run, **When** it completes, **Then** no network connection was
   attempted; only sync uses the network and its help text says so.

---

### User Story 2 - Normalize documents and inspect coverage (Priority: P2)

The maintainer runs an offline inspect command against the lock. Every acquired Markdown and RST
file is parsed into normalized documents that keep headings, paragraphs, lists, tables, code
blocks, and — critically — S-CORE's requirement records (Sphinx-Needs directives) with their exact
IDs, options, and relationships, each tied to its source file and line numbers. The command prints
a coverage report showing what was included, skipped, failed, or only partially understood, and
lists relationships that could not be resolved. Anything the parser does not understand is shown,
never silently dropped.

**Why this priority**: this is the content every later feature searches and cites; its fidelity
and honesty about gaps is the foundation of "evidence precedes assertions".

**Independent Test**: run inspect on fixture sources (including excerpts copied from the pinned
upstream revisions) and compare extracted need IDs, options, links, tables and code blocks with
expected values; run it on the real pinned sources and check that every file is classified and
every unknown construct has a diagnostic.

**Acceptance Scenarios**:

1. **Given** an RST file containing `.. feat_req:: Title` with `:id: feat_req__orchestration__exec_async_rt`,
   `:derived_from: stkh_req__execution_model__processes[version==1]`, and other options, **When**
   inspected, **Then** an entity is produced with the exact ID (case and punctuation preserved),
   type `feat_req`, title, every option's raw value, and a link record with target
   `stkh_req__execution_model__processes`, qualifier `version==1`, and the raw text.
2. **Given** the same need-directive syntax inside a `.. code-block:: rst` example, **When**
   inspected, **Then** it is kept as inert code text and **no** entity is created.
3. **Given** `.. needextend::`, `.. needtable::` or other dynamic Sphinx-Needs directives, or the
   `:ndf:` role, **When** inspected, **Then** they are not evaluated; their raw text (including
   filter expressions) is retained as inert data and a diagnostic states that dynamic content was
   not computed.
4. **Given** a `.. raw:: html` block, **When** inspected, **Then** its content is excluded from
   normalized text and a diagnostic is recorded; the raw source span remains available.
5. **Given** an unknown directive that has an `:id:` option, **When** inspected, **Then** it is not
   guessed to be a need; a `POSSIBLE_UNCONFIGURED_NEED` diagnostic names the directive and file.
6. **Given** an `include` whose target escapes the source root, does not exist, is not selected,
   exceeds the nesting depth, or forms a cycle, **When** inspected, **Then** the include is not
   followed and an unresolved-include diagnostic appears in the coverage report.
7. **Given** a need ID defined in two sources (synthetic fixture; master spec §9.1),
   **When** inspected, **Then** two distinct entities exist, keyed `<source_id>:<need_id>`, and a
   link targeting that ID from a third source is reported `ambiguous` with both candidates.
8. **Given** the same lock inspected twice, **When** outputs are compared, **Then** normalized
   documents, entities, and their hashes are byte-identical.
9. **Given** an RST file with an `SPDX-License-Identifier: CC-BY-SA-4.0` header (observed
   upstream), **When** inspected, **Then** the document records that declared license and the
   report marks it as requiring review before redistribution.

---

### User Story 3 - Import a published Sphinx-Needs export as a separately identified artifact (Priority: P3)

The maintainer adds the project's published `needs.json` export to the registry. Sync downloads
it within size and host limits; inspect validates it strictly and turns its records into entities
in their own namespace. Because the export carries no commit identity, it is always labelled as an
unverified artifact identified by URL, download time and content hash — never as belonging to a
git revision. The report shows how consistent it is with the pinned source it claims to describe,
without that ever upgrading it to "verified".

**Why this priority**: the export contains build-time results the safe parser deliberately does
not compute (tags added by `needextend`, back-links), but it is supplementary evidence only.

**Independent Test**: sync and inspect a fixture export plus a malformed/oversized/hostile one;
check namespace, revision status, preserved fields, and the consistency statistic.

**Acceptance Scenarios**:

1. **Given** a registry entry of kind `needs-export` with an allowlisted HTTPS URL, **When** sync
   runs, **Then** the file is stored with its SHA-256, URL and fetch time (UTC) in the lock, and
   revision status `unverified`.
2. **Given** an export larger than the cap, not valid JSON, missing required fields, or served via
   a redirect to a non-allowlisted host, **When** sync or inspect runs, **Then** it is rejected
   with a diagnostic and no entity is created from it.
3. **Given** a valid export associated with a git source, **When** inspected, **Then** its
   entities are keyed `<export_source_id>:<need_id>`, keep all raw fields including `tags` and link
   lists, report `revision_status: unverified`, and the report shows counts of export needs found /
   not found in the associated source's parsed needs.

---

### Edge Cases

- Tab-indented RST content (observed upstream) → expanded to 8-column tab stops, as RST defines.
- File not valid UTF-8 → file classified `failed` with `ENCODING_ERROR`; no lossy replacement.
  A UTF-8 BOM is removed.
- Directive nested inside a need body (observed: `.. note::` inside `std_req`) → nested block kept
  as part of the entity's content.
- Text that only looks like a directive (observed: `' .. document::` with a leading apostrophe,
  followed by `:id: doc__platform_mgt_plan`) → ordinary paragraph; no entity.
- Link option values continued over several indented lines (observed: `:complies:` over 9 lines)
  → all items parsed.
- Need with no `:id:` → entity not created; `NEED_WITHOUT_ID` diagnostic.
- Same need ID twice within one source → both occurrences kept, `DUPLICATE_ID_IN_SOURCE` warning;
  neither silently wins.
- Link option value with an empty item, a malformed qualifier bracket, or whitespace → raw text
  kept, `MALFORMED_LINK` diagnostic, well-formed items still parsed.
- Link targets referring to needs not present in any selected source → `unresolved` in the report
  (not an error; upstream legitimately references needs in repositories not yet ingested).
- `:need:` roles in prose → recorded as references with their target; resolution handled like
  links.
- Markdown raw HTML blocks/inline HTML → excluded from normalized text with a diagnostic.
- Images and figures → URI and caption text retained; image files are never read or fetched.
- `csv-table`/`literalinclude`/`include` with `:url:` or absolute paths → rejected, diagnostic.
- Empty file → included with zero blocks and an `EMPTY_DOCUMENT` info diagnostic.
- A selected file disappears between ref resolution and fetch (force-push) → source fails with a
  clear message; lock unchanged.
- Registry change that removes a source → the next lock no longer lists it; previously acquired
  files remain on disk until removed by the F003 retention process (not deleted by sync).
- `ref` given as a full SHA → used as-is (no resolution needed); abbreviated SHAs are rejected.
- `git` not installed → sync fails before any network access with a message naming the
  prerequisite; validate and inspect are unaffected.
- Upstream `conf.py` files → never selected by default selectors and never imported even if
  selected (treated as an unsupported file type).

## Requirements *(mandatory)*

### Functional Requirements

**Registry and acquisition**

- **FR-001** (SRC-001): Sources MUST come only from an operator-maintained registry file
  declaring per source: `source_id`, `kind` (`git` or `needs-export`), origin URL, `ref`
  (git only), include/exclude selectors, `authority`, `license_policy`, `required`, and parser
  profile. The registry MUST be schema-validated and MUST reject unknown keys.
- **FR-002** (SEC-005): Every origin URL MUST use HTTPS, contain no credentials, and have a host on
  the registry's `allowed_hosts` list. No configuration value can enable another protocol.
- **FR-003** (SRC-002): Sync MUST resolve each `ref` to a full 40-character commit SHA before
  fetching and record in the lock: ref, SHA, retrieval time (UTC), selector hash, per-file SHA-256
  and size, and SHA-256 of the repository's license and notice files.
- **FR-004** (SRC-003): The lock MUST identify each source's revision individually. A product
  release label MUST NOT be recorded unless an explicit, evidenced mapping exists; F002 records
  `release_mapping: null` for every source.
- **FR-005** (SRC-006, SEC-005): Acquisition MUST NOT execute repository content: no working-tree
  checkout, git hooks, submodule recursion, LFS or attribute filters, or symlink materialization;
  the user's and system's git configuration MUST be ignored.
- **FR-006** (SEC-005): Acquired files MUST be written only under
  `data/sources/<source_id>/<revision>/`. Entries that are absolute, contain `..`, resolve outside
  that root, are symlinks, or are submodule links MUST be skipped with a diagnostic.
- **FR-007** (SEC-005): Acquisition MUST enforce a per-text-file cap (default 10 MiB), a
  per-export cap (default 100 MiB), a total-per-sync cap (default 1 GiB), and network timeouts;
  exceeding a cap fails that file or source — content is never truncated. HTTP redirects to a host
  outside the allowlist MUST be refused.
- **FR-008** (SRC-002, SRC-009 precondition): A failed sync of any required source MUST leave the
  previous lock and previously acquired revision directories unchanged; new revisions are staged
  and moved into place only when complete; the lock is written atomically.
- **FR-009** (LOC-003): Only `sources sync` may use the network. `sources validate` and
  `sources inspect` MUST be fully offline. Help text of `sources sync` MUST state it uses the
  network.

**Normalization**

- **FR-010** (SRC-005): The parser MUST support, for RST: section headings, paragraphs, bullet and
  enumerated lists, definition and field lists, literal and code blocks (language kept), simple,
  grid, list and CSV tables (header rows and row identity kept), admonitions, toctree entries,
  configured need directives, and cross-reference roles; for Markdown (CommonMark + tables):
  headings, paragraphs, lists, fenced/indented code (language kept), tables, block quotes.
- **FR-011** (SRC-005): Directives whose name is in the source's parser profile need-type list MUST
  become entities with: exact ID (case and punctuation preserved), type, title, every option's raw
  value, parsed links for the profile's link-option names (each item split into target ID and
  optional bracket qualifier, raw text kept), body content with nested blocks, and source span.
- **FR-012** (SRC-005, SRC-011): Unknown or unsupported directives and roles MUST produce a
  diagnostic (code, file, line) and keep their textual content; nothing is silently dropped. An
  unknown directive carrying an `:id:` option MUST produce `POSSIBLE_UNCONFIGURED_NEED` and MUST
  NOT be treated as a need.
- **FR-013** (SRC-006): The parser MUST NOT evaluate dynamic Sphinx-Needs directives (e.g.
  `needextend`, `needtable`, `needpie`, `needarch`, `needuml`, `needflow`, `needlist`,
  `needfilter`), the `:ndf:` role, or any expression; their raw text is retained as inert data
  with a `DYNAMIC_NOT_EVALUATED` diagnostic. `raw` directive and Markdown HTML content MUST be
  excluded from normalized text with a diagnostic. The parser MUST NOT import `conf.py`, read
  parser configuration files, or read image/file/URL targets.
- **FR-014** (SRC-006, constitution IV/V): Content of literal and code blocks MUST remain inert
  text; directive or need syntax inside it MUST NOT create entities or trigger parsing.
- **FR-015** (SRC-007): `include` and `literalinclude` MUST resolve only to files of the same
  source revision that are selected by that source's selectors, with a maximum nesting depth of 8
  and cycle detection; anything else is not followed and is reported as an unresolved include.
- **FR-016** (SRC-004): Every normalized block and entity MUST retain source ID, revision, file
  path, heading path, raw-content SHA-256, and start/end line where the parser provides them; both
  the normalized text and the raw source span MUST be retrievable.
- **FR-017** (SRC-010): Given identical source bytes and parser profile, normalization MUST produce
  identical records and hashes. Hashes MUST be computed over a versioned canonical serialization
  that includes the parser profile and parser library versions.
- **FR-018** (RET-003, SRC-005): Entity keys MUST be `<source_id>:<need_id>`. Link and `:need:`
  targets MUST resolve to an entity in the same source first; otherwise to the unique entity with
  that ID in another selected source; otherwise be reported `ambiguous` (listing candidates) or
  `unresolved`. Relationships absent from the source MUST NOT be inferred.

**Needs export**

- **FR-019** (SRC-008): A `needs-export` source MUST be downloaded by sync within the caps and host
  allowlist, validated strictly (structure, required fields, per-field and count limits) by
  inspect, and turned into entities keyed `<export_source_id>:<need_id>` with all raw fields
  retained. Its revision status MUST be `unverified` and its identity URL + fetch time + SHA-256.
- **FR-020** (SRC-008): When the export declares an `associated_source`, inspect MUST report how
  many export needs are / are not found (by ID and by document path, mapped through the
  export's declared `docs_root`) among that source's parsed needs. This statistic MUST NOT change the export's revision status.

**Licensing and notices**

- **FR-021** (SRC-012): Each document MUST record its license as `declared` (from an
  `SPDX-License-Identifier` line), `inherited` (from the repository license), or `unknown`.
  Documents whose license is unknown, or whose license is not on the redistribution allowlist in
  the registry, MUST be flagged `redistribution: requires_review` in the report. Local ingestion
  continues.
- **FR-022** (SRC-012): Repository `LICENSE*`, `NOTICE*` and `COPYING*` files at the repository
  root MUST be acquired with every revision regardless of selectors and recorded in the lock.

**Reporting and commands**

- **FR-023** (SRC-011): Inspect MUST produce, per source, a coverage report listing selected,
  included, excluded-by-selector count, skipped (with reason), failed (with reason), and
  partially-parsed files; unresolved, ambiguous, and resolved relationship counts with the
  unresolved/ambiguous items; diagnostics by code; license summary; and export consistency —
  as JSON and as a human-readable summary.
- **FR-024**: The CLI MUST provide `sources validate --config PATH`, `sources sync --config PATH
  [--json]`, and `sources inspect --lock PATH [--json] [--output DIR]`, with exit codes `0`
  success, `1` operational failure (including any required source failed or missing), `2`
  configuration/usage error. `--output` writes normalized documents and entities as deterministic
  JSON Lines.
- **FR-025** (OPS-005): Dependencies added by this feature MUST pass the license gate, and the gate
  MUST NOT auto-pass a license string that names a copyleft license alongside a permissive one;
  such packages require a reviewed exception.

### Key Entities

- **SourceRegistry / SourceDefinition**: allowlisted hosts, redistribution license allowlist, and
  per-source definitions (see FR-001).
- **ParserProfile**: named set of need types, link-option names, and dynamic directive names used
  to interpret a source; versioned.
- **SourceLock / LockedSource**: per source: kind, ref, resolved SHA or export SHA-256, fetch time,
  selector hash, files (path, SHA-256, size), license/notice file hashes, status, revision status.
- **NormalizedDocument**: source ID, revision, path, format, title, license record, raw and
  normalized hashes, ordered blocks, diagnostics.
- **Block**: kind, normalized text, heading path, line span, attributes (language, directive name,
  options), children.
- **Entity**: namespaced key, need ID, type, title, raw options, links, content blocks, span,
  origin (`rst` or `needs-export`), revision status (`pinned` or `unverified`).
- **LinkRef**: option name or `role`, target ID, qualifier, raw text, resolution (`resolved`,
  `ambiguous`, `unresolved`) and resolved key(s).
- **Diagnostic**: code, severity, source, path, line, message.
- **CoverageReport**: per-source classification and summaries described in FR-023.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100 % of need records in the fixture set — including at least 10 excerpts copied from
  the pinned upstream revisions — are extracted with exact ID, type, options, and link targets and
  qualifiers.
- **SC-002**: For both initial sources at their pinned revisions, 100 % of selected files appear in
  exactly one report category, and every directive or role occurrence is either parsed or
  represented by a diagnostic (zero silent drops).
- **SC-003**: 0 of the hostile fixtures (traversal paths, absolute paths, symlinks, submodules,
  include escape and cycle, oversized file, non-HTTPS URL, credentials in URL, non-allowlisted
  host, off-allowlist redirect, repository with hooks/filters) result in a file outside the source
  root, a request to a non-allowlisted host, or execution of repository content.
- **SC-004**: Inspecting the same lock twice yields byte-identical normalized output.
- **SC-005**: Inspect over both initial sources completes in under 2 minutes on the reference
  workstation; sync of both completes in under 5 minutes on a typical broadband connection.
- **SC-006**: 100 % of entities originating from a needs export report `unverified` revision status.
- **SC-007**: 0 entities are created from need-like syntax inside literal/code blocks in the real
  corpus (upstream contains such template examples).

## Assumptions

- Initial sources are `eclipse-score/score` and `eclipse-score/process_description` (master spec
  §6.1) plus their published `needs.json` exports; further repositories are added later by
  registry edits, not code changes.
- Hosts allowlisted initially: `github.com` (git) and `eclipse-score.github.io` (exports).
- The parser profile for S-CORE is maintained in the repository, derived from observed usage
  (41 need types, 22 link options — research.md R1) because upstream `conf.py` may not be executed.
- Git is available on the machine running sync (it is a documented prerequisite, like Ollama).
- Chunking, embeddings, snapshot storage and activation are F003; normalized output is consumed
  in memory by F003's build and optionally written as JSON Lines for inspection.

## Out of Scope

Chunking and token counting, embeddings, SQLite/FTS storage, snapshot activation and retention
(F003); search (F004); rendering to HTML and sanitization for display (F006); a controlled Sphinx
build adapter and rendered-HTML artifacts (master spec §6.3 "future"); PDF/OCR; issues, pull
requests, and meeting notes; private repositories and authentication.

## Exit Criteria to Move to F003

All FRs verified by automated tests; SC-001–SC-004, SC-006, SC-007 measured by the suite or a real
run and recorded; SC-005 measured once on the workstation; real sync and inspect of both initial
sources recorded in `verification.md`; traceability updated; converge clean.
