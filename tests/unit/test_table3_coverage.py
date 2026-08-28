import pytest

from scripts.metrics.definitions import (
    compute_table3_coverage,
    project_segment_assignments_to_bins,
)


def _gate(timestamp, score):
    return {
        "frame_index": round(timestamp * 10),
        "aligned_timestamp_seconds": timestamp,
        "asd_score": score,
        "emitted": score is not None and score > 0.0,
        "reason": None if score is not None and score > 0.0 else "gate_failed",
    }


def _artifact(*segments):
    rows = []
    for segment_id, start, end, camera, gates in segments:
        rows.append(
            {
                "transcript_segment_id": segment_id,
                "speaker_id": f"speaker-{segment_id}",
                "start_seconds": start,
                "end_seconds": end,
                "camera_scores": [
                    {
                        "camera_id": candidate,
                        "track_id": f"track:{candidate}:1" if candidate == camera else None,
                        "mean_asd": 0.5 if candidate == camera else None,
                        "eligible_frame_count": len(gates) if candidate == camera else 0,
                        "reason": None if candidate == camera else "not_selected",
                    }
                    for candidate in ("cam1", "cam2", "cam3")
                ],
                "selected_camera_id": camera,
                "selected_track_id": f"track:{camera}:1" if camera else None,
                "frame_gate": [_gate(timestamp, score) for timestamp, score in gates],
            }
        )
    return {"schema_version": "1.0.0", "session_id": "session-001", "segments": rows}


def _asd_for(best_angle):
    tracks_by_camera = {"cam1": {}, "cam2": {}, "cam3": {}}
    for segment in best_angle["segments"]:
        camera = segment["selected_camera_id"]
        track_id = segment["selected_track_id"]
        if camera is None:
            continue
        samples = tracks_by_camera[camera].setdefault(track_id, [])
        samples.extend(
            {
                "frame_index": item["frame_index"],
                "aligned_timestamp_seconds": item["aligned_timestamp_seconds"],
                "score": item["asd_score"],
            }
            for item in segment["frame_gate"]
        )
    return {
        camera: {
            "tracks": [
                {"track_id": track_id, "samples": samples}
                for track_id, samples in camera_tracks.items()
            ]
        }
        for camera, camera_tracks in tracks_by_camera.items()
    }


BEST_ANGLE = _artifact(
    ("seg-0", 0, 1, "cam1", [(0.2, 0.9)]),
    ("seg-1", 1, 2, "cam2", [(1.2, 0.7)]),
    ("seg-2", 2, 3, "cam2", [(2.2, 0.7)]),
    ("seg-3", 3, 4, "cam1", [(3.2, 0.2)]),
)


@pytest.mark.parametrize(
    ("signal", "present"),
    [
        (
            "asd",
            {
                "cam1": [True, False, True, False],
                "cam2": [False, True, True, True],
                "cam3": [False, True, False, False],
            },
        ),
        (
            "face",
            {
                "cam1": [True, True, False, False],
                "cam2": [False, True, True, True],
                "cam3": [True, False, True, False],
            },
        ),
        (
            "head_pose",
            {
                "cam1": [False, True, False, True],
                "cam2": [True, False, False, True],
                "cam3": [False, True, True, False],
            },
        ),
    ],
)
def test_union_is_at_least_selected_for_every_table3_signal(signal, present):
    result = compute_table3_coverage(signal, present, BEST_ANGLE, _asd_for(BEST_ANGLE))

    assert result.selected_covered_bins <= result.union_covered_bins
    assert len(result.union_covered_bins) >= len(result.selected_covered_bins)


def test_confidence_gate_removes_selected_signal_even_when_a_camera_has_it():
    face = {
        "cam1": [True, True, True],
        "cam2": [False, False, True],
        "cam3": [False, False, False],
    }
    best_angle = _artifact(
        ("seg-0", 0, 1, "cam1", [(0.2, 0.8)]),
        ("seg-1", 1, 2, "cam1", [(1.2, 0.0)]),
        ("seg-2", 2, 3, "cam1", [(2.2, None)]),
    )

    result = compute_table3_coverage("face", face, best_angle, _asd_for(best_angle))

    assert result.union_covered_bins == frozenset({0, 1, 2})
    assert result.selected_covered_bins == frozenset({0})
    assert result.selected_gate_passed_bins == frozenset({0})
    assert result.selected_gate_failed_bins == frozenset({1, 2})


def test_segment_projection_uses_fixed_stage3_camera_across_bins():
    present = {
        "cam1": [True, False],
        "cam2": [False, True],
        "cam3": [False, False],
    }
    best_angle = _artifact(
        ("seg-long", 0, 2, "cam1", [(0.2, 0.2), (1.2, 0.1)]),
    )
    asd = _asd_for(best_angle)
    asd["cam2"]["tracks"].append(
        {
            "track_id": "track:cam2:unrelated",
            "samples": [{"aligned_timestamp_seconds": 1.2, "score": 0.99}],
        }
    )

    result = compute_table3_coverage("asd", present, best_angle, asd)

    assert result.selected_segments_by_bin == (
        (("seg-long", "cam1"),),
        (("seg-long", "cam1"),),
    )
    assert result.union_covered_bins == frozenset({0, 1})
    assert result.selected_covered_bins == frozenset({0})


def test_projection_uses_half_open_intervals_and_preserves_overlapping_segments():
    best_angle = _artifact(
        ("seg-a", 0.25, 2.0, "cam1", [(0.3, 0.2)]),
        ("seg-b", 1.8, 2.2, "cam2", [(1.9, 0.3)]),
    )

    projected = project_segment_assignments_to_bins(best_angle, 4)

    assert projected == (
        (("seg-a", "cam1"),),
        (("seg-a", "cam1"), ("seg-b", "cam2")),
        (("seg-b", "cam2"),),
        (),
    )


def test_inter_segment_bins_stay_in_shared_denominator_and_fail_selected_closed():
    present = {
        "cam1": [True, True, True, True],
        "cam2": [False, False, True, False],
        "cam3": [False, False, False, False],
    }
    best_angle = _artifact(
        ("seg-0", 0.1, 0.9, "cam1", [(0.2, 0.5)]),
        ("seg-2", 2.1, 2.8, "cam2", [(2.2, 0.5)]),
    )

    result = compute_table3_coverage("head_pose", present, best_angle, _asd_for(best_angle))

    assert result.denominator_bins == 4
    assert result.inter_segment_bins == frozenset({1, 3})
    assert result.selected_covered_bins == frozenset({0, 2})
    assert result.rate(result.union_covered_bins) == 1.0
    assert result.rate(result.selected_covered_bins) == 0.5
    assert result.selected_gate_failed_bins == frozenset()


def test_union_selected_gap_is_allowed_to_be_zero():
    present = {
        "cam1": [True, False],
        "cam2": [False, True],
        "cam3": [False, False],
    }
    best_angle = _artifact(
        ("seg-0", 0, 1, "cam1", [(0.2, 0.4)]),
        ("seg-1", 1, 2, "cam2", [(1.2, 0.6)]),
    )

    result = compute_table3_coverage("asd", present, best_angle, _asd_for(best_angle))

    assert result.selected_covered_bins == result.union_covered_bins == frozenset({0, 1})
