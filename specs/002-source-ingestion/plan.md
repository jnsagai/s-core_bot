# Implementation Plan: F002 Source Registry and Safe Document Normalization

**Branch**: `002-source-ingestion` | **Date**: 2026-09-28 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002-source-ingestion/spec.md`

## Summary

Add an operator registry and parser profile, a `sources sync` command that resolves refs to SHAs
and extracts selected files from git objects without any checkout (plus allowlisted `needs.json`
downloads), an atomic lock, and an offline `sources inspect` command that normalizes RST
(hardened docutils) and Markdown (markdown-it-py) into documents, blocks and namespaced need
entities with exact provenance, resolves relationships without guessing, and reports coverage,
diagnostics and licensing. Tighten F001's license gate so mixed copyleft strings need review.

## Technical Context

**Language/Version**: Python 3.12 (unchanged)

**Primary Dependencies**: new — docutils 0.23 (RST), markdown-it-py 4.2.0 (Markdown, promoted from
transitive to direct); existing — Pydantic, Typer, httpx, PyYAML. External tool: `git` ≥ 2.34 on
PATH for `sources sync` only. See [research.md](research.md) R2–R5.

**Storage**: files only — `config/sources.yaml`, `config/parser-profiles/s-core.yaml` (committed);
`data/source-lock.json`, `data/sources/<id>/<rev>/`, `data/cache/git/`, `data/staging/`,
`data/reports/` (generated, git-ignored). No database (F003).

**Testing**: pytest with F001's loopback-only socket guard; local fixture git repositories built
in `tmp_path` and fetched over `file://` via a test-only `GitClient(allowed_protocols={"file"})`;
`httpx.MockTransport` for exports; golden fixtures including ≥ 10 Apache-2.0 upstream excerpts;
optional `real_network` marker (skipped unless `SCORE_ASSISTANT_REAL_NETWORK=1`).

**Target Platform**: Linux x86-64 (unchanged).

**Project Type**: single Python project, CLI + library.

**Performance Goals**: inspect of both initial sources < 2 min; sync < 5 min (SC-005).

**Constraints**: no execution of repository content; network only in `sources sync`; no writes
outside `data/`; deterministic output; caps 10 MiB/file, 100 MiB/export, 1 GiB/sync.

**Scale/Scope**: ~620 files, ~2 200 need records, 2 exports (~2 MB) today; profile-driven so new
repositories need registry edits only.

## Constitution Check

*GATE: evaluated before Phase 0 and re-checked after Phase 1 design.*

| Principle | Status | How this plan complies |
| --- | --- | --- |
| I. Local operation | PASS | Network confined to operator-invoked `sources sync`; validate/inspect offline (FR-009); no paid service. |
| II. Evidence precedes assertions | PASS | Every block/entity carries source, revision, path, span, hashes (FR-016) so later citations can be server-assembled. |
| III. Snapshots explicit | PASS | Refs resolved to full SHAs; lock records per-file hashes; exports labelled `unverified` with URL+time+SHA-256 (FR-003, FR-019). |
| IV. Documentation is untrusted input | PASS | No checkout/hooks/filters/symlinks; `conf.py` never imported; include/raw/image/url I/O disabled or replaced; dynamic directives and `:ndf:` never evaluated; literal content inert (FR-005, FR-013, FR-014, FR-015). |
| V. Read-only assistance | N/A (PASS) | Ingestion only; no Q&A path touched. |
| VI. Modular monolith | PASS | New `sources/` and `ingestion/` packages behind `SourceAdapter` and `DocumentParser` protocols (master spec §5.1); domain records free of docutils/httpx types. No new services. |
| VII. Honest verification | PASS | Hostile fixtures, golden upstream excerpts, determinism double-run test; real sync/inspect recorded; `real_network` tests reported "not run" when skipped. |
| VIII. Privacy by default | PASS | No telemetry; sync logs only source IDs, SHAs, counts. |
| IX. Spec-first increments | PASS | FR↔master IDs mapped; TRACEABILITY expanded to one row per SRC ID. |
| X. Public profile separate | N/A (PASS) | No serving changes. |
| XI. Licenses follow artifacts | PASS | Per-file SPDX/inherited/unknown license, repo LICENSE/NOTICE acquired and hashed, redistribution review flag (FR-021, FR-022); license gate tightened (FR-025). |
| XII. No implied authority | PASS | `authority` label is descriptive metadata only; exports never presented as verified. |

