# Data Model: F007

All records are Pydantic models in `domain/comparison.py` (frozen, independent of FastAPI/Ollama).

## ComparisonRequest

| Field | Type | Rules |
| --- | --- | --- |
| question | str | 1..`limits.question_characters` after strip |
| left_snapshot_id | str | valid snapshot ID format; queryable |
| right_snapshot_id | str | valid format; queryable; ≠ left |
| response_language | str | `"en"` only |

Unknown fields → 422. There is no `history` field (FR-015).

## Difference

| Field | Type | Rules |
| --- | --- | --- |
| type | `changed` \| `unchanged` \| `conflicting` \| `not_established` | |
| statement | str | no removal/deletion/addition wording (R3) |
| left_evidence_ids | list[str] | each `L<n>` present in `evidence.left` |
| right_evidence_ids | list[str] | each `R<n>` present in `evidence.right` |
| origin | `model` \| `exact_record` \| `coverage` | |
| coverage_reason | `source_absent` \| `source_failed` \| `source_partial` \| `record_not_found` \| `record_without_excerpt` \| `not_retrieved` \| `no_evidence` \| null | required iff type is `not_established` |
| missing_side | `left` \| `right` \| `both` \| null | required iff type is `not_established` |

Invariants: `changed`/`unchanged`/`conflicting` → both ID lists non-empty. `not_established` → the
ID list of `missing_side` is empty.

## SourceRelation (row of SnapshotDiff)

`source_id`, `relation` (`same`/`different`/`left_only`/`right_only`), `left_revision`,
`right_revision`, `left_revision_status`, `right_revision_status`, `left_status`, `right_status`
(the side values are null when the source is absent on that side).

## SnapshotDiff

`left_snapshot_id`, `right_snapshot_id`, `left_created_at`, `right_created_at`, `sources:
list[SourceRelation]`, `processing: list[ProcessingDifference]` (`field`, `left`, `right`),
`release_label: None` (always null in F007, R6), `warnings: list[str]`.

## ComparisonEvidence

`left: list[Citation]`, `right: list[Citation]` — F005 `Citation` records whose `evidence_id` is
`L<n>`/`R<n>` and whose `snapshot_id` equals the side's snapshot.

## ComparisonResult

`schema_version: 1`, `request_id`, `question`, `left: AnswerEnvelope`, `right: AnswerEnvelope`,
`differences: list[Difference]`, `evidence: ComparisonEvidence`, `snapshots: SnapshotDiff`,
`model: GenerationIdentity | None`, `origin` (`model` \| `deterministic_only`), `warnings`,
`policy_version`, `timings_ms`.

Invariants (validated on construction): `left.snapshot_id == snapshots.left_snapshot_id`, same for
right; every citation in `left` and `evidence.left` has the left snapshot ID (same for right);
every difference ID resolves on its side.

## ComparisonConfig (`config/schema.py`, section `comparison`)

`deadline_seconds` (240, 1..7200), `evidence_items_per_side` (5, 1..20), `max_differences` (5,
1..30), `max_statement_characters` (600, 80..2000; the output schema allows one more character so a
grammar cut-off is always rejected; lowered after a real run in which the model
copied whole excerpts into statements and its output was cut off at the token limit).

## Evaluation records

`ComparisonCase` (`id`, `question`, `category` ∈ {changed, unchanged, missing_coverage,
exact_id, conflicting}, `expected_type`, `acceptable_types: list`), `ComparisonCaseFile`
(`reviewed: bool`, `left_snapshot`, `right_snapshot` optional defaults, `cases` ≥ 1; ≥ 10 enforced
for the committed file by a test), `ComparisonCaseResult`, `ComparisonReport` (metrics + labels).
