# Contract: Snapshot Bundle (F003)

File: `<name>.score-bundle.tar.gz`. It is a POSIX (ustar/pax) tar compressed with gzip, written by
stdlib `tarfile`.

## Layout (member order is fixed)

```text
bundle-manifest.json          # first member, ≤ 1 MiB
snapshot/manifest.json
snapshot/corpus.sqlite
snapshot/embedding-manifest.json   # if semantic
snapshot/embeddings.f32            # if semantic
snapshot/reports/coverage.json
snapshot/reports/build-validation.json
```

Every member is a regular file with mode 0644 and uid/gid 0; mtime is the snapshot `created_at`.
Uname/gname are empty. No directory entries.

## `bundle-manifest.json` (bundle_format 1)

```json
{
  "bundle_format": 1,
  "schema_version": 1,
  "corpus_schema_version": 1,
  "snapshot_id": "20260928T101500Z-3fa2b1c9",
  "manifest_sha256": "…",
  "created_at": "2026-09-28T11:00:00Z",
  "app_version": "0.1.0",
  "files": [{"path": "snapshot/corpus.sqlite", "sha256": "…", "size": 0}],
  "total_size": 0,
  "entry_count": 7,
  "license_acknowledgement": {"reason": "…", "files": ["score-process:path/x.rst"]}
}
```

`license_acknowledgement` is `null` when the snapshot lists no `license_review` documents.
`entry_count` includes `bundle-manifest.json`. `total_size` is the sum of all member sizes.

## Import rules (all checked in pass 1, before any byte is written)

| Rule | Rejection reason |
| --- | --- |
| first member is `bundle-manifest.json`, valid JSON, ≤ 1 MiB, known `bundle_format` | `manifest_invalid` |
| `schema_version`, `corpus_schema_version` ≤ supported | `schema_unsupported` |
| every member `isreg()` (no dir, symlink, hardlink, device, FIFO) | `entry_type` |
| name relative, POSIX, no `..`/`.`/empty segment, no backslash/NUL, under `snapshot/` | `unsafe_path` |
| no duplicate names; member set = manifest `files` + manifest itself | `entry_mismatch` |
| member count ≤ `bundles.max_entries` (scanning stops at max + 1) | `too_many_entries` |
| Σ sizes ≤ `bundles.max_total_bytes`, and = `total_size` | `too_large` / `size_mismatch` |
| free disk on `data_dir` ≥ `total_size` + `bundles.disk_margin_bytes` | `disk_insufficient` |

Pass 2 (extraction into `data/staging/import-<job>/`): each file is written with
`O_CREAT|O_EXCL|O_NOFOLLOW` and hashed while written. Writing more bytes than the header states is
an error. After extraction, the SHA-256 of every file must equal the bundle manifest,
`snapshot/manifest.json` must hash to `manifest_sha256`, and the full snapshot validator
(research R9) must pass. Then the snapshot is registered `validated`. Any failure removes staging
and registers nothing.
