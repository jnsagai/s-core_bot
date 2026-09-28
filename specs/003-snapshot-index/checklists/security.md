# Snapshot Integrity, Isolation & Untrusted Bundle Requirements Quality Checklist: F003

**Purpose**: Unit-test the *requirements* (spec, plan, research, contracts) for snapshot
integrity, reader isolation, crash safety, and handling of untrusted bundles before task
generation.
**Created**: 2026-09-28
**Feature**: [spec.md](../spec.md)
**Depth**: Standard, reviewer (PR) audience. Focus was chosen by the agent from the request
(integrity/isolation, untrusted bundle input); no questions were asked, per the owner's autonomy
instruction.
**Reviewer**: agent review (Claude Opus 5.5), not a human approval. Evidence cited per item.

## Requirement Completeness

- [x] CHK001 Are all states and allowed transitions of a snapshot specified, including which states can never become active? [Completeness, Spec FR-011, FR-013, data-model state machine]
- [x] CHK002 Is every interruption point of a build enumerated, with the required outcome for the active snapshot and pointer? [Completeness, Spec US1 AS6, FR-011, research R7]
- [x] CHK003 Is the recovery of orphaned staging data and stale `building` rows specified, including who performs it and when? [Completeness, FR-011, research R7 step 2]
- [x] CHK004 Is the crash window between moving the staged directory and committing the publish transaction addressed? [Completeness, research R7 step 2: dirs of `failed` rows removed]
- [x] CHK005 Are requirements defined for insufficient disk before a build starts, not only for disk-full mid-write? [Gap → resolved: research R7 step 1 `DISK_INSUFFICIENT`, added in this review]
- [x] CHK006 Is every artifact that validation must check listed (checksums, unlisted files, schema, FTS, vector shape, finiteness, norm, row map, counts)? [Completeness, FR-016, research R9]
- [x] CHK007 Are requirements defined that stop an imported corpus from carrying extra schema objects (triggers, views) that execute on read? [Gap → resolved: research R9 exact `sqlite_master` match + R4 hardening pragmas, added in this review]
- [x] CHK008 Are all bundle entry types and path forms that must be rejected enumerated? [Completeness, FR-020, contracts/bundle.md rules table]
- [x] CHK009 Is the behavior for importing a snapshot ID that already exists specified? [Gap → resolved: contracts/bundle.md "Existing snapshot ID", added in this review]
- [x] CHK010 Is the license-review gate on export specified, including what gets recorded? [Completeness, FR-018, US3 AS4, contracts/bundle.md `license_acknowledgement`]

## Requirement Clarity

- [x] CHK011 Is "pinned" defined precisely: its scope (cross-process), its lifetime, and its release on crash? [Clarity, FR-014, clarification Q1, research R8]
- [x] CHK012 Is the rollback target defined unambiguously, including behavior after two consecutive rollbacks? [Clarity, FR-013, clarification Q4, research R7]
- [x] CHK013 Are "integrity failure" and "semantic disabled/unverified" distinguished, with distinct exit codes? [Clarity, FR-016, clarification Q2, data-model ValidationReport]
- [x] CHK014 Are the bundle caps quantified, and are their defaults stated? [Clarity, FR-020, clarification Q3, config `bundles.*`]
- [x] CHK015 Is "never silently truncate" made concrete for the embedding runtime, whose default does truncate? [Clarity, FR-007, research R1 `truncate:false`]
- [x] CHK016 Is the conservative token estimate named, defined and bounded, with its limits against adversarial text stated honestly? [Clarity, FR-003, research R2]

## Requirement Consistency

- [x] CHK017 Do the spec, contracts/cli.md and F001 agree on exit codes 0/1/2/130 for all new commands? [Consistency, FR-022, contracts/cli.md header]
- [x] CHK018 Do the plan and the catalog contract agree on which commands take the single-writer lock? [Consistency → resolved: contracts/cli.md `snapshots activate` now states `BUILD_BUSY`, matching contracts/catalog.md]
- [x] CHK019 Is "only validated/retired can become active" stated consistently in the spec, data model and CLI contract? [Consistency, FR-013, US2 AS1, data-model, contracts/cli.md]
- [x] CHK020 Is the network statement consistent: loopback embedding only in build, identity-only in validate and activate, none in bundles? [Consistency, FR-022, contracts/cli.md help lines, quickstart G]

## Acceptance Criteria Quality

- [x] CHK021 Are the isolation outcomes (SC-004, SC-008) stated as 100 % of enumerated cases, so they can be measured? [Measurability, Spec SC-004, SC-008]
- [x] CHK022 Is export→import equality defined over concrete identities (file hashes, chunk IDs, entity keys)? [Measurability, SC-006]

## Scenario & Edge Case Coverage

- [x] CHK023 Are recovery requirements defined for a crash during retention (partially deleted snapshot)? [Gap → resolved: research R12 deletion order and completion, added in this review]
- [x] CHK024 Is the race between a reader resolving the active ID and pinning it addressed? [Coverage, research R8, contracts/catalog.md pin protocol]
- [x] CHK025 Are the corrupted-catalog and newer-schema cases specified without automatic repair? [Coverage → resolved: contracts/catalog.md "never recreated or repaired automatically", added; FR-017]
- [x] CHK026 Is decompression work bounded during the pre-extraction scan of a bundle? [Edge Case → resolved: contracts/bundle.md scanning aborts at cap, added in this review]
- [x] CHK027 Are tampering after validation and tampering during activation or rollback covered? [Coverage, Edge Cases "files modified after validation", FR-013]

## Non-Functional / Threat Model

- [x] CHK028 Is the trust boundary for local snapshot files documented, i.e. what 0444 plus verification-at-activation protects against and what it does not? [Gap → resolved: research R13 added in this review]
- [x] CHK029 Is deserialization of corpus data restricted to non-executable formats (raw float32, JSON, SQLite without extensions)? [Security, constitution Tech constraints, research R4, R5]
- [x] CHK030 Are logging requirements for builds free of chunk or document text? [Privacy, plan Constitution VIII]

## Dependencies & Assumptions

- [x] CHK031 Are the runtime facts the design depends on (context bound, dimension, truncation default, prefix) measured rather than assumed? [Assumption, Spec Assumptions, research R1]
- [x] CHK032 Is the new NumPy dependency justified against the constitution and scheduled for the license gate? [Dependency, plan Technical Context, quickstart A]

## Notes

- Resolutions made in this review (agent review, 2026-09-28): CHK005 build disk precheck
  (research R7); CHK007 exact corpus schema match and SQLite hardening pragmas (research R4, R9);
  CHK009 import ID collision (contracts/bundle.md); CHK018 activation holds the ingest lock
  (contracts/cli.md); CHK023 retention crash recovery (research R12); CHK025 no automatic catalog
  repair (contracts/catalog.md); CHK026 bounded scan (contracts/bundle.md); CHK028 threat boundary
  (research R13). The plan's verification table was extended to cover each.
- Result: 32/32 items pass after resolutions (agent review).
