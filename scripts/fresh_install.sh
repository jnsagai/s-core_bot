#!/usr/bin/env bash
# Fresh installation and restore exercise, fully offline (F009 FR-006, FR-007).
#   scripts/fresh_install.sh PACKAGE_DIR WORK_DIR
# Runs inside an unprivileged loopback-only network namespace (as scripts/offline_check.sh):
# clone from the package's git bundle → uv sync --offline → frontend from the package → bundle
# import + activate into an empty data dir → doctor → serve → probe (cited answer, excerpt, search)
# → restore check against this machine's data. Writes data/reports/fresh-install-*.json and
# data/reports/restore-*.json.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE="$(cd "${1:?usage: fresh_install.sh PACKAGE_DIR WORK_DIR}" && pwd)"
WORK="${2:?usage}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
PY="$ROOT/.venv/bin/python"
OLLAMA_BIN="${OLLAMA_BIN:-$( [ -x /snap/ollama/current/bin/ollama ] && echo /snap/ollama/current/bin/ollama || command -v ollama )}"
OLLAMA_MODELS_DIR="${OLLAMA_MODELS_DIR:-/var/snap/ollama/common/models}"

if [ "${3:-}" != "--inside" ]; then
  FREE_KIB=$(df --output=avail -k "$(dirname "$WORK")" | tail -1 | tr -d ' ')
  if [ "$FREE_KIB" -lt $((3 * 1024 * 1024)) ]; then echo "refusing: less than 3 GiB free" >&2; exit 2; fi
  if [ -e "$WORK" ]; then echo "refusing: $WORK exists" >&2; exit 2; fi
  "$PY" -m score_docs_assistant.qualification.package verify "$PACKAGE" || exit 1
  export STAMP OLLAMA_BIN OLLAMA_MODELS_DIR ROOT PY
  exec unshare -rn bash "${BASH_SOURCE[0]}" "$PACKAGE" "$WORK" --inside
fi

# --- inside the namespace ------------------------------------------------------------------------
mkdir -p "$WORK"
STEPS="$WORK/steps.tsv"; : > "$STEPS"
step() { local name="$1"; shift; if out=$("$@" 2>&1); then printf '%s\tok\t%s\n' "$name" "$(echo "$out" | tail -1 | tr '\t\n' '  ')" >> "$STEPS"; return 0; else printf '%s\tfail\t%s\n' "$name" "$(echo "$out" | tail -3 | tr '\t\n' '  ')" >> "$STEPS"; return 1; fi; }
cleanup() { [ -n "${SERVE_PID:-}" ] && kill "$SERVE_PID" 2>/dev/null; [ -n "${OLLAMA_PID:-}" ] && kill "$OLLAMA_PID" 2>/dev/null; wait 2>/dev/null; }
trap cleanup EXIT
ip link set lo up
step "external egress blocked" "$PY" -c "
import socket, sys
try: socket.getaddrinfo('github.com', 443); sys.exit(1)
except OSError: print('DNS lookup failed as expected')"
APPDIR="$WORK/app"; DATA="$WORK/data"
step "clone source from the package bundle" git clone -q "$PACKAGE/source.git.bundle" "$APPDIR"
cd "$APPDIR"
step "install locked dependencies offline" env UV_OFFLINE=1 uv sync --frozen --offline --no-dev
step "install built frontend" tar --no-same-owner -C frontend -xzf "$PACKAGE/frontend-dist.tar.gz"
mkdir -p "$DATA" && cp "$PACKAGE/model-lock.json" "$DATA/model-lock.json"
sed -e "s|^data_dir: .*|data_dir: $DATA|" config/local.yaml > config/fresh.yaml
APP="$APPDIR/.venv/bin/score-assistant"
OLLAMA_MODELS="$OLLAMA_MODELS_DIR" OLLAMA_NOPRUNE=1 OLLAMA_HOST=127.0.0.1:11434 HOME="$WORK" \
  "$OLLAMA_BIN" serve > "$WORK/runtime.log" 2>&1 &
OLLAMA_PID=$!
for _ in $(seq 1 60); do "$PY" -c "import httpx; httpx.get('http://127.0.0.1:11434/api/version', timeout=1)" 2>/dev/null && break; sleep 0.5; done
step "import corpus bundle" "$APP" --config config/fresh.yaml bundle import "$PACKAGE/corpus.score-bundle.tar.gz"
SNAP=$("$PY" -c "import json; print(json.load(open('$PACKAGE/package-manifest.json'))['snapshot_id'])")
step "activate restored snapshot" "$APP" --config config/fresh.yaml snapshots activate "$SNAP"
step "doctor" "$APP" --config config/fresh.yaml doctor
"$APP" --config config/fresh.yaml serve > "$WORK/serve.log" 2>&1 &
SERVE_PID=$!
for _ in $(seq 1 60); do "$PY" -c "import httpx; httpx.get('http://127.0.0.1:8080/health/live', headers={'host': '127.0.0.1:8080'}, timeout=1)" 2>/dev/null && break; sleep 0.5; done
step "serve: cited answer, excerpt, search, UI" "$APPDIR/.venv/bin/python" -m score_docs_assistant.qualification.offline \
  --out "$ROOT/data/reports/offline-fresh-$STAMP.json" --lock "$DATA/model-lock.json" --log "$WORK/serve.log"
step "restore keeps citations" "$APPDIR/.venv/bin/python" -m score_docs_assistant.qualification.restore \
  --original "$ROOT/data" --restored "$DATA" --out "$ROOT/data/reports/restore-$STAMP.json"
"$PY" -m score_docs_assistant.qualification.package report "$STEPS" --out "$ROOT/data/reports/fresh-install-$STAMP.json"
