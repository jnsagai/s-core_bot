# S-CORE Docs Assistant — Community Project

A local-first, open-source documentation assistant for Eclipse S-CORE. This is an
**independent community project** — it is not endorsed by, affiliated with, or certified by the
Eclipse Foundation or the Eclipse S-CORE maintainers.

## Status

- **F001 (done)** — validated configuration, Ollama runtime client, hardware/corpus probes,
  `score-assistant doctor | models inspect | models pull | serve`, and a loopback-only HTTP service
  exposing liveness, readiness, and capabilities.
- **F002 (done)** — approved-source registry
  (`config/sources.yaml`), `sources validate | sync | inspect`: pinned acquisition of the S-CORE
  documentation repositories without executing any repository content, and offline normalization
  of RST, Markdown (incl. MyST directives) and Sphinx-Needs requirement records with exact source
  locations, relationships and licensing.

- **F003 (done)** — immutable corpus snapshots: structure-aware chunking, an SQLite
  corpus with a full-text index, local embeddings from `nomic-embed-text` (never truncated, reused
  across builds), manifests with checksums, staged builds, atomic activation and rollback,
  reader pins, retention, and verified bundle export/import:
  `index build | validate`, `snapshots list | activate | rollback`,
  `bundle export | inspect | import`.

- **F004 (done)** — evidence search over one pinned snapshot: exact requirement-ID lookup
  with stored relationships, keyword search, and semantic search with the local embedding model,
  fused into a short ranked list with provenance. It falls back to keyword-only search (stated
  plainly) when embeddings are unavailable, and never needs the answer model. `search`, `lookup`,
  `eval retrieval | exact-ids | latency`, and HTTP `/api/v1/search`, `/entities`,
  `/relationships`, `/snapshots`, `/sources`, `/citations/…`.

- **F005 (done)** — grounded local answers: `ask "question"` and `POST /api/v1/chat`
  (JSON or a server-sent-event progress stream) answer from one snapshot with the locked local
  model. Answers are short claims, each documented claim citing stored excerpts (with exact-revision
  GitHub links where provable). They are validated server-side, with one repair and otherwise a
  labelled extractive fallback. Weak evidence gives `insufficient_evidence`/`partial`, one answer is
  generated at a time with a bounded queue, and there is no cloud fallback.
  `eval answers` measures status, citation integrity and evidence overlap; human-judged quality stays
  "not run" until reviewed.

- **F006 (implemented)** — local web UI served by the same backend at `http://127.0.0.1:8080/`:
  ask with progress, stop and retry, citation panel, direct search, snapshot selector, status view,
  Markdown/JSON export. Conversations stay in page memory only; no CDN, telemetry or third-party
  requests (strict CSP). Build once with `cd frontend && npm ci && npm run build`. See
  `docs/user/local-ui.md`. Its real-browser walkthrough has not been run on the development machine
  (no browser installed there).

## Scope

- Runs entirely on your own machine: no paid API, API key, vendor login, or cloud inference.
- Network access is used only for explicit preparation steps (`uv sync`, `models pull`,
  `sources sync`); `serve`, `sources inspect`, `snapshots` and `bundle` make no external calls.
  `index build` talks only to the local embedding runtime on loopback.
- Binds to `127.0.0.1` by default; a public-facing profile is a separate, not-yet-available mode.

See `docs/PROJECT_SPEC.md` for the full product baseline and `.specify/memory/constitution.md` for
the non-negotiable project principles.

## Prerequisites

- Linux x86-64
- `git` ≥ 2.34 (also used by `sources sync`)
- [`uv`](https://docs.astral.sh/uv/) ≥ 0.12 (manages the Python 3.12 environment)
- Optional, for runtime-dependent commands: [Ollama](https://ollama.com) running on
  `127.0.0.1:11434`

## Quickstart

```bash
uv sync --locked                       # install the locked Python 3.12 environment
uv run ruff format --check . && uv run ruff check .
uv run mypy src
uv run pytest                          # deterministic tests; no network, no models
uv run python scripts/check_licenses.py
uv run score-assistant --config config/local.yaml doctor

# Documentation sources (sync uses the network; validate and inspect are offline)
uv run score-assistant sources validate --config config/sources.yaml
uv run score-assistant --config config/local.yaml sources sync --config config/sources.yaml
uv run score-assistant --config config/local.yaml sources inspect --lock data/source-lock.json

# Snapshots (offline; index build uses only the local Ollama embedding runtime)
uv run score-assistant --config config/local.yaml index build --activate   # add --lexical-only without Ollama
uv run score-assistant --config config/local.yaml snapshots list
uv run score-assistant --config config/local.yaml index validate --snapshot <id>
uv run score-assistant --config config/local.yaml snapshots rollback
uv run score-assistant --config config/local.yaml bundle export --snapshot <id> --output <file>

# Evidence search (offline; may use the local embedding runtime, never the answer model)
uv run score-assistant --config config/local.yaml search "How do I build the documentation?"
uv run score-assistant --config config/local.yaml lookup feat_req__com__interfaces --relationships
uv run score-assistant --config config/local.yaml eval retrieval --cases eval/retrieval-dev.yaml

# Grounded answers (local model; cites stored evidence)
uv run score-assistant --config config/local.yaml ask "Which work products does the architecture process require?"
uv run score-assistant --config config/local.yaml eval answers --cases eval/answers-dev.yaml
```

A build ends `validated` (integrity-checked, not an engineering approval) and is served only after
activation. See `specs/003-snapshot-index/quickstart.md` for the full walkthrough.

The global `--config` (before the subcommand) selects the app configuration; `sources … --config`
selects the source registry.

`doctor` reports local readiness (runtime reachable, models present, disk/memory, corpus state)
with stable status codes and exit codes `0` (ok), `1` (operational failure), or `2`
(configuration/usage error). See `specs/001-foundation/contracts/cli.md` for the full contract and
`specs/001-foundation/quickstart.md` for the complete validation walkthrough.

## Development

This project uses [Spec Kit](https://github.com/github/spec-kit) for spec-first development; see
`CLAUDE.md` for the governing documents and workflow.
