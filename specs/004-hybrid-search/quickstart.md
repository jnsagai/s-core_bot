# Quickstart / Validation Guide: F004

Starting point: F003 done, with an active snapshot (`score-assistant --config config/local.yaml
snapshots list` shows `*`) and Ollama on loopback with `nomic-embed-text` for the hybrid
scenarios. Contracts: [contracts/cli.md](contracts/cli.md),
[contracts/http-api.md](contracts/http-api.md), [contracts/eval-cases.md](contracts/eval-cases.md).
Below, `C=config/local.yaml`.

## A. Deterministic checks (no network, no models)

```bash
uv run ruff format --check . && uv run ruff check . && uv run mypy src
uv run pytest            # fixture snapshots + fake embedding provider
```

## B. Exact lookup and relationships (offline)

```bash
uv run score-assistant --config $C lookup feat_req__com__interfaces --relationships
uv run score-assistant --config $C lookup FEAT_REQ-COM-INTERFACES           # alias match, labelled
uv run score-assistant --config $C eval exact-ids                          # every ID first: exit 0
```

Expected: the pinned `score-platform:` entity first, then its `score-platform-needs:` copy labelled
`unverified`; outgoing and incoming links exactly as stored.

## C. Search (hybrid, then degraded)

```bash
uv run score-assistant --config $C search "How do I build the documentation locally?"
uv run score-assistant --config $C search "feat_req__com__interfaces dependencies" --json | jq '.results[0].matched_by'
uv run score-assistant --config $C search "safety analysis" --source score-process --kind prose
uv run score-assistant --config $C search "bazel" --lexical
```

Runtime unavailable (config copy pointing `runtime.base_url` at an unused loopback port): the same
search returns keyword results, `mode: lexical`, `degraded.reason: embedding_runtime_unavailable`.

## D. HTTP API

```bash
uv run score-assistant --config $C serve &
curl -s -H 'Host: 127.0.0.1:8080' localhost:8080/health/ready | jq .capabilities.search
curl -s -H 'Host: 127.0.0.1:8080' -H 'Content-Type: application/json' \
  -d '{"query":"code review guideline","limit":5}' localhost:8080/api/v1/search | jq '.mode,.results[].path'
curl -s -H 'Host: 127.0.0.1:8080' 'localhost:8080/api/v1/entities?id=feat_req__com__interfaces' | jq '.entities[].key'
curl -s -o /dev/null -w '%{http_code}\n' -H 'Host: 127.0.0.1:8080' -H 'Origin: https://evil.example' \
  -H 'Content-Type: application/json' -d '{"query":"x"}' localhost:8080/api/v1/search   # 403
```

## E. Evaluation (development measurement)

```bash
uv run score-assistant --config $C eval retrieval --cases eval/retrieval-dev.yaml
uv run score-assistant --config $C eval latency --cases eval/retrieval-dev.yaml --queries 50
```

Record recall@10 by category with counts, and the p50/p95 for keyword-only and hybrid, with the
environment in `verification.md`, labelled "unreviewed cases, development measurement".

## F. Offline (`unshare -rn`)

`lookup`, `eval exact-ids` and `search` (degraded to lexical, with the warning) succeed with no
network at all.
