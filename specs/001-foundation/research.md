# Research: F001 Foundation and Local Runtime Contract

All checks performed 2026-09-27 on the workstation recorded in `docs/toolchain.md`.
"Verified" = observed directly; "Documented" = read from upstream docs, not yet exercised.

## R1. Python version and packaging

- **Decision**: Python 3.12 (`requires-python = ">=3.12,<3.13"`, `.python-version` = `3.12`),
  uv for environment and lock (`uv.lock`), hatchling build backend, `src/` layout, console
  script `score-assistant`.
- **Rationale**: master spec §1.2 fixes 3.12; uv-managed 3.12.14 is present (verified); uv 0.12.17
  produces a cross-platform lock usable by CI with `uv sync --locked`.
- **Alternatives**: system 3.13 (rejected: deviates from baseline); Poetry/pip-tools (rejected:
  uv already installed, faster, single tool).

## R2. Runtime dependencies (versions from PyPI, 2026-09-27)

| Package | Version | License | Purpose |
| --- | --- | --- | --- |
| fastapi | 0.141.1 | MIT | HTTP API (baseline §1.2) |
| uvicorn | 0.54.0 | BSD-3-Clause | ASGI server (no `[standard]` extras, to keep deps minimal) |
| pydantic | 2.13.5 | MIT | Config and contract schemas |
| typer | 0.27.2 | MIT | CLI |
| httpx | 0.28.1 | BSD-3-Clause | Ollama client (sync + streaming), `MockTransport` for tests |
| pyyaml | 6.0.3 | MIT | YAML via `safe_load` only |
| psutil | 7.2.2 | BSD-3-Clause | RAM and disk probes |

Dev: pytest 9.1.1 (MIT), pytest-cov 7.1.0 (MIT), ruff 0.16.9 (MIT), mypy 2.3.1 (MIT),
types-PyYAML (Apache-2.0), pip-licenses 5.5.5 (MIT). Exact resolution is fixed by `uv.lock`;
minimum bounds in `pyproject.toml` use the versions above.

- **Rejected**: pydantic-settings (its env-source silently ignores unknown variables; FR-015/Edge
  case requires unknown `SCORE_ASSISTANT_*` variables to be errors — a ~60-line custom loader is
  simpler and testable); respx and hypothesis (not needed; hypothesis is MPL-2.0).

## R3. Ollama API surface used by F001

- Verified: `GET /api/version` → `{"version":"0.34.0"}`; `GET /api/tags` → `{"models":[]}` on the
  workstation (runtime running, no models).
- Documented `/api/tags` model fields: `name`, `model`, `remote_model`, `remote_host`,
  `modified_at`, `size`, `digest` (SHA-256), `details.{format,family,families,parameter_size,
  quantization_level}`.
- **Decision**: identity = `digest` from `/api/tags`; presence = tag match (normalising an omitted
  `:latest`). A model entry with non-empty `remote_model` or `remote_host` is a **cloud-proxied
  model** and is reported as a failure (`MODEL_REMOTE`), because it would violate constitution I.
- Acquisition uses `POST /api/pull` with streaming JSON progress (`status`, `digest`, `total`,
  `completed`). Stream field names are **documented only in older API docs; must be verified**
  during implementation against 0.34.0 with a real pull (task in tasks.md).
- Timeouts: connect 1 s, read 3 s for probes; pull uses read timeout 60 s between progress lines.

## R4. Ollama cloud features

- Documented: cloud features are disabled with `OLLAMA_NO_CLOUD=1` or `"disable_ollama_cloud":
  true` in `~/.ollama/server.json`. These apply to the **Ollama server process**, which the client
  cannot inspect.
- **Decision**: `doctor` (a) fails on any remote model among configured models, (b) emits an
  informational check `RUNTIME_CLOUD_UNVERIFIED` telling the user how to disable cloud features,
  stating it cannot be verified from the client. Real verification is a blocked-egress test in
  F005/F009 (spec §8.3). Not claimed as verified here.

## R5. Model storage location and disk check

- Verified: snap-installed Ollama stores models at `/var/snap/ollama/common/models`; documented
  default for the Linux service install is `/usr/share/ollama/.ollama/models`, and per-user
  `~/.ollama/models`; `OLLAMA_MODELS` overrides.
- **Decision**: resolution order: `runtime.models_dir` config key (optional) → `OLLAMA_MODELS` in
  the CLI environment → first existing of the three known paths → data directory (with a note that
  the check used a fallback location). Required free space = Σ profile sizes + margin (default
  2 GiB).
- Observed free space varied 14–37 GiB on 2026-09-27, confirming it must be measured each time.

