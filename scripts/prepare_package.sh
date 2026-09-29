#!/usr/bin/env bash
# Prepare a transferable package from this prepared machine (F009 FR-005). Offline.
#   scripts/prepare_package.sh OUT_DIR [--with-runtime-image] [--with-models]
#                               [--acknowledge-license-review TEXT]
# Contents: corpus bundle of the active snapshot, source as a git bundle, the built frontend,
# the model lock, the app image archive, and package-manifest.json with SHA-256 hashes.
# The runtime image (~5.5 GB) and model weights are opt-in (disk; redistribution not reviewed).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
OUT="${1:?usage: prepare_package.sh OUT_DIR [...]}"; shift
WITH_RUNTIME=0; WITH_MODELS=0; ACK=()
while [ $# -gt 0 ]; do
  case "$1" in
    --with-runtime-image) WITH_RUNTIME=1 ;;
    --with-models) WITH_MODELS=1 ;;
    --acknowledge-license-review) ACK=(--acknowledge-license-review "$2"); shift ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
  shift
done
FREE_KIB=$(df --output=avail -k "$(dirname "$OUT")" | tail -1 | tr -d ' ')
if [ "$FREE_KIB" -lt $((3 * 1024 * 1024)) ]; then echo "refusing: less than 3 GiB free" >&2; exit 2; fi
if [ -e "$OUT" ] && [ -n "$(ls -A "$OUT" 2>/dev/null)" ]; then echo "refusing: $OUT is not empty" >&2; exit 2; fi
mkdir -p "$OUT"
APP=.venv/bin/score-assistant
C=config/local.yaml
SNAP=$(.venv/bin/python -c "from score_docs_assistant.storage.catalog import Catalog; from score_docs_assistant.config.loader import load_config; from pathlib import Path; c=load_config(config_path=Path('$C')).config; cat=Catalog.open(c.data_dir, create=False); print(cat.active_id() if cat else '')")
[ -n "$SNAP" ] || { echo "no active snapshot" >&2; exit 1; }
"$APP" --config "$C" bundle export --snapshot "$SNAP" --output "$OUT/corpus.score-bundle.tar.gz" "${ACK[@]}"
git bundle create "$OUT/source.git.bundle" HEAD
git rev-parse HEAD > "$OUT/source-commit.txt"
tar -C frontend -czf "$OUT/frontend-dist.tar.gz" dist
cp data/model-lock.json "$OUT/model-lock.json"
docker save score-docs-assistant:0.1.0 | gzip > "$OUT/app-image.tar.gz"
RUNTIME_IMAGE=$(awk '/image: ollama/ {print $2}' compose.yaml)
if [ "$WITH_RUNTIME" = 1 ]; then docker save "$RUNTIME_IMAGE" | gzip > "$OUT/runtime-image.tar.gz"; fi
if [ "$WITH_MODELS" = 1 ]; then cp -r "${SCORE_MODELS_DIR:-/var/snap/ollama/common/models}" "$OUT/models"; fi
.venv/bin/python -m score_docs_assistant.qualification.package manifest "$OUT" \
  --meta "snapshot_id=$SNAP" --meta "source_commit=$(git rev-parse HEAD)" \
  --meta "app_image=$(docker image inspect score-docs-assistant:0.1.0 --format '{{.Id}}')" \
  --meta "runtime_image=$RUNTIME_IMAGE" --meta "runtime_image_included=$WITH_RUNTIME" \
  --meta "models_included=$WITH_MODELS" \
  --meta "native_dependencies=locked uv cache of the prepared machine (container images carry them)"
du -sh "$OUT"
