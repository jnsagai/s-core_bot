#!/usr/bin/env bash
# Blocked-egress check (F008 FR-011, AT-01): runs the application and a private local runtime in an
# unprivileged network namespace that has only a loopback interface, then probes it over HTTP.
# The runtime reads the already-installed models (never pulls or modifies them). No root needed.
#
#   scripts/offline_check.sh            # writes data/reports/offline-<utc>.json
# Environment: OLLAMA_BIN, OLLAMA_MODELS_DIR, CONFIG (default config/local.yaml).
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="${OUT:-data/reports/offline-$STAMP.json}"
CONFIG="${CONFIG:-config/local.yaml}"
PY="$ROOT/.venv/bin/python"
APP="$ROOT/.venv/bin/score-assistant"
OLLAMA_BIN="${OLLAMA_BIN:-$( [ -x /snap/ollama/current/bin/ollama ] && echo /snap/ollama/current/bin/ollama || command -v ollama )}"
OLLAMA_MODELS_DIR="${OLLAMA_MODELS_DIR:-/var/snap/ollama/common/models}"

if [ "${1:-}" != "--inside" ]; then
  if ! unshare -rn true 2>/dev/null; then
    "$PY" -m score_docs_assistant.qualification.offline --out "$OUT" --not-run "unprivileged network namespace unavailable (unshare -rn failed)"
    exit 0
  fi
  if [ -z "$OLLAMA_BIN" ] || [ ! -d "$OLLAMA_MODELS_DIR" ]; then
    "$PY" -m score_docs_assistant.qualification.offline --out "$OUT" --not-run "local runtime binary or models directory not found"
    exit 0
  fi
  export OUT CONFIG OLLAMA_BIN OLLAMA_MODELS_DIR
  exec unshare -rn bash "${BASH_SOURCE[0]}" --inside
fi

# --- inside the namespace ---------------------------------------------------------------------
WORK="$(mktemp -d)"
cleanup() { [ -n "${SERVE_PID:-}" ] && kill "$SERVE_PID" 2>/dev/null; [ -n "${OLLAMA_PID:-}" ] && kill "$OLLAMA_PID" 2>/dev/null; wait 2>/dev/null; rm -rf "$WORK"; }
trap cleanup EXIT
ip link set lo up
OLLAMA_MODELS="$OLLAMA_MODELS_DIR" OLLAMA_NOPRUNE=1 OLLAMA_HOST=127.0.0.1:11434 HOME="$WORK" \
  "$OLLAMA_BIN" serve > "$WORK/runtime.log" 2>&1 &
OLLAMA_PID=$!
for _ in $(seq 1 60); do "$PY" -c "import httpx; httpx.get('http://127.0.0.1:11434/api/version', timeout=1)" 2>/dev/null && break; sleep 0.5; done
"$APP" --config "$CONFIG" serve > "$WORK/serve.log" 2>&1 &
SERVE_PID=$!
for _ in $(seq 1 60); do "$PY" -c "import httpx; httpx.get('http://127.0.0.1:8080/health/live', headers={'host': '127.0.0.1:8080'}, timeout=1)" 2>/dev/null && break; sleep 0.5; done
"$PY" -m score_docs_assistant.qualification.offline --out "$OUT" --log "$WORK/serve.log"
STATUS=$?
echo "report: $OUT"
exit $STATUS
