from scripts.core.records import canonical_track_id
from scripts.diarization.link_speakers_multicam import (
    build_identity_map, gate_best_angle_frames, select_best_angle,
)


def test_synthetic_identity_selection_and_gate_flow():
    segment = {
        "transcript_segment_id": "segment-001", "speaker_id": "speaker-a",
        "start_seconds": 0.0, "end_seconds": 1.0,
    }
    track = canonical_track_id("cam2", "17")
    asd = {
        "cam1": None,
        "cam2": {"tracks": [{"track_id": track, "samples": [
            {"frame_index": 4, "aligned_timestamp_seconds": 0.4, "score": 0.7},
            {"frame_index": 5, "aligned_timestamp_seconds": 0.5, "score": 0.0},
        ]}]},
        "cam3": None,
    }
    identity = build_identity_map([segment], asd, session_id="synthetic-session")
    selection = select_best_angle(segment, identity, asd)
    gated = gate_best_angle_frames(
        selection,
        asd_samples=[
            {"camera_id": "cam2", "track_id": track, "frame_index": 4, "score": 0.7},
            {"camera_id": "cam2", "track_id": track, "frame_index": 5, "score": 0.0},
        ],
        head_pose_samples=[
            {"camera_id": "cam2", "track_id": track, "frame_index": 4, "aligned_timestamp_seconds": 0.4, "yaw": 10},
            {"camera_id": "cam2", "track_id": track, "frame_index": 5, "aligned_timestamp_seconds": 0.5, "yaw": 11},
        ],
    )
    assert identity["speakers"][0]["link_status"] == "fully_linked"
    assert selection["selected_camera_id"] == "cam2"
    assert [item["frame_index"] for item in gated["emitted"]] == [4]

