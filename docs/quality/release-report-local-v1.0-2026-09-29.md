# Release report

Generated 2026-09-29 17:26 UTC by `release report` (app 0.1.0).
Active snapshot `20260928T140548Z-7c6a05b3`, locked generation model digest `0edcdef34593…`, held-out freeze `frozen on 2026-09-29`.

## Verdict: **blocked**

Blocking items:

- recall_at_10: blocked — suite cases unreviewed (development measurement)
- support_precision: blocked — awaiting human review (no imported review sheet)
- required_fact_coverage: blocked — awaiting human review (no imported review sheet)
- safe_handling: blocked — suite cases unreviewed (development measurement)
- false_abstention: blocked — suite cases unreviewed (development measurement)
- reviewed_suite: blocked — awaiting human review: all 100 cases are agent-authored and unreviewed (eval/suite/*.yaml)
- screen_reader: blocked — awaiting a person with a screen reader; automated real-browser checks pass (browser_automated)

Statuses: `pass` (evidence meets the target), `fail`, `blocked` (a required input is
missing, for example a human review), `not run` (no current evidence). No gate passes
without an evidence file; nothing here is an approval.

## Gates

| Gate | Title | Target | Measured | Status | Evidence kind | Evidence | Reason |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `recall_at_10` | Evidence recall@10, held-out answerable cases, every run | >= 90% | 0.962, 0.962, 0.962 | blocked | real_model | suite-heldout-20260929T170034Z-combined.json | suite cases unreviewed (development measurement) |
| `exact_id_retrieval` (critical) | Exact-ID retrieval, every requirement ID in the active snapshot | 100% correct first | len [0] | pass | real_model | exact-ids-20260928T140548Z-7c6a05b3-20260929T124242Z.json | failures len == 0 |
| `citation_integrity` (critical) | Citation integrity on held-out answers, every run | 100% | 1.000, 1.000, 1.000 | pass | real_model | suite-heldout-20260929T170034Z-combined.json | runs[*].citation_integrity.value == 1.0 |
| `support_precision` | Factual support precision (human-reviewed held-out answers) | >= 95% | — | blocked | human | — | awaiting human review (no imported review sheet) |
| `required_fact_coverage` | Required-fact coverage (human-reviewed held-out answers) | >= 85% macro | — | blocked | human | — | awaiting human review (no imported review sheet) |
| `safe_handling` | Safe handling of unsupported and adversarial held-out cases, every run | >= 95% | 1.000, 1.000, 1.000 | blocked | real_model | suite-heldout-20260929T170034Z-combined.json | suite cases unreviewed (development measurement) |
| `false_abstention` | False abstention on answerable held-out cases, every run | <= 10% | 0.000, 0.000, 0.000 | blocked | real_model | suite-heldout-20260929T170034Z-combined.json | suite cases unreviewed (development measurement) |
| `snapshot_isolation` (critical) | Snapshot isolation (single-snapshot and comparison) | zero failures | 3/3 tests passed | pass | deterministic | pytest-20260929T172250Z.xml | all listed tests passed |
| `comparison_isolation_real` (critical) | Comparison isolation and deletion claims on the real benchmark | 0 violations, 0 deletion claims | 0 | pass | real_model | comparison-20260929T165447Z.json | isolation_violations == 0 |
| `injection_resistance` (critical) | Injection resistance, synthetic adversarial suite (real model) | zero failures | 0 | pass | real_model | adversarial-20260929T172026Z.json | failures == 0 |
| `offline_operation` (critical) | Chat/search/evidence/export with external egress blocked | pass | pass | pass | real_model | offline-fresh-20260929T171824Z.json | status == pass |
| `operational_recovery` | Failed update leaves service intact; rollback and restore succeed | pass | 4/4 tests passed | pass | deterministic | pytest-20260929T172250Z.xml | all listed tests passed |
| `reviewed_suite` | Evaluation suite reviewed by a person | 100 cases human-reviewed | — | blocked | human | — | awaiting human review: all 100 cases are agent-authored and unreviewed (eval/suite/*.yaml) |
| `lexical_retrieval_p95` | Lexical retrieval p95 | <= 500 ms | pass | pass | measurement | performance-20260929T124231Z.json | budgets[name=lexical_retrieval].status == pass |
| `hybrid_retrieval_p95` | Hybrid retrieval p95, embedding model warm | <= 2 s | pass | pass | measurement | performance-20260929T124231Z.json | budgets[name=hybrid_retrieval_warm].status == pass |
| `first_progress` | First visible progress event p95 | <= 1 s | pass | pass | measurement | performance-20260929T124231Z.json | budgets[name=first_progress_warm].status == pass |
| `answer_p95` | Final validated answer p95, warm | <= 30 s | pass | pass | measurement | performance-20260929T124231Z.json | budgets[name=answer_warm].status == pass |
| `cancellation` | Cancellation releases queue/application resources | <= 2 s | pass | pass | measurement | performance-20260929T124231Z.json | budgets[name=cancellation_release].status == pass |
| `memory_recorded` | Peak GPU memory recorded (no OOM in the qualified profile) | recorded | present | pass | measurement | performance-20260929T124231Z.json | memory.gpu_peak present |
| `deterministic_suite` (critical) | Deterministic test suites (pytest + vitest) pass | 0 failed | 8/8 tests passed | pass | deterministic | pytest-20260929T172250Z.xml, vitest-20260929T172250Z.xml | all listed tests passed |
| `traceability` | Traceability complete for every local requirement | complete | complete | pass | deterministic | docs/TRACEABILITY.md | every local requirement mapped |
| `model_qualification` | Installed models match the model lock | all match | True, True | pass | real_model | models-20260929T122209Z.json | models[*].lock_match == true |
| `privacy_logs` | No question text in logs during held-out runs | 0 occurrences | 0 | pass | real_model | suite-heldout-20260929T170034Z-run1.json | privacy.question_text_found == 0 |
| `at_02_generation_unavailable` | AT-02: search works while generation is unavailable | pass | 2/2 tests passed | pass | deterministic | pytest-20260929T172250Z.xml | all listed tests passed |
| `at_08_embedding_change` | AT-08: changed embedding identity refused/degraded explicitly | pass | 2/2 tests passed | pass | deterministic | pytest-20260929T172250Z.xml | all listed tests passed |
| `at_09_fake_evidence_ids` | AT-09: fake evidence IDs rejected, repaired or fallen back | pass | 3/3 tests passed | pass | deterministic | pytest-20260929T172250Z.xml | all listed tests passed |
| `at_10_conflicts` | AT-10: conflicting excerpts surfaced without precedence | pass | 2/2 tests passed | pass | deterministic | pytest-20260929T172250Z.xml | all listed tests passed |
| `at_11_diagnostics` | AT-11: unsupported directives and includes keep diagnostics | pass | 2/2 tests passed | pass | deterministic | pytest-20260929T172250Z.xml | all listed tests passed |
| `at_12_concurrent_activation` | AT-12: citations stay on the request's snapshot during activation | pass | 2/2 tests passed | pass | deterministic | pytest-20260929T172250Z.xml | all listed tests passed |
| `at_13_deleted_content` | AT-13: deleted source content absent from the new snapshot | pass | 1/1 tests passed | pass | deterministic | pytest-20260929T172250Z.xml | all listed tests passed |
| `at_14_abort` | AT-14: browser abort cancels the job and admits the next | pass | 2/2 tests passed | pass | deterministic | pytest-20260929T172250Z.xml | all listed tests passed |
| `at_15_hostile_rendering` | AT-15: hostile Markdown/images inert in the UI | pass | 3/3 tests passed | pass | deterministic | vitest-20260929T172250Z.xml | all listed tests passed |
| `at_18_host_origin` (critical) | AT-18: hostile website calling localhost is rejected | pass | 3/3 tests passed | pass | deterministic | pytest-20260929T172250Z.xml | all listed tests passed |
| `browser_automated` | Real browser (headless Firefox): same-origin, CSP, axe incl. contrast, keyboard, ask → citation → Escape, storage, reload | pass | pass | pass | real_model | browser-20260929T171545Z.json | status == pass |
| `screen_reader` | Screen-reader use and human judgement of the UI | pass | — | blocked | human | — | awaiting a person with a screen reader; automated real-browser checks pass (browser_automated) |
| `container_loopback_private_runtime` (critical) | Containers: app published on 127.0.0.1 only, runtime without host port, hardened, cited answer | pass | pass | pass | real_model | container-20260929T171639Z.json | status == pass |
| `container_config_rules` (critical) | Container mode is the only, image-gated exception to the loopback rules | pass | 4/4 tests passed | pass | deterministic | pytest-20260929T172250Z.xml | all listed tests passed |
| `fresh_install_offline` | Fresh offline install from the prepared package reaches a cited answer | pass | pass | pass | real_model | fresh-install-20260929T171824Z.json | status == pass |
| `restore_keeps_citations` (critical) | Restored corpus keeps snapshot identity, chunks and citations | pass | pass | pass | real_model | restore-20260929T171824Z.json | status == pass |
| `contract_parity` | Same API contract natively and in containers | pass | pass | pass | real_model | contract-20260929T172133Z.json | status == pass |
| `sbom` | Release SBOM (CycloneDX) from the locks | present | 1.5 | pass | deterministic | sbom-20260929T172250Z.cdx.json | specVersion == 1.5 |
| `log_retention` | Logs are body-free, rotate, and keep at most seven days | pass | 1/1 tests passed | pass | deterministic | pytest-20260929T172250Z.xml | all listed tests passed |
| `operator_documents` | Runbooks, hardware matrix and known limitations present | present | 1/1 tests passed | pass | deterministic | pytest-20260929T172250Z.xml | all listed tests passed |
| `public_profile` (not required) | Public hosting profile (AT-19, AT-20, PUB-001–PUB-008) | deferred | — | not run | deterministic | — | deferred to F010 until a public-hosting decision |

## Deterministic tests and checks

- `pytest-20260929T172250Z.xml`: 1123 passed, 0 failed, 10 skipped (skipped = not run)
- `vitest-20260929T172250Z.xml`: 76 passed, 0 failed, 0 skipped (skipped = not run)

- `snapshot_isolation` — pass: 3/3 tests passed (all listed tests passed)
- `operational_recovery` — pass: 4/4 tests passed (all listed tests passed)
- `deterministic_suite` — pass: 8/8 tests passed (all listed tests passed)
- `traceability` — pass: complete (every local requirement mapped)
- `at_02_generation_unavailable` — pass: 2/2 tests passed (all listed tests passed)
- `at_08_embedding_change` — pass: 2/2 tests passed (all listed tests passed)
- `at_09_fake_evidence_ids` — pass: 3/3 tests passed (all listed tests passed)
- `at_10_conflicts` — pass: 2/2 tests passed (all listed tests passed)
- `at_11_diagnostics` — pass: 2/2 tests passed (all listed tests passed)
- `at_12_concurrent_activation` — pass: 2/2 tests passed (all listed tests passed)
- `at_13_deleted_content` — pass: 1/1 tests passed (all listed tests passed)
- `at_14_abort` — pass: 2/2 tests passed (all listed tests passed)
- `at_15_hostile_rendering` — pass: 3/3 tests passed (all listed tests passed)
- `at_18_host_origin` — pass: 3/3 tests passed (all listed tests passed)
- `container_config_rules` — pass: 4/4 tests passed (all listed tests passed)
- `sbom` — pass: 1.5 (specVersion == 1.5)
- `log_retention` — pass: 1/1 tests passed (all listed tests passed)
- `operator_documents` — pass: 1/1 tests passed (all listed tests passed)
- `public_profile` — not run: — (deferred to F010 until a public-hosting decision)

## Real-model runs

- `recall_at_10` — blocked: 0.962, 0.962, 0.962 (suite cases unreviewed (development measurement))
- `exact_id_retrieval` — pass: len [0] (failures len == 0)
- `citation_integrity` — pass: 1.000, 1.000, 1.000 (runs[*].citation_integrity.value == 1.0)
- `safe_handling` — blocked: 1.000, 1.000, 1.000 (suite cases unreviewed (development measurement))
- `false_abstention` — blocked: 0.000, 0.000, 0.000 (suite cases unreviewed (development measurement))
- `comparison_isolation_real` — pass: 0 (isolation_violations == 0)
- `injection_resistance` — pass: 0 (failures == 0)
- `offline_operation` — pass: pass (status == pass)
- `model_qualification` — pass: True, True (models[*].lock_match == true)
- `privacy_logs` — pass: 0 (privacy.question_text_found == 0)
- `browser_automated` — pass: pass (status == pass)
- `container_loopback_private_runtime` — pass: pass (status == pass)
- `fresh_install_offline` — pass: pass (status == pass)
- `restore_keeps_citations` — pass: pass (status == pass)
- `contract_parity` — pass: pass (status == pass)

## Human reviews

- `support_precision` — blocked: — (awaiting human review (no imported review sheet))
- `required_fact_coverage` — blocked: — (awaiting human review (no imported review sheet))
- `reviewed_suite` — blocked: — (awaiting human review: all 100 cases are agent-authored and unreviewed (eval/suite/*.yaml))
- `screen_reader` — blocked: — (awaiting a person with a screen reader; automated real-browser checks pass (browser_automated))

## Measurements

- `lexical_retrieval_p95` — pass: pass (budgets[name=lexical_retrieval].status == pass)
- `hybrid_retrieval_p95` — pass: pass (budgets[name=hybrid_retrieval_warm].status == pass)
- `first_progress` — pass: pass (budgets[name=first_progress_warm].status == pass)
- `answer_p95` — pass: pass (budgets[name=answer_warm].status == pass)
- `cancellation` — pass: pass (budgets[name=cancellation_release].status == pass)
- `memory_recorded` — pass: present (memory.gpu_peak present)

## Unresolved limitations

- A-028: Development finding, not a decision: for template/guideline needs, the need-directive chunk holds only title and options while the template body follows in chunks without the entity key, so entity-key gold locations miss
- A-048: Reviewer items from the held-out runs (agent observation, not a review): ho-031 ("Is every S-CORE feature developed to the same ASIL?") is expected `safe_handling`, but the documentation may answer it (features range fro
- public_profile: deferred to F010 until a public-hosting decision
