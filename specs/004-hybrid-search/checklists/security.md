# Isolation & Untrusted-Query Requirements Quality Checklist: F004

**Purpose**: Unit-test the *requirements* (spec, plan, research, contracts) for snapshot isolation,
safe handling of user queries and identifiers, bounded work, and honest result semantics.
**Created**: 2026-09-28
**Feature**: [spec.md](../spec.md)
**Depth**: Standard, reviewer (PR) audience; focus chosen by the agent per the owner's autonomy
instruction.
**Reviewer**: agent review (Claude Opus 5.5), not a human approval.

## Requirement Completeness

- [x] CHK001 Is binding of every request type (search, lookup, relationships, citations, sources) to exactly one snapshot specified? [Completeness, Spec FR-013, research R5]
- [x] CHK002 Are the searchable snapshot states enumerated, including what happens for the others? [Completeness, Clarification Q1, Edge Cases]
- [x] CHK003 Is filter-before-rank specified for every retrieval path, not only keyword? [Completeness, FR-008, research R2/R3]
- [x] CHK004 Are all degraded-mode triggers enumerated with reason codes? [Completeness, FR-014]
- [x] CHK005 Is the treatment of full-text operators and punctuation in queries specified? [Completeness, FR-007, Edge Cases, research R2]
- [x] CHK006 Are identifiers taken from requests (snapshot ID, chunk ID, entity key) validated before any filesystem or database use? [Gap → resolved: research R6 identifier validation incl. the F003 pin-before-check path, data-model SearchRequest, added in this review]
- [x] CHK007 Is the amount of keyword work bounded for long queries? [Gap → resolved: research R2 64-term cap, added in this review]

## Requirement Clarity

- [x] CHK008 Is "exact match" distinguished from alias matching, and is fuzzy matching excluded? [Clarity, FR-001, FR-002]
- [x] CHK009 Is duplicate-ID ordering defined without inventing authority between sources? [Clarity, FR-003 as amended by research R1]
- [x] CHK010 Is the meaning of any numeric ranking value stated, with forbidden labels named? [Clarity, FR-011, SC-007, contracts/http-api.md]
- [x] CHK011 Are result, excerpt, candidate, relationship and concurrency bounds quantified? [Clarity, FR-009/010, Clarifications Q4/Q5, data-model config]

## Requirement Consistency

- [x] CHK012 Do the spec, contracts and master spec §10.1 agree on HTTP status codes and the error envelope? [Consistency, FR-016, contracts/http-api.md]
- [x] CHK013 Is readiness for search consistent between FR-015, research R7 and the F003 behaviour it replaces? [Consistency]
- [x] CHK014 Are CLI exit codes consistent with F001–F003? [Consistency, contracts/cli.md]

## Scenario & Edge Case Coverage

- [x] CHK015 Is activation (or retention) during an in-flight request covered? [Coverage, US2 AS4, Edge Cases, research R5]
- [x] CHK016 Is failure of the query embedding mid-request covered, with an outcome other than an error? [Coverage, Edge Cases, FR-014]
- [x] CHK017 Are empty, whitespace-only, over-long and operator-only queries covered? [Coverage, Edge Cases]
- [x] CHK018 Are unknown filter values specified to fail rather than silently return nothing? [Coverage, Edge Cases]
- [x] CHK019 Is the no-active-snapshot case specified for both CLI and API? [Coverage, Edge Cases]

## Non-Functional / Security & Privacy

- [x] CHK020 Is logging of query and result bodies prohibited? [Privacy, FR-018, constitution VIII]
- [x] CHK021 Is protection against cross-origin calls to the costly search endpoint specified? [Security, FR-018, research R6]
- [x] CHK022 Are excerpts required to be plain text with no link fetching or rendering? [Security, Edge Cases, research R9]
- [x] CHK023 Are latency targets measurable, with the measurement method and its limits stated? [Measurability, SC-004, research R8]

## Dependencies & Assumptions

- [x] CHK024 Is the query-embedding convention measured rather than assumed? [Assumption, research R3]
- [x] CHK025 Is it explicit that agent-authored evaluation cases are not release evidence? [Assumption, FR-022, SC-005, constitution VII]

## Notes

- Resolutions made in this review (agent review, 2026-09-28): CHK006 identifier validation at the
  edge and inside `FileSnapshotStore.pin()` (closes a latent path-construction issue in F003's pin
  helper once request-supplied IDs reach it); CHK007 64-term cap for keyword queries.
- Result: 25/25 items pass after resolutions (agent review).
