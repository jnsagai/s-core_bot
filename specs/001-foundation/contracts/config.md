# Configuration Contract (schema_version 1, F001)

Format: YAML, parsed with `yaml.safe_load`. Unknown keys at any level → error. Every error reports
dotted path + reason (e.g. `server.host: must be a loopback address`).

## Keys, defaults, constraints

| Key | Default | Constraint |
| --- | --- | --- |
| `schema_version` | 1 | must be 1 |
| `profile` | `local` | only `local` in F001 |
| `server.host` | `127.0.0.1` | IP in 127.0.0.0/8, `::1`, or `localhost` |
| `server.port` | 8080 | 1–65535 |
| `server.allowed_hosts` | `[localhost, 127.0.0.1]` | non-empty; entries are hostnames or IPs, optional `:port`; an entry without port matches only the bound port (see http-api.md Guard) |
| `server.allowed_origins` | `["http://127.0.0.1:8080", "http://localhost:8080"]` | `http(s)://host[:port]`, no path, no wildcard |
| `data_dir` | `data` (built-in default, resolved against CWD); `config/local.yaml` sets `../data` so it resolves to `<repo>/data` | path |
| `runtime.provider` | `ollama` | only `ollama` |
| `runtime.base_url` | `http://127.0.0.1:11434` | scheme `http`, loopback host, no userinfo, no path |
| `runtime.cloud_fallback` | `false` | must be `false` |
| `runtime.model_profile` | `local-small` | must exist in `config/model-profiles.yaml` |
| `runtime.generation_model` | `qwen3:4b-instruct` | non-empty tag |
| `runtime.embedding_model` | `nomic-embed-text` | non-empty tag |
| `runtime.models_dir` | unset | optional path, used for the disk check only |
| `runtime.context_tokens` | 8192 | 1024–131072 |
| `runtime.output_tokens` | 900 | 1 – `context_tokens`/2 |
| `retrieval.*` | §10.3 values | positive ints (validated only; unused until F004) |
| `limits.question_characters` | 4000 | 1–100000 |
| `limits.history_characters` | 12000 | 0–1000000 |
| `limits.active_generations` | 1 | must be 1 in `local` |
| `limits.queued_generations` | 4 | 0–100 |
| `limits.request_deadline_seconds` | 120 | 1–3600 |
| `privacy.persist_chats` | `false` | must be `false` in F001 (no persistence feature exists) |
| `privacy.log_message_bodies` | `false` | bool |
| `privacy.telemetry` | `false` | must be `false` |
| `diagnostics.runtime_connect_timeout_seconds` | 1.0 | 0.1–10 |
| `diagnostics.runtime_read_timeout_seconds` | 3.0 | 0.1–30 |
| `diagnostics.readiness_cache_seconds` | 2.0 | 0–60 |
| `diagnostics.disk_margin_bytes` | 2147483648 | ≥ 0 |

## Precedence

built-in defaults < config file < environment < CLI flags (FR-016).

- Config file: `--config PATH`, else `SCORE_ASSISTANT_CONFIG`, else none (defaults; doctor reports
  "using built-in defaults"). A requested file that does not exist is a configuration error
  (`config_file: config file not found: <path>`, exit 2), never a fallback to the defaults
  (amended 2026-10-02, A-061).
- Environment: `SCORE_ASSISTANT_<SECTION>__<KEY>` (upper-case, double underscore for nesting),
  e.g. `SCORE_ASSISTANT_SERVER__PORT=9000`. Values parsed as YAML scalars/flow sequences. Any
  other `SCORE_ASSISTANT_*` variable except `SCORE_ASSISTANT_CONFIG` and
  `SCORE_ASSISTANT_REAL_RUNTIME` (test-only) → error `CONFIG_UNKNOWN_ENV`.
- CLI flags: `serve --host/--port` only in F001.
- Relative paths resolve against the config file's directory; with no file, against CWD.

## Redaction (FR-008)

Before display: URL userinfo replaced by `***`; values of keys/env names matching
`(?i)(secret|token|password|passwd|api[_-]?key|authorization|credential)` replaced by `***`.
F001 schema has no secret-bearing keys; redaction guards env echoes and error messages that quote
input.
