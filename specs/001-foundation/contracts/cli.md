# CLI Contract: `score-assistant` (F001)

Global options (before the subcommand): `--config PATH` (else `SCORE_ASSISTANT_CONFIG`, else
built-in defaults), `--version`. Only the commands below exist in F001 (FR-003).

## Exit codes (all commands)

| Code | Meaning |
| --- | --- |
| 0 | Success (for `doctor`: no failed check; warnings allowed) |
| 1 | Operational failure (a failed check, runtime unreachable, bind failed, pull failed) |
| 2 | Configuration or usage error (invalid/unknown key, non-loopback bind, bad arguments) |
| 130 | Interrupted by user (SIGINT) |

## `score-assistant doctor [--json]`

Network: loopback runtime only. Never pulls.
Checks, in order: `config.valid`, `app.version`, `platform`, `memory`, `gpu`, `disk.data`,
`disk.models`, `data_dir.writable`, `runtime.reachable`, `runtime.cloud` (info),
`model.generation`, `model.embedding`, `model.lock`, `corpus.state`.

Dependent checks: when `runtime.reachable` is not `ok`, `model.generation`, `model.embedding` and
`model.lock` are reported with status `skipped` and code `RUNTIME_REQUIRED` (they neither pass nor
fail); the runtime failure alone drives exit code 1.

Text output: one line per check `[STATUS] id: message` plus indented `→ next action`.
JSON output (`--json`) — stdout, single object:

```json
{
  "schema_version": 1,
  "app_version": "0.1.0",
  "generated_at": "2026-09-27T12:00:00Z",
  "exit_code": 1,
  "config": {"file": "config/local.yaml", "sources": {"server.port": "file"}},
  "checks": [
    {"id": "runtime.reachable", "status": "failure", "code": "RUNTIME_UNREACHABLE",
     "message": "No runtime answered at http://127.0.0.1:11434 within 1.0 s.",
     "next_action": "Start Ollama (e.g. `sudo snap start ollama`) and re-run doctor.",
     "details": {"base_url": "http://127.0.0.1:11434"}}
  ]
}
```

Status/code catalogue (minimum): `CONFIG_INVALID` (exit 2), `RUNTIME_UNREACHABLE`,
`RUNTIME_TIMEOUT`, `RUNTIME_INCOMPATIBLE`, `RUNTIME_CLOUD_UNVERIFIED` (info),
`MODEL_MISSING` (warning), `MODEL_REMOTE` (failure), `MODEL_LOCK_MISMATCH` (failure),
`MODEL_NOT_LOCKED` (warning), `DATA_DIR_MISSING` (warning), `DATA_DIR_NOT_WRITABLE` (failure),
`DISK_LOW` (warning), `GPU_NOT_DETECTED` (info), `CORPUS_ABSENT` (warning),
`CORPUS_INCOMPATIBLE` (failure).

## `score-assistant models inspect [--json]`

Network: loopback runtime only. Never pulls. Lists each profile model with `role`, `tag`,
`present`, `digest`, `size_bytes`, `family`, `quantization`, `is_remote`, `lock_status`.
Exit 0 if runtime reachable (even if models absent), 1 if unreachable.

## `score-assistant models pull --profile NAME [--allow-unknown-size] [--json]`

Help text first line: **"Uses the network: downloads models via the local runtime."**
Steps: validate config → resolve profile (unknown → exit 2) → runtime reachable (else 1) →
disk check (`required = Σ approx_size + margin`; shortfall → exit 1 `DISK_INSUFFICIENT`, no
request sent) → pull each missing model with progress on stderr → list models → write lock
atomically. Already-present models are not re-pulled (idempotent) but are (re)locked.
SIGINT: stops the stream, leaves the existing lock unchanged, exit 130.
JSON result: `{"profile", "network_used": true, "models": [{"tag","digest","size_bytes","action": "pulled|already_present"}], "lock_path"}`.

## `score-assistant serve [--host H] [--port P]`

Network: listens on loopback only; outbound only to the loopback runtime for readiness. Never
pulls. Validation before binding: non-loopback host → exit 2 `BIND_NOT_LOOPBACK` with message
"Remote exposure requires the public profile, which is not available in this release."
Port in use → exit 1 `BIND_FAILED`. Logs to stderr as JSON lines; startup line includes bound
address, app version, profile.
