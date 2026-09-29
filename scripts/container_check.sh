#!/usr/bin/env bash
# Container deployment check (F009 FR-001–FR-003): start the `bundled` profile from prepared images
# (never pulls), inspect ports/networks/hardening, probe a cited answer, stop it again.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
FREE_KIB=$(df --output=avail -k . | tail -1 | tr -d ' ')
if [ "$FREE_KIB" -lt $((3 * 1024 * 1024)) ]; then echo "refusing: less than 3 GiB free" >&2; exit 2; fi
PROJECT="${PROJECT:-scorecheck}"
OUT="${OUT:-data/reports/container-$(date -u +%Y%m%dT%H%M%SZ).json}"
if ss -ltn | grep -q "127.0.0.1:8080 "; then echo "port 8080 is busy; stop the native server first" >&2; exit 2; fi
docker compose -p "$PROJECT" --profile bundled up -d --pull never --wait --wait-timeout 180
UP=$?
STATUS=1
if [ $UP -eq 0 ]; then
  .venv/bin/python -m score_docs_assistant.qualification.container --project "$PROJECT" --out "$OUT"
  STATUS=$?
  docker compose -p "$PROJECT" logs app --no-log-prefix > "${OUT%.json}.app.log" 2>&1
else
  echo "compose up failed" >&2
fi
docker compose -p "$PROJECT" --profile bundled down
echo "report: $OUT"
exit $STATUS
