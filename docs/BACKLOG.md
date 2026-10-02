# Feature backlog

Source: `docs/PROJECT_SPEC.md` §16. States: planned → specified → planned-ready → in-progress →
verified → done (or blocked/deferred). A feature is `done` only when its definition of done
(constitution, Development Workflow) is met with recorded evidence.

| Feature | Directory | Depends on | Milestone | State | Evidence |
| --- | --- | --- | --- | --- | --- |
| F001 Foundation and local runtime contract | `specs/001-foundation/` | — | M0 | **done** (all 63 tasks implemented and verified — 127 tests passed, 2 skipped by design; `/speckit-converge` reports 0 findings; real CI run, real `models pull`, and real stop/restart of Ollama all confirmed by project owner 2026-09-28; no open scenarios) | `specs/001-foundation/verification.md` |
| F002 Source registry and safe normalization | `specs/002-source-ingestion/` | F001 | M1 | **done** (65 tasks; 350 passed, 3 skipped opt-in; converge clean; real sync + inspect of both S-CORE sources with need-set parity to the official builds; docutils license exception accepted by owner 2026-09-28) | `specs/002-source-ingestion/verification.md` |
| F003 Immutable snapshots and local embedding index | `specs/003-snapshot-index/` | F001, F002 | M1 | **done** (62 tasks incl. 3 convergence; 570 passed, 6 skipped opt-in; converge clean) — real build of both sources: 5 658 chunks in 47 s, unchanged rebuild 9.9 s with full embedding reuse | `specs/003-snapshot-index/verification.md` |
| F004 Evidence search and exact-ID navigation | `specs/004-hybrid-search/` | F003 | M1 | **done** (41 tasks incl. 2 convergence; 728 passed, 7 skipped opt-in; converge clean) — real snapshot: exact-ID 2168/2168, recall@10 90.6 % on 32 unreviewed dev cases, p95 8.1 ms keyword / 111 ms hybrid | `specs/004-hybrid-search/verification.md` |
| F005 Grounded local answers | `specs/005-grounded-chat/` | F004 | M2 | **done** (36 tasks incl. 2 convergence; 858 passed, 9 skipped opt-in; converge clean) — real model: status agreement 18/18, unanswerable safely handled 5/5, citation integrity 18/18, evidence overlap 92.3 % (unreviewed dev cases); injection fixtures blocked | `specs/005-grounded-chat/verification.md` |
| F006 Local web experience and privacy | `specs/006-local-web-ui/` | F005 | M2 | **done** (39 tasks; 873 passed backend, 60 frontend; converge clean) — real-browser walkthrough open for the owner (A-040) | `specs/006-local-web-ui/verification.md` |
| F007 Explicit snapshot comparison | `specs/007-version-comparison/` | F005, F006 | M3 | **done** (33 tasks + amendment A (speed, A-054): SC-006 met, benchmark p50 13.1 s) — real baseline vs active: isolation violations 0, deletion claims 0, citation integrity 12/12, type agreement 9–10/12 on 12 unreviewed dev cases; SC-006 not met (3.5–3.9×, A-044); Compare-tab browser walkthrough open for the owner | `specs/007-version-comparison/verification.md` |
| F008 Quality qualification and release evidence | `specs/008-quality-qualification/` | F007 (eval tooling starts F002–F005) | M3 | **done** (26 tasks; converge clean; human review and browser checks open for the owner) — release report: 27 gates pass (incl. real blocked-egress run, 0/10 adversarial failures, all §13.4 budgets), 7 blocked awaiting human review/browser checks, public profile deferred | `specs/008-quality-qualification/verification.md` |
| F009 Portable local release and hosting preparation | `specs/009-portable-deployment/` | F008 | M4 | **done** (18 tasks; converge clean) — hardened image + Compose (app on 127.0.0.1 only, runtime without host port, internal network), offline fresh install + restore (50/50 chunks, 23/23 citations), native/container contract parity (10 endpoints), CycloneDX SBOM, runbooks; local v1.0 report: 36 pass, 7 blocked on human review/screen reader, public profile deferred | `specs/009-portable-deployment/verification.md` |
| F011 Scheduled corpus refresh | `specs/015-scheduled-refresh/` | F002, F003 | post-v1.0 (owner request 2026-10-02) | **done** (24 tasks incl. 1 convergence; converge clean; one-shot `refresh` with upstream check, promotion gate and opt-in systemd user timer) — real: upstream refresh activated in 24.5 s (exact-ID 2177/2177), unchanged rerun 2.0 s with only the state file changed, running `serve` followed activations without restart, overlap → busy; timer rendered and `systemd-analyze verify`ed, not enabled on the owner's machine | `specs/015-scheduled-refresh/verification.md` |
| F010 Public hosting profile | `specs/010-public-hosting/` | F009 | M5 | **deferred** until a public-hosting decision | — |

## Release gates

- **M0**: F001 done. **M1**: F002–F004. **M2**: F005–F006 (labelled experimental).
- **M3**: F007–F008. **M4 / local v1.0**: F009 plus §18.3 gate. **M5**: F010 plus §18.4 gate.
