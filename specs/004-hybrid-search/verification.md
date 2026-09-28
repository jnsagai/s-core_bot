# Verification Record: F004 Evidence Search and Exact-ID Navigation

Commands actually run, with results. Categories are kept apart (constitution VII): **mocked**
(fixture snapshots + `FakeEmbeddingProvider`), **real runtime** (local Ollama), **real snapshot**
(active snapshot `20260928T140548Z-7c6a05b3` built from the pinned F002 lock). "Not run" means
not run.

## Phases 1–3 (setup, foundation, US1 exact lookup) checkpoint — 2026-09-28

```text
$ uv run ruff format --check . && uv run ruff check . && uv run mypy src
281 files already formatted / All checks passed! / Success: no issues found in 95 source files
$ uv run pytest -q
635 passed, 6 skipped (opt-in markers, not run)
```

Mocked coverage: config additions; query tokenization, alias rule, quoted-literal FTS expressions
(checked valid against a real FTS5 table for operator-only inputs), 64-term cap, excerpts;
identifier validation, including `FileSnapshotStore.pin()` refusing `../../escape` **before**
creating any file; exact/alias lookup, pinned-before-unverified ordering, export-only records,
namespaced queries, no fuzzy matches; relationships exactly as stored (resolved and unresolved,
incoming via resolved keys, paging bounds); snapshot binding (active, validated, retired queryable;
failed/deleted/building → `SNAPSHOT_NOT_FOUND`; no active → `NO_ACTIVE_SNAPSHOT`); `lookup` CLI.

Real snapshot:

```text
$ score-assistant --config config/local.yaml lookup feat_req__com__interfaces --relationships
[exact] score-platform:feat_req__com__interfaces  feat_req  'Communication Interfaces'  status valid
  score-platform@e2373d822fc2 (pinned)  docs/features/communication/requirements/index.rst:67-82
  links: 6 outgoing, 7 incoming   (all listed with resolution)
$ … lookup feat_req__com__interfaces --json | jq -r '.entities[] | .key+" "+.revision_status'
score-platform:feat_req__com__interfaces pinned
score-platform-needs:feat_req__com__interfaces unverified
$ … lookup STD_REQ-ASPICE_40-SWE-5-BP2
[alias] score-process:std_req__aspice_40__SWE-5-BP2 … process/standards/aspice_40/swe/swe.5.rst:83-99
```

- Deviations: the quickstart example ID `feat_req__baselibs__json` (written during planning) does
  not exist in the corpus. It was replaced with the real `feat_req__com__interfaces`.
- `id_tokens` also strips leading `([\"'` (an ID in parentheses would otherwise never match); FR-006
  updated accordingly.
- Environment: planning was interrupted when the root filesystem filled up (0 MB free), caused by
  a 30 GB `~/.fabro/storage/logs/server.log` outside this project; the owner truncated it and
  work resumed.
