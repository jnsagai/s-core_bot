# CLI contract: `score-assistant refresh`

```text
score-assistant [--config <app.yaml>] refresh
    [--sources <registry.yaml>]      # default config/sources.yaml
    [--profiles-dir <dir>]           # default config/parser-profiles
    [--lexical-only]                 # force a keyword-only build
    [--json]
```

Uses the network (allowlisted source hosts only). Never started by `serve`.

## Outcomes and exit codes

| Outcome | Exit | Meaning |
| --- | --- | --- |
| `up-to-date` | 0 | active snapshot already built from the current upstream state; nothing built |
| `activated` | 0 | a new snapshot passed the gate and is active |
| `failed` | 1 | check, sync or build failed; nothing activated, previous state kept |
| (config/usage) | 2 | invalid configuration or arguments (as every command) |
| `held` | 3 | candidate built but gate failed (or active changed meanwhile); candidate stays `validated` |
| `busy` | 4 | another refresh, build, import or activation is running; nothing changed |

## Text output (stdout, last line is the summary)

```text
check  score-platform        changed    e2373d8 → 4e8b93a
check  score-platform-needs  unchanged  304 not modified
sync   lock updated (2 sources changed)
build  20261002T101500Z-1a2b3c4d  validated  semantic present  (38.2 s)
gate   integrity pass | exact_ids pass (2201/2201) | coverage_drop pass | semantic pass | required_sources pass
activated 20261002T101500Z-1a2b3c4d (previous 20260928T140548Z-7c6a05b3)
```

Progress from sync/build goes to stderr, as in `sources sync` and `index build`.

## JSON output (`--json`, one object on stdout)

The `RefreshRun` record of `data-model.md` plus `"network_used": true|false` (false only for
`busy`) and `"state_path"`. Keys are stable; no document text.

## Guarantees

- `up-to-date` writes only `data/refresh-state.json`.
- `failed`, `held`, `busy` never change the active snapshot.
- `busy` writes nothing at all (not even the state file), so it cannot hide the running job's result.
