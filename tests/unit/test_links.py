"""Link grammar `ID[qualifier]` and cross-source resolution (FR-011, FR-018)."""

from __future__ import annotations

from score_docs_assistant.ingestion.links import (
    EntityIndex,
    parse_link_value,
    parse_role_target,
    resolve,
)


def test_single_item_with_qualifier() -> None:
    (ref,) = parse_link_value("derived_from", "stkh_req__execution_model__processes[version==1]")
    assert (ref.via, ref.target_id, ref.qualifier) == (
        "derived_from",
        "stkh_req__execution_model__processes",
        "version==1",
    )
    assert ref.raw == "stkh_req__execution_model__processes[version==1]"


def test_multiple_items_over_newlines_and_duplicates_kept() -> None:
    # Shape observed upstream: a 9-line `:complies:` value with a repeated target.
    raw = "a__x[version==1],\nb__y[version==1],\nb__y[version==1],\n  c__z"
    refs = parse_link_value("complies", raw)
    assert [r.target_id for r in refs] == ["a__x", "b__y", "b__y", "c__z"]
    assert refs[3].qualifier is None


def test_comma_inside_brackets_does_not_split() -> None:
    (ref,) = parse_link_value("links", "a__x[version==1, status==valid]")
    assert ref.qualifier == "version==1, status==valid"


def test_malformed_items_kept_raw_and_well_formed_still_parsed() -> None:
    refs = parse_link_value("links", "a__x, , b__y[unclosed, has space")
    kinds = [(r.resolution, r.raw) for r in refs]
    assert ("unresolved", "a__x") in kinds
    assert ("malformed", "") in kinds
    assert ("malformed", "b__y[unclosed, has space") in kinds


def test_role_target_forms() -> None:
    assert parse_role_target("need", "feat_req__a__b").target_id == "feat_req__a__b"
    titled = parse_role_target("need", "Nice title <feat_req__a__b>")
    assert titled.target_id == "feat_req__a__b" and titled.via == "role:need"


def _index() -> EntityIndex:
    return EntityIndex.build(
        {
            "src-a": ["x__1", "shared__id"],
            "src-b": ["y__2", "shared__id"],
            "src-c": ["z__3"],
            "exp-a": ["x__1"],
        },
        export_sources={"exp-a"},
    )


def test_resolution_rules() -> None:
    index = _index()
    same = resolve(parse_link_value("links", "x__1")[0], "src-a", index)
    assert (same.resolution, same.resolved_keys) == ("resolved", ["src-a:x__1"])
    other = resolve(parse_link_value("links", "y__2")[0], "src-a", index)
    assert (other.resolution, other.resolved_keys) == ("resolved", ["src-b:y__2"])
    ambiguous = resolve(parse_link_value("links", "shared__id")[0], "src-c", index)
    assert ambiguous.resolution == "ambiguous"
    assert ambiguous.resolved_keys == ["src-a:shared__id", "src-b:shared__id"]
    same_first = resolve(parse_link_value("links", "shared__id")[0], "src-a", index)
    assert same_first.resolved_keys == ["src-a:shared__id"]
    missing = resolve(parse_link_value("links", "nope__0")[0], "src-a", index)
    assert (missing.resolution, missing.resolved_keys) == ("unresolved", [])


def test_export_namespace_isolation() -> None:
    index = _index()
    from_git = resolve(parse_link_value("links", "z__3")[0], "src-a", index)
    assert from_git.resolved_keys == ["src-c:z__3"]
    # A git-source link never resolves to an export entity, and vice versa.
    only_in_export = EntityIndex.build({"src-a": [], "exp-a": ["q__9"]}, export_sources={"exp-a"})
    assert resolve(parse_link_value("l", "q__9")[0], "src-a", only_in_export).resolution == (
        "unresolved"
    )
    from_export = resolve(parse_link_value("links", "z__3")[0], "exp-a", index)
    assert from_export.resolution == "unresolved"


def test_malformed_never_resolved() -> None:
    (ref,) = parse_link_value("links", "bad[")
    assert resolve(ref, "src-a", _index()).resolution == "malformed"
