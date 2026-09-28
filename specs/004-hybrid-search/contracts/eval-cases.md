# Contract: Retrieval Case File (F004)

`eval/retrieval-dev.yaml`, YAML parsed with `yaml.safe_load` into strict Pydantic models (unknown
keys rejected).

```yaml
schema_version: 1
review_status: "unreviewed (agent-authored)"   # or "reviewed by <role> on <date>" (F008)
written_against:                                # source revisions the gold locations refer to
  score-platform: e2373d822fc2f6e9a3f8a0538904f3faa39309ea
  score-process: 66321fe6bd131eae58fbd6395b0f0b92d63e00f5
cases:
  - id: onb-001
    category: onboarding_build        # onboarding_build | architecture_interfaces |
                                      # process_work_products | requirements_templates
    question: "How do I build the documentation locally?"
    expected:                         # list of evidence groups; each group is satisfied by any locator
      - - {source_id: score-platform, path: docs/…/doc_generation.rst}
      - - {entity_key: "score-process:gd_guidl__example"}
        - {source_id: score-process, path: process/…/x.rst, line_start: 10, line_end: 30}
    notes: "why these locations answer the question"
```

(Paths above are illustrative; the committed file contains real locations read from the pinned
sources.)

Rules: `id` values are unique; each case has ≥ 1 group and each group ≥ 1 locator; each locator has
either `entity_key` or (`source_id` and `path`); if `line_start` is given, `line_end ≥ line_start`.
Gold locations are chosen by reading the sources, never from the system's own search output.
Recall@10 of a case = satisfied groups / total groups among the top 10 results; the report
macro-averages over cases and per category, always with case counts.
