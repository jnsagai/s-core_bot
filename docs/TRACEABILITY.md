# Requirements traceability

One row per normative requirement from `docs/PROJECT_SPEC.md` §4. Many-to-many mapping is
allowed; no requirement may be dropped. Status: open → implemented → verified (with evidence).
"Feature FR" is the requirement ID inside the owning feature's `spec.md`.

| Req | Owning feature(s) | Feature FR | Tasks | Implementation | Tests / evaluation | Evidence | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| LOC-001 | F001, F009 | F001 FR-001, FR-002 | F001 tasks.md | — | — | — | open |
| LOC-002 | F005, F009 | — | — | — | — | — | open |
| LOC-003 | F001 (install, acquire-models, serve), F002 (sync-sources), F003 (build-index), F009 | F001 FR-003, FR-004, FR-023 | F001 tasks.md | — | — | — | open |
| LOC-004 | F001, F009 | F001 FR-010, FR-011, FR-020 | F001 tasks.md | — | — | — | open |
| LOC-005 | F001, F009 | F001 FR-005–FR-008, FR-022, FR-024 | F001 tasks.md | — | — | — | open |
| LOC-006 | F004 (F001 reports readiness) | F001 FR-009 | F001 tasks.md | — | — | — | open |
| LOC-007 | F001, F009 | F001 FR-018 | F001 tasks.md | — | — | — | open |
| SRC-001 | F002 | — | — | — | — | — | open |
| SRC-002 | F002 | — | — | — | — | — | open |
| SRC-003 | F002, F007 | — | — | — | — | — | open |
| SRC-004 | F002 | — | — | — | — | — | open |
| SRC-005 | F002 | — | — | — | — | — | open |
| SRC-006 | F002 | — | — | — | — | — | open |
| SRC-007 | F002 | — | — | — | — | — | open |
| SRC-008 | F002 | — | — | — | — | — | open |
| SRC-009 | F003 | — | — | — | — | — | open |
| SRC-010 | F002, F003 | — | — | — | — | — | open |
| SRC-011 | F002, F003 | — | — | — | — | — | open |
| SRC-012 | F002 (F001 notices framework) | F001 FR-017 | F001 tasks.md | — | — | — | open |
| RET-001 | F004 | — | — | — | — | — | open |
| RET-002 | F004 | — | — | — | — | — | open |
| RET-003 | F004 | — | — | — | — | — | open |
| RET-004 | F004 | — | — | — | — | — | open |
| RET-005 | F005 | — | — | — | — | — | open |
| RET-006 | F007 | — | — | — | — | — | open |
| RET-007 | F003 | — | — | — | — | — | open |
| RET-008 | F004 | — | — | — | — | — | open |
| ANS-001 – ANS-012 | F005 (ANS-005, ANS-007 also F007) | — | — | — | — | — | open |
| UX-001 – UX-005 | F006 | — | — | — | — | — | open |
| SEC-001 | F005, F009 | — | — | — | — | — | open |
| SEC-002 | F006, F009 | — | — | — | — | — | open |
| SEC-003 | F006, F009 | — | — | — | — | — | open |
| SEC-004 | F001, F009 | F001 FR-012–FR-014 | F001 tasks.md | — | — | — | open |
| SEC-005 | F002, F009 | — | — | — | — | — | open |
| OPS-001 | F006, F009 | — | — | — | — | — | open |
| OPS-002 | F003, F009 | — | — | — | — | — | open |
| OPS-003 | F003, F009 | — | — | — | — | — | open |
| OPS-004 | F001, F009 | F001 FR-015, FR-016 | F001 tasks.md | — | — | — | open |
| OPS-005 | F001, F009 | F001 FR-017, FR-019 | F001 tasks.md | — | — | — | open |
| OPS-006 | F005, F009 | — | — | — | — | — | open |
| PUB-001 – PUB-008 | F010 (deferred) | — | — | — | — | — | open (deferred) |

Grouped rows (ANS, UX, PUB) are expanded to one row per ID when their owning feature is specified.
