# Untrusted-Input & Acquisition Security Requirements Quality Checklist: F002

**Purpose**: Unit-test the *requirements* (spec, plan, contracts) for safe handling of untrusted
upstream content and network acquisition, before task generation.
**Created**: 2026-09-28
**Feature**: [spec.md](../spec.md)
**Depth**: Standard, reviewer (PR) audience
**Reviewer**: agent review (Claude Opus 5.5) — authorised per PROJECT_SPEC §15.2/§20; not a human
approval. Evidence cited per item.

## Requirement Completeness

- [x] CHK001 Are all mechanisms by which git could execute repository content (hooks, filters, LFS, submodules, checkout, symlinks, user/system config) explicitly excluded? [Completeness, Spec FR-005, research R5]
- [x] CHK002 Are all docutils I/O paths (include, raw file/url, csv-table file/url, image probing, config files) addressed? [Completeness, FR-013, FR-015, research R2]
- [x] CHK003 Is the handling of every observed dynamic construct (`needextend`, `needtable`, `needpie`, `needarch`, `needuml`, `:ndf:`) specified? [Completeness, FR-013, research R1]
- [x] CHK004 Are size caps specified for files, exports and whole syncs, and is truncation forbidden? [Completeness, FR-007]
- [x] CHK005 Is redirect handling specified for both git and HTTP downloads? [Completeness, FR-007, research R5, R7]
- [x] CHK006 Is behavior specified for the literal/code-block trap observed upstream? [Completeness, FR-014, SC-007]

## Requirement Clarity

- [x] CHK007 Is "allowed host" defined precisely (case, port, userinfo, query)? [Clarity, contracts/registry.md]
- [x] CHK008 Is the glob dialect defined, including what is rejected? [Clarity, research R8, contracts/registry.md]
- [x] CHK009 Is the link-value grammar (ID + bracket qualifier, comma separation) defined? [Clarity, plan Key Design 7]
- [x] CHK010 Is "unverified" revision status defined with what identifies an export instead? [Clarity, FR-019, contracts/lock.md]
- [x] CHK011 Is the maximum include nesting depth consistent everywhere it is stated? [Consistency] — **Finding**: spec FR-015 and research R6 say 8; data-model/contracts do not restate it; acceptable. But plan Verification row says "depth 9" as the refused case — consistent (9 > 8). Checked in resolution note.

## Requirement Consistency

- [x] CHK012 Do spec (exit codes), contracts/cli.md and F001's CLI contract agree on 0/1/2/130? [Consistency]
- [x] CHK013 Do FR-008 (failed required sync), contracts/cli.md and quickstart E agree that the previous lock is unchanged? [Consistency]
- [x] CHK014 Is the treatment of optional-source failure consistent between US1 AS6, clarification Q4 and contracts/lock.md (`status: failed`)? [Consistency]
- [x] CHK015 Do data-model severity→classification rules match the diagnostic catalogue? [Consistency, contracts/normalized-output.md]

## Scenario & Edge Case Coverage

- [x] CHK016 Is behavior specified for force-push/disappearing commits between resolve and fetch? [Edge Case, spec Edge Cases]
- [x] CHK017 Is behavior specified for abbreviated SHAs and full-SHA refs? [Edge Case, spec Edge Cases]
- [x] CHK018 Is tampering/corruption of acquired files between sync and inspect addressed? [Coverage, plan Key Design 4, `HASH_MISMATCH`]
- [x] CHK019 Are malformed-tree defenses layered (git fsck + own path validation)? [Coverage, plan Key Design 2]
- [x] CHK020 Is behavior specified when two sources resolve to paths that would collide on disk? [Gap] — see resolution note.

## Non-Functional / Measurability

- [x] CHK021 Can "no execution of repository content" be objectively tested? [Measurability, SC-003, plan Verification FR-005 marker-file test]
- [x] CHK022 Is determinism measurable byte-for-byte? [Measurability, SC-004]
- [x] CHK023 Are performance targets quantified? [Measurability, SC-005]

## Dependencies & Assumptions

- [x] CHK024 Is the git version prerequisite and its scope (sync only) documented? [Dependency, plan Technical Context, quickstart]
- [x] CHK025 Is the docutils license analysis recorded rather than assumed? [Assumption, research R3, FR-025]

## Notes

- CHK011 resolution: depth limit is 8 in FR-015 and R6; the plan's "depth 9" is the refused test
  case. Consistent → checked below after re-read (agent review, 2026-09-28).
- CHK020 resolution: on-disk paths are `data/sources/<source_id>/<revision>/…` and `source_id` is
  unique in the registry (data-model), so collisions across sources are impossible by
  construction; within one source, git trees cannot contain duplicate paths. Added an explicit
  statement to data-model.md (Lock side) during this review. → checked.
- Result: 25/25 items passing after resolutions (agent review).
