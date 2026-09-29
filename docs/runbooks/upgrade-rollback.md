# Runbook: upgrade and roll back

- **Corpus update**: `sources sync` (network), then `index build` (never activates), then
  `index validate --snapshot <id>`, then `snapshots activate <id>`. A failed build leaves the active
  snapshot untouched.
- **Roll back the corpus**: `snapshots rollback` (atomic; in-flight requests keep their pinned
  snapshot).
- **Application upgrade (native)**: pull the new commit and run `uv sync`, rebuild the UI, run
  `doctor` (checks snapshot compatibility), then restart `serve`. To roll back, check out the
  previous commit and repeat.
- **Application upgrade (containers)**: build or load the new image tag, change `image:` in
  `compose.yaml`, then `up -d --pull never`. To roll back, point to the previous tag. Snapshots in
  `/data` are shared; `doctor` refuses an incompatible corpus schema.
- **Models**: `models pull` requalifies; a digest change makes old snapshots degrade to keyword
  search until rebuilt (explicit reason, AT-08).
