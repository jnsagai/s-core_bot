# Research: F007 Explicit Snapshot Comparison

Decisions made by the agent (agent review) from the spec clarifications, the master spec §10.1 and
the F003–F006 code. Each lists the alternatives considered.

## R1 — Pipeline: per-side answers, then one comparison step

**Decision**: `ComparisonService` pins both snapshots, takes one generation slot, and runs the
F005 pipeline once per side (`AnswerService.answer_in_slot`, a refactor that separates the slot
from the flow). Then one comparison model call runs over both sides' packed evidence under
side-namespaced IDs, followed by validation, at most one repair, and otherwise deterministic
differences only.

**Rationale**: master §10.1 wants `left`/`right` as ordinary envelopes; reusing the validated
pipeline keeps every F005 guarantee (policy, injection handling, citations from provenance). The
comparison step never writes into either envelope, so no envelope can mix versions.

**Alternatives**: a single model call producing both answers and the differences (fewer calls,
but one draft would mix versions and need a new validator for everything); a deterministic-only
text diff of retrieved chunks (cannot say what changed in meaning, and ranking noise looks like
change).

## R2 — Comparison evidence and namespacing

**Decision**: each side contributes the evidence items its own answer prompt used (cited items
first), at most `comparison.evidence_items_per_side` (default 5), re-labelled `L1…`/`R1…`,
inside `<left_evidence snapshot="…">` and `<right_evidence snapshot="…">` blocks, escaped exactly
like F005. The comparison result carries `evidence.left` and `evidence.right` citation lists
(built from stored provenance, each with its own `snapshot_id`); every difference ID resolves into
exactly one of them.

**Budget**: the comparison prompt uses the F005 budget arithmetic. Available evidence tokens are
`min(generation.evidence_tokens, context − output − policy − question − margin)`, split evenly
between the sides. Each side keeps whole excerpts in its order (cited first, then rank) until its
half is used, and a side may use what the other leaves unused. Dropped items are reported as
`comparison_evidence_reduced: left N, right M`. Nothing is cut mid-text.

**Alternatives**: re-running retrieval with a joint query (a second retrieval with different
results from the answers the user sees would be confusing); passing only cited items (a side whose
answer is `insufficient_evidence` would have nothing to compare).

## R3 — Validation rules for differences

**Decision**: schema (type enum, statement ≤ `max_claim_characters`, ID patterns `^L[0-9]{1,2}$` /
`^R[0-9]{1,2}$`, ≤ `comparison.max_differences`); per-side membership (`L` IDs only in
`left_evidence_ids` and existing, likewise `R`); `changed`/`unchanged`/`conflicting` need ≥ 1 ID on
each side; `not_established` needs IDs on exactly one side; `changed` is rejected when every cited
left excerpt is text-identical to a cited right excerpt (`CHANGED_WITHOUT_DIFFERENCE`); forbidden
wording (`DELETION_CLAIM`: removed/removal, deleted/deletion, dropped, no longer, was/were/has
been/have been added, newly added, discontinued, eliminated); plus F005's URL, hidden-thought,
quote-in-evidence and injection-advice checks. Any error triggers the single repair; a second
failure drops all model differences, and a warning is added.

**Rationale**: AT-17 and FR-006 need a hard guarantee, not a prompt request. The wording check is
deliberately broad; a false rejection only costs a repair or a deterministic fallback, whereas a
false deletion claim is the harm this feature must prevent.

**Alternatives**: letting the model state absence with a softer word ("not present"), which is
still an absence claim, so absence is always typed `not_established` instead.

## R4 — Coverage reasons are server-derived

**Decision**: for every `not_established` difference (model or deterministic), the server derives
the reason from the manifests: the other side's snapshot lacks the source (`source_absent`); the
source failed or is partial there (`source_failed` / `source_partial`); for records, the ID is not
in the other snapshot's records (`record_not_found`); or it was simply not found in retrieved
evidence (`not_retrieved`). The model never supplies the reason.

