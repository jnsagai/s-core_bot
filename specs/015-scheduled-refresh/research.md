# Research: F011 Scheduled Corpus Refresh

All decisions are agent decisions (agent review, not an approval).

## R1 — How to detect upstream change cheaply

- **Decision**: git sources: `GitClient.resolve_ref` (`git ls-remote` of `refs/heads/<ref>` and
  `refs/tags/<ref>`), compared with the lock's `revision`. Needs exports: conditional `GET` with
  `If-None-Match` (stored ETag) and `If-Modified-Since` (stored Last-Modified); `304` = unchanged,
  `200` = changed (body not read), no stored validators = unknown.
- **Evidence**: 2026-10-02, `curl -sI https://eclipse-score.github.io/score/main/needs.json` returned
  `etag: "6abe5765-b06f3"`, `last-modified: Thu, 01 Oct 2026 12:51:49 GMT`, `content-length: 722675`;
  a request with `If-None-Match: "6abe5765-b06f3"` returned `304` with 0 bytes. The process export
  also carries ETag/Last-Modified.
- **Alternatives**: always run a full sync (incremental git fetch, but ~2 MB of exports per run and a
  rewritten lock every run — rejected for polling); `HEAD` requests (same validators but some
  servers treat HEAD differently; conditional GET is the standard cache-revalidation path);
  GitHub API (needs tokens/rate limits — rejected).

## R2 — Avoid file accumulation when nothing changed

- **Finding**: `SyncService` always writes `source-lock.json` with new `generated_at`/`fetched_at`,
  and `archive_lock` stores a content-addressed copy, so every sync creates a new archive file.
- **Decision**: `SyncService(keep_unchanged_lock=True)` compares the new lock to the current one
  ignoring those timestamps and skips both writes when equal (`SyncOutcome.lock_changed=False`).
  `sources sync` keeps its existing behaviour (default `False`) so F002 contracts are unchanged.
- **Also**: `index build` writes reports only when it runs; refresh writes only its state file.

## R3 — Does `serve` see a new active snapshot without restart?

- **Finding**: `SearchService.pinned(None)` calls `FileSnapshotStore.pin_active()` per request, and
  the per-snapshot cache is keyed by snapshot ID (LRU of a few snapshots). Activation switches the
  catalog pointer in one transaction (F003 OPS-002).
- **Decision**: no server change; add an integration test that activates through refresh while a
  `SearchService` instance stays alive and asserts the next search reports the new snapshot ID and an
  in-flight pinned request keeps the old one.

## R4 — Promotion gate contents

- **Decision**: integrity (`verify_for_activation`), `exact_ids` (`exact_id_suite`), coverage drop
  (documents, chunks, entities; default max drop 0.20), semantic not lost, required sources ok.
- **Rationale**: these catch the realistic failure classes (parser regression, truncated export,
  embedding runtime down, mass deletion/rename) without depending on specific documents.
  Eval suites excluded (clarification Q1).
- **Alternatives**: retrieval recall threshold (cases drift with upstream); diff-size limit
  (legitimate large upstream reorganisations would be held forever; the count drop guard only
  blocks shrinkage, which is the dangerous direction).

## R5 — Overlap protection

- **Decision**: a separate non-blocking `flock` on `data/locks/refresh.lock` for the whole run
  (→ `busy`, exit 4); the existing ingest lock still guards build/activation; a `BUILD_BUSY` from it
  also maps to `busy`.
- **Rationale**: the ingest lock alone would let two refreshes sync concurrently.

## R6 — Scheduler

- **Decision**: systemd user `.service` (Type=oneshot) + `.timer` (`OnBootSec=2min`,
  `OnUnitActiveSec=<interval>`, `RandomizedDelaySec=2min`, `Persistent=true`), rendered by
  `scripts/install_refresh_timer.sh`. systemd never runs two instances of the same oneshot unit.
- **Alternatives**: in-process scheduler in `serve` (violates Principle I and the serve-path rule);
  cron (documented as untested alternative); a separate daemon (Principle VI).
- **Verification**: `systemd-analyze verify` on rendered units in a temp dir (CI-safe when the tool
  exists; skipped otherwise); enabling on the owner's machine is a separate, reported step.

## R7 — Containers

- **Finding**: `Dockerfile` installs no `git`; the bundled runtime has no host port.
- **Decision**: out of scope (spec Assumptions); runbook explains refreshing natively with the
  `host-runtime` profile, which shares the host's data directory and loopback runtime.