## R6. Candidate model profile `local-small`

| Role | Tag | Approx. download | Notes (ollama.com, 2026-09-27) |
| --- | --- | --- | --- |
| generation | `qwen3:4b-instruct` | 2.5 GB | Q4_K_M, digest prefix `0edcdef34593`, Apache-2.0 |
| embedding | `nomic-embed-text` | 274 MB | 2K context; license to confirm from model card |

Sizes are approximate and stored in `config/model-profiles.yaml` with their source and date. The
digest prefix is informational; the authoritative identity is written to the model lock after a
real pull. Qualification is out of scope (F005/F008).

## R7. Model lock location

- **Decision**: `<data_dir>/model-lock.json` (machine state, git-ignored). It records what *this*
  machine acquired. A release-qualified, committed lock is an F008 artifact.
- **Alternative rejected**: committing `config/model-lock.json` now — no qualified identities exist
  yet, and committing per-machine state would create false provenance.

## R8. Host / Origin protection

- **Decision**: one pure-ASGI middleware applied before routing:
  1. `Host` must match `allowed_hosts` (host, optionally with the bound port) → else 400
     `HOST_NOT_ALLOWED`.
  2. If `Origin` present and not in `allowed_origins` → 403 `ORIGIN_NOT_ALLOWED`.
  3. If `Sec-Fetch-Site: cross-site` → 403 `CROSS_SITE_REQUEST`.
  4. CORS: respond with `Access-Control-Allow-Origin` only for allowed origins; preflight for
     disallowed origins → 403. No wildcard, no credentials.
- **Rationale**: Starlette's `TrustedHostMiddleware` covers only step 1 with a plain-text body;
  a single custom middleware gives stable error codes and is simpler to test exhaustively.
- `Origin: null` is treated as not allowed.

## R9. Non-loopback bind refusal

- **Decision**: validation at configuration level: `server.host` must parse as an IP address in
  `127.0.0.0/8` or `::1`, or be `localhost`. Anything else is a config error (exit 2) whose message
  names the public profile as unavailable. `profile` accepts only `local` in F001.
- Same rule for `runtime.base_url` host in the local profile, and scheme must be `http`.

## R10. Configuration loading and precedence

- Defaults (Pydantic model defaults, `extra="forbid"`) ← YAML file (`--config` or
  `SCORE_ASSISTANT_CONFIG`; absent file → defaults with notice) ← env vars
  `SCORE_ASSISTANT_<SECTION>__<KEY>` (values parsed as YAML scalars) ← CLI flags.
- Unknown env var under the prefix → config error. Relative paths resolve against the config file
  directory, or CWD when no file.
- Every effective value records its source (`default|file|env|cli`) for `doctor` output.

## R11. Hardware probing

- RAM, disk: psutil. GPU: `nvidia-smi --query-gpu=name,memory.total,memory.free
  --format=csv,noheader,nounits` via `subprocess.run` with fixed argv, `shell=False`, 3 s
  timeout; absence/timeout → "not detected". Verified output on the workstation: RTX 4070 Laptop
  GPU, 8188 MiB. This invokes a local system binary chosen by the application, never document
  content (constitution IV/V unaffected).

## R12. Network isolation in tests

- **Decision**: an autouse pytest fixture replaces `socket.socket.connect`/`connect_ex` to allow
  only loopback and AF_UNIX addresses, raising on anything else (SC-004). Runtime tests use
  `httpx.MockTransport`; one integration test runs a fake Ollama on a loopback port. Tests needing
  a real Ollama are marked `real_runtime` and skipped (reported "not run") unless
  `SCORE_ASSISTANT_REAL_RUNTIME=1`.

## R13. License check

- **Decision**: `scripts/check_licenses.py` runs `pip-licenses --format=json` on the synced env and
  fails on any package whose license is not in the allowlist {MIT, BSD-2/3-Clause, Apache-2.0,
  ISC, PSF-2.0, MPL-2.0, Unlicense} or is UNKNOWN, with an explicit per-package exception file
  `config/license-exceptions.yaml` (reviewed entries only). `THIRD_PARTY_NOTICES.md` generated from
  the same data.

## R14. CI

- GitHub Actions `.github/workflows/ci.yml`: `astral-sh/setup-uv` (pinned by commit SHA),
  `uv sync --locked`, `ruff format --check`, `ruff check`, `mypy --strict src`, `pytest`,
  license check. No Ollama, no model download. Frontend build step added in F006.

## R15. Readiness evaluation

- Computed on demand with a 2 s cache and bounded probe timeouts, so a runtime stop/start is
  visible within one query after cache expiry (SC-007 measured with cache TTL in tests set to 0).
