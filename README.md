# S-CORE Docs Assistant

Ask questions about the [Eclipse S-CORE](https://github.com/eclipse-score) documentation and get
short answers that cite exactly where each statement comes from. It runs entirely on your own
machine.

> **Community project.** This is an independent, open-source project. It is not endorsed by,
> affiliated with, or certified by the Eclipse Foundation or the Eclipse S-CORE maintainers.

## What it is

S-CORE has a large body of documentation: platform docs, process descriptions, and thousands of
requirement records. The assistant downloads a pinned copy of that documentation once, indexes it,
and then lets you:

- **Ask** a question in plain English and get a short answer where each statement cites a stored
  excerpt, with a link to the exact upstream revision.
- **Search** the documentation directly, by keyword or meaning, without the answer model.
- **Look up** a requirement ID (for example `feat_req__com__interfaces`) and see its relationships.
- **Compare** how two documentation snapshots answer the same question.

You can use it from the command line, a local web page, or a local HTTP API.

### What makes it different

- **Local only.** A small open model ([Ollama](https://ollama.com) with `qwen3:4b-instruct`)
  answers on your machine. There are no API keys, paid services, accounts, telemetry, or cloud
  fallback.
- **Grounded.** Answers come only from the indexed documentation. When the evidence is weak, the
  assistant says so (`insufficient_evidence` or `partial`) instead of guessing.
- **Offline once prepared.** Only two explicit steps use the internet: downloading the models and
  downloading the documentation. Asking, searching, and serving never do.
- **Private by default.** The server listens on `127.0.0.1` only. Questions and answers are not
  logged or saved.

### How it works

```text
 S-CORE repos ──sources sync──▶ pinned copy ──index build──▶ snapshot ──▶ search / ask / web UI
 (GitHub, network)              (data/)        (local model)   (SQLite + embeddings)  (offline)
```

Each **snapshot** is an immutable, checksummed index of one set of documentation revisions. You can
keep several, switch between them, and roll back.

## Requirements

| What | Version | Why |
|---|---|---|
| Linux x86-64 | — | Supported platform (macOS and Windows are not validated) |
| [`uv`](https://docs.astral.sh/uv/) | ≥ 0.12 | Installs Python 3.12 and the locked dependencies |
| [Ollama](https://ollama.com) | 0.34.0 | Runs the local models on `127.0.0.1:11434` |
| `git` | ≥ 2.34 | Downloads the documentation |
| Node.js | 22 | Builds the web UI once (optional if you only use the CLI) |

Plan for about **3 GB of disk** for the models plus space for the documentation and indexes. A GPU
makes answers fast (about 8 s on an RTX 4070 laptop); CPU-only works but a first answer can take
about a minute.

## Build and set up

Run these from the repository root. Steps 3 and 4 are the only ones that use the internet.

**1. Install the Python environment**

```bash
uv sync
```

**2. Start Ollama** (if it is not already running as a service)

```bash
OLLAMA_NO_CLOUD=1 ollama serve
```

`OLLAMA_NO_CLOUD=1` disables Ollama's own cloud features so everything stays local.

**3. Download the models** (network)

```bash
uv run score-assistant --config config/local.yaml models pull --profile local-small
```

This fetches `qwen3:4b-instruct` (answers) and `nomic-embed-text` (semantic search) through your
local Ollama and records their exact digests.

**4. Download the S-CORE documentation** (network)

```bash
uv run score-assistant sources sync --config config/sources.yaml
```

The approved sources are listed in `config/sources.yaml`. Nothing from the downloaded repositories
is ever executed.

**5. Build and activate a snapshot**

```bash
uv run score-assistant --config config/local.yaml index build --activate
```

This uses only the local embedding model. Without Ollama, add `--lexical-only` to get a
keyword-only index.

**6. Build the web UI** (optional, once)

```bash
(cd frontend && npm ci && npm run build)
```

**7. Check that everything is ready**

```bash
uv run score-assistant --config config/local.yaml doctor
```

You should see `[OK]` lines like these:

```text
[OK] config.valid: Configuration is valid.
[OK] runtime.reachable: Ollama 0.34.0 reachable at http://127.0.0.1:11434.
[OK] model.generation: qwen3:4b-instruct is installed.
[OK] model.embedding: nomic-embed-text:latest is installed.
[OK] model.lock: Installed models match the lock.
[OK] corpus.state: An active, compatible corpus snapshot is installed.
```

`doctor` exits with `0` when ready, `1` on an operational problem, and `2` on a configuration
error. Each problem comes with a suggested fix.

> **Tip:** `--config config/local.yaml` is a global option and goes *before* the subcommand. The
> `--config` after `sources …` points to the source list instead.

## Hello world

### Ask your first question

```bash
uv run score-assistant --config config/local.yaml ask "What is Eclipse S-CORE?"
```

```text
snapshot 20260928T140548Z-7c6a05b3  status answered  model qwen3:4b-instruct (0edcdef34593)
- Eclipse S-CORE is a comprehensive process model designed to establish organizational rules for
  developing open source automotive software in safety and security-critical contexts. This
  project is part of the Eclipse Foundation and provides standardized processes for the automotive
  industry. [E1]
citations:
[E1] score-process  README.md:5-9  (pinned)
     https://github.com/eclipse-score/process_description/blob/66321fe6bd131eae58fbd6395b0f0b92d63e00f5/README.md#L5-L9
```

Every statement ends with a citation such as `[E1]`, and the citation points to the exact file,
lines, and upstream commit. Your snapshot ID, commit, and wording will differ. Add `--json` for
machine-readable output or `--show-evidence` to print the cited excerpts.

### Search without the answer model

```bash
uv run score-assistant --config config/local.yaml search "How do I build the documentation?"
```

```text
snapshot 20260928T140548Z-7c6a05b3  mode hybrid  8 results
 1. [keyword semantic] score-platform  docs/users_guide/building_simple_application/doc_generation.rst:98-101  (code)  Documentation generation > Building documentation
    % bazel build //:docs
 ...
```

Look up a requirement by its ID:

```bash
uv run score-assistant --config config/local.yaml lookup feat_req__com__interfaces --relationships
```

### Open the web UI

```bash
uv run score-assistant --config config/local.yaml serve
```

Then open <http://127.0.0.1:8080/> in a browser on the same machine. You can ask questions, click a
citation to read its excerpt, search, compare snapshots, and export an answer as Markdown or JSON.
Conversations live only in the page and are cleared on reload. Press `Ctrl+C` to stop the server.

## Running with Docker instead

After steps 3–5 (models downloaded, active snapshot in `./data`), you can run the app and the model
runtime in hardened containers. The app is published on `127.0.0.1:8080` only and the runtime has
no internet access.

```bash
docker compose build
docker compose --profile bundled pull ollama
SCORE_DATA_DIR=./data SCORE_MODELS_DIR=/var/snap/ollama/common/models \
  docker compose --profile bundled up -d --pull never
docker compose --profile bundled down        # stop
```

`SCORE_MODELS_DIR` is where your Ollama keeps its models. Containers run on CPU by default, so
answers are slower. See [`docs/runbooks/install.md`](docs/runbooks/install.md) for the
`host-runtime` profile and GPU notes.

## Common problems

| Symptom | Fix |
|---|---|
| `runtime.reachable` fails | Start Ollama (`ollama serve`) and check it listens on `127.0.0.1:11434`. |
| A model is reported missing | Run step 3 (`models pull --profile local-small`). |
| "no active snapshot" | Run steps 4 and 5. |
| Search shows keyword results only | The embedding model is unavailable. Search still works; start Ollama for semantic results. |
| Web page shows "answers unavailable" | Start Ollama, then press **Check again** on the Status tab. |
| The browser gets a 400/403 from the server | Use `http://127.0.0.1:8080` or `http://localhost:8080`. Other host names are rejected on purpose. |

More in [`docs/runbooks/troubleshooting.md`](docs/runbooks/troubleshooting.md).

## Keeping the documentation up to date

One command checks upstream S-CORE and, only if something changed, downloads it, builds a new
snapshot, checks it, and switches to it:

```bash
uv run score-assistant --config config/local.yaml refresh      # network
```

```text
check  score-platform         changed    e2373d8 → 4e8b93a
check  score-platform-needs   unknown    no stored validator
check  score-process          changed    66321fe → d0f9291
check  score-process-needs    unknown    no stored validator
sync   lock updated (4 source(s) changed)
build  20261002T082027Z-edd42609  (13.7 s)
gate   integrity pass (…) | exact_ids pass (2177/2177 found first) | coverage_drop pass (…) | semantic pass (…) | required_sources pass (…)
activated: activated 20261002T082027Z-edd42609 (previous 20260928T140548Z-7c6a05b3)
```

Running it again right away prints `up-to-date: no upstream change` in about 2 seconds and creates
no files. A new snapshot that looks broken (for example far fewer documents, or semantic search
lost) is **held**: the current snapshot keeps serving and the reason is shown. A running `serve`
picks up a new snapshot without a restart.

To run it automatically every 15 minutes (opt-in, systemd user timer):

```bash
scripts/install_refresh_timer.sh --config config/local.yaml
scripts/install_refresh_timer.sh --uninstall                     # turn it off again
```

Read [`docs/runbooks/refresh.md`](docs/runbooks/refresh.md) first. In particular, every activation
removes snapshots beyond `index.retention_count` (default 2), including a comparison baseline you
never activated.

## Day-to-day commands

```bash
# Refresh the documentation by hand, step by step (what `refresh` automates)
uv run score-assistant sources sync --config config/sources.yaml
uv run score-assistant --config config/local.yaml index build --activate

# Manage snapshots
uv run score-assistant --config config/local.yaml snapshots list
uv run score-assistant --config config/local.yaml snapshots rollback

# Compare two snapshots
uv run score-assistant --config config/local.yaml snapshots diff <left> <right>
uv run score-assistant --config config/local.yaml compare "question" --left <id> --right <id>

# Move a snapshot to another machine
uv run score-assistant --config config/local.yaml bundle export --snapshot <id> --output <file>
uv run score-assistant --config config/local.yaml bundle import <file>     # on the other machine
uv run score-assistant --config config/local.yaml snapshots activate <id>
```

Run `uv run score-assistant --help` (or `<command> --help`) for every option.

## Further reading

- [Web UI guide](docs/user/local-ui.md) and [snapshot comparison](docs/user/comparison.md)
- Runbooks: [install](docs/runbooks/install.md),
  [offline preparation](docs/runbooks/offline-preparation.md),
  [backup and restore](docs/runbooks/backup-restore.md),
  [upgrade and rollback](docs/runbooks/upgrade-rollback.md), [logs](docs/runbooks/logs.md),
  [refresh](docs/runbooks/refresh.md)
- [Release notes 1.0.0](docs/releases/v1.0.0.md) and
  [known limitations](docs/KNOWN_LIMITATIONS.md)
- [Quality and evaluation](docs/user/quality.md)

## Project status

**1.0.0** is a local release: CLI, web UI, HTTP API, snapshot comparison, containers, and offline
packaging. It is qualified on one Linux laptop with an NVIDIA GPU. Public hosting is not part of
this release. Read the [known limitations](docs/KNOWN_LIMITATIONS.md) before relying on the
answers.

## Contributing and development

Development is spec-first with [Spec Kit](https://github.com/github/spec-kit). Start with
[`CLAUDE.md`](CLAUDE.md), the constitution in `.specify/memory/constitution.md`, and
[`docs/PROJECT_SPEC.md`](docs/PROJECT_SPEC.md).

```bash
uv run pytest                                          # deterministic tests (no network, no models)
uv run ruff check . && uv run ruff format --check .
uv run mypy src
uv run python scripts/check_licenses.py
(cd frontend && npm run lint && npm run typecheck && npm test)
```

## License

Apache License 2.0, see [`LICENSE`](LICENSE), [`NOTICE`](NOTICE), and
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md). Model weights and documentation content are not
redistributed with this project and keep their own licenses.
