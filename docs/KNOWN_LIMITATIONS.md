# Known limitations (local release 1.0.0rc1)

State on 2026-09-30, from `docs/ASSUMPTIONS.md` and the release report.

- **Development cases unreviewed.** The 60 development cases of the evaluation suite have not been
  reviewed by a person. This is the only open release gate (the 40 held-out cases were accepted with
  the held-out review).
- **Human review is a blanket acceptance.** The held-out answers were accepted in bulk by the owner,
  not judged claim by claim (A-055). Support precision and required-fact coverage (100%) reflect
  that acceptance, not a per-claim measurement; ho-022 is answered only partially in every run.
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