Post-design re-check (after Phase 1): **PASS** — contracts add one network path (sync), guarded
by HTTPS + host allowlist + caps + no-redirect-off-allowlist; no other principle affected. No
Complexity Tracking entries.

## Project Structure

### Documentation (this feature)

```text
specs/002-source-ingestion/
├── plan.md, research.md, data-model.md, quickstart.md
├── contracts/
│   ├── cli.md               # sources validate | sync | inspect
│   ├── registry.md          # config/sources.yaml + parser profile schema
│   ├── lock.md              # data/source-lock.json schema
│   └── normalized-output.md # documents/entities JSONL + coverage report JSON
├── checklists/ requirements.md, security.md
├── tasks.md
└── verification.md          # written during implementation
```

### Source Code (repository root)

```text
config/
├── sources.yaml                         # registry: allowed_hosts, limits, 4 initial sources
└── parser-profiles/s-core.yaml          # 41 need types, 22 link options, dynamic/literal lists
src/score_docs_assistant/
├── domain/ingestion.py                  # SourceDefinition, LockedSource, NormalizedDocument,
│                                        # Block, Entity, LinkRef, Diagnostic, CoverageReport,
│                                        # SourceAdapter + DocumentParser protocols
├── sources/
│   ├── registry.py                      # load/validate sources.yaml (extra=forbid, URL rules)
│   ├── profile.py                       # load/validate parser profile, profile hash
│   ├── selectors.py                     # glob→regex (R8)
│   ├── paths.py                         # safe_relative_path(), containment checks
│   ├── git_client.py                    # GitClient: fixed argv/env, ls-remote, fetch, ls-tree, cat-file batch
│   ├── http_fetch.py                    # export download: allowlist redirects, caps, sha256
│   ├── lock.py                          # read/write lock (atomic), verify acquired files
│   └── sync.py                          # SyncService: staging, per-source status, atomic move
├── ingestion/
│   ├── decode.py                        # strict UTF-8, BOM strip, EMPTY/ENCODING diagnostics
│   ├── licenses.py                      # SPDX header detection, inherited/unknown, redistribution flag
│   ├── canonical.py                     # canonical JSON, hashes, document keys (R9)
│   ├── rst/settings.py                  # hardened docutils settings (R2)
│   ├── rst/directives.py                # NeedDirective, DynamicDirective, Literal, Raw, Generic, SafeInclude
│   ├── rst/roles.py                     # need/ref/doc/term/ndf + GenericRole
│   ├── rst/parser.py                    # RstParser: prescan, registry context, doctree→blocks/entities
│   ├── markdown.py                      # MarkdownParser: tokens→blocks, html exclusion
│   ├── links.py                         # parse "ID[qualifier]" lists; cross-source resolution
│   ├── needs_export.py                  # strict export model → entities; consistency stat
│   ├── normalize.py                     # NormalizationService: lock → documents/entities/diagnostics
│   └── report.py                        # CoverageReport build, text + JSON rendering
└── cli/sources.py                       # `sources validate|sync|inspect`
scripts/check_licenses.py                # tightened copyleft rule (FR-025)
config/license-exceptions.yaml           # + reviewed docutils entry
tests/
├── fixtures/rst/ fixtures/md/ fixtures/needs_export/   # synthetic, marked SYNTHETIC
├── fixtures/upstream/                   # ≥10 Apache-2.0 excerpts + NOTICE with repo@sha
├── helpers/git_repos.py                 # build fixture repos (normal, symlink, submodule, hooks, oversize)
├── unit/ contract/ integration/
```

**Structure Decision**: follows master spec §14 (`sources/`, `ingestion/`). `domain/ingestion.py`
holds the records F003 consumes. `SourceAdapter` (master spec §5.1) is realised by the git and
export fetchers in `sources/`; `DocumentParser` is the protocol implemented by `RstParser` and
`MarkdownParser`.

## Key Design Decisions

1. **No checkout, ever**: files come from `git cat-file --batch` on the pinned tree; symlink and
   gitlink modes are skipped by mode before any path is considered (R5).
2. **Two-layer path safety**: git `fsckObjects` rejects malformed trees at fetch; our
   `safe_relative_path()` rejects absolute paths, `..`, empty/`.` segments, NUL, backslashes, and
   verifies `resolve()` containment before every write.
