# Quickstart / Validation Guide: F009

## A. Deterministic
```bash
uv run ruff format --check . && uv run ruff check . && uv run mypy src && uv run pytest
```

## B. Containers (preparation: builds/pulls images once)
```bash
docker compose build && docker compose --profile bundled pull ollama
scripts/container_check.sh          # up → ports/hardening/probe → down; data/reports/container-*.json
```

## C. Package, fresh install, restore (offline)
```bash
scripts/prepare_package.sh /tmp/score-package
scripts/fresh_install.sh /tmp/score-package /tmp/score-fresh
```

## D. Contract parity
```bash
uv run python -m score_docs_assistant.qualification.contract --base-url http://127.0.0.1:8080 --out data/reports/contract-native.json
# with the container stack up on 8080 instead:
uv run python -m score_docs_assistant.qualification.contract --base-url http://127.0.0.1:8080 --out data/reports/contract-container.json
uv run python -m score_docs_assistant.qualification.contract --compare data/reports/contract-native.json data/reports/contract-container.json
```

## E. SBOM, release assembly, report
```bash
uv run python scripts/sbom.py --out data/reports/sbom-$(date -u +%Y%m%dT%H%M%SZ).cdx.json
uv run score-assistant --config config/local.yaml release assemble
uv run score-assistant --config config/local.yaml release report
```
