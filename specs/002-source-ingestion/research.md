# Research: F002 Source Registry and Safe Document Normalization

All checks performed 2026-09-28. "Verified" = observed directly; "Documented" = read from upstream
docs or metadata, not yet exercised by this project's code.

## R1. Upstream sampling (master spec §16 F002: "sample actual upstream constructs")

Shallow clones (scratch space, not committed):

| Source | Commit | Commit date | `.rst` | `.md` | Largest `.rst` |
| --- | --- | --- | --- | --- | --- |
| `eclipse-score/score` | `e2373d822fc2f6e9a3f8a0538904f3faa39309ea` | 2026-09-25 | 304 | 19 | 51 010 B |
| `eclipse-score/process_description` | `66321fe6bd131eae58fbd6395b0f0b92d63e00f5` | 2026-09-25 | 304 | 11 | 45 469 B |

**Directives** (both repos, occurrences): need types dominate — `std_req` 581, `feat_req` 355,
`document` 193, `gd_req` 177, `std_wp` 122, `stkh_req` 98, `workflow` 80, `aou_req` 75, … (41 need
types, each carrying `:id:` on 100 % of occurrences). Structural: `note` 418, `list-table` 181,
`code-block` 179, `toctree` 174, `figure` 70, `image` 46, `uml` 35, `grid`/`grid-item-card`
(sphinx-design) 71, `rubric` 17, `glossary` 7, `csv-table` 4, `mermaid` 4, `raw` 8 (all
`raw:: html`). Dynamic Sphinx-Needs: `needextend` 228, `needtable` 132, `needpie` 44, `needarch`
40, `needuml` 4.

**Roles**: `:need:` 2375, `:ref:` 520, `:ndf:` 188 (e.g. `` :ndf:`copy('status', need_id='…')` `` —
a build-time dynamic function), `:term:` 143, `:doc:` 69, `:octicon:` 15, others ≤ 2.

**Includes**: 0 `include` / `literalinclude` in either repo. SRC-007 handling is still required
(master spec) but is exercised by fixtures only for now.

**Need record shape** (verified example):

```rst
.. feat_req:: Async Cooperative Task Runtime
   :id: feat_req__orchestration__exec_async_rt
   :reqtype: Functional
   :security: NO
   :safety: QM
   :derived_from: stkh_req__execution_model__processes[version==1]
   :satisfied_by: feat__orchestration[version==1]
   :status: valid
   :version: 1
   :valid_from: v2.0.0

   The executor shall provide a cooperative task runtime …
```

IDs use `__` separators, mixed case and hyphens (`std_req__aspice_40__MAN-5-BP1`). Link values
are comma-separated IDs with an optional **bracket qualifier** (`[version==1]`). Directives nest
inside need bodies (`.. note::` inside `std_req`). Some content is **tab-indented**.

**Link-valued options** (values consisting only of need-ID-shaped items; values may continue over several
indented lines, e.g. `:complies:` spanning 9 lines in `platform_management_template.rst`): `derived_from` 384,
`satisfied_by` 384, `complies` 282, `realizes` 203, `satisfies` 174, `links` 156, `included_by`
118, `responsible` 79, `approved_by` 79, `input` 75, `supported_by` 60, `contains` 60, `output` 49,
`has` 37, `belongs_to` 30, `fulfils` 30, `includes` 11, `uses` 11, `implements` 10, `violates` 3,
`mitigated_by` 3, `consists_of` 2. (`name` matched twice by the heuristic and is excluded.)

**Traps a naive parser falls into** (verified):

- 2214 `:id:` lines but 2197 distinct values: the duplicates are template examples such as
  `dd_sta__<Feature>__<Title>` **inside `.. code-block:: rst`** — must not become entities.
- ~~`doc__platform_mgt_plan` and `doc__verification_plan` are defined in both repositories~~ —
  **corrected 2026-09-28 during T008**: that was an artifact of the naive grep. In
  `process_description` the first appears after a leading apostrophe (`' .. document::`), which
  makes it an ordinary paragraph, and the second is template text; the published exports share
  **zero** IDs (score 918, process_description 1250). A further trap for naive parsers, and a
  golden test case. Namespaced keys remain required by master spec §9.1 (more repositories will
  be added); cross-source ambiguity is tested with synthetic fixtures.
