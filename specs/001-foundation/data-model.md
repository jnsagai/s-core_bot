# Data Model: F001 Foundation and Local Runtime Contract

All types are immutable (frozen Pydantic models or frozen dataclasses) and live in
`src/score_docs_assistant/domain/` unless noted. Timestamps are UTC ISO 8601.

## AppConfig (`config/schema.py`)

See [contracts/config.md](contracts/config.md) for every key, default and constraint.

| Field | Type | Rules |
| --- | --- | --- |
| schema_version | int | must equal 1 |
| profile | literal `"local"` | other values → `CONFIG_PROFILE_UNSUPPORTED` |
| server | ServerConfig | host loopback-only; port 1–65535; allowed_hosts/origins non-empty |
| data_dir | Path | resolved against config dir |
| runtime | RuntimeConfig | provider `"ollama"`; `cloud_fallback` must be `false`; base_url `http://` + loopback host |
| limits | LimitsConfig | positive ints; `active_generations` = 1 in local profile |
| privacy | PrivacyConfig | `telemetry` must be `false`; `persist_chats`, `log_message_bodies` default `false` |
| diagnostics | DiagnosticsConfig | probe timeouts, readiness cache TTL, disk margin |

`EffectiveConfig` = `AppConfig` + `sources: dict[str, Literal["default","file","env","cli"]]`
keyed by dotted path, + `config_file: Path | None`.

## ModelProfile / ProfileModel (`domain/models.py`)

| Field | Type | Notes |
| --- | --- | --- |
| name | str | e.g. `local-small` |
| models | list[ProfileModel] | exactly one `generation` and one `embedding` role |
| ProfileModel.role | `generation` \| `embedding` | |
| ProfileModel.tag | str | Ollama tag |
| ProfileModel.approx_size_bytes | int \| None | None = unknown (needs override to pull) |
| ProfileModel.size_source | str | e.g. `ollama.com library page, 2026-09-27` |
| ProfileModel.license | str \| None | recorded, not verified |

## InstalledModel / RuntimeInfo (`models/runtime.py`)

| Field | Type |
| --- | --- |
| RuntimeInfo.provider | `"ollama"` |
| RuntimeInfo.base_url | str (redacted form) |
| RuntimeInfo.version | str |
| InstalledModel.tag | str (normalised with `:latest`) |
| InstalledModel.digest | str (sha256 hex) |
| InstalledModel.size_bytes | int |
| InstalledModel.family / parameter_size / quantization | str \| None |
| InstalledModel.is_remote | bool (true if `remote_model` or `remote_host` set) |

## ModelLock / ModelLockEntry (`domain/models.py`, persisted by `models/lock.py`)

File `<data_dir>/model-lock.json`:

```json
{
  "schema_version": 1,
  "profile": "local-small",
  "runtime": {"provider": "ollama", "version": "0.34.0"},
  "models": [
    {"role": "generation", "tag": "qwen3:4b-instruct", "digest": "<sha256>",
     "size_bytes": 0, "acquired_at": "2026-09-27T00:00:00Z"}
  ]
}
```

Rules: written atomically; unknown fields rejected; comparison per role/tag → `match`,
`mismatch` (digest differs), `missing_installed`, `not_locked`.

## CheckResult / DiagnosticReport (`domain/diagnostics.py`)

| Field | Type | Notes |
| --- | --- | --- |
| CheckResult.id | str | stable, e.g. `runtime.reachable`, `model.generation`, `disk.models` |
| CheckResult.status | `ok` \| `warning` \| `failure` \| `info` \| `skipped` | |
| CheckResult.code | str | stable upper-snake code, e.g. `RUNTIME_UNREACHABLE` |
| CheckResult.message | str | human-readable, redacted |
| CheckResult.next_action | str \| None | required when status ∈ {warning, failure} |
| CheckResult.details | dict[str, str \| int \| float \| bool \| None] | redacted |
| DiagnosticReport.app_version | str | |
| DiagnosticReport.generated_at | datetime | |
| DiagnosticReport.checks | list[CheckResult] | fixed order |
| DiagnosticReport.exit_code | 0 \| 1 \| 2 | 2 only for config/usage error |

Invariant: `exit_code == 1` iff any check has status `failure`; a `CONFIG_*` error produces a
report containing only the config check and `exit_code == 2`.

## Readiness (`domain/readiness.py`)

| Field | Type |
| --- | --- |
| Capability | enum `search`, `chat`, `compare` |
| CapabilityState.available | bool |
| CapabilityState.reasons | list[ReasonCode] (empty iff available) |
| ReasonCode | enum: `corpus_missing`, `corpus_incompatible`, `runtime_unreachable`, `runtime_incompatible`, `generation_model_missing`, `embedding_model_missing`, `model_identity_mismatch`, `not_implemented` |
| Readiness.capabilities | dict[Capability, CapabilityState] |
| Readiness.checked_at | datetime |

Derivation (F001): `search` requires corpus `compatible` (never in F001) → reasons from corpus
state; `chat` requires `search` + generation model present and not mismatched + runtime reachable;
`compare` always `not_implemented` until F007. Ready (HTTP 200) iff `search.available`.

## CorpusState (`storage/corpus_probe.py`)

Enum `absent` | `incompatible` (F001); `compatible` added by F003. Probe checks only for
`<data_dir>/catalog.sqlite` existence; it MUST NOT open the file in F001.

## HardwareInfo (`diagnostics/hardware.py`)

`os`, `arch`, `cpu_count`, `ram_total_bytes`, `ram_available_bytes`, `gpus: list[GpuInfo]`
(`name`, `memory_total_mib`, `memory_free_mib`), `gpu_detection: detected|not_detected|error`,
`disk: {path, free_bytes, total_bytes, is_fallback}`.
