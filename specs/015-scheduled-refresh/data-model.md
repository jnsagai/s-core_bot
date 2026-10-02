# Data Model: F011 Scheduled Corpus Refresh

All records are Pydantic models with `extra="forbid"`, independent of FastAPI/Ollama.

## RefreshConfig (app config section `refresh`)

| Field | Type | Default | Rule |
| --- | --- | --- | --- |
| `max_count_drop` | float | 0.20 | 0 ≤ x < 1; max allowed fractional drop of documents, chunks, entities |
| `check_exports` | bool | true | false → exports always `unknown` (always sync) |

## SourceCheck

| Field | Type | Notes |
| --- | --- | --- |
| `source_id` | str | registry ID |
| `kind` | `git` \| `needs-export` | |
| `status` | `unchanged` \| `changed` \| `unknown` | |
| `locked` | str \| null | revision in the current lock |
| `upstream` | str \| null | resolved commit (git) or `null` (exports: content hash unknown until sync) |
| `detail` | str | e.g. "304 not modified", "no stored validator" |

## GateCheck

| Field | Type | Notes |
| --- | --- | --- |
| `id` | `integrity` \| `exact_ids` \| `coverage_drop` \| `semantic` \| `required_sources` | |
| `status` | `pass` \| `fail` | |
| `detail` | str | measured values and threshold, never document text |

## RefreshRun (one execution; also the `last_run` of the state)

| Field | Type | Notes |
| --- | --- | --- |
| `started_at`, `finished_at` | datetime (UTC) | |
| `outcome` | `up-to-date` \| `activated` \| `held` \| `failed` \| `busy` | exactly one |
| `reason` | str | human-readable, one line |
| `active_before` | str \| null | active snapshot at start |
| `active_after` | str \| null | active snapshot at end |
| `candidate` | str \| null | snapshot built in this run |
| `checks` | list[SourceCheck] | empty if the check did not run |
| `synced` | bool | sync ran |
| `lock_changed` | bool | sync wrote a new lock |
| `revision_changes` | list[{source_id, before, after}] | lock before vs after |
| `gate` | list[GateCheck] | empty if no candidate |
| `timings` | dict[str, float] | seconds per step: check, sync, build, gate, activate |

## ExportValidator

| Field | Type |
| --- | --- |
| `url` | str |
| `etag` | str \| null |
| `last_modified` | str \| null |

## RefreshState (`data/refresh-state.json`)

| Field | Type | Notes |
| --- | --- | --- |
| `schema_version` | 1 | |
| `last_run` | RefreshRun \| null | |
| `last_success_at` | datetime \| null | last `up-to-date` or `activated` |
| `exports` | dict[source_id, ExportValidator] | saved only after a successful sync |

## State transitions

```text
start ──lock busy──▶ busy
  │
  ▼ check ──error──▶ failed
  │ all unchanged & built-from-lock ──▶ up-to-date
  ▼ sync ──required source failed──▶ failed
  │ active built from (unchanged) lock ──▶ up-to-date
  ▼ build ──error (incl. embedding unavailable, BUILD_BUSY→busy)──▶ failed
  ▼ gate ──any fail──▶ held (candidate stays validated)
  ▼ activate ──active changed meanwhile──▶ held
  └──▶ activated
```
