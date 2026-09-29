# Quickstart / Validation Guide: F008

`C=config/local.yaml`. Real runs need Ollama on loopback with the locked models and the active
snapshot.

## A. Deterministic checks

```bash
uv run ruff format --check . && uv run ruff check . && uv run mypy src
uv run pytest --junitxml=data/reports/pytest-$(date -u +%Y%m%dT%H%M%SZ).xml
uv run python scripts/check_traceability.py
cd frontend && npx vitest run --reporter=junit --outputFile=../data/reports/vitest-$(date -u +%Y%m%dT%H%M%SZ).xml
```

## B. Suite (real model)

```bash
uv run score-assistant --config $C eval suite --split dev
uv run score-assistant --config $C eval suite --split heldout --runs 3     # refused if not frozen
```

## C. Adversarial, offline, performance, models

```bash
uv run score-assistant --config $C eval adversarial
scripts/offline_check.sh
uv run score-assistant --config $C eval performance --cases eval/suite/dev.yaml --cases eval/suite/heldout.yaml
uv run score-assistant --config $C models qualify
```

## D. Human review (owner)

Fill `data/reports/suite-heldout-*-review.yaml` following `docs/quality/review-rubric.md`, then:

```bash
uv run score-assistant --config $C eval review import --sheet <sheet> --report <run report>
```

## E. Release report

```bash
uv run score-assistant --config $C release report
```

Expected before a human review: verdict `blocked`, human-judged gates `blocked — awaiting human
review`, every other gate `pass`/`fail`/`not run` with its evidence file.
