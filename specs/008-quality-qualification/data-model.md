# Data Model: F008

Pydantic models in `qualification/` (domain records free of FastAPI/Ollama types).

## SuiteCase / SuiteFile (`eval/suite/*.yaml`)

| Field | Type | Rules |
| --- | --- | --- |
| id | str | unique across both files; `dev-NNN` / `ho-NNN` |
| category | `onboarding_build` \| `architecture_interfaces` \| `process_work_products` \| `requirements_templates` \| `unsupported` \| `adversarial` | |
| tags | list[str] | secondary tags (R1) |
| question | str | 1..4000 characters |
| expected_status | `answered` \| `partial` \| `insufficient_evidence` \| `clarification_needed` \| `safe_handling` | |
| expected_facts | list[{fact, variants: list[str], required: bool}] | ≥ 1 for answered/partial |
| evidence | list[list[Locator]] | ≥ 1 group for answered/partial |
| forbidden | list[str] | substring or `re:<regex>` |
| review | {status, reviewer?, date?, notes?} | `human_reviewed` requires reviewer and date |

File: `schema_version: 1`, `split: dev|heldout`, `review_status`, `written_against`, `cases`.
Suite validation: 100 cases in total; category minimums; stratification ± 1; IDs unique across
files.

## FreezeManifest (`eval/suite/heldout.freeze.json`)

`file`, `sha256`, `cases`, `frozen_on` (date), `reason`, `previous_sha256` (nullable).

## SuiteCaseResult / SuiteRunReport

Per case: `id`, `category`, `tags`, `expected_status`, `status`, `status_ok`, `answerable`,
`safe_ok` (nullable), `false_abstention` (nullable), `recall_at_10` (nullable),
`citation_integrity`, `forbidden_hits: list[str]`, `evidence_overlap` (nullable), `origin`,
`latency_ms`, `claims: int`.
Report: `split`, `run`, `snapshot_id`, `model`, `case_file_sha256`, `freeze_ok`, `labels`,
`metrics` (named `Ratio`/float values with numerator/denominator), `by_category`, `cases`,
`privacy` (`log_bytes_scanned`, `question_text_found`), `created_at`.
Combined: `runs: list[metrics]`, `spread: {metric: {min, max}}`.

## ReviewSheet / HumanReview

Sheet: `run_reference` (report file name + SHA-256), `reviewer`, `reviewed_on`, `cases[]`
{`id`, `question`, `status`, `facts[]` {`fact`, `required`, `judgement`}, `claims[]`
{`claim_id`, `text`, `kind`, `citations[]`, `judgement`, `note`}, `forbidden_hits`}.
HumanReview: `reviewer`, `reviewed_on`, `run_reference`, `support_precision` (Ratio + per
category), `required_fact_coverage` (value, n, per category), `unreviewed_claims`,
`unreviewed_facts`.

## Gate / ReleaseReport

Gate: `id`, `title`, `target`, `kind`, `critical`, `status` (`pass` | `fail` | `blocked` |
`not run`), `value` (text), `evidence_file` (nullable), `reason`.
ReleaseReport: `created_at`, `app_version`, `models`, `snapshot_id`, `gates`, `verdict`
(`ready` | `blocked`), `blocking`, `limitations`, `sections`.

## Adversarial, offline, performance, model records

`AdversarialReport` (cases, failures by kind, per-case judgements), `OfflineReport` (steps with
ok/detail, egress probe results, `status`), `PerformanceReport` (samples and percentiles per
operation, warm/cold, memory, budgets), `ModelQualification` (role, tag, digest, lock_match,
runtime version, license summary/path, context length, details).
