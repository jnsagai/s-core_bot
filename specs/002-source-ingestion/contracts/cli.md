# CLI Contract: `score-assistant sources …` (F002)

Exit codes follow F001: `0` success, `1` operational failure, `2` configuration/usage error,
`130` interrupted.

## `sources validate --config PATH`

Offline. Validates the registry and every referenced parser profile (schema, unknown keys, URL
rules, host allowlist, glob syntax, duplicate IDs, `associated_source` targets). Prints each error
as `<dotted.path>: <reason>`. Exit 0 valid, 2 invalid. Never touches the network or `data/`.

## `sources sync --config PATH [--json]`

Help text first line: **"Uses the network: resolves refs and downloads approved sources."**
Steps: validate (errors → exit 2) → for each source in `source_id` order: resolve ref → fetch →
extract selected files + root LICENSE/NOTICE/COPYING into staging (git) or download export
(needs-export) → if every `required` source succeeded: place revisions atomically, write
`data/source-lock.json` atomically, exit 0; else discard staging, keep previous lock, exit 1.
Progress lines on stderr (`<source_id>: resolved main -> <sha>`, `… extracted 304 files`).
`--json` result on stdout (values illustrative):

```json
{"lock_path": "data/source-lock.json", "network_used": true,
 "sources": [{"source_id": "score-platform", "status": "ok", "revision": "e2373d8…",
              "files": 323, "skipped": 0, "bytes": 1234567}]}
```

Ctrl-C: staging removed, previous lock untouched, exit 130.

## `sources inspect --lock PATH [--json] [--output DIR]`

Offline (no network, no git). Verifies every acquired file hash against the lock, normalizes all
`ok` sources, resolves relationships, builds the coverage report, and writes it to
`data/reports/coverage-<lock-sha256-prefix>.json`. Human summary on stdout, e.g. (numbers illustrative, not measured):

```
score-platform @ e2373d8  selected 323  included 290  partial 31  failed 2  entities 1403
  links: resolved 2811  ambiguous 2  unresolved 144  malformed 0
  requires review: 0 files   top diagnostics: DYNAMIC_NOT_EVALUATED 214, UNKNOWN_DIRECTIVE 71
```

`--json` prints the full report ([normalized-output.md](normalized-output.md)) instead.
`--output DIR` additionally writes `documents.jsonl` and `entities.jsonl` (deterministic order).
Exit 0 when every required source in the lock is `ok` and was normalized; exit 1 if a required
source is `failed` in the lock, missing from disk, or fails hash verification; exit 2 for an
unreadable/invalid lock.
