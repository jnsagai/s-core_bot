# Runbook: keep the documentation up to date (refresh)

`score-assistant refresh` brings the active snapshot up to date with upstream S-CORE in one
command. Run it by hand, or enable the shipped timer to run it every 15 minutes. It is the only
command that combines network access with activation, and `serve` never runs it.

## What one run does

1. **Check** (cheap): asks GitHub for the current commit of each git source (`git ls-remote`, no
   download) and sends a conditional request for each needs export (an unchanged export answers
   `304 Not Modified` with no body).
2. If nothing changed and the active snapshot was built from the current lock, it stops:
   **up-to-date**. Only `data/refresh-state.json` is replaced, and no other file is created.
3. Otherwise it **syncs** (the same code as `sources sync`; an identical result does not rewrite
   the lock) and **builds** a new snapshot in the same mode as the active one (semantic or
   keyword-only; it never downgrades semantic search). If a keyword-only snapshot is active, for
   example after a rollback, refresh keeps building keyword-only ones until you activate a semantic
   build yourself (`index build --activate`).
4. **Gate**: the new snapshot must pass every check:

   | Check | Passes when |
   | --- | --- |
   | `integrity` | the snapshot is `validated` and its checksums match |
   | `exact_ids` | every requirement ID is returned first by exact lookup |
   | `coverage_drop` | documents, chunks and entities each dropped by at most `refresh.max_count_drop` (default 20 %) against the active snapshot |
   | `semantic` | semantic search is not lost |
   | `required_sources` | every required source is present |

5. **Activate** atomically, and only if the active snapshot is still the one the gate compared
   against. A running `serve` answers from the new snapshot from its next request on; a request
   already in progress finishes on its original snapshot.

## Outcomes and exit codes

| Outcome | Exit | What to do |
| --- | --- | --- |
| `up-to-date` | 0 | nothing |
| `activated` | 0 | nothing; `snapshots rollback` returns to the previous snapshot |
| `failed` | 1 | read the reason (network, sync, build, embedding runtime); the active snapshot is untouched |
| `held` | 3 | the candidate failed the gate and stays `validated`. Inspect it (`search --snapshot <id>`, `snapshots diff <active> <id>`) and activate it yourself with `snapshots activate <id>` if it is fine |
| `busy` | 4 | another refresh, build, import or activation was running; the next run retries |

`refresh --json` prints the full run record (checks, revision changes, gate results, timings).
`doctor` shows the latest outcome as `corpus.refresh`. A `held` or `failed` outcome is a warning
and never changes `doctor`'s exit code.

## Enable the timer (opt-in)

```bash
scripts/install_refresh_timer.sh --config config/local.yaml            # every 15 min
scripts/install_refresh_timer.sh --config config/local.yaml --interval 5min
systemctl --user list-timers score-assistant-refresh.timer
journalctl --user -u score-assistant-refresh.service -n 20            # last runs
scripts/install_refresh_timer.sh --uninstall                           # disable and remove
```

The timer is a systemd **user** timer: it runs while you are logged in. To keep it running after
logout, run `loginctl enable-linger "$USER"`. It needs `uv sync` to have been run (it calls
`.venv/bin/score-assistant`) and Ollama running for semantic builds. `busy` (exit 4) counts as
success for systemd; `held` and `failed` show the unit as failed in `systemctl --user status`.
Cron works too (`*/15 * * * * cd <repo> && .venv/bin/score-assistant --config config/local.yaml
refresh`) but is not tested.

"Real time" is approximated by polling: the active snapshot trails upstream by at most one interval
plus one build (about 25 s on the reference laptop). Push notifications from GitHub would need a
public endpoint, which the local profile does not have.

## Before you enable it: retention

Every activation applies retention (`index.retention_count`, default 2). The active snapshot and the
rollback target are kept. **Other snapshots, including a comparison baseline you never activated,
are deleted.** To keep a baseline, raise the count in your config, for example
`index: {retention_count: 4}`, or rebuild it later (`docs/user/comparison.md`).

## Tuning

```yaml
refresh:
  max_count_drop: 0.2     # 0–<1; larger lets bigger upstream deletions through
  check_exports: true     # false: always sync exports (no conditional requests)
```

## Containers

Automatic refresh inside containers is not supported: the image has no `git`, and the bundled
runtime has no host port. With the `host-runtime` profile, run refresh natively on the host
against the same data directory; the container picks up the new snapshot from its next request on.

## Safety notes

- Activation by refresh is an operational step, not an engineering review or approval. Answers
  always name their snapshot, and you can roll back.
- The gate catches broken builds (parser regressions, truncated exports, lost embeddings, mass
  deletions), not subtle content changes.
- A `--config` path that does not exist stops every command with exit 2 (A-061); before
  2026-10-02 it silently fell back to the defaults (`data_dir: data`).
