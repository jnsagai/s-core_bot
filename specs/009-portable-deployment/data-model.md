# Data Model: F009

- `DeploymentConfig`: `mode: "native" | "container" = "native"`, `runtime_private_hosts:
  list[str] = []` (DNS labels only; allowed only in container mode).
- `LoggingConfig`: `file: Path | None = None`, `retention_days: int = 7` (1..7).
- `PackageManifest` (`package-manifest.json`): `created_at`, `app_version`, `snapshot_id`,
  `models: [{role, tag, digest}]`, `images: [{name, id, archive}]`,
  `items: [{path, kind, sha256, size}]`, `excluded: [{what, reason}]`.
- `ContainerReport`: `created_at`, `profile`, `published_ports` (from `docker port`/inspect),
  `runtime_ports`, `app_security` (user, read_only, cap_drop, no_new_privileges, memory, cpus,
  pids), `probe` (health, search, cited answer), `status`, `reason`.
- `FreshInstallReport`: `steps [{name, ok, detail}]`, `network` (namespace egress probe), `status`.
- `RestoreReport`: `original_snapshot`, `restored_snapshot`, `chunks_compared`,
  `chunk_mismatches`, `citations_compared`, `citation_mismatches`, `status`.
- `ContractReport`: `base_url`, `signatures {endpoint: {status, shape}}`; comparison: `equal`,
  `differences[]`.
- `ReleaseManifest`: `version`, `created_at`, `items [{path, sha256, size, kind}]`, `excluded`.
