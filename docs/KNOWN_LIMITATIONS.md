# Known limitations (local release)

Generated from the open items in `docs/ASSUMPTIONS.md` and the release report at release time.
Current state (2026-09-29):

- **Human review pending.** The 100-case suite is agent-authored and unreviewed. Factual support
  precision and required-fact coverage are blocked until a person reviews the held-out answers
  (A-045, A-048).
- **Real-browser checks pending.** The UI walkthrough, keyboard-only review, colour contrast and
  screen reader have not been run in a browser (A-040).
- **Comparison speed.** A comparison takes about 3.5–3.9× a single answer, above the 3× target
  (A-044).
- **Held-out safe handling.** It dipped to 13/14 in one of three runs; ho-031's expected status
  may be wrong (A-048).
- **Hardware.** GPU acceleration in containers is not run; Windows/WSL2 and macOS are not
  validated; no second physical machine was available (see `docs/quality/hardware-matrix.md`).
- **CPU containers are slow**: about 60 s for a first answer.
- **Automated checks are proxies.** The forbidden-assertion and adversarial judges are heuristics
  (A-046, A-047); the human review decides.
- **Redistribution.** Model weights and corpus bundles are not redistributed; three
  process-description documents need license review before any redistribution.
- **Public hosting** is not part of this release (F010).
