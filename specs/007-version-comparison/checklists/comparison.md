# Comparison Semantics, Isolation & Safety Requirements Quality Checklist: F007

**Purpose**: Unit-test the *requirements* (spec, plan, research, contracts) for snapshot
comparison: version isolation, missing-coverage semantics, metadata honesty, and the generation
budget/execution rules.
**Created**: 2026-09-29
**Feature**: [spec.md](../spec.md)
**Depth**: Standard, reviewer (PR) audience; focus chosen by the agent per the owner's autonomy
instruction.
**Reviewer**: agent review (Claude Opus 5.5), not a human approval.

## Requirement Completeness

- [x] CHK001 Is it specified how every difference ID resolves to evidence of exactly one side?
  [Completeness, FR-004, data-model.md Difference/ComparisonEvidence invariants]
- [x] CHK002 Is the prompt budget for two evidence sets specified (split, reduction, warnings)?
  [Gap → resolved: research R2 "Budget" added in this review]
- [x] CHK003 Is the source of every `not_established` reason specified, and is it independent of
  model output? [Completeness, research R4]
- [x] CHK004 Is behaviour specified for a side with no evidence, a side with extractive fallback,
  and a failed comparison step? [Completeness, Edge Cases, FR-008]
- [x] CHK005 Is the snapshot metadata comparison defined for sources present on one side only
  and for processing identity differences? [Completeness, FR-009, research R5a]
- [x] CHK006 Are the UI defaults and the fewer-than-two-snapshots state specified? [Gap →
  resolved: FR-018 amended in this review]
- [x] CHK007 Is the baseline snapshot procedure specified so that it cannot disturb the active
  snapshot or the current lock? [Completeness, research R9, quickstart §0]

## Requirement Clarity

- [x] CHK008 Are `changed` and `conflicting` distinguishable by a stated rule, and is it stated
  that neither implies which side is newer? [Gap → resolved: FR-007 and the comparison policy
  amended in this review]
- [x] CHK009 Is the forbidden deletion/addition wording defined as a testable list, not "no
  deletion claims"? [Clarity, research R3]
- [x] CHK010 Is the scope of the no-deletion rule clear (differences only, not side answers that
  quote documentation)? [Gap → resolved: FR-006 amended in this review]
- [x] CHK011 Is "release label" defined precisely enough to test that none is inferred?
  [Clarity, research R6, SnapshotDiff.release_label always null]

## Requirement Consistency

- [x] CHK012 Are master §10.1's four difference types and envelope structure used unchanged in
  the spec, data model and contracts? [Consistency]
- [x] CHK013 Is the queue/slot rule consistent with F005 (one active generation, shared bounded
  queue, 429)? [Consistency, FR-013, research R8]
- [x] CHK014 Is the existing `compare` readiness mode reused rather than adding a new capability
  name? [Consistency, contracts/http-api.md — `modes.compare` exists since F001 as
  `not_implemented`]
- [x] CHK015 Is the immutable-link rule for older revisions consistent with F005's "exact lock
  revision" rule? [Consistency, research R7 keeps the exact (source, revision) requirement]

## Scenario & Edge Case Coverage

- [x] CHK016 Are identical-revision snapshots covered, including that no `changed` may be shown
  without differing evidence? [Coverage, US3 AS2, research R3 `CHANGED_WITHOUT_DIFFERENCE`]
- [x] CHK017 Is activation or retirement during a comparison covered? [Coverage, US1 AS4, FR-002]
- [x] CHK018 Is prompt injection in either side's evidence covered for the comparison step?
  [Coverage, Edge Cases, research R3 `INJECTION_SUSPECTED`]
- [x] CHK019 Are export-only requirement records without an excerpt covered? [Coverage, research
  R5b `record_without_excerpt`]

## Measurability

- [x] CHK020 Are isolation and deletion-claim outcomes measurable as counts that must be zero?
  [Measurability, SC-001, SC-002, research R10]
- [x] CHK021 Is the benchmark composition specified (≥ 10 cases, category minimums)?
  [Measurability, FR-020]
- [x] CHK022 Is the performance target relative to a measured baseline rather than an absolute
  number that was never measured? [Measurability, SC-006]

## Notes

- 4 gaps were found and resolved in the spec/research/contracts during this review (CHK002,
  CHK006, CHK008, CHK010).
