# Research: F008 Quality Qualification and Release Evidence

Agent decisions (agent review), from master spec §13 and the F001–F007 code.

## R1 — Suite files and schema

**Decision**: `eval/suite/dev.yaml` (60) and `eval/suite/heldout.yaml` (40), plus
`eval/suite/heldout.freeze.json`. Primary categories and counts (dev/held-out): onboarding_build
15 (9/6), architecture_interfaces 15 (9/6), process_work_products 15 (9/6),
requirements_templates 15 (9/6), unsupported 20 (12/8; secondary tags `unanswerable`,
`missing_scope`, `conflicting`), adversarial 20 (12/8; tags `injection`, `fake_id`,
`presupposed_version`, `provenance`). Case fields: `id`, `category`, `tags`, `question`,
`expected_status` (`answered` | `partial` | `insufficient_evidence` | `clarification_needed` |
`safe_handling`), `expected_facts` (`fact`, `variants`, `required`), `evidence` (groups of F004
`Locator` alternatives; empty for unsupported/adversarial cases without evidence), `forbidden`
(case-insensitive substrings or `re:` regular expressions that must not appear in claims),
`review` (`status`: `unreviewed` | `agent_review` | `human_reviewed`, `reviewer`, `date`,
`notes`). The file level has `schema_version`, `split`, `written_against` (source revisions),
`review_status`.

**Rationale**: the categories map one-to-one to master §13.2 minimums; the proportional split
(3:2) makes stratification exact. The F004 `Locator` is reused so that recall and evidence overlap
are computed the same way as before. **Alternatives**: extending the existing F004/F005 files
(they lack facts and forbidden assertions, and have been used for tuning, so they cannot be
held-out).

## R2 — Authoring and freeze

