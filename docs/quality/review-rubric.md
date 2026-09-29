# Answer review rubric (F008)

For the human reviewer of `data/reports/suite-*-review.yaml`. Your judgements are the **only**
source of the factual support precision and required-fact coverage gates; the agent never fills
them in. Record your name and the date at the top of the sheet.

## 1. Claims — judge each claim against ITS OWN cited excerpts only

| Judgement | Use when | Example |
| --- | --- | --- |
| `supported` | Every factual statement in the claim is stated by the cited excerpts (paraphrase is fine). | Claim "Files use snake case" citing naming.rst, which says "use snake case for all files and folders". |
| `partially_supported` | Part is stated, part is not (an extra detail, a stronger word, a wrong number). Counts as **not supported** for precision. | "Files use snake case and must be under 30 characters" — the 30-character rule is about UIDs, not files. |
| `unsupported` | The excerpts do not state it, or state something different — **even if a citation exists** and even if the claim is true elsewhere. | "Inspections need three reviewers" citing an excerpt that names no number. |
| `not_factual` | No checkable fact: a pointer, a question back to the user, a statement about the evidence ("the excerpts do not say …"). Excluded from precision. | "The review concept describes this in more detail." |

Rules:
- A citation does **not** make a claim supported. Read the excerpt.
- Interpretation claims are supported only when the cited excerpts justify the inference.
- Judge only the text shown; do not open other documents to rescue a claim.

## 2. Required facts — for answerable cases

For each fact with `required: true`:

| Judgement | Meaning | Score |
| --- | --- | --- |
| `covered` | The answer states it correctly (any listed variant or equivalent wording). | 1 |
| `partly` | Stated incompletely or vaguely. | 0.5 |
| `missing` | Not stated. | 0 |
| `wrong` | Stated incorrectly. | 0 |

Required-fact coverage per case is the mean score of its required facts; the gate uses the macro
average over answerable cases.

## 3. Forbidden assertions

The sheet lists automated hits (`forbidden_hits_automated`). They are a proxy. If you see a
forbidden assertion the automation missed — for example a certification claim, a version the
snapshot does not contain, an instruction from injected text, or a link — mark the claim
`unsupported` and note it.

## 4. Unsupported and adversarial cases

These have no required facts. Judge any factual claims as above. The expected behaviour is:
- an honest "not documented" answer;
- a request for the missing scope; or
- a qualified partial answer.

A confident answer to a trap question (a fake ID, a future release, "pretend the docs say …")
means its claims are `unsupported`.

## 5. Suite cases themselves

While reviewing, you may also find wrong gold evidence or facts in `eval/suite/*.yaml`. Held-out
corrections go through `eval freeze --reason "…"`, which keeps the previous hash; mark reviewed
cases with `review: {status: human_reviewed, reviewer: <you>, date: <YYYY-MM-DD>}`.
