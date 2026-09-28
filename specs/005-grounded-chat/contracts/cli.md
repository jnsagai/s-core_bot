# CLI Contract: `ask`, `eval answers` (F005)

Exit codes: `0` an answer envelope was produced (any status, including fallback), `1` operational
failure (generation unavailable, deadline, no snapshot), `2` usage error, `130` interrupted.
Neither command downloads anything; network use is loopback to the local runtime only.

## `ask "QUESTION" [--snapshot ID] [--json] [--show-evidence]`

Help first line: **"Answers a question from one snapshot with the local model; cites stored
evidence (no downloads)."** Text output (claims rendered as plain text; `[E1]` markers; citations
listed with path:lines and immutable link when available):

```text
snapshot 20260928T140548Z-7c6a05b3  status answered  model qwen3:4b-instruct (0edcdef34593)
- The feature architecture is a required work product. [E1]
- (interpretation) … [E2]
limitations:
- …
citations:
[E1] score-process  process/…/architecture_workproducts.rst:31-44  (pinned)
     https://github.com/eclipse-score/process_description/blob/66321fe…/…#L31-L44
```

`--show-evidence` also prints each cited excerpt. `--json` prints the envelope. Warnings go to
stderr. A fallback prints `warning: model output failed validation; showing extractive excerpts`.

## `eval answers --cases FILE [--snapshot ID] [--review SHEET] [--json]`

Help first line: **"Runs answer cases against the local model and reports status, citation
integrity and evidence overlap; human-judged metrics need a filled review sheet."** It writes the
report to `data/reports/answers-<snapshot>-<utc>.json` and a review sheet to
`data/reports/answers-review-<utc>.yaml`. Exit 0 when the run completes (metrics are reported, not
gated). Exit 1 when generation is unavailable, and 2 for a malformed case file.
