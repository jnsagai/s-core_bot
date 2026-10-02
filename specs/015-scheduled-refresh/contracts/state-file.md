# Contract: `data/refresh-state.json`

Written by `refresh` only, atomically (temp file + fsync + `os.replace`), once per run except
`busy`. Read by `doctor`. Format: `RefreshState` in `data-model.md`, `schema_version: 1`.

```json
{
  "schema_version": 1,
  "last_success_at": "2026-10-02T10:15:41Z",
  "exports": {
    "score-platform-needs": {
      "url": "https://eclipse-score.github.io/score/main/needs.json",
      "etag": "\"6abe5765-b06f3\"",
      "last_modified": "Thu, 01 Oct 2026 12:51:49 GMT"
    }
  },
  "last_run": { "outcome": "up-to-date", "reason": "no upstream change", "...": "..." }
}
```

- An unreadable or invalid file is treated as absent (refresh then syncs; `doctor` reports it as
  a warning) and is replaced at the end of the run.
- The file holds no secrets: URLs come from the registry, which already rejects credentials.

## `doctor` line

| State | Status | Code |
| --- | --- | --- |
| no file | info | `REFRESH_NOT_RUN` |
| last outcome `up-to-date` / `activated` | ok | `REFRESH_OK` |
| last outcome `held` / `failed` | warning | `REFRESH_HELD` / `REFRESH_FAILED` (reason + last success time) |
| invalid file | warning | `REFRESH_STATE_INVALID` |

A refresh line never makes `doctor` exit non-zero.