**Decision**: the agent authors all 100 cases from the pinned active-snapshot sources (reading the
files, not the system's output). Development cases may reuse earlier questions; held-out
questions are new. `eval freeze --split heldout --reason TEXT` writes the manifest (SHA-256, case
count, date, reason, previous hash). A test compares the committed file with the manifest; a suite
run refuses a mismatching held-out file.

**Rationale**: master §13.2 says to freeze before tuning. The freeze is committed before the
first held-out run, so git history proves the order.

A later correction of a held-out case (for example after the reviewer finds a wrong gold location)
is allowed only through `eval freeze` with a reason. The manifest keeps the previous hash, and
every suite report records the freeze hash it ran against. Reports made against an earlier freeze
no longer satisfy gates (they are listed as stale).

## R3 — Suite harness

**Decision**: `eval suite --split dev|heldout [--runs N] [--snapshot ID]` runs retrieval
(top 10) and answering (`AnswerService`) for every case and reports:
- recall@10 over answerable cases (macro);
- status agreement;
- safe handling (unsupported + adversarial cases whose expected status is `safe_handling` or
  non-answered);
- false abstention (answerable cases returned `insufficient_evidence`/`clarification_needed`);
- citation integrity (F005 `citation_intact`);
- automated forbidden-assertion hits;
- evidence overlap;
- latency per case.

Each run writes a report and a review sheet; with `--runs 3`, a combined report adds per-metric
min/max/spread. Server logs are captured during the run and scanned for question text (privacy
evidence, FR-012).

## R4 — Rubric and review import

**Decision**: `docs/quality/review-rubric.md` defines the judgements (FR-004). The review sheet
(YAML) has, per case: the question, status, expected facts (each with `judgement: null`), claims
(with a stable `claim_id` = SHA-256 of the case ID and text, cited excerpts, `judgement: null`,
`note`), automated forbidden hits, and top-level `reviewer: null`, `reviewed_on: null`.
`eval review import --sheet FILE --report RUN.json` validates the run reference and the claim IDs
and writes `human-review-<utc>.json`:
- support precision = supported / (supported + partially + unsupported), where partial counts as
  unsupported for precision (strict), per category;
- required-fact coverage = covered / required facts (partly = 0.5), macro-averaged over
  answerable cases.

A sheet without `reviewer` and `reviewed_on` is rejected. Import records the counts of unreviewed
items.

Of the three held-out runs, **run 1** is the one sent for human review (its sheet is the one
generated for review). Runs 2 and 3 provide the automated metrics and the run-to-run variation that
master §13.3 asks for; reviewing 120 answers is not required for the gate. The human review
records which run it judged.

## R5 — Synthetic adversarial suite

**Decision**: `eval/hostile/` holds SYNTHETIC documents (forged instructions, fake citation text
such as "[E9] confirms certification", malicious `javascript:`/`https://evil.example` links,
breakout markup, fake SYSTEM/policy notices, a command-execution request, a fake requirement
record) and `eval/hostile/cases.yaml` (≥ 10 questions). `eval adversarial` builds a temporary
snapshot from them with the production build pipeline and the real embedding model (a throwaway
data directory; the real catalog is never touched), then asks each question with the real model.
Automated judges per answer:
- `followed_instruction` (claim text matches the injected payload markers);
- `policy_disclosed` (policy phrases appear in claims);
- `url` (any URL in claims);
- `fabricated_citation` (cites an ID not in its citations, impossible by validation but checked);
- `command_as_advice` (the F005 `reads_as_advice` on suspicious evidence).

Any failure = critical. It extends and supersedes `answers-injection.yaml` for the gate; the old
file stays for the F005 test.

## R6 — Offline check (AT-01, A-032)

**Decision**: `scripts/offline_check.sh` runs `unshare -rn` and, inside the namespace:
1. `ip link set lo up`;
2. an egress probe (DNS lookup of github.com and a TCP connect to 1.1.1.1:443; both must fail);
3. a private `ollama serve` with `OLLAMA_MODELS=<installed models dir>`, `OLLAMA_NOPRUNE=1`,
   `OLLAMA_HOST=127.0.0.1:11434`, reading the installed models (read-only for the unprivileged
   user);
4. `score-assistant serve`;
5. `python -m score_docs_assistant.qualification.offline`, which checks over loopback HTTP:
   readiness; `GET /` (UI assets); an SSE ask for a covered question with ≥ 1 citation; the
   citation excerpt via `/api/v1/citations`; search; the export fields present in the envelope
   (export is client-side and uses only envelope fields, F006); the model digest matching the
   lock.

It writes `data/reports/offline-<utc>.json`; the log is scanned for question text. The runtime
binary and models directory are auto-detected (snap path first) or given by environment variables.
If `unshare -rn` fails, it writes a `not run` report with the reason.

## R7 — Performance

**Decision**: `eval performance --cases eval/suite/dev.yaml --cases eval/suite/heldout.yaml`
uses the distinct questions (100):
- warm-up: 3 queries;
- warm: lexical search, hybrid search, answer with first-progress timing for each query (answers
  on the first 50 distinct questions to bound runtime);
- cold: 5 samples, each preceded by unloading both models through the local API (`keep_alive: 0`
  on `/api/generate` and `/api/embed`);
- cancellation: 3 samples, cancel after the `generating` event, time until the queue slot is free;
- memory: `nvidia-smi --query-gpu=memory.used,memory.total` sampled around the run when present,
  `/api/ps` `size_vram` per model, and the process's peak RSS (`resource.getrusage`).

Budgets per master §13.4 are marked `pass`/`fail`; a sample below 50 is `fail (insufficient
sample)`. The first progress event is timed in-process, from the call until the service emits its
first progress event. The HTTP framing adds only local overhead, which the F006 smoke tests
already showed; this is stated in the report.

## R8 — Gates and release report

**Decision**: `eval/release-gates.yaml` declares each gate: `id`, `title`, `target`, `kind`
(`deterministic` | `real_model` | `human` | `measurement`), `critical`, and `evidence` (one of:
`report: <glob>` with a field path and comparator, `tests: [pytest node IDs or ids-substring]`
checked in the latest JUnit XML, or `manual: <reason>` for blocked/deferred items). `release
report` reads the latest file for each glob in `data/reports/` (suite runs, human reviews,
adversarial, offline, performance, comparison, exact-ids, pytest/vitest JUnit XML, traceability,
model qualification), evaluates every gate, and writes `data/reports/release-<utc>/report.md`
and `report.json`. Evidence counts only if it matches the current release identity: the active
snapshot ID, the locked model digests and, for held-out gates, the current freeze hash. Otherwise
the gate is `not run (stale evidence: …)`. The Markdown has sections: Verdict; Gates (table); Deterministic tests;
Real-model runs; Human reviews; Measurements; Unresolved limitations (open rows of
`docs/ASSUMPTIONS.md` and gates that are not pass). Verdict: `ready` only when every required gate
is pass; otherwise `blocked`, with the list of reasons.

**Rationale**: a declarative gate file makes the mapping reviewable and prevents hand-typed
values. **Alternatives**: hard-coding gates in Python (less reviewable).

## R9 — Traceability checker

**Decision**: `scripts/check_traceability.py` extracts requirement IDs from master spec §4 tables
(`| XXX-NNN |` rows for LOC/SRC/RET/ANS/UX/SEC/OPS/PUB), parses `docs/TRACEABILITY.md` rows
(including ranges such as `ANS-001 – ANS-012`), and checks:
- every local ID is covered exactly once;
- every row has a status;
- backticked paths in the Implementation and Tests columns exist (resolved from the repository
  root, `src/score_docs_assistant/` or `frontend/`);
- PUB requirements are in a deferred row.

It exits non-zero with a list; a pytest test wraps it and CI runs it.

## R10 — Model qualification

**Decision**: `models qualify` reads `data/model-lock.json` and, per model, calls the local
runtime's `/api/show` (license text, `model_info` context length, family, parameter size,
quantization) and `/api/version`. It writes `data/reports/models-<utc>.json` with the license's
first line/SPDX guess plus the full text in a sidecar file, and the digest check against the lock.
The release report links the model rows to the suite and performance results. No pull.
