# Toolchain record

Recorded 2026-09-27 on the primary development workstation. Update when any pin changes.

## Spec Kit

| Item | Value |
| --- | --- |
| Package | `specify-cli` (official `github/spec-kit`) |
| Installed version | 0.14.0 (`specify --version`) |
| Install method | `uv tool install specify-cli` (pre-installed; exact source to be pinned — see below) |
| Initialization | `specify init --here --force --integration claude --script sh` |
| Integration | `claude` (skills mode, installed to `.claude/skills/speckit-*/SKILL.md`) |
| Invocation form | `/speckit-<name>` (hyphen separator, per `.specify/integration.json`) |
| Feature numbering | `sequential` (`specs/NNN-short-name/`) |
| Active-feature tracking | `.specify/feature.json` (`feature_directory`), independent of git branch |
| Extension hooks | none (`.specify/extensions.yml` absent) — no automatic branch creation |

Available skills: constitution, specify, clarify, plan, checklist, tasks, analyze, implement,
converge, taskstoissues.

Reproducible pin (to apply when onboarding a new machine):
`uv tool install "specify-cli @ git+https://github.com/github/spec-kit.git@v0.14.0"`
— verify the tag exists upstream before relying on it (not verified offline on 2026-09-27).

Deviation from `PROJECT_SPEC.md` §15.1/§20: the spec assumed the Codex integration
(`$speckit-*`). The project owner chose Claude Code on 2026-09-27; see `docs/ASSUMPTIONS.md` A-001.

## Workstation (reference machine candidate, not yet qualified)

| Item | Value |
| --- | --- |
| OS | Ubuntu 22.04.5 LTS, Linux 6.8, x86-64 |
| CPU threads | 32 |
| RAM | 31 GiB |
| GPU | NVIDIA GeForce RTX 4070 Laptop GPU, 8188 MiB, driver 580.178.04 |
| Disk (repo filesystem) | 246 GiB, **14 GiB free (95 % used)** at time of recording |
| Ollama | 0.34.0 (snap) |
| Python | 3.12.14 available via uv; system default 3.13.13 (pyenv) |
| uv | 0.12.17 |
| Node.js | 20.20.2 |

Low free disk is a known risk for model acquisition and snapshot staging; `doctor` must report it.

## F001 locked dependencies (`uv.lock`, recorded 2026-09-27 after `uv sync --locked`)

| Package | Version | | Package | Version |
| --- | --- | --- | --- | --- |
| fastapi | 0.141.1 | | pytest | 9.1.1 |
| starlette | 1.7.0 | | pytest-cov | 7.1.0 |
| uvicorn | 0.54.0 | | ruff | 0.16.9 |
| pydantic | 2.13.5 | | mypy | 2.3.1 |
| pydantic-core | 2.46.5 | | types-pyyaml | 6.0.12.20260906 |
| typer | 0.27.2 | | pip-licenses | 5.5.5 |
| httpx | 0.28.1 | | click | 8.5.0 |
| pyyaml | 6.0.3 | | anyio | 4.15.1 |
| psutil | 7.2.2 | | h11 | 0.16.0 |

All 42 locked packages resolved and installed offline-reproducibly via `uv.lock`; versions match the
minimums recorded in `specs/001-foundation/research.md` R2 exactly (uv resolved to the latest
version satisfying each `>=` bound at lock time).

Real license check (`scripts/check_licenses.py`, 2026-09-28): all 39 packages the synced venv
actually installs (2 more, `s-core-docs-assistant` itself and `prettytable`/`shellingham`/`rich`/
`wcwidth`/`ast-serialize`/`librt`/`packaging`/`iniconfig`/`pluggy`/`pygments`/`markdown-it-py`/
`mdurl`/`mypy-extensions`/`typing-extensions`/`typing-inspection`/`coverage`/`pathspec`/`idna`/
`certifi`/`httpcore`/`annotated-types`/`annotated-doc`, brought in transitively or as dev-group
deps not listed in the table above) report MIT, BSD-2/3-Clause, Apache-2.0, MPL-2.0, ISC, or
PSF-2.0 — all on the allowlist. Zero entries needed in `config/license-exceptions.yaml`. Full list
in `THIRD_PARTY_NOTICES.md`.

## CI action pins (`.github/workflows/ci.yml`, resolved 2026-09-28)

| Action | Release tag | Commit SHA |
| --- | --- | --- |
| `actions/checkout` | v7.0.1 | `3d3c42e5aac5ba805825da76410c181273ba90b1` |
| `astral-sh/setup-uv` | v10.2.0 | `c18668ad3cf93ea998bef934396af7bb5c839dc7` |

Resolved via the GitHub API (`.../releases/latest` then `.../git/ref/tags/<tag>`) from this
workstation. Exercised in real GitHub Actions (run 36391821731, green, 2026-09-28); re-verify
these pins are still current before the next CI-affecting change if much time has passed.

## F002 dependency additions (`uv.lock`, recorded 2026-09-28)

| Package | Version | License | Purpose |
| --- | --- | --- | --- |
| docutils | 0.23 | Public Domain / BSD-2/3-Clause / PSF (GPL-3.0 only for `tools/editors/emacs/rst.el`, not in the wheel — reviewed exception, F002 research R3) | Hardened RST parsing |
| markdown-it-py | 4.2.0 | MIT (promoted from transitive to direct) | Markdown parsing |
| types-docutils (dev) | 0.23.0.20260923 | Apache-2.0 | Type stubs for `mypy --strict` |

`sources sync` additionally requires `git` ≥ 2.34 on PATH (workstation: 2.34.1).

## F003 dependency additions (`uv.lock`, recorded 2026-09-28)

| Package | Version | License | Purpose |
| --- | --- | --- | --- |
| numpy | 2.5.3 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 (all permissive; passes the license gate without an exception) | float32 vector files, validation, exact cosine (F004) |

Runtime facts used by F003 (measured 2026-09-28, F003 research R1): Ollama 0.34.0;
`nomic-embed-text:latest` context bound 2048 tokens, dimension 768, Apache-2.0; SQLite 3.53.1 with
FTS5 (Python stdlib `sqlite3`).
