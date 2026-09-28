# Answer Safety, Untrusted Input & Bounded Operation Requirements Quality Checklist: F005

**Purpose**: Unit-test the *requirements* (spec, plan, research, contracts) for grounded answers:
citation integrity, handling of untrusted evidence/history/model output, abstention, and bounded
resource use.
**Created**: 2026-09-28
**Feature**: [spec.md](../spec.md)
**Depth**: Standard, reviewer (PR) audience; focus chosen by the agent per the owner's autonomy
instruction.
**Reviewer**: agent review (Claude Opus 5.5), not a human approval.

## Requirement Completeness

- [x] CHK001 Is every source of untrusted text (evidence, history, model output) identified with its handling rule? [Completeness, FR-005, FR-011, FR-016, research R3/R4]
- [x] CHK002 Are all validation rules for model output enumerated with stable codes? [Completeness, FR-007, contracts/answer-schema.md]
- [x] CHK003 Is the outcome after a failed repair fully specified (fallback vs typed failure)? [Completeness, FR-008, Clarification Q1, research R5]
- [x] CHK004 Is the no-evidence path specified without a model call? [Completeness, FR-009]
- [x] CHK005 Are the model identity and "no fallback provider" requirements specified with the failure behaviour? [Completeness, FR-014]
- [x] CHK006 Is it specified which text the quote-consistency check compares against, given that evidence is escaped for the prompt? [Gap → resolved: research R3, added in this review]
- [x] CHK007 Is escaping of history, not only evidence, specified? [Gap → resolved: research R3, added in this review]
- [x] CHK008 Is the size of raw model output bounded before parsing? [Gap → resolved: research R4 64 KiB cap, added in this review]
- [x] CHK009 Is SSE framing protected against injection of event fields by document or model text? [Gap → resolved: research R8 single-line JSON, added in this review]
- [x] CHK010 Is the interaction between the repair attempt and the remaining deadline specified? [Gap → resolved: research R7 15-second minimum, added in this review]

## Requirement Clarity

- [x] CHK011 Are the claim kinds and the status/claim consistency rules unambiguous? [Clarity, FR-003, research R4]
- [x] CHK012 Is "immutable upstream link" defined, including when none is given? [Clarity, FR-004, research R6]
- [x] CHK013 Are the context budgets quantified, along with the order of reductions? [Clarity, FR-012, research R2]
- [x] CHK014 Are admission limits (active, queued) and the busy response quantified? [Clarity, FR-018]

## Requirement Consistency

- [x] CHK015 Do the error codes and HTTP statuses agree across the spec, the data model and the HTTP contract? [Consistency, contracts/http-api.md]
- [x] CHK016 Is readiness for chat consistent with F004's search readiness (independent capabilities)? [Consistency, FR-023, research R10]
- [x] CHK017 Is retrieval degradation kept separate from answer status everywhere? [Consistency, FR-002, Edge Cases]

## Scenario & Edge Case Coverage

- [x] CHK018 Are conflicting evidence, hostile instructions and certification/approval questions covered by acceptance scenarios? [Coverage, US2 AS5/AS6/AS8]
- [x] CHK019 Are cancellation, deadline and queue-full scenarios covered with timing bounds? [Coverage, US3 AS3/AS5/AS6, SC-005]
- [x] CHK020 Is a snapshot change during a conversation, and during generation, covered? [Coverage, FR-017, Edge Cases]
- [x] CHK021 Are output-length overrun and hidden-thought content covered? [Coverage, Edge Cases, contracts/answer-schema.md]

## Non-Functional / Privacy & Security

- [x] CHK022 Is logging of question, history and answer text prohibited for chat? [Privacy, FR-022, OPS-001]
- [x] CHK023 Is the absence of tools/function calling stated as a requirement, not only in prose? [Security, FR-010, constitution V]
- [x] CHK024 Is the blocked-egress verification specified, including an honest fallback if the environment cannot isolate loopback? [Measurability, SC-007, quickstart F]

## Dependencies & Assumptions

- [x] CHK025 Are runtime capabilities (structured output, thinking control) measured rather than assumed? [Assumption, research R1]
- [x] CHK026 Is it explicit that quality thresholds are F008 gates and that human-judged metrics remain "not run" until reviewed? [Assumption, SC-006, FR-025, constitution VII]

## Notes

- Resolutions made in this review (agent review, 2026-09-28): CHK006/CHK007 escaping and quote
  comparison; CHK008 raw-output cap; CHK009 single-line SSE data; CHK010 repair-time floor.
- Result: 26/26 items pass after resolutions (agent review).
