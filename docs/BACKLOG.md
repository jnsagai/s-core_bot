# Feature backlog

Source: `docs/PROJECT_SPEC.md` §16. States: planned → specified → planned-ready → in-progress →
verified → done (or blocked/deferred). A feature is `done` only when its definition of done
(constitution, Development Workflow) is met with recorded evidence.

| Feature | Directory | Depends on | Milestone | State | Evidence |
| --- | --- | --- | --- | --- | --- |
| F001 Foundation and local runtime contract | `specs/001-foundation/` | — | M0 | planned-ready (spec, plan, tasks, analyze complete; implementation not started) | `specs/001-foundation/` |
| F002 Source registry and safe normalization | `specs/002-source-ingestion/` | F001 | M1 | planned | — |
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
