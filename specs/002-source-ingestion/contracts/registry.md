# Registry and Parser Profile Contract (schema_version 1)

YAML via `yaml.safe_load`; unknown keys rejected at every level; errors reported as
`<dotted.path>: <reason>`.

## `config/sources.yaml`

```yaml
schema_version: 1
allowed_hosts: [github.com, eclipse-score.github.io]
redistribution_allowed_licenses: [Apache-2.0, MIT, BSD-2-Clause, BSD-3-Clause, CC0-1.0, CC-BY-4.0]
limits:
  max_text_file_bytes: 10485760      # 10 MiB
  max_export_bytes: 104857600        # 100 MiB
  max_sync_bytes: 1073741824         # 1 GiB
  connect_timeout_seconds: 10
  read_timeout_seconds: 60
sources:
  - source_id: score-platform
    kind: git
    repository: https://github.com/eclipse-score/score.git
    ref: main
    include: ["docs/**/*.rst", "docs/**/*.md", "README.md", "CONTRIBUTION.md"]
    exclude: []
    authority: official-project
    repository_license: Apache-2.0
    license_policy: inspect-file-and-repository-notices
    required: true
    parser_profile: s-core
  - source_id: score-process
    kind: git
    repository: https://github.com/eclipse-score/process_description.git
    ref: main
    include: ["process/**/*.rst", "process/**/*.md", "README.md"]
    exclude: []
    authority: official-project
    repository_license: Apache-2.0
    license_policy: inspect-file-and-repository-notices
    required: true
    parser_profile: s-core
  - source_id: score-platform-needs
    kind: needs-export
    url: https://eclipse-score.github.io/score/main/needs.json
    associated_source: score-platform
    docs_root: docs
    authority: official-project-build-artifact
    repository_license: Apache-2.0
    license_policy: inspect-file-and-repository-notices
    required: false
  - source_id: score-process-needs
    kind: needs-export
    url: https://eclipse-score.github.io/process_description/main/needs.json
    associated_source: score-process
    docs_root: process
    authority: official-project-build-artifact
    repository_license: Apache-2.0
    license_policy: inspect-file-and-repository-notices
    required: false
```

Validation rules: see data-model.md SourceDefinition. Additionally: URL scheme must be `https`;
host (lowercased, no port other than 443) must be in `allowed_hosts`; no userinfo, query or
fragment; globs may use only `**`, `*`, `?` and literal characters (no `[…]`, no leading `/`,
no `..`); `.git/**` is always excluded implicitly; limits must be positive and
`max_text_file_bytes ≤ max_sync_bytes`.

## `config/parser-profiles/<name>.yaml`

```yaml
profile_version: 1
need_types: [std_req, feat_req, document, gd_req, std_wp, stkh_req, workflow, aou_req, workproduct,
             logic_arc_int_op, gd_temp, logic_arc_int, gd_guidl, comp_req, doc_concept, role, feat,
             doc_getstrt, comp, assertion, gd_chklst, doc_tool, dec_rec, real_arc_int, tenet,
             comp_arc_sta, comp_saf_dfa, comp_saf_fmea, mod, feat_arc_sta, feat_saf_fmea,
             feat_saf_dfa, dd_sta, dd_dyn, mod_view_sta, gd_method, plat_saf_dfa, feat_arc_dyn,
             comp_arc_dyn, tsf, tool_req]
link_options: [derived_from, satisfied_by, complies, realizes, satisfies, links, included_by,
               responsible, approved_by, input, supported_by, contains, output, has, belongs_to,
               fulfils, includes, uses, implements, violates, mitigated_by, consists_of]
reference_roles: [need]
dynamic_directives: [needextend, needtable, needpie, needarch, needuml, needflow, needlist,
                     needfilter, needgantt, needsequence, needbar, needservice, needimport, needreport]
dynamic_roles: [ndf]
literal_directives: {code-block: null, sourcecode: null, uml: plantuml, mermaid: mermaid, graphviz: dot}
excluded_directives: [raw]
```

Rules: lists non-empty where shown, entries unique, no name in more than one list; names match
`^[A-Za-z][A-Za-z0-9_-]*$`. Provenance comment in the file records it was derived from
research.md R1 (commits `e2373d8`, `66321fe`). Changing the file changes `profile_hash` and
therefore every document key (intended: SRC-010).
