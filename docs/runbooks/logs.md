# Runbook: logs and retention (OPS-001)

- The access log is one body-free JSON line per request (request_id, method, path, status,
  duration). Question and answer text are never logged.
- Native: stderr by default. Set `logging.file: /path/access.log` (and optionally
  `logging.retention_days: 1..7`, default 7) for a daily-rotated file that keeps at most that many
  rotated files.
- Containers: the json-file driver caps each container's logs at 7 files of 10 MB. Read them with
  `docker compose logs app`.
- Reports under `data/reports/` hold measurements, never conversation text. The suite privacy scan
  checks that.
