# Hardware and OS matrix (what was actually run)

| Platform | Mode | Status | Evidence |
| --- | --- | --- | --- |
| Linux x86-64, NVIDIA RTX 4070 Laptop 8 GiB, Ollama 0.34.0 snap | native, GPU | **qualified** (F008): answer p95 7.6 s warm, hybrid p95 101 ms, peak GPU 4.4 GiB | `performance-*.json`, F008 verification |
| Same machine | container `bundled`, CPU (runtime in a container, no GPU) | **functional**: cited answer in ~60 s including model load | `container-*.json`, F009 verification |
| Same machine | container `bundled` + `compose.nvidia.yaml` | **not run**: NVIDIA container toolkit not installed; installing system packages is out of scope | — |
| Same machine | container `host-runtime` (host network, host GPU runtime) | compose policy tested; not run end-to-end | `tests/unit/test_compose_policy.py` |
| Same machine, loopback-only network namespace | native, offline | **pass** (F008, F009 fresh install) | `offline-*.json`, `fresh-install-*.json` |
| Linux CPU-only host | native | expected to work (CPU path used in containers); not measured separately | — |
| Windows via WSL2, macOS | any | **not validated** (master spec: document after validation) | — |
| Second physical machine | fresh install | **not available**; the fresh install ran in a clean directory and namespace on the reference machine | `fresh-install-*.json` |
