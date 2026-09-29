# Research: F009 Portable Local Release

Agent decisions (agent review).

## R1 — Image

**Decision**: a multi-stage `Dockerfile`:
- stage 1 `node:22-bookworm-slim` runs `npm ci && npm run build` in `frontend/`;
- stage 2 `python:3.12-slim-bookworm` copies `uv` (pinned version, from the official
  `ghcr.io/astral-sh/uv` image by digest) and runs `uv sync --frozen --no-dev` into `/app/.venv`,
  then copies `src/`, `config/` and `frontend/dist`.

The image runs as user `score` (uid 10001), sets `SCORE_ASSISTANT_CONTAINER=1`, and has
`WORKDIR /app`, `VOLUME /data`, `EXPOSE 8080` and a `HEALTHCHECK` on `/health/live` using the
bundled Python. Base images are pinned by digest in the Dockerfile; `.dockerignore` excludes
`data/`, `.venv/`, `node_modules/`, `.git/` and caches.

## R2 — Compose

**Decision**: `compose.yaml` with two profiles.
- `bundled`:
  - `ollama` (`ollama/ollama:0.34.0@sha256:…`) on network `internal` (internal: true), no
    `ports`, models volume read-only, `OLLAMA_NOPRUNE=1`;
  - `app` on networks `internal` and `edge`, with `ports: ["127.0.0.1:8080:8080"]` and config
    `config/container.yaml`;
  - `edge` is a normal bridge network that exists only to allow the published port; the app has no
    egress need, and the `internal` network blocks egress for the runtime.
- `host-runtime`: `app-host` with `network_mode: host` and the native config (loopback bind,
  loopback runtime).

Hardening on `app`: `user: "10001:10001"`, `read_only: true`, `tmpfs: /tmp`,
`cap_drop: [ALL]`, `security_opt: [no-new-privileges:true]`, `mem_limit`, `cpus`, `pids_limit`,
`logging: json-file max-size 10m, max-file 7`. The models path comes from `SCORE_MODELS_DIR`
(default `/var/snap/ollama/common/models`) and the data path from `SCORE_DATA_DIR` (default
`./data`). Pulling images is a preparation step; `docker compose up --pull never` is documented
for prepared machines.

**Ports and Host validation**: the guard admits `Host: 127.0.0.1:<server.port>` only, so the host
port must equal the container port (8080 by default). To use another port, change `server.port`
and `allowed_origins` in `config/container.yaml` and the mapping together. The Compose file uses
one variable (`SCORE_PORT`) for both sides.

**Data ownership**: the app writes pins, locks and the catalog while serving, so `/data` is
read-write. The Compose file runs the app as the host user (`user: "${SCORE_UID:-1000}:${SCORE_GID:-1000}"`),
so a bind-mounted `./data` keeps its ownership. The image's default user (10001) applies when it is
run without Compose. The models mount stays read-only.

## R3 — Container mode validation

**Decision**: `AppConfig.deployment = DeploymentConfig(mode: native|container,
runtime_private_hosts: list[str])`. The loopback checks move from field validators to one
`AppConfig` model validator:
- `server.host` must be loopback, or `0.0.0.0` in container mode;
- the `runtime.base_url` host must be loopback, or listed in `runtime_private_hosts` in container
  mode;
- container mode requires `os.environ["SCORE_ASSISTANT_CONTAINER"] == "1"`.

The Ollama providers get an `allowed_hosts` argument from the factory (loopback, plus private hosts
in container mode), so a direct construction still refuses non-loopback. `serve` prints
`deployment: container` at startup, and `doctor` reports the mode.

## R4 — Log retention

**Decision**: `LoggingConfig(file: Path | None, retention_days: 1..7 = 7)`. When `file` is set,
`serve` adds a `TimedRotatingFileHandler(when="midnight", backupCount=retention_days,
encoding="utf-8")` for the access-log records, and the access middleware writes through the
`score.access` logger besides stderr. Rotation is tested with a fake clock (`rolloverAt`).

## R5 — Preparation, install, restore

**Decision**: `scripts/prepare_package.sh OUT_DIR` does the following:
1. `bundle export` of the active snapshot;
2. `docker save` of the app and runtime images;
3. copies `data/model-lock.json`;
4. writes `package-manifest.json` (sha256, sizes, snapshot, model digests, image IDs).

Models are referenced, not copied, unless `--with-models` is given (disk). `scripts/fresh_install.sh
PACKAGE_DIR WORK_DIR` then:
1. clones the current commit (`git worktree`/`git clone --local`);
2. runs `uv sync --frozen --offline`;
3. runs `bundle import` into a new data directory and copies the model lock;
4. runs `doctor`, `serve` on a spare port, and a probe (health, search, cited answer);
5. runs `restore_check` against the original data directory.

The whole sequence runs inside the loopback-only namespace from F008, so the "no network" claim is
enforced rather than asserted. The native offline install relies on uv's local package cache
(present on a prepared machine). The fully self-contained transfer path is the saved container
images, which carry the locked dependencies; the package manifest states which path it covers. `qualification/restore.py` compares the snapshot ID, a sample of 50
chunk IDs (excerpt and revision), and the citations of 3 fixed questions using the search-only path
(deterministic; generation varies).

## R6 — Contract parity

**Decision**: `qualification/contract.py` probes a base URL:
- `/health/live`, `/health/ready`, `/api/v1/capabilities`, `/api/v1/snapshots`;
- `POST /api/v1/search`, `GET /api/v1/citations/…`, `POST /api/v1/chat` (JSON), and
  `/api/v1/snapshots/diff` when two snapshots exist.

It records the status code and a key/type tree (list lengths ignored). `compare_signatures`
reports differences. Values are not compared, because timings and IDs differ.

## R7 — SBOM and release assembly

**Decision**: `scripts/sbom.py` reads `uv.lock` (TOML via `tomllib`) and
`frontend/package-lock.json` and writes CycloneDX 1.5 JSON: components with `purl`
(`pkg:pypi/…`, `pkg:npm/…`), version, license (from the license inventory the license gate
builds, when available), and `scope` (required/optional for dev). `release assemble` copies the
locks, SBOM, `THIRD_PARTY_NOTICES.md`, the latest model record, the active manifest, the latest
suite/performance/release reports, `docs/quality/hardware-matrix.md` and
`docs/KNOWN_LIMITATIONS.md` into `data/releases/<version>-<utc>/` with `release-manifest.json`.
Weights and bundles are excluded unless `--include-bundle` is given.

## R8 — Gates

**Decision**: new gates in `eval/release-gates.yaml` reading new reports:
`container-*.json` (ports, hardening, cited answer through the stack), `fresh-install-*.json`,
`restore-*.json`, `contract-*.json`, the SBOM presence and component count, and a log-retention
test in JUnit. `docs/quality/hardware-matrix.md` records what was qualified.
