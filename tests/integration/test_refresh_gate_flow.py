"""Bad updates never replace a good snapshot (F011 US2: FR-006, FR-007, FR-016, SC-003)."""

from __future__ import annotations

from pathlib import Path

from score_docs_assistant.refresh.models import RefreshState
from score_docs_assistant.refresh.state import read_state
from score_docs_assistant.sources.lock import read_lock
from score_docs_assistant.storage import lifecycle
from tests.helpers.lifecycle import MESSAGES
from tests.helpers.refresh import commit, make_upstream, reqs_rst


def test_mass_deletion_is_held(tmp_path: Path) -> None:
    up = make_upstream(tmp_path)
    good = up.refresh()
    commit(up.repo, {}, remove=[f"docs/topic_{i}.rst" for i in range(6)] + ["docs/reqs.rst"])
    run = up.refresh()
    assert run.outcome == "held" and run.exit_code == 3
    failed = {g.id for g in run.gate if g.status == "fail"}
    assert "coverage_drop" in failed
    assert up.active() == good.candidate == run.active_after
    assert run.candidate is not None and up.state_of(run.candidate) == "validated"


def test_held_candidate_can_be_activated_by_hand(tmp_path: Path) -> None:
    up = make_upstream(tmp_path)
    up.refresh()
    commit(up.repo, {}, remove=[f"docs/topic_{i}.rst" for i in range(6)])
    run = up.refresh()
    assert run.outcome == "held" and run.candidate is not None
    lifecycle.activate(
        config=up.config(),
        snapshot_id=run.candidate,
        runtime=up.provider,
        progress=MESSAGES.append,
    )
    assert up.active() == run.candidate


def test_small_change_within_threshold_passes(tmp_path: Path) -> None:
    up = make_upstream(tmp_path)
    up.refresh()
    commit(up.repo, {}, remove=["docs/topic_0.rst"])
    run = up.refresh(max_count_drop=0.5)
    assert run.outcome == "activated"


def test_unexpected_build_crash_is_recorded_as_failed(tmp_path: Path) -> None:
    """The same need ID defined twice in one source crashes the F003 build (A-058); refresh must
    record that as `failed`, keep the active snapshot and write its state."""
    up = make_upstream(tmp_path)
    good = up.refresh()
    commit(up.repo, {"docs/reqs_copy.rst": reqs_rst(12)})
    run = up.refresh()
    assert run.outcome == "failed" and run.exit_code == 1
    assert run.reason.startswith("unexpected error during build: IntegrityError")
    assert up.active() == good.candidate == run.active_after
    state = read_state(up.data)
    assert isinstance(state, RefreshState) and state.last_run is not None
    assert state.last_run.outcome == "failed"


def test_required_source_unreachable_fails_and_keeps_everything(tmp_path: Path) -> None:
    up = make_upstream(tmp_path)
    good = up.refresh()
    lock_bytes = (up.data / "source-lock.json").read_bytes()
    broken = up.repo.path.rename(tmp_path / "gone")
    run = up.refresh()
    assert run.outcome == "failed" and run.exit_code == 1
    assert "upstream check failed" in run.reason
    assert (up.data / "source-lock.json").read_bytes() == lock_bytes
    assert up.active() == good.candidate
    broken.rename(up.repo.path)


def test_embedding_runtime_down_with_semantic_active_fails(tmp_path: Path) -> None:
    up = make_upstream(tmp_path)
    good = up.refresh()
    commit(up.repo, {"docs/extra.rst": "Extra\n=====\n\nSYNTHETIC — extra.\n"})
    run = up.refresh(provider_error=True)
    assert run.outcome == "failed" and "EMBEDDING_UNAVAILABLE" in run.reason
    assert up.active() == good.candidate
    assert run.candidate is None


def test_lexical_only_never_replaces_semantic_active(tmp_path: Path) -> None:
    up = make_upstream(tmp_path)
    good = up.refresh()
    commit(up.repo, {"docs/extra.rst": "Extra\n=====\n\nSYNTHETIC — extra.\n"})
    run = up.refresh(lexical_only=True)
    assert run.outcome == "held"
    assert [g.id for g in run.gate if g.status == "fail"] == ["semantic"]
    assert up.active() == good.candidate


def test_optional_export_failure_still_activates(tmp_path: Path) -> None:
    up = make_upstream(tmp_path)
    up.refresh()
    assert up.export is not None
    up.export.fail = True
    commit(up.repo, {"docs/extra.rst": "Extra\n=====\n\nSYNTHETIC — extra.\n"})
    run = up.refresh()
    export_check = next(c for c in run.checks if c.source_id == "fx-needs")
    assert export_check.status == "unknown"
    lock = read_lock(up.data / "source-lock.json")
    assert next(s for s in lock.sources if s.source_id == "fx-needs").status == "failed"
    # The optional export failed; entity coverage may drop but required sources are present.
    assert next(g for g in run.gate if g.id == "required_sources").status == "pass"
