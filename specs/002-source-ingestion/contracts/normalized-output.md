# Normalized Output and Coverage Report Contract (F002)

Records are defined in [../data-model.md](../data-model.md). All JSON is canonical (sorted keys)
when hashed; files written by `--output` use one canonical JSON object per line.

## `documents.jsonl` / `entities.jsonl`

One `NormalizedDocument` / `Entity` per line, ordered by (`source_id`, `path`) and by `key`.
Each line also carries `"canonical_version": 1`. Two runs over the same lock and profile produce
byte-identical files (SC-004).

## Coverage report (`data/reports/coverage-<prefix>.json`, `sources inspect --json`)

Shape only — all numbers below are illustrative, not measurements.

```json
{
  "schema_version": 1,
  "lock_sha256": "…",
  "processing_hash": "…",
  "sources": [
    {"source_id": "score-platform", "kind": "git", "revision": "e2373d8…", "status": "ok",
     "selected": 323, "included": 290, "partial": 31, "failed": [{"path": "…", "reason": "ENCODING_ERROR"}],
     "skipped": [{"path": "…", "reason": "symlink"}], "excluded_by_selector": 1402,
     "entities": 1403,
     "links": {"resolved": 2811, "ambiguous": 2, "unresolved": 144, "malformed": 0,
               "ambiguous_items": [{"from": "score-platform:…", "target_id": "doc__platform_mgt_plan",
                                    "candidates": ["score-platform:doc__platform_mgt_plan",
                                                   "score-process:doc__platform_mgt_plan"]}],
               "unresolved_items": [{"from": "…", "via": "derived_from", "target_id": "…"}]},
     "diagnostics_by_code": {"DYNAMIC_NOT_EVALUATED": 214},
     "licenses": {"Apache-2.0": 321, "unknown": 2},
     "requires_review": ["…"],
     "export_consistency": null}
  ],
  "totals": {"entities": 0, "diagnostics": 0}
}
```

For `needs-export` sources: `selected`/`included` count 1 file; `export_consistency` =
`{"associated_source": "score-platform", "docs_root": "docs", "matched": 0, "id_only_matched": 0,
"missing_in_source": 0, "missing_in_export": 0, "note": "statistic only; does not verify revision"}`.

## Diagnostic codes

| Code | Severity | Meaning |
| --- | --- | --- |
| `ENCODING_ERROR` | error | not valid UTF-8 → file `failed` |
| `EMPTY_DOCUMENT` | info | zero blocks |
| `PARSE_ERROR` | warning | docutils error-level system message (text retained) |
| `UNKNOWN_DIRECTIVE` | info | generic handler used; content kept |
| `UNKNOWN_ROLE` | info | text kept |
| `POSSIBLE_UNCONFIGURED_NEED` | warning | unknown directive with `:id:` option |
| `NEED_WITHOUT_ID` | warning | configured need type lacking `:id:` → no entity |
| `DUPLICATE_ID_IN_SOURCE` | warning | same need ID twice in one source |
| `MALFORMED_LINK` | warning | link item not `ID[qualifier]` |
| `DYNAMIC_NOT_EVALUATED` | info | dynamic directive/role kept inert |
| `RAW_EXCLUDED` | info | `raw` directive / Markdown HTML excluded from text |
| `EXTERNAL_RESOURCE_NOT_READ` | info | image/figure/csv-table target not read |
| `INCLUDE_UNRESOLVED` | warning | include refused (escape, missing, unselected, depth, cycle, url) |
| `HASH_MISMATCH` | error | acquired file differs from lock → source failed |
| `EXPORT_INVALID` | error | export failed schema/size validation |
| `LICENSE_UNKNOWN` | warning | no SPDX header and no repository license |

Severity drives classification: any `error` → `failed`; any `warning` → `partial`.
