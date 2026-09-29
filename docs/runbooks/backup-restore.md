# Runbook: backup and restore

- **Back up a snapshot**: `score-assistant --config $C bundle export --snapshot <id> --output <file>`
  (per-file SHA-256; license-review acknowledgement required when flagged documents are present).
- **Restore**: `score-assistant --config $C bundle import <file>` (verified and registered as
  `validated`), then `score-assistant --config $C snapshots activate <id>`.
- **Verify the restore**: `python -m score_docs_assistant.qualification.restore --original <old data>
  --restored <new data> --out restore.json` compares the snapshot ID, 50 chunks and fixed citations.
- Keep `data/model-lock.json` with the backup; the restored snapshot is served only with the same
  embedding model identity (otherwise search degrades to keyword with a visible reason).
- Retention (default 2) runs on activation and rollback. It keeps the active snapshot and its
  rollback target; export anything else you want to keep.
