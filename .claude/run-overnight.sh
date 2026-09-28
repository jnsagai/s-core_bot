#!/usr/bin/env bash
# Unattended overnight run (prompt: .claude/overnight-prompt.md). Tools are granted explicitly
# via --allowedTools instead of bypassing permissions, and a disk guard stops the run before the
# (nearly full) disk runs out.
set -uo pipefail
cd /home/jefferson/s-core_bot
LOG=overnight.log
MIN_FREE_KIB=$((2 * 1024 * 1024))   # 2 GiB
echo "=== overnight run started at $(date -u +%FT%TZ) on branch $(git branch --show-current) ===" >> "$LOG"

systemd-inhibit --what=sleep:idle --why="overnight F006 run" \
  claude -p "$(cat .claude/overnight-prompt.md)" \
  --model claude-sonnet-5 \
  --permission-mode acceptEdits \
  --allowedTools \
    "Read" "Edit" "Write" "Glob" "Grep" "Skill" "TodoWrite" \
    "Bash(uv run:*)" "Bash(uv sync:*)" "Bash(uv lock:*)" \
    "Bash(git status:*)" "Bash(git diff:*)" "Bash(git log:*)" "Bash(git show:*)" \
    "Bash(git add:*)" "Bash(git commit:*)" "Bash(git push -u origin 006-local-web-ui:*)" \
    "Bash(git push origin 006-local-web-ui:*)" \
    "Bash(gh pr create:*)" "Bash(gh pr view:*)" "Bash(gh pr checks:*)" \
    "Bash(gh run list:*)" "Bash(gh run view:*)" \
    "Bash(npm install:*)" "Bash(npm ci:*)" "Bash(npm run:*)" "Bash(npm test:*)" \
    "Bash(npm ls:*)" "Bash(npm view:*)" "Bash(npm pkg:*)" \
    "Bash(ls:*)" "Bash(cat:*)" "Bash(head:*)" "Bash(tail:*)" "Bash(wc:*)" "Bash(find:*)" \
    "Bash(grep:*)" "Bash(jq:*)" "Bash(sed:*)" "Bash(awk:*)" "Bash(mkdir:*)" "Bash(df:*)" \
    "Bash(kill:*)" "Bash(pgrep:*)" "Bash(sleep:*)" "Bash(python3:*)" \
    "Bash(.venv/bin/score-assistant:*)" "Bash(.specify/scripts/bash/*)" \
    "Bash(curl * http://127.0.0.1:*)" "Bash(curl * http://localhost:*)" \
  --disallowedTools \
    "Bash(sudo:*)" "Bash(git reset:*)" "Bash(git clean:*)" "Bash(git push --force:*)" \
    "Bash(git push -f:*)" "Bash(gh pr merge:*)" "Bash(npx:*)" "Bash(rm -rf /*)" \
    "Bash(ollama:*)" "Bash(uv run score-assistant models pull:*)" \
  >> "$LOG" 2>&1 &
RUN_PID=$!

# Disk guard: stop the run (SIGTERM, then SIGKILL) if free space drops below 2 GiB.
while kill -0 "$RUN_PID" 2>/dev/null; do
  FREE_KIB=$(df --output=avail -k / | tail -1 | tr -d ' ')
  if [ "$FREE_KIB" -lt "$MIN_FREE_KIB" ]; then
    echo "=== disk guard: only ${FREE_KIB} KiB free, stopping the run at $(date -u +%FT%TZ) ===" >> "$LOG"
    pkill -TERM -P "$RUN_PID" 2>/dev/null; kill -TERM "$RUN_PID" 2>/dev/null
    sleep 30
    kill -KILL "$RUN_PID" 2>/dev/null
    break
  fi
  sleep 60
done
wait "$RUN_PID" 2>/dev/null
echo "=== overnight run ended at $(date -u +%FT%TZ) ===" >> "$LOG"
