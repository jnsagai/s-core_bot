# CLI and deployment contracts (F009)

| Command / file | Contract |
| --- | --- |
| `Dockerfile` | non-root (uid 10001), `SCORE_ASSISTANT_CONTAINER=1`, `VOLUME /data`, health check, locked deps, no data/secrets |
| `compose.yaml` profile `bundled` | app `127.0.0.1:8080:8080` only; `ollama` no ports, internal network, models read-only; caps, cap_drop ALL, no-new-privileges, read_only, log caps |
| `compose.yaml` profile `host-runtime` | app on the host network with the loopback bind and loopback runtime (Linux) |
| `compose.nvidia.yaml` | GPU override for `ollama` (needs the NVIDIA container toolkit; not run on the reference machine) |
| `config/container.yaml` | `deployment.mode: container`, `server.host: 0.0.0.0`, `runtime.base_url: http://ollama:11434`, `runtime_private_hosts: [ollama]`, `data_dir: /data` |
| `scripts/prepare_package.sh OUT` | bundle + image archives + model lock + manifest (hashes); `--with-models` copies models |
| `scripts/fresh_install.sh PACKAGE WORK` | offline (namespace) clean install → doctor → serve → probe → restore check; writes `data/reports/fresh-install-*.json`, `restore-*.json` |
| `scripts/container_check.sh` | brings up the `bundled` profile, inspects ports and hardening, probes, writes `data/reports/container-*.json`, brings it down |
| `uv run python -m score_docs_assistant.qualification.contract --base-url URL --out FILE` | writes a contract signature; `--compare A B` exits 1 on differences |
| `uv run python scripts/sbom.py --out FILE` | CycloneDX 1.5 JSON |
| `score-assistant release assemble [--include-bundle]` | "Collects the release contents (locks, SBOM, notices, model record, corpus identity, reports, hardware matrix, limitations) with a hash manifest." |
