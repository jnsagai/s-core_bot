# Feature backlog

Source: `docs/PROJECT_SPEC.md` §16. States: planned → specified → planned-ready → in-progress →
verified → done (or blocked/deferred). A feature is `done` only when its definition of done
(constitution, Development Workflow) is met with recorded evidence.

| Feature | Directory | Depends on | Milestone | State | Evidence |
| --- | --- | --- | --- | --- | --- |
| F001 Foundation and local runtime contract | `specs/001-foundation/` | — | M0 | **done** (all 63 tasks implemented and verified — 127 tests passed, 2 skipped by design; `/speckit-converge` reports 0 findings; real CI run, real `models pull`, and real stop/restart of Ollama all confirmed by project owner 2026-09-28; no open scenarios) | `specs/001-foundation/verification.md` |
| F002 Source registry and safe normalization | `specs/002-source-ingestion/` | F001 | M1 | planned-ready (spec, clarify, plan, checklists, 60 tasks, analyze complete; implementation not started) | `specs/002-source-ingestion/` |
| F003 Immutable snapshots and local embedding index | `specs/003-snapshot-index/` | F001, F002 | M1 | planned | — |
| F004 Evidence search and exact-ID navigation | `specs/004-hybrid-search/` | F003 | M1 | planned | — |
| F005 Grounded local answers | `specs/005-grounded-chat/` | F004 | M2 | planned | — |
| F006 Local web experience and privacy | `specs/006-local-web-ui/` | F005 | M2 | planned | — |
| F007 Explicit snapshot comparison | `specs/007-version-comparison/` | F005, F006 | M3 | planned | — |
| F008 Quality qualification and release evidence | `specs/008-quality-qualification/` | F007 (eval tooling starts F002–F005) | M3 | planned | — |
| F009 Portable local release and hosting preparation | `specs/009-portable-deployment/` | F008 | M4 | planned | — |
| F010 Public hosting profile | `specs/010-public-hosting/` | F009 | M5 | **deferred** until a public-hosting decision | — |

## Release gates

- **M0**: F001 done. **M1**: F002–F004. **M2**: F005–F006 (labelled experimental).
- **M3**: F007–F008. **M4 / local v1.0**: F009 plus §18.3 gate. **M5**: F010 plus §18.4 gate.
