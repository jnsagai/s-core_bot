# Quickstart / Validation Guide: F002

Demonstrates F002 from a known state (F001 installed, `uv sync --locked` done). Expected output
shapes are in [contracts/cli.md](contracts/cli.md) and
[contracts/normalized-output.md](contracts/normalized-output.md).

## Prerequisites

- `git` ≥ 2.34 on PATH (only for scenario B). Network to `github.com` and
  `eclipse-score.github.io` for scenario B only.
- ~50 MB free under `data/` (sources are small; see research.md R1).

## A. Deterministic checks (no network)

```bash
uv run ruff format --check . && uv run ruff check . && uv run mypy src
uv run pytest                           # includes hostile git fixtures over file://
uv run python scripts/check_licenses.py # docutils passes only via its reviewed exception
```

## B. Validate and sync the real registry (uses network)

```bash
uv run score-assistant sources validate --config config/sources.yaml; echo "exit=$?"   # 0
time uv run score-assistant sources sync --config config/sources.yaml --json
python3 -m json.tool data/source-lock.json | head -40
```

Expected: both git sources `ok` with 40-hex `revision`, `revision_status: pinned`,
`release_mapping: null`, LICENSE and NOTICE under `notice_files`; both exports `ok` (or `failed`
without failing the sync, since they are optional) with `revision_status: unverified`. Record the
resolved SHAs and wall time (SC-005).

## C. Inspect offline

```bash
time uv run score-assistant sources inspect --lock data/source-lock.json
uv run score-assistant sources inspect --lock data/source-lock.json --json > /tmp/cov.json
uv run score-assistant sources inspect --lock data/source-lock.json --output /tmp/norm1
uv run score-assistant sources inspect --lock data/source-lock.json --output /tmp/norm2
cmp /tmp/norm1/documents.jsonl /tmp/norm2/documents.jsonl && cmp /tmp/norm1/entities.jsonl /tmp/norm2/entities.jsonl && echo IDENTICAL
```

Check: every source satisfies `selected == included + partial + failed` (SC-002); record the `ambiguous`
count (expected 0 for today's two sources — research R1 correction); zero entities with `need_id` containing `<` (template examples
in code blocks, SC-007); `requires_review` lists the CC-BY-SA-4.0 files in `score-process`;
export entities all `unverified` (SC-006); `IDENTICAL` printed (SC-004); wall time < 2 min.

## D. Offline guarantee

```bash
# With network disabled (e.g. unplug / airplane mode), inspect must still succeed:
uv run score-assistant sources inspect --lock data/source-lock.json; echo "exit=$?"   # 0
```

## E. Failure safety

```bash
cp data/source-lock.json /tmp/lock.before
cp config/sources.yaml /tmp/sources-broken.yaml
sed -i 's#eclipse-score/score.git#eclipse-score/does-not-exist-xyz.git#' /tmp/sources-broken.yaml
uv run score-assistant sources sync --config /tmp/sources-broken.yaml; echo "exit=$?"   # 1
cmp data/source-lock.json /tmp/lock.before && echo LOCK-UNCHANGED
ls data/staging 2>/dev/null | wc -l   # 0
```

## Recording

Record commands, SHAs, counts, timings and any "not run" items with reasons in
`specs/002-source-ingestion/verification.md`.
