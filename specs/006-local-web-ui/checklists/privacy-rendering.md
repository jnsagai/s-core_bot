# Privacy, Rendering Safety & Cross-Origin Requirements Quality Checklist: F006

**Purpose**: Unit-test the *requirements* (spec, plan, research, contracts) for the browser client:
sanitized rendering, same-origin-only communication, ephemeral state, and the narrowed guard
exemption needed to load the app at all.
**Created**: 2026-09-28
**Feature**: [spec.md](../spec.md)
**Depth**: Standard, reviewer (PR) audience; focus chosen by the agent per the owner's autonomy
instruction.
**Reviewer**: agent review (Claude Sonnet 5), not a human approval.

## Requirement Completeness

- [x] CHK001 Is every source of untrusted rendered content (answer claims, search excerpts,
  citation excerpts) identified with its sanitization rule? [Completeness, FR-009, research R2]
- [x] CHK002 Is the exact set of paths exempted from the cross-site guard fully enumerated and
  matched against what the build actually emits, rather than assumed? [Gap → resolved: research
  R4 pins `vite.config.ts` `publicDir: false` so `/` and `/assets/*` are the complete output;
  FR-011a updated in this review]
- [x] CHK003 Is defense-in-depth against a rendering-sanitizer defect specified (not only
  client-side library behaviour)? [Gap → resolved: added FR-010a, strict CSP header, in this
  review]
- [x] CHK004 Is clickjacking (framing the app in a hostile page) addressed, given that the guard
  exemption necessarily allows some cross-site top-level loads? [Gap → resolved: research R5
  `frame-ancestors 'none'` closes this distinct threat; FR-010a, in this review]
- [x] CHK005 Is the behaviour specified when `frontend/dist/` does not exist (e.g. a backend-only
  deployment)? [Completeness, contracts/ui-contract.md §2]
- [x] CHK006 Is every export field traced to an existing, already-validated backend field (no new
  invented content)? [Completeness, FR-016, data-model.md ExportDocument]

## Requirement Clarity

- [x] CHK007 Is "no automatic remote image loads" defined precisely enough to test (not just
  "sanitized")? [Clarity, FR-009, research R2 — no `<img>` element is ever emitted from Markdown]
- [x] CHK008 Is the snapshot-switch confirmation rule stated as a single deterministic condition,
  not an either/or? [Clarity, FR-017, A-035]
- [x] CHK009 Is "no background polling" precise about which actions do trigger a re-check?
  [Clarity, FR-006a, A-036]
- [x] CHK010 Is the SSE cancellation/no-reconnect rule stated as an implementation-testable
  behaviour (abort, no retry loop)? [Clarity, contracts/ui-contract.md §3, research R3]

## Requirement Consistency

- [x] CHK011 Does the guard-exemption requirement (FR-011a) agree with the actual current guard
  code path it modifies? [Consistency, research R5 cites `guard.py:108-113` directly]
- [x] CHK012 Is the question/history character-limit source (capabilities, not a hardcoded
  constant) consistent between the spec, data model and quickstart? [Consistency, FR (Edge Cases),
  A-037, data-model.md AppReadinessState]
- [x] CHK013 Does the "no new server logging" claim (FR-014) agree with F001's existing OPS-001
  implementation rather than silently assuming a new log path is fine? [Consistency, spec
  Assumptions, plan.md Constitution Check row VIII]

## Scenario & Edge Case Coverage

- [x] CHK014 Are the hostile-Markdown fixtures (raw HTML, unsafe URL schemes, remote images)
  covered by an acceptance scenario and a concrete automated test plan? [Coverage, US3 AS3,
  quickstart.md §D]
- [x] CHK015 Is a cross-site top-level navigation to the app itself covered as an edge case, given
  it is the entire reason for FR-011a? [Coverage, Edge Cases]
- [x] CHK016 Is the two-tabs-independent-state case covered without inventing new coordination
  code? [Coverage, Edge Cases, Technical Context "Scale/Scope"]
- [x] CHK017 Is disabled JavaScript / failed bundle load covered with an honest fallback, not a
  blank page? [Coverage, Edge Cases]

## Non-Functional / Privacy & Security

- [x] CHK018 Is it specified that no Web Storage/cookie is ever written, and how that would be
  tested? [Privacy, FR-013, SC-004, plan.md Verification Strategy]
- [x] CHK019 Is the absence of any analytics/telemetry/crash-reporting SDK stated as a
  requirement, not only inferred from "we didn't add one"? [Security, FR-015, constitution VIII]
- [x] CHK020 Is the browser's request surface bounded to exactly the documented endpoint list, in
  a form a future dependency review can re-check in one place? [Security, FR-011,
  contracts/ui-contract.md §1 — single `client.ts` module]

## Dependencies & Assumptions

- [x] CHK021 Is the choice not to add `rehype-raw`/`rehype-sanitize` justified by the library's
  actual dependency graph rather than assumed from memory of the library's general reputation?
  [Assumption, research R2, real `npm view` output]
- [x] CHK022 Is it explicit that real-browser, keyboard-only and screen-reader verification are
  deferred to the owner, rather than silently reported as passed? [Assumption, spec Assumptions,
  constitution VII]

## Notes

- Resolutions made in this review (agent review, 2026-09-28): CHK002 pinned the exact static-path
  set via `publicDir: false`; CHK003/CHK004 added FR-010a (CSP incl. `frame-ancestors 'none'`) as
  defense-in-depth distinct from the rendering-time sanitizer and from the guard's header check.
  All three resolutions were folded back into `spec.md`, `research.md` and `contracts/ui-contract.md`
  before this checklist was finalized, not left as open findings.
- Result: 22/22 items pass after resolutions (agent review).
