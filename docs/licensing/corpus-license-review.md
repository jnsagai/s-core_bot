# Corpus license review — flagged documents (agent review, 2026-09-29)

**Status: agent review, not a legal approval.** It was requested by the owner ("you decide") for
A-052. It covers only the documents the license gate flags for review before redistribution.

| Document (score-process @ 66321fe) | SPDX header | Origin stated in the file | Finding |
| --- | --- | --- | --- |
| `process/trustable/index.rst` | CC-BY-SA-4.0 | modified from CodethinkLabs Trustable (gitlab.com/CodethinkLabs/trustable/trustable), "licensed under CC-BY-SA-4.0 in compliance with the original license" | redistributable with attribution; share-alike applies to modified versions |
| `process/trustable/tenets/tenets.rst` | CC-BY-SA-4.0 | same | same |
| `process/trustable/assertions/assertions.rst` | CC-BY-SA-4.0 | same | same |

Decision (agent):

1. **Owner's own transfer** (a package moved between the owner's machines) is not redistribution.
   Export with a reason such as "own transfer; files kept verbatim with their CC-BY-SA-4.0
   headers".
2. **Redistribution to others** (for example a published corpus bundle) is permitted by
   CC-BY-SA-4.0 if the files stay verbatim with their SPDX headers and attribution, and the bundle
   is accompanied by a notice that these files are CC-BY-SA-4.0, originate from CodethinkLabs
   Trustable, and were modified by the Eclipse S-CORE project. Any modification must keep
   CC-BY-SA-4.0.
3. **Answers and excerpts** shown by the assistant quote short passages with a citation to the file
   and revision, which carries the attribution.
4. **Not decided here:** any legal judgement beyond the license texts, and whether the project
   *should* publish bundles at all. Publishing remains outside this project's scope (CLAUDE.md
   hard rule: stop before external publication).

The export gate stays on: each export still asks for a reason, so the decision is made at the time
of export.
