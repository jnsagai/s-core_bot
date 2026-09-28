# Quickstart / Validation Guide: F005

Starting point: F004 done with an active snapshot, and Ollama on loopback with the locked
`qwen3:4b-instruct` and `nomic-embed-text`. `C=config/local.yaml`. Contracts:
[contracts/cli.md](contracts/cli.md), [contracts/http-api.md](contracts/http-api.md),
[contracts/answer-schema.md](contracts/answer-schema.md).

## A. Deterministic checks (fake generation provider, no models)

```bash
uv run ruff format --check . && uv run ruff check . && uv run mypy src
uv run pytest
```

## B. Ask covered and uncovered questions (real model)

```bash
uv run score-assistant --config $C ask "Which work products does the architecture design process require?"
uv run score-assistant --config $C ask "What is the recommended way to set up the development environment?" --show-evidence
uv run score-assistant --config $C ask "What is the capital of France?" --json | jq '.status, .claims'
```

Expected: cited `answered`/`partial` answers for the first two; `insufficient_evidence` (or a
limitation-only answer) for the third, with no documented claims.

## C. HTTP JSON and streaming

```bash
uv run score-assistant --config $C serve &
curl -s -H 'Host: 127.0.0.1:8080' -H 'Content-Type: application/json' \
  -d '{"question":"How do I build the documentation locally?"}' localhost:8080/api/v1/chat | jq '.status,.citations[0].immutable_url'
curl -sN -H 'Host: 127.0.0.1:8080' -H 'Content-Type: application/json' -H 'Accept: text/event-stream' \
  -d '{"question":"How are inspections performed?"}' localhost:8080/api/v1/chat
```

## D. Generation outage preserves search

With a config copy whose `runtime.base_url` points to an unused loopback port, `ask` exits 1 with
`GENERATION_UNAVAILABLE`, while `search` still returns keyword evidence. `/health/ready` reports chat
unavailable and search available.

## E. Answer evaluation (development measurement)

```bash
uv run score-assistant --config $C eval answers --cases eval/answers-dev.yaml
SCORE_ASSISTANT_REAL_RUNTIME=1 uv run pytest -m real_runtime -k injection
```

Record status agreement, safe handling of unanswerable cases, citation integrity and injection
results in `verification.md`. Human-judged metrics stay "not run" unless a review sheet is filled in.

## F. Blocked egress (AT-01)

`unshare -rn` removes loopback access to Ollama as well, so it cannot demonstrate AT-01. Instead,
run `ask` while external egress is unavailable to the process but loopback works (e.g. a network
namespace with only `lo` up and Ollama started inside it, if feasible), or record the constraint
honestly as a deviation, with the socket-guard test proving that no non-loopback connection is
attempted.
