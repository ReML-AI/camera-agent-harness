import pytest

from scripts.reid.embeddings import (
    average_then_l2_normalize,
    select_temporally_stratified,
)


def test_crop_selection_is_temporally_stratified_not_confidence_ranked():
    observations = [
        {
            "frame_index": index,
            "presentation_timestamp_seconds": float(index),
            "confidence": 1.0 if index < 3 else 0.1,
        }
        for index in range(10)
    ]
    selected = select_temporally_stratified(observations, maximum_crops=3)

    selected_frames = [item["frame_index"] for item in selected]
    assert len(selected_frames) == 3
    assert selected_frames[0] < 3
    assert 3 <= selected_frames[1] <= 6
    assert selected_frames[2] >= 7
    assert selected_frames != [0, 1, 2]
    assert selected_frames == [item["frame_index"] for item in select_temporally_stratified(
        reversed(observations), maximum_crops=3
    )]


def test_osnet_outputs_are_averaged_before_l2_normalization():
    result = average_then_l2_normalize([(2.0, 0.0), (0.0, 2.0)])
    assert result == pytest.approx((2 ** -0.5, 2 ** -0.5))
