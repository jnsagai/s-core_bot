# Contract: Catalog, Locks and Pins (F003)

## `data/catalog.sqlite` (user_version 1, WAL)

```sql
CREATE TABLE snapshots (
  snapshot_id TEXT PRIMARY KEY,
  state TEXT NOT NULL CHECK (state IN ('building','validated','active','retired','failed','deleted')),
  created_at TEXT NOT NULL, validated_at TEXT, activated_at TEXT, retired_at TEXT, deleted_at TEXT,
  manifest_sha256 TEXT, schema_version INTEGER, semantic TEXT CHECK (semantic IN ('present','absent')),
  chunks INTEGER, job_id TEXT, failure TEXT);
CREATE UNIQUE INDEX one_active ON snapshots (state) WHERE state = 'active';
CREATE TABLE active_pointer (id INTEGER PRIMARY KEY CHECK (id = 1),
  snapshot_id TEXT REFERENCES snapshots, updated_at TEXT NOT NULL);
CREATE TABLE activation_history (seq INTEGER PRIMARY KEY AUTOINCREMENT,
  snapshot_id TEXT NOT NULL, previous_id TEXT, kind TEXT NOT NULL CHECK (kind IN ('activate','rollback')),
  at TEXT NOT NULL);
CREATE TABLE build_jobs (job_id TEXT PRIMARY KEY,
  kind TEXT NOT NULL CHECK (kind IN ('build','import')),
  state TEXT NOT NULL CHECK (state IN ('running','succeeded','failed')),
  pid INTEGER NOT NULL, started_at TEXT NOT NULL, finished_at TEXT, snapshot_id TEXT,
  stage TEXT, failure TEXT);
```

Invariants: `active_pointer.snapshot_id` equals the single `state='active'` row (or both are
absent). Every mutation runs in `BEGIN IMMEDIATE … COMMIT`. `user_version > 1` → every command
refuses with `SCHEMA_UNSUPPORTED` before reading tables. The catalog is created on first write
(`index build`, `bundle import`). Read-only commands never create it.

### Transactions

| Operation | Single transaction content |
| --- | --- |
| build start | insert job `running` + snapshot `building` |
| publish | snapshot `building → validated` + `manifest_sha256`, `semantic`, `chunks`; job `succeeded` |
| failure (caught) | snapshot `failed` + `failure`; job `failed` + `failure` |
| recovery (next build) | stale `running` jobs → `failed('interrupted')`; their `building` rows → `failed` |
| activate / rollback | old active → `retired`; target → `active`; pointer; history row |
| retention delete | row → `deleted`, `deleted_at` (after the directory is removed) |
| import register | insert snapshot `validated` (+ import job `succeeded`) |

## Locks and pins (`data/locks/`, `data/pins/`)

| File | Holder | Mode | Meaning |
| --- | --- | --- | --- |
| `data/locks/ingest.lock` | `index build`, `bundle import`, `snapshots activate/rollback` (retention) | `flock LOCK_EX\|LOCK_NB` | single writer; busy → exit 1 `BUILD_BUSY` |
| `data/pins/<id>.pin` | any reader (serve/F004 handles, a build reading reuse vectors, export) | `flock LOCK_SH` | snapshot in use; released on close or process exit (incl. SIGKILL) |
| `data/pins/<id>.pin` | retention | `flock LOCK_EX\|LOCK_NB` | acquired → safe to delete; busy → skip ("pinned") |

`SnapshotStore.pin(id)` protocol: `open(O_CREAT)` → `flock(LOCK_SH)` → re-read catalog row
(state ∉ {deleted, failed, building}) and check that the directory exists → return the handle.
If the check fails: unlock, raise `SNAPSHOT_NOT_FOUND`. `SnapshotStore.pin_active()` resolves the
active pointer and retries once if the pinned target was deleted between resolve and pin.

A pinned handle exposes: the manifest, a read-only `corpus.sqlite` connection
(`file:…?mode=ro&immutable=1`, `check_same_thread=False`), and a lazily opened read-only
`numpy.memmap` of `embeddings.f32` (shape checked against the embedding manifest). All reads
go through the handle, so a reader never observes a mix of snapshots (FR-014).
