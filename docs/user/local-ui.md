# Using the local web UI

The web UI (F006) is a static bundle served by the same local backend process; there is no
separate web server and nothing is loaded from the internet.

## Build and run

```bash
cd frontend && npm ci && npm run build && cd ..        # once, or after frontend changes
uv run score-assistant --config config/local.yaml serve
```

Open <http://127.0.0.1:8080/> in a browser on the same machine.

## What you can do

- **Ask**: type a question about the selected documentation snapshot. Progress is shown as
  queued → searching → generating → checking. The answer lists short statements; documented ones
  cite sources (`[E1]`). Select a citation to read the stored excerpt, its file, section and
  revision, and (where it can be proven) a link to the exact upstream revision. **Stop** aborts a
  running answer; **Retry** re-asks after a failure.
- **Search**: search the documentation directly (no answer model), optionally filtered by source
  and content kind. Requirement IDs are matched exactly.
- **Status**: which capabilities are available, installed models and limits. It re-checks only
  when you open it or press "Check again" — the UI never polls in the background.
- **Snapshot**: pick another documentation snapshot. If the conversation has turns you are asked
  to confirm, because switching clears it.
- **Export**: download a finished answer as Markdown or JSON (question, statements, citations,
  snapshot and model identity).

## Privacy

Conversations live only in the page's memory: nothing is written to browser storage or cookies,
and a reload or **New conversation** clears everything. The server does not log questions or
answers. The page sends requests only to this local application.

## If something is unavailable

- *Answers unavailable, search still works*: the answer model is missing or not running — run
  `score-assistant models pull` or start Ollama, then press "Check again".
- *Keyword results only*: the embedding model is unavailable; search still works.
- *No snapshot*: run `score-assistant sources sync` and `score-assistant index build --activate`.
