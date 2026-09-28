# Quickstart / Validation Guide: F003

Demonstrates F003 from a known state: F001 installed with models pulled (`data/model-lock.json`),
and F002 synced (`data/source-lock.json`, `data/sources/`). Expected output shapes are in
[contracts/cli.md](contracts/cli.md); file formats in
[contracts/snapshot-files.md](contracts/snapshot-files.md),
[contracts/catalog.md](contracts/catalog.md), [contracts/bundle.md](contracts/bundle.md).
`C=config/local.yaml` below.

## Prerequisites

- Ollama running on loopback with `nomic-embed-text` (scenarios B, C, E). No other network.
- Free disk: about 3× the snapshot size (active + previous + staging) plus bundle space; the build
  checks this. Record the real snapshot size.

## A. Deterministic checks (no network, no models)

```bash
uv run ruff format --check . && uv run ruff check . && uv run mypy src
uv run pytest                            # fake embedding provider; fixture locks
uv run python scripts/check_licenses.py  # numpy (BSD-3-Clause) must pass without exception
```

## B. Real build, determinism, and reuse

```bash
time uv run score-assistant --config $C index build --json > /tmp/b1.json      # SC-001 (< 15 min)
time uv run score-assistant --config $C index build --json > /tmp/b2.json      # SC-001 (< 2 min)
uv run score-assistant --config $C snapshots list
```

Expected: both `validated`. `b2.embedded.new == 0` and `reused == chunks`. Comparing the two
corpora' `chunks` tables (all columns except `rowid`) shows identical rows (SC-002):

```bash
for id in $(jq -r .snapshot_id /tmp/b1.json /tmp/b2.json); do
  uv run python -c "import sqlite3,sys,hashlib; c=sqlite3.connect(f'file:{sys.argv[1]}?mode=ro',uri=True); \
print(hashlib.sha256(repr(c.execute('select chunk_id,content_hash,embedding_input_hash,text from chunks order by rowid').fetchall()).encode()).hexdigest())" \
    "data/snapshots/$id/corpus.sqlite"
done   # two equal hashes (the sqlite3 CLI is not required)
```

A successful real build proves that every embedding input fit the runtime bound
(`truncate:false`, research R1/R2 → SC-003). Record chunk counts by kind and the maximum
`embedding_token_estimate`.

## C. Activate, pin, roll back, retention

```bash
A=$(jq -r .snapshot_id /tmp/b1.json); B=$(jq -r .snapshot_id /tmp/b2.json)
uv run score-assistant --config $C snapshots activate $A
uv run score-assistant --config $C doctor          # corpus.state compatible; search not_implemented
python3 -c "import fcntl,time;f=open('data/pins/$A.pin','a');fcntl.flock(f,fcntl.LOCK_SH);time.sleep(600)" &
uv run score-assistant --config $C snapshots activate $B   # A retired; retention keeps both anyway
uv run score-assistant --config $C index build --activate  # third snapshot; retention skips pinned A
kill -9 %1; uv run score-assistant --config $C snapshots rollback; uv run score-assistant --config $C snapshots rollback
```

Expected: while pinned, `snapshots list` shows A `PINNED yes` and not deleted. After SIGKILL,
the next retention can delete it. Two rollbacks return to the same active snapshot.

## D. Integrity failures

```bash
chmod u+w data/snapshots/$B/reports/coverage.json && echo x >> data/snapshots/$B/reports/coverage.json
uv run score-assistant --config $C index validate --snapshot $B; echo "exit=$?"   # 1, names the file
uv run score-assistant --config $C snapshots activate $B; echo "exit=$?"         # 1; active unchanged
```

## E. Lexical-only and embedding identity

```bash
sudo snap stop ollama   # or stop the runtime by other means
uv run score-assistant --config $C index build; echo "exit=$?"                 # 1 EMBEDDING_UNAVAILABLE
uv run score-assistant --config $C index build --lexical-only --json           # semantic: absent
uv run score-assistant --config $C index validate --snapshot $A                # semantic: unverified, exit 0
sudo snap start ollama
```

## F. Bundles

```bash
uv run score-assistant --config $C bundle export --snapshot $A --output /tmp/a.score-bundle.tar.gz
uv run score-assistant --config $C bundle inspect /tmp/a.score-bundle.tar.gz
mkdir -p /tmp/fresh && printf 'data_dir: /tmp/fresh/data\n' > /tmp/fresh/c.yaml
uv run score-assistant --config /tmp/fresh/c.yaml bundle import /tmp/a.score-bundle.tar.gz
uv run score-assistant --config /tmp/fresh/c.yaml snapshots list                # validated, not active
```

Expected: identical manifest SHA-256, chunk IDs and entity keys (SC-006). If the snapshot lists
license-review documents (the 3 `score-process` files flagged in F002), export without
`--acknowledge-license-review "<reason>"` exits 1 and names them.

## G. Offline guarantee

Run `index validate`, `snapshots list/activate/rollback` and `bundle *` inside a network namespace
without loopback runtime access (`unshare -rn`). They must succeed, with semantic status
`unverified` where identity cannot be checked. `index build --lexical-only` must also succeed there.
