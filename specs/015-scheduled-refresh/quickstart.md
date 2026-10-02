# Quickstart: F011 Scheduled Corpus Refresh

Prerequisites: the README setup (models pulled, Ollama running, `uv sync`). For safety this
walkthrough uses a copy of `data/` so activation and retention cannot touch the main data.

## 1. Deterministic tests (no network, no models)

```bash
uv run pytest tests/unit/test_refresh_*.py tests/integration/test_refresh_*.py tests/contract/test_cli_refresh.py
```

## 2. Real refresh against upstream (network)

```bash
cp -a data /tmp/refresh-data
sed 's#^data_dir: .*#data_dir: /tmp/refresh-data#' config/local.yaml > /tmp/refresh.yaml
uv run score-assistant --config /tmp/refresh.yaml refresh            # expect: activated (exit 0)
uv run score-assistant --config /tmp/refresh.yaml refresh --json     # expect: up-to-date (exit 0)
find /tmp/refresh-data -newer /tmp/refresh-data/refresh-state.json -type f   # expect: nothing new
uv run score-assistant --config /tmp/refresh.yaml doctor | grep refresh
uv run score-assistant --config /tmp/refresh.yaml search "How do I build the documentation?"
```

## 3. Overlap

```bash
uv run score-assistant --config /tmp/refresh.yaml refresh & sleep 1
uv run score-assistant --config /tmp/refresh.yaml refresh; echo "exit $?"   # expect: busy, exit 4
wait
```

## 4. Timer units (rendered into a temporary directory, not enabled)

```bash
scripts/install_refresh_timer.sh --unit-dir /tmp/units --config config/local.yaml --no-enable
systemd-analyze verify --user /tmp/units/score-assistant-refresh.service /tmp/units/score-assistant-refresh.timer
```

Enable for real (owner's choice): `scripts/install_refresh_timer.sh --config config/local.yaml`;
disable: `scripts/install_refresh_timer.sh --uninstall`. See `docs/runbooks/refresh.md`.