- `needextend` arguments are Python-like filter expressions
  (`c.this_doc() and is_external == False and "feo/docs/requirements" in docname`) — evaluating
  them would violate SRC-006.

**Licensing**: both repos ship Apache-2.0 `LICENSE` and an Eclipse `NOTICE`. Per-file SPDX
headers: `score` 302/304 Apache-2.0 (2 files without header); `process_description` 301
Apache-2.0, 3 **CC-BY-SA-4.0**, 1 CC0-1.0. Both repos contain a Sphinx `conf.py` (never imported).

**Markdown**: READMEs, contribution guides, `.github/` PR/release templates, design decision
records (`DR-*.md`), training modules.

**Correction 2 (found during implementation, 2026-09-28):** the sampling above counted only RST
directives. Comparing our parse against the published export showed 10 `dec_rec` needs missing —
all defined in `DR-*.md` Markdown via **MyST backtick directives** (```` ```{dec_rec} Title ````,
11 occurrences, plus one `{mermaid}` and one `{toctree}`). No inline MyST roles, no YAML option
blocks. Training modules use Docusaurus-style `:::tip`/`:::quiz` fences (not MyST); CommonMark
keeps their content as paragraphs, so no text is lost (cosmetic limitation, no needs involved).

**Published exports** (verified): `https://eclipse-score.github.io/score/main/needs.json`
(718 776 B, 918 needs) and `…/process_description/main/needs.json` (1 236 569 B). Structure:
`{current_version, project, project_url, versions: {"0.1": {creator: {program: sphinx_needs,
version: 8.3.1}, needs_amount, needs_schema, needs_defaults_removed, needs: {id: {…}}}}}`. Need
fields include `id, type, title, content, docname, lineno, status, tags, sections, section_name,
derived_from, satisfied_by, fulfils_back, is_modified, modifications, …`. **No commit SHA or
revision anywhere in the file** → association with a git revision cannot be verified.

## R2. RST parsing engine

- **Decision**: docutils 0.23 as the RST engine, hardened: `file_insertion_enabled=False`,
  `raw_enabled=False`, `_disable_config=True` (no `docutils.conf` is read), `report_level=5`,
  `halt_level=5` (never raises on markup problems; we collect system messages as diagnostics),
  `warning_stream` captured, `tab_width=8`, `smart_quotes=False`, `syntax_highlight="none"`,
  `doctitle_xform=False`, `docinfo_xform=False`, `sectsubtitle_xform=False`, `line_length_limit`
  raised to 1 000 000. Input decoded by us (strict UTF-8, BOM stripped) and passed as `str`.
- **Directive/role registration**: docutils keeps module-level registries. Our module registers
  (a) need types → `NeedDirective` (permissive option mapping that accepts every option as raw
  text), (b) dynamic directives → `DynamicDirective` (inert, records arguments/options/content),
  (c) literal/diagram directives (`code-block`, `sourcecode`, `uml`, `mermaid`, `graphviz`) →
  literal nodes with language, (d) `raw` → excluded marker, (e) `include`/`literalinclude` →
  `SafeInclude` (R6), (f) Sphinx structural (`toctree`, `glossary`, `only`, …) → generic
  containers. Before each parse, a prescan registers a `GenericDirective` (parses its content as
  nested RST, keeps name/argument/options, emits `UNKNOWN_DIRECTIVE`) for every directive name not
  yet known, and a `GenericRole` for unknown roles, inside a context manager that restores the
  registries afterwards. Parsing is single-threaded (a module lock guards the registries).
- **Rationale**: RST is indentation-, tab- and table-sensitive; docutils is the reference
  implementation and gives exact directive line numbers and real table structure. It executes no
  code; its only I/O paths (include, raw file/url, csv-table file/url, image size probing) are
  disabled by settings or replaced by our directives.
- **Alternatives rejected**: hand-written block parser (would mis-handle grid tables, tabs,
  nested directives — high risk of silent content loss); Sphinx itself (executes `conf.py` and
  extensions — forbidden by SRC-006/ADR-005).
- **Line numbers — verified by prototype 2026-09-28 (T038)**: directive `lineno` is exact
  (1-based) and `content_offset` is 0-based; paragraph/list-item/table-cell `node.line` is the
  exact *first* line and the end follows from `rawsource` line count; section/title `line` is
  the **underline** line (title line + 1) and is corrected by locating the title text; a need
  with options but no body ends at its last option line, taken from `block_text`. Other
  prototype findings: an empty permissive option mapping is falsy, so docutils skips option
  parsing and swallows `:id:` into the title — the mapping must define `__bool__`; directive
  lookup must use the registries (the public lookup needs a live document); docutils 0.23 maps
  `code-block`/`sourcecode` to its own `code`; `role` is both a docutils directive and an S-CORE
  need type (need type wins); `' .. document::` parses as a definition-list term (no need).
- (Original R2 note, superseded by the verification above:) directive `lineno` and content offsets are exact; docutils' `node.line` for
  some body elements (paragraphs, list items) is approximate. Plan: entities, sections and
  directive blocks carry exact spans (asserted by tests); other blocks carry the best available
  line, with the rule documented in data-model.md (FR-016 "where the parser provides them").
  Implementation must verify these against fixtures before relying on them (task T038).

## R3. Docutils license (FR-025)

- PyPI classifiers: `BSD License`, `GNU General Public License (GPL)`, `Public Domain`.
- Verified by installing docutils 0.23 into a scratch venv and reading `COPYING.rst`: the only
  GPL-3.0 item is `tools/editors/emacs/rst.el`, **which is not part of the installed wheel**;
  `docutils/utils/math/math2html.py` (ex-eLyXer, GPL) was relicensed to BSD-2-Clause. Installed
  files are Public Domain / BSD-2-Clause / BSD-3-Clause / PSF — all acceptable.
- **Finding against F001**: `scripts/check_licenses.py` matches allowed keywords by substring, so
  the combined string `BSD License; GNU General Public License (GPL); Public Domain` would
  auto-pass because it contains "BSD". The gate must instead fail any license string containing a
  copyleft identifier (GPL/LGPL/AGPL/"General Public License"/EUPL/SSPL/CC-BY-SA/share-alike)
  unless a reviewed exception exists. docutils then gets an exception entry citing this analysis.

## R4. Markdown engine

- **Decision**: markdown-it-py 4.2.0 (MIT; already present transitively via `rich`, becomes a
  direct dependency), `MarkdownIt("commonmark", {"html": True}).enable("table")`. `html=True` only
  so raw HTML surfaces as `html_block`/`html_inline` tokens that we *exclude with a diagnostic* —
  nothing is rendered. Token `.map` gives 0-based `[start, end)` line ranges → 1-based spans.
- **Alternatives rejected**: mistune/python-markdown (render-oriented, weaker source maps);
  MyST (Sphinx-coupled).

## R5. Git acquisition without executing repository content

- **Decision**: git CLI (verified 2.34.1 locally; prerequisite documented) via fixed argv, never a
  shell. Environment: `GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_GLOBAL=/dev/null` (ignores user
  `insteadOf` rewrites, credential helpers, hooks), `GIT_TERMINAL_PROMPT=0`, `GIT_ASKPASS=` ,
  `GIT_LFS_SKIP_SMUDGE=1`, `GIT_ALLOW_PROTOCOL=https`. Options on every call:
  `-c protocol.allow=never -c protocol.https.allow=always -c core.hooksPath=/dev/null
  -c http.followRedirects=false -c transfer.fsckObjects=true -c submodule.recurse=false
  -c credential.helper=`.
- **Flow**: `git ls-remote --exit-code <url> refs/heads/<ref> refs/tags/<ref>` (exactly one
  match or error; a 40-hex `ref` skips resolution) → bare cache repo `data/cache/git/<id>.git`
  (`git init --bare`) → `git fetch --depth 1 --no-tags --no-recurse-submodules <url> <sha>` →
  `git cat-file -t <sha>` must be `commit` → `git ls-tree -r -z -l --full-tree <sha>` →
  `git cat-file --batch` streams blob bytes. **No checkout ever happens**, so hooks, attribute
  filters, LFS smudge and symlink materialization cannot run; tree entries with mode `120000`
  (symlink) and `160000` (gitlink/submodule) are skipped by mode.
- `transfer.fsckObjects=true` additionally rejects malformed trees (e.g. `..` or `.git` path
  components) at fetch time — defense in depth behind our own path validation.
- **Tests**: `GitClient(allowed_protocols=...)` is a constructor argument; production code passes
  `{"https"}`, tests pass `{"file"}` to use local fixture repositories. The value is not reachable
  from configuration (FR-002).
- **Alternatives rejected**: `git clone` + checkout (runs filters, creates symlinks); `git archive`
  + tar extraction (tar path/symlink pitfalls); dulwich (extra dependency, no benefit here).

## R6. Safe includes (SRC-007)

- **Decision**: `SafeInclude` replaces docutils' `include`/`literalinclude`. It accepts only a
  relative path; resolves it against the including file's directory inside the **acquired
  revision tree**; requires the result to be in the source's selected file set; rejects `:url:`,
  absolute paths and `<standard>` includes; enforces depth ≤ 8 and cycle detection via an include
  stack stored on the document; reads the file through the same strict decoder; inserts lines with
  `state_machine.insert_input(lines, source=<path>)` so line attribution stays per file.
  `literalinclude` inserts a literal block instead. All refusals → `INCLUDE_UNRESOLVED` diagnostic.

## R7. Export download

- **Decision**: httpx (already a dependency) with `follow_redirects=False`; redirects followed
  manually up to 3 hops only when the target is HTTPS and on the allowlist; streamed with a byte
  cap; connect 10 s / read 30 s timeouts; SHA-256 computed while streaming. Stored as
  `data/sources/<id>/<sha256>/needs.json`.
- **Validation (inspect)**: Pydantic models with `extra="allow"` on need objects (raw fields kept)
  but required `id`, `type`, `title`, `docname`; string fields ≤ 1 MiB; ≤ 200 000 needs; exactly
  the declared `current_version` key used. Consistency statistic matches by `id` + path `<docs_root>/<docname>.rst|.md` in the
  associated source. Verified necessary: export `docname` is Sphinx-source-relative
  (`features/orchestration/requirements/index`) while the repository path is
  `docs/features/orchestration/requirements/index.rst`; `docs_root` is `docs` (score) and
  `process` (process_description). Also report `id_only_matched` (same ID, different path).

## R8. Selectors (globs)

- **Decision**: own glob→regex translation with POSIX semantics: `**` = zero or more whole path
  segments, `*` = any run of non-`/` characters, `?` = one non-`/` character, character classes
  unsupported (rejected by validate). Python 3.12 lacks `PurePath.full_match` and `fnmatch` lets
  `*` cross `/`, so neither is used. Exhaustively unit-tested.

## R9. Canonical serialization and IDs (SRC-010)

- **Decision**: canonical JSON = `json.dumps(obj, sort_keys=True, separators=(",", ":"),
  ensure_ascii=False)` encoded UTF-8, wrapped with `canonical_version: 1`. `processing_hash` =
  SHA-256 of canonical {parser profile content, `PARSER_VERSION`, docutils version,
  markdown-it-py version}. Document key = SHA-256(`source_id`, `path`, raw SHA-256,
  `processing_hash`); identical bytes + configuration ⇒ identical key regardless of revision
  (enables F003 embedding reuse). Floating point never appears in normalized records.

## R10. Registry, profile and lock locations

- `config/sources.yaml` (committed, human-edited) and `config/parser-profiles/s-core.yaml`
  (committed, versioned). Lock at `data/source-lock.json` (generated, git-ignored; master spec
  §10.2 path). Acquired trees `data/sources/<id>/<revision>/` (files chmod 0444), git cache
  `data/cache/git/`, staging `data/staging/sync-<uuid>/`, reports `data/reports/`.
- Redistribution license allowlist (registry, initial): `Apache-2.0, MIT, BSD-2-Clause,
  BSD-3-Clause, CC0-1.0, CC-BY-4.0`. CC-BY-SA-4.0 intentionally absent → `requires_review`.

## R11. Performance expectation

- ~620 small files (≤ 51 KB). docutils parses typical files in tens of milliseconds → inspect of
  both sources expected well under the 2-minute SC-005 budget; to be measured, not assumed.
