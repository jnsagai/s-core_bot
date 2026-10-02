# Known limitations (local release 1.0.0)

State on 2026-09-30, from `docs/ASSUMPTIONS.md` and the release report.

- **Human review is a blanket acceptance.** The owner accepted the held-out answers and all 100
  suite cases in bulk, not claim by claim or case by case (A-055, A-056). Support precision and
  required-fact coverage (100%) reflect that acceptance, not a per-claim measurement; ho-022 is
  answered only partially in every run. A per-claim review would give real numbers.
- **Automated checks are proxies.** The forbidden-assertion and adversarial judges are heuristics
  (A-046, A-047).
- **Comparisons trade completeness for speed.** Invalid model differences are dropped (with a
  warning) instead of repaired when valid ones exist (A-054); `comparison.repair: always` restores
  repairs.
- **Hardware.** Qualified on one Linux laptop with an NVIDIA RTX 4070 (native). CPU containers are
  functional but slow (about 60 s for a first answer). GPU in containers, Windows/WSL2 and macOS are
  not validated. No second physical machine was used (`docs/quality/hardware-matrix.md`).
- **Redistribution.** Model weights and corpus bundles are not redistributed. Three
  process-description files are CC-BY-SA-4.0 and need attribution if ever redistributed (agent
  license review, not legal advice: `docs/licensing/corpus-license-review.md`).
- **Public hosting** is not part of this release (F010, deferred).
- **Refresh (F011)** approximates real time by polling (default every 15 min, opt-in timer); it runs only natively on Linux with systemd user timers (not inside containers), and its promotion gate is a proxy for broken builds, not a content review. Each activation applies retention, which removes unactivated snapshots such as a comparison baseline (`docs/runbooks/refresh.md`). A duplicate need ID within one source fails the build (A-059).
