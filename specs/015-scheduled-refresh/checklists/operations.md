# Operations Requirements Quality Checklist: F011 Scheduled Corpus Refresh

**Purpose**: Unit tests for the requirements on unattended activation safety, network and serve-path
boundaries, file accumulation, concurrency and observability.
**Created**: 2026-10-02
**Feature**: [spec.md](../spec.md) · [plan.md](../plan.md)
**Depth/Audience**: standard, PR reviewer. Agent review (not an approval); generated autonomously
(no interactive questions, defaults applied).

## Unattended activation safety

- [x] CHK001 - Is every condition under which a new snapshot may become active enumerated? [Completeness, Spec §FR-006, §FR-007]
- [x] CHK002 - Are the gate thresholds quantified (coverage drop fraction, exact-ID "all first")? [Clarity, Spec §FR-006]
- [x] CHK003 - Is the fate of a candidate that fails the gate specified (kept `validated`, manually activatable)? [Completeness, Spec §US2-AS5, §FR-007]
- [x] CHK004 - Is the rule against downgrading a semantic active snapshot consistent between the gate, the build mode and the edge cases? [Consistency, Spec §FR-006, §FR-016, Edge Cases]
- [x] CHK005 - Is the behaviour defined when the active snapshot changes between gate and activation? [Edge Case, data-model.md state transitions]
- [x] CHK006 - Is retention's deletion of unactivated snapshots on auto-activation called out as a consequence the operator must know? [Assumption, Spec Edge Cases]
- [x] CHK007 - Is auto-activation explicitly distinguished from engineering approval? [Consistency, Constitution XII, Spec Assumptions]

## Network and serve-path boundaries

- [x] CHK008 - Is it unambiguous that `serve` never refreshes or contacts upstream? [Clarity, Spec §FR-012]
- [x] CHK009 - Are the hosts, redirects and timeouts the upstream check may use bounded by the same rules as sync? [Completeness, Spec §FR-002]
- [x] CHK010 - Is "operator-invoked" interpreted for the timer case and recorded as a decision? [Assumption, Spec Assumptions, A-057]
- [x] CHK011 - Is the absence of any automatic installation or enabling of the timer stated? [Completeness, Spec §FR-013, §US3-AS1]
- [x] CHK012 - Is the rejected webhook/real-time alternative documented with its reason? [Gap→resolved, Spec Assumptions, research R6]

## File accumulation

- [x] CHK013 - Is "creates no files" for an unchanged run defined precisely (which file may change)? [Measurability, Spec §FR-010, §SC-002]
- [x] CHK014 - Is the lock/archive non-rewrite on an unchanged sync specified? [Completeness, Spec §FR-004]
- [x] CHK015 - Is growth of snapshots and source revisions on changed runs bounded by an existing rule? [Coverage, Spec Edge Cases (retention)]

## Concurrency

- [x] CHK016 - Are overlap outcomes defined for refresh-vs-refresh and refresh-vs-manual build/activation? [Coverage, Spec §FR-009, Edge Cases]
- [x] CHK017 - Is in-flight request isolation during activation specified and measurable? [Measurability, Spec §US1-AS3, §SC-004]
- [x] CHK018 - Is it specified that `busy` leaves even the state file untouched? [Clarity, contracts/cli.md Guarantees]

## Failure and recovery

- [x] CHK019 - Are failure outcomes defined for check errors, sync failures, build errors, disk exhaustion and an invalid state file? [Coverage, Spec Edge Cases, §US2-AS4]
- [x] CHK020 - Is recovery after an interrupted build specified by reference to existing behaviour? [Dependency, Spec Edge Cases]
- [x] CHK021 - Is the needs-export lag scenario resolved without ambiguity? [Clarity, Spec Clarifications Q5, Edge Cases]

## Observability

- [x] CHK022 - Are the outcome set and exit codes complete and mutually exclusive? [Completeness, Spec §FR-008]
- [x] CHK023 - Is the `doctor` severity mapping for each refresh state defined, including "never fails doctor"? [Clarity, Spec §FR-011, contracts/state-file.md]
- [x] CHK024 - Are output privacy rules (no document text) stated for refresh output and state? [Completeness, Spec §FR-014]
- [x] CHK025 - Is the freshness bound measurable (interval + build time)? [Measurability, Spec §SC-001]

## Notes

- Iteration 1 found three gaps (timeouts/allowlist for the check, disk exhaustion, invalid state
  file); the spec was amended (FR-002, Edge Cases) before marking CHK009 and CHK019.