## R5 — Deterministic comparisons

**Decision**:
(a) `SnapshotDiff` from both manifests: per-source relation (`same`/`different`/`left_only`/
`right_only`), revisions, revision status, source status; processing identity differences
(chunker version/config hash, embedding model tag/digest, corpus schema); warnings
`identical_revisions`, `source_only_on_one_side`, `unverified_revision`, `source_not_ok`.
(b) Exact records: requirement-ID tokens in the question are matched on each side's
`EntityIndex`. The fingerprint is the record's type, title, status, options, and the text of the
first chunk. Path and line changes are reported in the statement but never count as a change on
their own. Both sides present and equal → `unchanged`; different → `changed` (the statement names
the differing fields); one side only → `not_established` (`record_not_found`, or `source_absent`
when the other snapshot lacks the source). A record needs an excerpt on both sides to be cited as
`changed`/`unchanged`; otherwise it is `not_established` (`record_without_excerpt`). Record chunks
are appended to the side evidence lists with the next `L`/`R` numbers.

**Alternatives**: comparing chunk content hashes across snapshots to find unchanged documents
(useful later, but ranking-independent document diffing is beyond F007's question-driven scope).

## R6 — Release labels (SRC-003)

**Decision**: no release label is inferred or displayed. Identity is the per-source revisions. The
UI and CLI state "No release label: per-source revisions identify each snapshot". Published needs
exports stay `unverified` (A-014) and are flagged in the diff.

## R7 — Links for older revisions

**Decision**: `sources sync` also archives every lock it writes to
`data/source-locks/<lock_sha256>.json`, and `SourceLinks` reads the current lock plus archived
locks, still requiring an exact (source, revision) match on a pinned git source. Citations from an
older baseline snapshot therefore get immutable links to the revision they came from. Snapshots
built before this change use the current lock only (unchanged behaviour).

**Alternatives**: deriving links from `config/sources.yaml` repository URLs (the registry can change
after a snapshot was built, so the link would not be proven).

## R8 — Execution, deadline, streaming

**Decision**: the identity check happens first (fail fast with `GENERATION_UNAVAILABLE`), then the
snapshots are pinned (404/409), then one queue slot is held for the whole request with
`comparison.deadline_seconds` (default 240 = 2 × 120). SSE events: `progress` `{stage, side?}`
(`queued` with position, `searching`/`generating`/`validating` with side, `comparing`),
`comparison`, `error`, `done`. The disconnect watcher is the same as chat.

## R9 — Baseline snapshot for the benchmark

**Decision**: pick an older commit of each git source (about 3–4 months before the current one,
chosen by the first-parent history of `main`) and write `config/sources-baseline.yaml` with the
refs pinned to those SHAs, without the needs exports (they exist only for `main`). Back up
`data/source-lock.json`, run `sources sync --config config/sources-baseline.yaml`, move the
resulting lock to `data/source-lock-baseline.json`, restore the backup, and run
`index build --source-lock data/source-lock-baseline.json` without `--activate`. Retention runs
only on activation or rollback (checked in `storage/lifecycle.py`), so building deletes nothing.
A later activation may retire and delete the baseline (retention 2); it can be rebuilt with the
same commands.

## R10 — Evaluation

**Decision**: `eval/comparison-dev.yaml` (`reviewed: false`), with ≥ 10 cases authored from the
two real snapshots: changed topics, unchanged topics, missing coverage (topics only in the newer
process description, and requirement IDs whose export source is absent in the baseline), and an
exact-ID case. Each case gives `expected_type` and optional `acceptable_types`. Metrics: type
agreement (the expected type is among the observed types), side-isolation violations, citation
integrity (every difference ID resolves on its side; every citation's snapshot matches its side),
deletion-claim count over all difference statements, per-case timing. The report goes to
`data/reports/comparison-<utc>.json` and is labelled "development measurement, not release
evidence".
