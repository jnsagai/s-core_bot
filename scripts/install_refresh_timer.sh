#!/usr/bin/env bash
# Install, or remove, the opt-in systemd *user* timer that runs `score-assistant refresh` (F011).
# Nothing is installed unless you run this script; it never runs a refresh itself.
#
#   scripts/install_refresh_timer.sh [--config config/local.yaml] [--interval 15min]
#   scripts/install_refresh_timer.sh --uninstall
# Options: --unit-dir DIR (default ~/.config/systemd/user), --no-enable (write files only; never
# calls systemctl). User timers run while you are logged in; `loginctl enable-linger` keeps them
# running after logout. See docs/runbooks/refresh.md.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
CONFIG="config/local.yaml"
INTERVAL="15min"
ENABLE=1
UNINSTALL=0
NAME="score-assistant-refresh"

usage() { sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --config) CONFIG="$2"; shift 2 ;;
    --interval) INTERVAL="$2"; shift 2 ;;
    --unit-dir) UNIT_DIR="$2"; shift 2 ;;
    --no-enable) ENABLE=0; shift ;;
    --uninstall) UNINSTALL=1; shift ;;
    -h|--help) usage 0 ;;
    *) echo "unknown option: $1" >&2; usage 2 ;;
  esac
done

if [ "$UNINSTALL" = 1 ]; then
  if [ "$ENABLE" = 1 ]; then
    systemctl --user disable --now "$NAME.timer" 2>/dev/null || true
  fi
  rm -f "$UNIT_DIR/$NAME.service" "$UNIT_DIR/$NAME.timer"
  [ "$ENABLE" = 1 ] && systemctl --user daemon-reload
  echo "removed $NAME.timer and $NAME.service from $UNIT_DIR"
  exit 0
fi

if ! [[ "$INTERVAL" =~ ^[1-9][0-9]*(s|min|h)$ ]]; then
  echo "--interval must look like 300s, 15min or 1h (got '$INTERVAL')" >&2
  exit 2
fi
case "$CONFIG" in /*) ;; *) CONFIG="$ROOT/$CONFIG" ;; esac
if [ ! -f "$CONFIG" ]; then
  echo "config file not found: $CONFIG" >&2
  exit 2
fi
if [ ! -x "$ROOT/.venv/bin/score-assistant" ]; then
  echo "missing $ROOT/.venv/bin/score-assistant; run 'uv sync' first" >&2
  exit 2
fi
for value in "$ROOT" "$CONFIG"; do
  if [[ "$value" == *[[:space:]@%\\]* ]]; then
    echo "path must not contain spaces, '@', '%' or backslashes: $value" >&2
    exit 2
  fi
done

mkdir -p "$UNIT_DIR"
render() {
  sed -e "s|@REPO@|$ROOT|g" -e "s|@CONFIG@|$CONFIG|g" -e "s|@INTERVAL@|$INTERVAL|g" \
    "$ROOT/deploy/systemd/$1" > "$UNIT_DIR/$1"
}
render "$NAME.service"
render "$NAME.timer"
echo "wrote $UNIT_DIR/$NAME.service and $NAME.timer (every $INTERVAL, config $CONFIG)"

if [ "$ENABLE" = 1 ]; then
  systemctl --user daemon-reload
  systemctl --user enable --now "$NAME.timer"
  systemctl --user list-timers "$NAME.timer" --no-pager || true
else
  echo "not enabled (--no-enable); enable with: systemctl --user daemon-reload && systemctl --user enable --now $NAME.timer"
fi
