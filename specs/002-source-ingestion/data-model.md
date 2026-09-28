# Data Model: F002 Source Registry and Safe Document Normalization

Frozen Pydantic models in `src/score_docs_assistant/domain/ingestion.py` unless noted. Timestamps
UTC ISO 8601. Hashes are lowercase hex SHA-256. No floats in any record (R9).

## Registry side (`sources/registry.py`, `sources/profile.py`)

**SourceRegistry**: `schema_version: 1`, `allowed_hosts: list[str]` (non-empty, lowercase host
names), `redistribution_allowed_licenses: list[str]` (SPDX IDs), `limits: SyncLimits`,
`sources: list[SourceDefinition]` (unique `source_id`s). See [contracts/registry.md](contracts/registry.md).

**SourceDefinition** — discriminated by `kind`:

| Field | git | needs-export | Rules |
| --- | --- | --- | --- |
| `source_id` | ✓ | ✓ | `^[a-z][a-z0-9-]{1,62}$` |
| `repository` | ✓ | — | `https://<allowed host>/…`, no userinfo/query/fragment |
| `ref` | ✓ | — | branch/tag name, or full 40-hex SHA; abbreviated SHA rejected |
| `url` | — | ✓ | same URL rules |
| `associated_source` | — | optional | must name a `git` source |
| `docs_root` | — | required with `associated_source` | repository-relative Sphinx source dir; export `docname` maps to `<docs_root>/<docname>.rst` or `.md` |
| `include` / `exclude` | ✓ | — | globs per R8; `include` non-empty |
| `authority` | ✓ | ✓ | free label, e.g. `official-project` |
| `repository_license` | ✓ | ✓ | SPDX ID declared by operator after inspecting LICENSE |
| `license_policy` | ✓ | ✓ | `inspect-file-and-repository-notices` (only value in F002) |
| `required` | ✓ | ✓ | bool |
| `parser_profile` | ✓ | — | name of a file in `config/parser-profiles/` |

**ParserProfile**: `profile_version: int`, `need_types: list[str]`, `link_options: list[str]`,
`reference_roles: list[str]` (e.g. `need`), `dynamic_directives: list[str]`, `dynamic_roles:
list[str]`, `literal_directives: dict[str, str|None]` (name → fixed language, e.g. `uml:
plantuml`), `excluded_directives: list[str]` (e.g. `raw`). `profile_hash` = canonical hash of the
file's parsed content.

## Lock side (`sources/lock.py`)

**SourceLock**: `schema_version: 1`, `generated_at`, `registry_sha256`,
`redistribution_allowed_licenses`, `sources: list[LockedSource]`
(sorted by `source_id`). Written atomically. See [contracts/lock.md](contracts/lock.md).

**LockedSource**: `source_id`, `kind`, `status: ok|failed`, `failure: str|None`, `required`, `revision`
(git: 40-hex SHA; export: SHA-256 of bytes), `ref` (git), `url`/`repository`, `fetched_at`,
`selector_sha256` + `excluded_by_selector` count (git), `authority`, `repository_license`, `parser_profile` (git),
`associated_source` + `docs_root` (export), `files: list[LockedFile]`, `notice_files: list[LockedFile]`,
`revision_status: pinned|unverified`, `release_mapping: None`, `skipped: list[SkippedEntry]`.

**LockedFile**: `path` (POSIX, relative), `sha256`, `size`. **SkippedEntry**: `path`, `reason`
(`symlink`, `submodule`, `oversize`, `unsafe_path`).

On-disk paths are `data/sources/<source_id>/<revision>/<path>`; `source_id` is unique in the
registry and a git tree cannot contain duplicate paths, so cross-source or intra-source path
collisions are impossible by construction.

State: a lock is only written when every `required` source is `ok`; optional sources may be
`failed` (with `failure`), producing a coverage limitation.

## Normalized side (`ingestion/*`)

**NormalizedDocument**

