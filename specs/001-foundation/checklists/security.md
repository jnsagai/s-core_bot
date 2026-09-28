# Security & Local-Operation Requirements Quality Checklist: F001

**Purpose**: Unit-test the *requirements* (spec, plan, contracts) for local-only operation,
exposure control and configuration safety before task generation.
**Created**: 2026-09-27
**Feature**: [spec.md](../spec.md)
**Depth**: Standard, reviewer (PR) audience
**Reviewer**: agent review (Claude) — authorised by the project owner per PROJECT_SPEC §15.2/§20;
not a human approval. Evidence cited per item.

## Requirement Completeness

- [x] CHK001 Are all network-using commands enumerated, with every other command explicitly forbidden from external network access? [Completeness, Spec FR-003, FR-004] — FR-004 + cli.md "Network:" line per command.
- [x] CHK002 Is the non-loopback bind behaviour specified for all address forms (IPv4 any, LAN IP, hostname, IPv6)? [Completeness, Spec FR-011, Edge Cases] — config.md `server.host` constraint; `::1` edge case.
- [x] CHK003 Are requirements defined for a runtime URL that points off-host? [Completeness, Edge Cases, contracts/config.md `runtime.base_url`]
- [x] CHK004 Is the treatment of cloud-proxied models specified? [Completeness, research R3, cli.md `MODEL_REMOTE`]
- [x] CHK005 Are CORS response headers specified for allowed, disallowed, and preflight requests? [Completeness, http-api.md Guard table]
- [x] CHK006 Are the contents of liveness/readiness responses bounded to avoid information disclosure? [Completeness, Spec FR-020, http-api.md]

## Requirement Clarity

- [x] CHK007 Is "loopback" defined precisely (address ranges and names)? [Clarity, contracts/config.md] — 127.0.0.0/8, ::1, localhost.
- [x] CHK008 Is "cross-site browser request" defined by an observable signal? [Clarity, Clarifications Q3] — `Sec-Fetch-Site: cross-site`.
- [x] CHK009 Is the handling of `Origin: null` specified? [Clarity, research R8, http-api.md]
- [x] CHK010 Is "secret" defined for redaction purposes with a concrete matching rule? [Clarity, contracts/config.md Redaction]
- [x] CHK011 Are error status codes for guard rejections fixed? [Clarity, Spec FR-013] — 400 Host, 403 Origin/cross-site.

## Requirement Consistency

- [x] CHK012 Do the default `allowed_origins` match the default bind host/port? [Consistency, config.md vs §10.3] — both 8080 on 127.0.0.1/localhost.
- [x] CHK013 Is the doctor exit-code rule consistent between spec FR-007, Clarifications, cli.md and data-model invariant? [Consistency]
- [x] CHK014 Is readiness HTTP status consistent between spec FR-020, Clarifications Q2 and http-api.md? [Consistency]
- [x] CHK015 Do allowed-hosts semantics state whether a `Host` without port is accepted when the server runs on a non-default port? [Consistency, Gap] — **Finding**: http-api.md says "compared as host, and host:port against bound port" but config.md allows entries "with optional :port" — ambiguous whether `localhost` entry matches `localhost:9000`. See resolution note.

## Scenario & Edge Case Coverage

- [x] CHK016 Is behaviour specified when the runtime hangs (timeouts) rather than refusing? [Coverage, Edge Cases, config.md diagnostics.*]
- [x] CHK017 Is behaviour specified for interrupted model acquisition with respect to the lock file? [Coverage, cli.md pull SIGINT]
- [x] CHK018 Is behaviour specified for an existing but unsupported corpus catalog (never opened)? [Coverage, FR-024]
- [x] CHK019 Are requirements defined for unknown `SCORE_ASSISTANT_*` environment variables? [Coverage, config.md Precedence]
- [x] CHK020 Is the absence of chat/placeholder routes stated as a verifiable requirement? [Coverage, FR-021, http-api.md Route inventory]

## Non-Functional / Measurability

- [x] CHK021 Can "no outbound network" be objectively measured? [Measurability, SC-004, research R12]
- [x] CHK022 Is the diagnostic time bound under runtime failure quantified? [Measurability, SC-002]
- [x] CHK023 Is logging content specified such that absence of bodies/secrets is verifiable? [Measurability, plan Key Design 6, SC-006]

## Dependencies & Assumptions

- [x] CHK024 Is the unverifiability of Ollama's server-side cloud setting documented rather than assumed? [Assumption, research R4]
- [x] CHK025 Is the `/api/pull` progress format marked as needing verification? [Assumption, research R3]

## Notes

- CHK015 resolution (applied to contracts in the same review): an `allowed_hosts` entry without a
  port matches that host on **the bound port only**; an entry with a port matches exactly. Any
  other port → 400. http-api.md and config.md updated accordingly; item checked after both contracts
  were updated (agent review, 2026-09-27). Result: 25/25 items passing.
