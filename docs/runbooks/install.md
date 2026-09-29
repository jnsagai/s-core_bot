# Runbook: install

Two supported ways to run the assistant on Linux x86-64. Both bind to loopback only.

## Native (reference path; NVIDIA GPU qualified)

Prerequisites: Python 3.12 with `uv`, Node 22 (to build the UI once), git ≥ 2.34 (sync only), and
Ollama 0.34.0 on `127.0.0.1:11434`.

```bash
uv sync                                                    # locked dependencies
(cd frontend && npm ci && npm run build)                   # UI, once
uv run score-assistant --config config/local.yaml models pull          # NETWORK: acquire models
uv run score-assistant sources sync --config config/sources.yaml       # NETWORK: acquire sources
uv run score-assistant --config config/local.yaml index build --activate
uv run score-assistant --config config/local.yaml doctor
uv run score-assistant --config config/local.yaml serve   # http://127.0.0.1:8080/
```

Serving never downloads anything; the networked steps are the explicit `models pull` and
`sources sync`.

## Containers (portable default: CPU)

Prerequisites: Docker Engine with Compose v2, a prepared models directory (for example Ollama's
`/var/snap/ollama/common/models` after `models pull`) and a data directory with an active snapshot.

```bash
docker compose build                                   # preparation: app image
docker compose --profile bundled pull ollama           # preparation: runtime image (~5.5 GB)
SCORE_DATA_DIR=./data SCORE_MODELS_DIR=/var/snap/ollama/common/models \
  docker compose --profile bundled up -d --pull never  # http://127.0.0.1:8080/
docker compose --profile bundled down
```

- The runtime container has **no host port** and sits on an internal network without internet
  access; it reads the models read-only.
- The app runs as your UID (`SCORE_UID`/`SCORE_GID`, default 1000) so that `./data` keeps its
  ownership, with a read-only root filesystem, no capabilities and resource caps.
- `SCORE_PORT` must equal `server.port` (8080) because the Host guard checks the port.
- CPU inference is slow: about 60 s for a first answer on the reference laptop (see the hardware
  matrix).

`host-runtime` profile (Linux only): `docker compose --profile host-runtime up -d --pull never`
runs the app on the host network against the host's loopback Ollama (fast when that uses the GPU).

GPU in containers: `docker compose -f compose.yaml -f compose.nvidia.yaml --profile bundled up -d`
needs the NVIDIA container toolkit on the host. This is **not run** on the reference machine.
