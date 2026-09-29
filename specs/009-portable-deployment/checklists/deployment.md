# Deployment Security & Portability Requirements Quality Checklist: F009

**Reviewer**: agent review (Claude Opus 5.5), not a human approval. **Created**: 2026-09-29

- [x] CHK001 Is the only exception to the loopback rules specified with an unforgeable-by-config precondition? [FR-003, R3]
- [x] CHK002 Is it specified that Host/Origin validation is unchanged in container mode? [FR-003]
- [x] CHK003 Is the interaction between the published host port and the Host-header guard specified? [Gap → resolved: R2 "Ports and Host validation"]
- [x] CHK004 Is data-volume ownership for a non-root container specified? [Gap → resolved: R2 "Data ownership"]
- [x] CHK005 Is the runtime's lack of a host port and network egress specified and testable? [FR-002, SC-001]
- [x] CHK006 Is "offline install" defined by an enforced condition (namespace), and are its dependency-cache limits stated? [Gap → resolved: R5]
- [x] CHK007 Is redistribution of weights/corpus excluded by default? [FR-011]
- [x] CHK008 Are GPU-container and second-machine limits recorded as not run rather than assumed? [FR-004, Assumptions]
- [x] CHK009 Is log retention bounded (≤ 7 days) and body-free? [FR-009]
- [x] CHK010 Is "report complete" defined measurably? [SC-006]

Notes: 3 gaps resolved in research.md during this review.
