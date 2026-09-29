# Evidence Honesty & Gate Semantics Requirements Quality Checklist: F008

**Purpose**: Unit-test the *requirements* for F008: that no path can yield an unearned "pass",
that human, real-model, deterministic and measured evidence stay distinct, and that the suite and
gates are specified precisely enough to test.
**Created**: 2026-09-29
**Feature**: [spec.md](../spec.md)
**Reviewer**: agent review (Claude Opus 5.5), not a human approval.

## Completeness

- [x] CHK001 Is the status of every gate defined for missing, stale, development-only and failing
  evidence? [Completeness, FR-015, contracts/release-gates.md; stale → added in this review, R8]
- [x] CHK002 Is it specified which of the three held-out runs is sent for human review? [Gap →
  resolved: run 1, R4, in this review]
- [x] CHK003 Is the procedure for correcting a frozen held-out case specified, including what
  happens to earlier reports? [Gap → resolved: R2, in this review]
- [x] CHK004 Are all master §13.3 thresholds and local AT scenarios required in the report?
  [Completeness, SC-001]
- [x] CHK005 Is behaviour specified when the namespace, GPU tools or runtime are unavailable?
  [Completeness, Edge Cases]

## Clarity

- [x] CHK006 Are support precision and required-fact coverage defined with exact numerators and
  denominators, including how partial judgements count? [Clarity, R4]
- [x] CHK007 Is "blocked egress" defined by an observable probe rather than by assertion?
  [Clarity, FR-011, R6]
- [x] CHK008 Is the first-progress timing point defined? [Gap → resolved: in-process, R7]
- [x] CHK009 Is "development measurement" labelling defined by a rule rather than case by case?
  [Clarity, FR-008]

## Consistency

- [x] CHK010 Do the category minimums and the split add up exactly (100 = 60 + 40, stratified)?
  [Consistency, R1]
- [x] CHK011 Is the adversarial suite's relation to F005's `answers-injection.yaml` stated without
  breaking F005 tests? [Consistency, R5]
- [x] CHK012 Is evidence tied to the current release identity (snapshot, model digests, freeze
  hash)? [Gap → resolved: R8, in this review]

## Honesty safeguards

- [x] CHK013 Is it impossible by specification for the agent to produce a human review? [FR-006,
  clarification Q1]
- [x] CHK014 Is a critical failure specified to override averages? [FR-015, US1 AS4]
- [x] CHK015 Are forbidden-assertion hits presented as an automated proxy, not a replacement for
  human review? [R3, R4]

## Notes

- 4 gaps were found and resolved in research.md during this review (CHK001 stale, CHK002, CHK003,
  CHK008/CHK012).
