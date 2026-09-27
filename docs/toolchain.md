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
