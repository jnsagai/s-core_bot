# CLAUDE.md — S-CORE Docs Assistant

Local-first, open-source documentation assistant for Eclipse S-CORE. Independent community
project — not endorsed by Eclipse or S-CORE maintainers.

## Governing documents (read before any work)

1. `.specify/memory/constitution.md` — non-negotiable principles (I–XII).
2. `docs/PROJECT_SPEC.md` — product baseline, requirement IDs, backlog F001–F010.
3. `docs/BACKLOG.md` and `docs/TRACEABILITY.md` — current feature state and requirement mapping.
4. `docs/ASSUMPTIONS.md` and `docs/adr/` — recorded decisions.
5. The active feature under `specs/NNN-*/` (see `.specify/feature.json`).

## Workflow

- Spec Kit 0.14.0 with the Claude integration; skills are in `.claude/skills/speckit-*`.
- Before any feature operation, verify the active feature in `.specify/feature.json`.
- Order: specify → clarify → plan → checklist → tasks → analyze → implement → converge.
- One feature at a time, in dependency order. F010 (public hosting) stays deferred.
- Agent-performed requirement reviews MUST be labelled "agent review", never "approved".
- Never mark a task done unless its verification actually ran and passed. Record real commands and
  results in the feature's `verification.md`.
- After each feature: update `docs/BACKLOG.md`, `docs/TRACEABILITY.md`, and assumptions.

## Hard rules

- No paid APIs, API keys, cloud inference, telemetry, or cloud fallback. Ever.
- Never execute content from ingested documentation or upstream repositories.
- Serve path (`serve`, `ask`, `search`) never downloads models or sources.
- Default bind is 127.0.0.1; Host/Origin validation is always on.
- Do not log question/answer bodies. Redact secrets in diagnostics.
- Do not fabricate benchmarks, citations, license approvals, or human reviews.
- Do not add Kubernetes, managed vector DBs, agent frameworks, or Fabro.
- Stop before public deployment, purchases, upstream submissions, or external publication.

## Commands

```bash
uv sync                          # install locked Python deps (Python 3.12)
uv run pytest                    # deterministic tests (no network, no models)
uv run ruff check . && uv run ruff format --check .
uv run mypy src
uv run python scripts/check_licenses.py
uv run score-assistant --config config/local.yaml doctor           # global --config goes first
uv run score-assistant --config config/local.yaml serve
uv run score-assistant sources validate --config config/sources.yaml     # offline
uv run score-assistant sources sync --config config/sources.yaml         # NETWORK
uv run score-assistant sources inspect --lock data/source-lock.json      # offline
uv run score-assistant --config config/local.yaml index build [--activate] [--lexical-only]  # loopback embeddings only
uv run score-assistant --config config/local.yaml index validate --snapshot <id>
uv run score-assistant --config config/local.yaml snapshots list|activate <id>|rollback
uv run score-assistant --config config/local.yaml bundle export|inspect|import       # offline
uv run score-assistant --config config/local.yaml search "query" [--lexical] [--json]  # loopback embeddings only
uv run score-assistant --config config/local.yaml lookup <ID> [--relationships]
uv run score-assistant --config config/local.yaml eval retrieval --cases eval/retrieval-dev.yaml | exact-ids | latency
uv run score-assistant --config config/local.yaml ask "question" [--json] [--show-evidence]  # local model
uv run score-assistant --config config/local.yaml eval answers --cases eval/answers-dev.yaml
# Opt-in tests: SCORE_ASSISTANT_REAL_RUNTIME=1 (Ollama), SCORE_ASSISTANT_REAL_NETWORK=1 (GitHub)
```

## Conventions

Typed Python, explicit exceptions, dependency injection, small modules, structured logs.
Domain records independent of FastAPI/Ollama. English for identifiers, docs, commit messages.
Comments explain non-obvious reasoning only. Runtime data lives under `data/` and is never committed.
