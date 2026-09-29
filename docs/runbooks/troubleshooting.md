# Runbook: troubleshooting

Start with `score-assistant --config $C doctor`; every failure names its fix.

| Symptom | Meaning | Fix |
| --- | --- | --- |
| Chat unavailable, search works | runtime unreachable, model missing or digest mismatch | start Ollama / `models pull`; check `doctor` models section |
| "Keyword results only" | embedding runtime unavailable or embedding identity changed | start Ollama; rebuild the index after a model change |
| `NO_ACTIVE_SNAPSHOT` | no corpus activated | `index build --activate` or `bundle import` + `snapshots activate` |
| HTTP 403 from the browser | Host/Origin mismatch (another port or hostname) | use `http://127.0.0.1:8080`; align `server.port`, `allowed_origins` and the published port |
| `deployment.mode container requires the application image` | container config used natively | use `config/local.yaml` natively |
| Container app cannot write `/data` | UID mismatch | set `SCORE_UID`/`SCORE_GID` to the data directory owner |
| 429 `CHAT_BUSY` | one generation at a time plus a queue of 4 | wait and retry |
| 504 `DEADLINE_EXCEEDED` on CPU containers | CPU inference is slow | raise `limits.request_deadline_seconds` in `config/container.yaml` |
