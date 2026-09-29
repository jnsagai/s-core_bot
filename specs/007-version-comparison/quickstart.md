# Quickstart / Validation Guide: F007

Starting point: F006 done, the active snapshot, Ollama on loopback with the locked models, and
(for B–E) a second snapshot with different content (the baseline, see §0). `C=config/local.yaml`.
Contracts: [contracts/http-api.md](contracts/http-api.md), [contracts/cli.md](contracts/cli.md),
[contracts/comparison-schema.md](contracts/comparison-schema.md).

## 0. Build the baseline snapshot (network for sync; never activated)

```bash
cp data/source-lock.json data/source-lock.main.json
uv run score-assistant sources sync --config config/sources-baseline.yaml
mv data/source-lock.json data/source-lock-baseline.json && cp data/source-lock.main.json data/source-lock.json
uv run score-assistant --config $C index build --source-lock data/source-lock-baseline.json
uv run score-assistant --config $C snapshots list      # baseline is `validated`, active unchanged
```

## A. Deterministic checks (fake provider, fixture snapshots)

```bash
uv run ruff format --check . && uv run ruff check . && uv run mypy src
uv run pytest
cd frontend && npm run lint && npm run typecheck && npm test && npm run build
```

## B. Snapshot identity without the model

```bash
uv run score-assistant --config $C snapshots diff <baseline> <active>
```

Expected: `different` git sources, needs exports `right only` and `unverified`, no release label.

## C. CLI comparison (real model)

```bash
uv run score-assistant --config $C compare "How are inspections performed?" --left <baseline> --right <active>
uv run score-assistant --config $C compare "What does gd_req__req_attr_uid require?" --left <baseline> --right <active> --json | jq '.differences'
```

Expected: side-labelled answers and citations; the requirement case is `unchanged`/`changed` when
both sides have the record, or `not_established` with a coverage reason. No statement says
removed, deleted or added.

## D. HTTP and UI

```bash
uv run score-assistant --config $C serve &
curl -s -H 'Host: 127.0.0.1:8080' -H 'Content-Type: application/json' \
  -d '{"question":"How are inspections performed?","left_snapshot_id":"<baseline>","right_snapshot_id":"<active>"}' \
  localhost:8080/api/v1/compare | jq '.differences[].type, .snapshots.warnings'
```

In a browser (owner): Compare tab → pick both snapshots → ask → open an `L` and an `R` citation →
export Markdown/JSON → check both snapshot IDs and revisions are present. Keyboard only.

## E. Comparison benchmark

```bash
uv run score-assistant --config $C eval comparison --cases eval/comparison-dev.yaml --left <baseline> --right <active>
```

Record type agreement, isolation violations (expect 0), citation integrity and deletion claims
(expect 0) in `verification.md` as a development measurement.
