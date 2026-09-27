# Quickstart / Validation Guide: F001

Demonstrates F001 from a known starting state. Expected outputs refer to
[contracts/cli.md](contracts/cli.md) and [contracts/http-api.md](contracts/http-api.md).

## Prerequisites

- Linux x86-64, `git`, `uv` ≥ 0.12, network for the install step only.
- Optional: Ollama running on `127.0.0.1:11434` (scenarios B–D).

## A. Install and run deterministic checks (US4, SC-004)

```bash
git clone git@github.com:jnsagai/s-core_bot.git && cd s-core_bot
uv sync --locked                       # installs Python 3.12 env from uv.lock
uv run ruff format --check . && uv run ruff check .
uv run mypy src
uv run pytest                          # socket guard active; no network, no models
uv run python scripts/check_licenses.py
```

Expected: all pass; pytest summary shows `real_runtime` tests as skipped ("not run").

## B. Diagnose with runtime stopped (US1, SC-002)

```bash
sudo snap stop ollama                  # or stop the systemd service
time uv run score-assistant --config config/local.yaml doctor; echo "exit=$?"
```

Expected: `runtime.reachable` FAILURE `RUNTIME_UNREACHABLE` with next action; memory/disk/GPU
still reported; `corpus.state` WARNING `CORPUS_ABSENT`; `exit=1`; wall time < 10 s.

## C. Diagnose with runtime running, models absent (US1 AS2, US3 AS1)

```bash
sudo snap start ollama
uv run score-assistant --config config/local.yaml doctor --json | python3 -m json.tool
uv run score-assistant --config config/local.yaml models inspect
```

Expected: runtime ok with version; both models `MODEL_MISSING` (warning) with the exact
`models pull --profile local-small` command; `exit=0`; no download occurs.

## D. Acquire models (US3 AS2 — uses network, ~2.8 GB)

```bash
uv run score-assistant --config config/local.yaml models pull --profile local-small
cat data/model-lock.json
uv run score-assistant --config config/local.yaml doctor
```

Expected: lock contains both tags with sha256 digests; doctor shows models ok and lock `match`.

## E. Configuration errors (US1 AS3, SC-005)

```bash
printf 'schema_version: 1\nserver:\n  hots: 127.0.0.1\n' > /tmp/bad.yaml
uv run score-assistant --config /tmp/bad.yaml doctor; echo "exit=$?"
SCORE_ASSISTANT_SERVER__HOST=0.0.0.0 uv run score-assistant serve; echo "exit=$?"
```

Expected: `server.hots: unknown key` with exit 2; non-loopback bind refused with exit 2.

## F. Service contract and guard (US2, SC-003)

```bash
uv run score-assistant --config config/local.yaml serve &
curl -s -i http://127.0.0.1:8080/health/live
curl -s -i http://127.0.0.1:8080/health/ready          # 503, reasons include corpus_missing
curl -s http://127.0.0.1:8080/api/v1/capabilities
curl -s -i -H 'Origin: https://evil.example' http://127.0.0.1:8080/api/v1/capabilities   # 403
curl -s -i -H 'Host: attacker.example' http://127.0.0.1:8080/health/live                 # 400
ss -ltnp | grep 8080                                   # listening on 127.0.0.1 only
kill %1
```

## Recording

Record commands, outputs (redacted), timings, and environment in
`specs/001-foundation/verification.md`. Scenario D is optional for F001 completion if disk or
network is unavailable; record it as "not run" with the reason.