| Field | Type | Notes |
| --- | --- | --- |
| `document_key` | str | SHA-256(source_id, path, raw_sha256, processing_hash) — R9 |
| `source_id`, `revision`, `path` | str | revision = SHA or export hash |
| `format` | `rst` \| `markdown` | |
| `title` | str \| None | first section title |
| `license` | LicenseRecord | |
| `raw_sha256` | str | of file bytes |
| `normalized_sha256` | str | canonical hash of `blocks` |
| `processing_hash` | str | profile + parser/library versions |
| `blocks` | list[Block] | document order |
| `diagnostics` | list[Diagnostic] | |
| `status` | `included` \| `partial` \| `failed` | partial = ≥1 warning diagnostic |

**LicenseRecord**: `spdx: str|None`, `basis: declared|inherited|unknown`, `redistribution:
allowed|requires_review`.

**Block**

| Field | Type | Notes |
| --- | --- | --- |
| `kind` | enum | `section`, `paragraph`, `list`, `list_item`, `table`, `code`, `literal`, `diagram`, `admonition`, `field_list`, `definition_list`, `block_quote`, `toctree`, `need`, `dynamic_view`, `raw_excluded`, `generic_directive`, `image` |
| `text` | str | normalized, whitespace-collapsed; empty for `raw_excluded`/`dynamic_view` |
| `heading_path` | list[str] | enclosing section titles |
| `line_start`, `line_end` | int \| None | 1-based inclusive; exact for `section`, `need`, directive-based kinds; best-available otherwise (R2) |
| `origin_path` | str | differs from document `path` for included lines (R6) |
| `raw_sha256` | str | of the raw source span |
| `attrs` | dict[str, str \| list[str] \| list[list[str]]] | e.g. `language`, `directive`, `argument`, `options` (raw), `admonition`, `rows` + `header_rows` for tables, `uri`/`alt` for images, `entries` for toctree |
| `references` | list[LinkRef] | `:need:`/`:ref:`/`:doc:` roles within the block |
| `children` | list[Block] | nested content (need bodies, admonitions, list items) |
| `entity_key` | str \| None | set on `need` blocks |

**Entity**

| Field | Type | Notes |
| --- | --- | --- |
| `key` | str | `<source_id>:<need_id>` (for duplicates within a source: `…#2` suffix by document order, with `DUPLICATE_ID_IN_SOURCE`) |
| `need_id` | str | exact, case preserved |
| `type`, `title` | str | |
| `options` | dict[str, str] | every option, raw |
| `links` | list[LinkRef] | from profile link options |
| `document_key`, `path`, `line_start`, `line_end` | | exact span of the directive block |
| `origin` | `rst` \| `markdown` \| `needs-export` | markdown = MyST fenced directive in a `.md` file |
| `revision_status` | `pinned` \| `unverified` | exports always `unverified` (FR-019) |
| `export_fields` | dict \| None | raw export fields (exports only; e.g. `tags`, `fulfils_back`) |

**LinkRef**: `via` (option name or `role:<name>`), `target_id`, `qualifier: str|None`, `raw`,
`resolution: resolved|ambiguous|unresolved|malformed`, `resolved_keys: list[str]`.

Resolution rules (FR-018): (1) entity with `target_id` in the same source → `resolved`;
(2) exactly one entity with that ID among other git sources → `resolved`; (3) several →
`ambiguous` with all keys; (4) none → `unresolved`. Export entities are never resolution targets
for git-source links (separate namespace); export links resolve within their own export only.

**Diagnostic**: `code`, `severity: info|warning|error`, `source_id`, `path`, `line: int|None`,
`message`. Code catalogue in [contracts/normalized-output.md](contracts/normalized-output.md).

**CoverageReport** (per source + totals): `selected`, `included`, `partial`, `failed` (path +
reason), `skipped` (path + reason, from lock), `excluded_by_selector` (count), `entities`,
`links: {resolved, ambiguous, unresolved, malformed}` + lists of ambiguous/unresolved items,
`diagnostics_by_code`, `licenses: {spdx → count}`, `requires_review` (paths),
`export_consistency: {matched, missing_in_source, missing_in_export}` for exports.
Invariant: `selected == included + partial + failed` for every git source (SC-002).
