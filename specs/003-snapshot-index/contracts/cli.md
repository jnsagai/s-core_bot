# CLI Contract: `index`, `snapshots`, `bundle` (F003)

Exit codes follow F001: `0` success, `1` operational/integrity failure, `2` configuration or
usage error, `130` interrupted. The global `--config` option comes first
(`score-assistant --config config/local.yaml index build …`). All commands read `data_dir`
from the app config. None of them downloads anything. The only network use is the loopback
embedding runtime at `runtime.base_url`, and every help text states this where it applies.
`--json` prints one machine-readable result object on stdout. Progress goes to stderr.

## `index build [--source-lock PATH] [--profiles-dir DIR] [--lexical-only] [--activate] [--json]`

Help first line: **"Builds a snapshot offline; uses only the local embedding runtime (no
downloads)."** Defaults: `--source-lock data/source-lock.json`, `--profiles-dir
config/parser-profiles`.

Steps (research R7): acquire ingest lock (busy → exit 1 `BUILD_BUSY`) → recover interrupted
jobs → verify lock (required source not `ok` or missing on disk → exit 1
`REQUIRED_SOURCE_FAILED`, before chunking) → normalize → chunk → write corpus → embed (reuse
first) → write manifests/reports → validate → publish as `validated` → optionally activate.

- Embedding runtime unreachable, model missing, or its digest ≠ model lock: without
  `--lexical-only` → exit 1 `EMBEDDING_UNAVAILABLE` (message suggests `--lexical-only` or `models
  pull`). With the flag, the build proceeds with `semantic: absent`.
- Stderr progress: `stage normalizing`, `chunks 12345 (prose 8001, need 2168, …)`,
  `embedding 1200/12345 (reused 11145)`, `published 20260928T101500Z-3fa2b1c9 (validated)`.
- `--activate` activates after validation in the same invocation (same rules as `snapshots
  activate`, including the lexical-over-semantic warning and retention).
- `--json` result: `{"snapshot_id", "state", "semantic", "counts", "embedded": {"reused",
  "new"}, "activated": bool, "duration_seconds", "network_used": "loopback-embedding-only" |
  "none"}`.
- Exit 0 on a validated (and, with `--activate`, activated) snapshot.

## `index validate --snapshot ID [--json]`

Help first line: **"Validates a snapshot offline; may query the local runtime for model
identity (never embeds)."** It runs every check in research R9 and writes
`data/reports/validate-<id>-<utc>.json` (the snapshot directory is immutable and never written).
Text output: one line per failed integrity check and a `semantic: enabled|absent|disabled|
unverified` line with guidance (e.g. `disabled: model digest 1234… differs from snapshot
0a10…; rebuild with "index build" to reindex`). Exit 0 no integrity failure, 1 any integrity
failure or unknown snapshot, 2 usage error.

## `snapshots list [--json]`

Offline. Table: `ID  STATE  SEMANTIC  CHUNKS  CREATED  ACTIVATED  PINNED`, newest first, marking the
active one with `*`. Deleted snapshots are hidden unless `--all` is passed. `PINNED` is `yes` when
a non-blocking exclusive lock attempt on the pin file fails. Exit 0.

## `snapshots activate ID`

Offline except the identity query (runtime digest check for semantic snapshots; unreachable →
`unverified` warning, activation proceeds). Re-verifies checksums and schema (mismatch → exit 1
`CHECKSUM_MISMATCH` naming the file; active unchanged). Only `validated`/`retired` targets are
allowed (otherwise exit 1 `NOT_ACTIVATABLE`). The already-active target is a no-op (exit 0).
Activating `semantic: absent` over an active `present` snapshot prints `warning: semantic search
will be unavailable`. It then runs retention and prints what was deleted or skipped (pinned).

## `snapshots rollback`

Activates the `previous_id` of the latest activation-history row (research R7). No history,
target deleted, or target not `retired` → exit 1 `NO_ROLLBACK_TARGET`. Otherwise it follows the same
verification and retention as `activate`.

## `bundle export --snapshot ID --output PATH [--acknowledge-license-review REASON] [--json]`

Offline. Refuses `failed`/`building`/`deleted` snapshots. If the manifest lists
`license_review` documents and no acknowledgement is given → exit 1
`LICENSE_REVIEW_REQUIRED`, listing each path. Writes `PATH` via a temp file + rename (refuses
to overwrite an existing file). Prints the bundle SHA-256.

## `bundle inspect PATH [--json]`

Offline and read-only. It runs import pass 1 (research R10) without extracting, then prints
snapshot ID, schema versions, counts, embedding identity, total size, entry count and license
notes/acknowledgement. An unsafe or oversized bundle, or a newer schema → exit 1 with the reason.

## `bundle import PATH [--json]`

Offline. Two-pass import (research R10). It registers `validated` (never active) and prints the
snapshot ID and `activate with: score-assistant snapshots activate <id>`. Any rejection →
exit 1 `BUNDLE_REJECTED` (reason), nothing registered, staging removed.
