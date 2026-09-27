# Assumptions and outstanding decisions

Each entry: ID, decision, source/rationale, owner, status. "Agent-derived" means resolved by the
coding agent from `PROJECT_SPEC.md` without explicit project-owner confirmation.

| ID | Decision | Source / rationale | Owner | Status |
| --- | --- | --- | --- | --- |
| A-001 | Coding agent is Claude Code with Spec Kit `claude` integration, not Codex. `CLAUDE.md` is the agent guide; `AGENTS.md` points to it. | Project owner instruction, 2026-09-27 | Project owner | Resolved |
| A-002 | The existing repository `jnsagai/s-core_bot` is the independent repository described as `s-core-docs-assistant`. The product/package name remains `s-core-docs-assistant` / `score_docs_assistant`. | Repo already created by owner; spec §14 requires an independent repo, not a specific name | Project owner | Resolved — accepted by project owner 2026-09-27 |
| A-003 | Master spec file moved from repo root to `docs/PROJECT_SPEC.md`. | Spec §14, §20 | Agent | Resolved |
| A-004 | Python 3.12 is provided via uv-managed interpreter (3.12.14 present); system 3.13 is not used for the project. | Spec §1.2 | Agent | Resolved |
| A-005 | Apache-2.0 LICENSE already present in the repository is adopted for original code. Dependency/attribution review remains open (F001 sets up the notices framework). | Spec §1.2 | Project owner | Resolved — Apache-2.0 accepted by project owner 2026-09-27; dependency license gate still enforced by F001 T055–T057 |
| A-006 | F001 scope excludes the frontend; frontend tooling and lock are introduced in F006. CI's "frontend build" step is added when `frontend/` exists. | Spec §16 F001 scope lists backend skeleton only; F006 owns UI | Agent | Agent-derived |
| A-007 | Clarify/analyze phases for F001 were run autonomously by the agent at the owner's request ("without stopping"); every clarification is recorded in the feature spec with its master-spec reference. | Owner instruction 2026-09-27; spec §15.2 step 2 | Project owner | Resolved |
| A-008 | F001 guard rejects every request marked `Sec-Fetch-Site: cross-site`, including top-level navigations. F006 must decide whether top-level `GET` navigations (`Sec-Fetch-Mode: navigate`) to the UI page are allowed; API routes stay protected. | F001 analyze finding A6 | Agent → F006 spec | Open (F006) |
