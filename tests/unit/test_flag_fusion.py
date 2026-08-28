from itertools import product

import pytest

from scripts.flags.fusion import fuse_flags, run_independent_sources
from scripts.flags.models import FlagArtifact, FlagRecord, FlagSource, FlagStatus


def artifact(source, state):
    if state == "nonempty":
        return FlagArtifact.success(
            session_id="session-1", source=source,
            flags=[FlagRecord(
                f"{source.value}-1", source, 1, 2, (f"evidence-{source.value}",),
                f"synthetic-{source.value}-policy",
            )],
            provenance={"policy_id": f"synthetic-{source.value}-policy"},
        )
    if state == "empty":
        return FlagArtifact.success(
            session_id="session-1", source=source, flags=[], provenance={"synthetic": True}
        )
    return FlagArtifact(
        session_id="session-1", source=source,
        status=FlagStatus.FAILED if state == "failed" else FlagStatus.UNAVAILABLE,
        failure_reason=f"synthetic {state}", provenance={},
    )


@pytest.mark.parametrize("states", product(("nonempty", "empty", "failed", "unavailable"), repeat=3))
def test_every_nonempty_empty_failed_unavailable_source_combination_is_preserved(states):
    artifacts = {source: artifact(source, state) for source, state in zip(FlagSource, states)}
    fused = fuse_flags(
        artifacts, merge_gap_seconds=0, merge_on_equal_gap=False,
        merge_policy_id="synthetic-merge", paper_mode=False
    )
    assert fused.source_statuses == {
        source: artifacts[source].status for source in FlagSource
    }
    assert sum(len(flag.contributions) for flag in fused.flags) == states.count("nonempty")


def test_all_sources_are_invoked_when_first_and_second_raise():
    calls = []

    def producer(source):
        def run():
            calls.append(source)
            if source != FlagSource.TRANSCRIPT_KEYWORD:
                raise RuntimeError(f"synthetic {source.value} failure")
            return artifact(source, "nonempty")
        return run

    results = run_independent_sources(
        "session-1", {source: producer(source) for source in FlagSource}
    )
    assert calls == list(FlagSource)
    assert results[FlagSource.CLIP_URGENCY].status == FlagStatus.FAILED
    assert results[FlagSource.VITALS_THRESHOLD].status == FlagStatus.FAILED
    assert results[FlagSource.TRANSCRIPT_KEYWORD].status == FlagStatus.SUCCESS_NONEMPTY


def test_resolved_fusion_policy_runs_in_paper_mode_and_preserves_all_source_statuses():
    artifacts = {source: artifact(source, "empty") for source in FlagSource}
    fused = fuse_flags(
        artifacts, merge_gap_seconds=10, merge_on_equal_gap=True,
        merge_policy_id="flag-fusion-v1.0.0", paper_mode=True,
    )
    assert fused.status == FlagStatus.SUCCESS_EMPTY
    assert fused.source_statuses == {
        source: FlagStatus.SUCCESS_EMPTY for source in FlagSource
    }


def test_merge_gap_boundary_is_inclusive_only_for_explicit_synthetic_policy():
    clip = artifact(FlagSource.CLIP_URGENCY, "nonempty")
    second = FlagRecord(
        "clip-2", FlagSource.CLIP_URGENCY, 3, 4, ("evidence-2",), "synthetic",
    )
    clip = FlagArtifact.success(
        session_id="session-1", source=FlagSource.CLIP_URGENCY,
        flags=[clip.flags[0], second], provenance={},
    )
    artifacts = {
        FlagSource.CLIP_URGENCY: clip,
        FlagSource.VITALS_THRESHOLD: artifact(FlagSource.VITALS_THRESHOLD, "empty"),
        FlagSource.TRANSCRIPT_KEYWORD: artifact(FlagSource.TRANSCRIPT_KEYWORD, "empty"),
    }
    assert len(fuse_flags(
        artifacts, merge_gap_seconds=1, merge_on_equal_gap=True,
        merge_policy_id="synthetic", paper_mode=False
    ).flags) == 1
    assert len(fuse_flags(
        artifacts, merge_gap_seconds=1, merge_on_equal_gap=False,
        merge_policy_id="synthetic", paper_mode=False
    ).flags) == 2
