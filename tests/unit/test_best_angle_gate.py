from scripts.core.records import canonical_track_id
from scripts.diarization.link_speakers_multicam import (
    build_best_angle_artifact,
    build_identity_map,
    gate_best_angle_frames,
    select_best_angle,
)


def _segment(segment_id, start, end):
    return {
        "transcript_segment_id": segment_id,
        "speaker_id": "speaker-a",
        "start_seconds": start,
        "end_seconds": end,
    }


def _camera(camera_id, samples):
    return {"tracks": [{
        "track_id": canonical_track_id(camera_id, "1"),
        "samples": [
            {"frame_index": index, "aligned_timestamp_seconds": timestamp, "score": score}
            for index, (timestamp, score) in enumerate(samples)
        ],
    }]}


def test_best_camera_can_change_per_segment_and_all_camera_scores_are_retained():
    segments = [_segment("seg-1", 0, 1), _segment("seg-2", 1, 2)]
    asd = {
        "cam1": _camera("cam1", [(0.2, 0.8), (1.2, 0.1)]),
        "cam2": _camera("cam2", [(0.2, 0.2), (1.2, 0.9)]),
        "cam3": None,
    }
    identity = build_identity_map(segments, asd, session_id="session-001")
    first = select_best_angle(segments[0], identity, asd)
    second = select_best_angle(segments[1], identity, asd)
    assert first["selected_camera_id"] == "cam1"
    assert second["selected_camera_id"] == "cam2"
    assert [row["camera_id"] for row in first["camera_scores"]] == ["cam1", "cam2", "cam3"]


def test_per_frame_gate_is_strict_selected_camera_only_and_has_no_fallback():
    track1, track2 = canonical_track_id("cam1", "1"), canonical_track_id("cam2", "1")
    selection = {"selected_camera_id": "cam1", "selected_track_id": track1}
    asd = [
        {"camera_id": "cam1", "track_id": track1, "frame_index": 1, "score": 0.1},
        {"camera_id": "cam1", "track_id": track1, "frame_index": 2, "score": 0.0},
        {"camera_id": "cam2", "track_id": track2, "frame_index": 2, "score": 0.9},
    ]
    poses = [
        {"camera_id": "cam1", "track_id": track1, "frame_index": 1, "aligned_timestamp_seconds": 0.1, "yaw": 1},
        {"camera_id": "cam1", "track_id": track1, "frame_index": 2, "aligned_timestamp_seconds": 0.2, "yaw": 2},
        {"camera_id": "cam1", "track_id": track1, "frame_index": 3, "aligned_timestamp_seconds": 0.3, "yaw": 3},
        {"camera_id": "cam2", "track_id": track2, "frame_index": 2, "aligned_timestamp_seconds": 0.2, "yaw": 99},
    ]
    result = gate_best_angle_frames(selection, asd_samples=asd, head_pose_samples=poses)
    assert [sample["frame_index"] for sample in result["emitted"]] == [1]
    assert result["reason_counts"] == {"asd_not_strictly_positive": 1, "missing_asd": 1}


def test_no_selected_camera_emits_nothing():
    result = gate_best_angle_frames(
        {"selected_camera_id": None, "selected_track_id": None},
        asd_samples=[], head_pose_samples=[],
    )
    assert result["emitted"] == []
    assert result["reason_counts"] == {"no_selected_camera": 1}


def test_best_angle_schema_round_trip_preserves_segment_and_track_namespaces():
    segments = [_segment("seg-identity-roundtrip", 0, 1)]
    asd = {"cam1": _camera("cam1", [(0.2, 0.8)]), "cam2": None, "cam3": None}
    identity = build_identity_map(segments, asd, session_id="session-001")
    artifact = build_best_angle_artifact("session-001", segments, identity, asd)
    row = artifact["segments"][0]
    assert row["transcript_segment_id"] == "seg-identity-roundtrip"
    assert row["selected_track_id"] == "track:cam1:1"
