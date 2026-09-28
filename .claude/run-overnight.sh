#!/usr/bin/env bash
set -uo pipefail
cd /home/jefferson/s-core_bot
echo "=== overnight run started at $(date -u +%FT%TZ) on branch $(git branch --show-current) ===" >> overnight.log
exec systemd-inhibit --what=sleep:idle --why="overnight F001 implementation run" \
  claude -p "$(cat .claude/overnight-prompt.md)" \
  --model claude-sonnet-5 \
  --permission-mode acceptEdits \
  >> overnight.log 2>&1
