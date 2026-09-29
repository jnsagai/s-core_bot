# Release gates file (`eval/release-gates.yaml`)

```yaml
schema_version: 1
gates:
  - id: recall_at_10
    title: Evidence recall@10 (held-out, answerable)
    target: ">= 0.90"
    kind: real_model            # deterministic | real_model | human | measurement
    critical: false
    evidence:
      report: "suite-heldout-*-combined.json"
      field: "runs[*].metrics.recall_at_10.value"   # every run must meet the target
      compare: ">= 0.90"
  - id: support_precision
    kind: human
    evidence: {report: "human-review-*.json", field: "support_precision.value", compare: ">= 0.95"}
  - id: at_12_concurrent_activation
    kind: deterministic
    evidence: {tests: ["test_activation_mid_generation", "test_activation_mid_comparison"]}
  - id: public_profile
    kind: deterministic
    evidence: {manual: "deferred to F010 (public hosting)"}
```

Evaluation: a missing report → `not run`; a human gate without a human review → `blocked —
awaiting human review`; `manual` → `blocked` with the text (or `not run` for deferrals marked so);
a `tests` gate passes only when every listed test is present and passed in the latest JUnit XML
(any skipped → `not run`, any failed → `fail`). A report whose labels include "development
measurement" can satisfy only gates whose `accept_development: true`.