3. **Staging then atomic placement**: each source is materialised in
   `data/staging/sync-<uuid>/<id>/<rev>/`; only after all required sources succeed are revision
   dirs moved with `os.replace` (existing identical revisions are reused, verified by hash) and
   the lock written via temp+fsync+replace. Staging is removed on every exit path.
4. **Inspect verifies before parsing**: every acquired file's SHA-256 is checked against the lock;
   a mismatch fails that source (`HASH_MISMATCH`) rather than parsing tampered content.
5. **docutils hardened and isolated** (R2): settings disable all file/URL/raw I/O; registries are
   patched within a context manager; system messages become diagnostics; `publish_doctree` only
   (no writer).
6. **Doctree → blocks**: a visitor maps sections (heading path), paragraphs, lists, tables (rows
   with header flag), literal/code (language), admonitions (kind), need entities (with nested
   blocks), dynamic views, excluded raw, generic directives, toctree entries, and roles
   (references recorded, text preserved). Normalized text never contains raw-HTML or dynamic
   content.
7. **Links**: option values split on commas outside brackets; each item matched against
   `^(?P<id>[^\s\[\]]+)(\[(?P<q>[^\]]*)\])?$`; failures keep raw text + `MALFORMED_LINK`.
   Resolution after all sources are parsed: same-source → unique other source → ambiguous/unresolved.
8. **Exports are separate sources**, never merged into git-source entities; the consistency
   statistic is report-only.
9. **Deterministic ordering**: sources by `source_id`, files by path (bytewise), blocks in
   document order, entities by key, diagnostics by (source, path, line, code).

## Verification Strategy

| Requirement | Verification (layer) |
| --- | --- |
| FR-001, FR-002 | unit: registry schema fixtures (unknown key, http/ssh/file URLs, userinfo, host off-allowlist, bad globs, duplicate source_id) |
| FR-003, FR-004 | integration: sync of fixture repo → lock fields; 40-hex ref passthrough; abbreviated SHA rejected; `release_mapping` null |
| FR-005 | integration: hooks/filters/LFS-pointer fixture repo → marker file never created, raw bytes stored; unit: GitClient argv/env snapshot |
| FR-006 | unit: `safe_relative_path` hostile matrix; integration: symlink + submodule fixture repo → skipped with diagnostics, nothing outside root |
| FR-007 | integration: oversize file → skipped; export over cap / off-allowlist redirect → rejected (MockTransport) |
| FR-008 | integration: required source failure mid-sync → previous lock and revision dirs byte-identical; staging removed |
| FR-009 | contract: socket guard + subprocess spy prove validate/inspect make no network or git calls; help text check |
| FR-010, FR-011, FR-014 | unit/golden: RST + MD fixtures and upstream excerpts → expected blocks/entities; code-block template not an entity |
| FR-012, FR-013 | unit: unknown directive/role, `needextend`, `needtable`, `:ndf:`, `raw`, image, csv-table `:file:` → diagnostics, no evaluation, no file read (open spy) |
| FR-015 | unit: include escape, missing, unselected, depth 9, cycle → `INCLUDE_UNRESOLVED`; valid include keeps per-file lines |
| FR-016 | golden: exact spans for entities/sections/directives; hashes present on every record |
| FR-017, SC-004 | integration: inspect twice → byte-identical JSONL; hash changes when profile changes |
| FR-018 | unit: duplicate-ID-across-sources fixture → ambiguous; same-source preference; unresolved |
| FR-019, FR-020, SC-006 | unit/integration: export fixtures valid/malformed/oversize/missing fields; namespace; `unverified`; consistency counts |
| FR-021, FR-022 | unit: SPDX detection (rst comment, md HTML comment, none, CC-BY-SA) → declared/inherited/unknown + redistribution flag; LICENSE/NOTICE acquired despite selectors |
| FR-023, FR-024 | contract: CLI exit codes, JSON report schema, text summary, `--output` JSONL |
| FR-025 | unit: mixed "BSD; GPL" string fails without exception, passes with reviewed exception |
| SC-001, SC-007 | golden upstream excerpts; real inspect run asserts zero entities from literal blocks |
| SC-002, SC-005 | real run on pinned sources recorded in verification.md (H/B) |

## Complexity Tracking

No constitution violations; section intentionally empty.
