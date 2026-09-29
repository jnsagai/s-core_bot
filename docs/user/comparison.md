# Comparing two documentation snapshots

`compare` asks one question of two snapshots that **you** choose and shows, side by side, how each
answers it. It is the only way the assistant ever uses more than one snapshot; chat and search
always stay on one snapshot.

## Commands

```bash
uv run score-assistant --config config/local.yaml snapshots list                     # pick two IDs
uv run score-assistant --config config/local.yaml snapshots diff LEFT RIGHT          # identities only, no model
uv run score-assistant --config config/local.yaml compare "question" --left LEFT --right RIGHT [--json] [--show-evidence]
uv run score-assistant --config config/local.yaml eval comparison --cases eval/comparison-dev.yaml
```

In the web UI, open the **Compare** tab. By default the right snapshot is the active one, and the left
is the newest other snapshot.

## Reading a comparison

- **What is being compared**: every source with its revision in each snapshot (commit hash, or an
  export hash marked `unverified`) and whether it is the same, different, or present on one side only.
  There is **no release label**. Per-source revisions are the identity, because no source proves a
  mapping to a product release.
- **Left / Right answers**: two ordinary answers, each citing only its own snapshot.
- **Differences**, each with evidence buttons for its side (`L1` = left, `R1` = right):
  - *Changed*: both sides address the point and say different things.
  - *Unchanged*: both say the same thing.
  - *Conflicting*: the two sides' guidance is mutually exclusive. The assistant does not choose between
    them or say which is newer.
  - *Not established*: only one side addresses the point, with the reason (for example "the source is
    not in the left snapshot" or "it was not found in the left snapshot's retrieved evidence").

**A comparison never says that something was removed, deleted or added.** Search cannot prove that
something is absent, so absence on one side is always reported as *not established* with its reason.
Model statements with such wording are rejected by validation.

Requirement IDs named in the question are compared directly, without the model. A record is
*unchanged* when its type, title, status, options and text are equal, and *changed* otherwise (the
changed fields are listed). A new file location alone is not a change.

## Getting a second snapshot

A comparison needs two snapshots. To compare against an older upstream state, pin older commits in a
copy of the registry and build without activating (this is how the benchmark baseline was made):

```bash
cp data/source-lock.json data/source-lock.main.json
uv run score-assistant --config config/local.yaml sources sync --config config/sources-baseline.yaml   # network
mv data/source-lock.json data/source-lock-baseline.json && cp data/source-lock.main.json data/source-lock.json
uv run score-assistant --config config/local.yaml index build --source-lock data/source-lock-baseline.json
```

Building never deletes anything. Activating or rolling back later applies retention (by default the
active snapshot and its predecessor are kept), which may delete a baseline you have not activated;
rebuild it with the commands above.

## Limits

A comparison runs two answers plus a comparison step, holding the single generation slot, so it takes
roughly 3–4 times as long as one answer (about 11–12 s warm on the reference workstation; see
A-044). The comparison benchmark results are a development measurement (agent-authored, unreviewed
cases).
