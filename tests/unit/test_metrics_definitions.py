"""Projection of best-angle segments onto the canonical Table 3 grid."""
import pytest

from scripts.metrics.definitions import project_segment_assignments_to_bins



def test_segment_overshooting_the_grid_is_scored_over_its_intersection():
    """The grid spans the shortest stream; ASR on a longer stream can end just past it.

    A real run failed entirely because one segment ended 57ms beyond a 180s grid. The
    in-grid portion is scored, exactly as an interior segment's portion is.
    """
    artifact = {"segments": [{
        "transcript_segment_id": "segment-000082",
        "start_seconds": 177.809,
        "end_seconds": 180.057,
        "selected_camera_id": "cam1",
    }]}

    projected = project_segment_assignments_to_bins(artifact, 180)

    assert projected[179] == (("segment-000082", "cam1"),)
    assert len(projected) == 180


def test_segment_starting_beyond_the_grid_still_fails():
    """No intersection to score, and too far out to be a boundary rounding effect."""
    artifact = {"segments": [{
        "transcript_segment_id": "segment-000099",
        "start_seconds": 190.0,
        "end_seconds": 191.0,
        "selected_camera_id": "cam1",
    }]}

    with pytest.raises(ValueError, match="outside the canonical grid"):
        project_segment_assignments_to_bins(artifact, 180)
