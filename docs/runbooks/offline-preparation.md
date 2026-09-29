# Runbook: prepare offline, transfer, install

1. On a prepared machine (models pulled, sources synced, index built and active):
   ```bash
   scripts/prepare_package.sh /path/to/package --acknowledge-license-review "<your reviewed reason>"
   ```
   This writes the corpus bundle, the source as a git bundle, the built UI, the model lock, the app
   image archive and `package-manifest.json` (SHA-256 of every file).
   - `--with-runtime-image` adds the ~5.5 GB runtime image, and `--with-models` copies the weights.
   - Three process-description documents are flagged for license review, so exporting requires
     your reviewed reason. Weights and bundles are for your own transfer: their redistribution has
     not been reviewed.
2. Transfer the directory. On the target, run
   `python -m score_docs_assistant.qualification.package verify <package>`.
3. Install without network: `scripts/fresh_install.sh <package> <work-dir>` exercises exactly
   this inside a loopback-only namespace. It clones from the bundle, runs `uv sync --offline`,
   unpacks the UI, imports and activates the bundle, and runs doctor, serve and a probe.
   Containers: `docker load -i app-image.tar.gz` (and the runtime image), then follow
   `install.md`.
   - A native offline install needs uv's package cache from a prepared machine.
   - The container images carry every dependency themselves.
