from scripts.analytics.compute_video_overlay import (
    build_selected_speaking_intervals,
    build_speaker_map,
    get_active_speaking_tracks,
)
from scripts.diarization.compute_interaction_analytics import (
    build_selected_attention_segments,
    build_speaker_track_map,
    compute_speaker_stats,
)


def identity_map():
    return {
        "speakers": [
            {
                "speaker_id": "speaker-a",
                "link_status": "fully_linked",
                "camera_candidates": [
                    {"camera_id": "cam1", "track_id": "track:cam1:7", "status": "linked"},
                    {"camera_id": "cam2", "track_id": "track:cam2:4", "status": "weak"},
                ],
            },
            {
                "speaker_id": "speaker-b",
                "link_status": "unlinked",
                "camera_candidates": [
                    {"camera_id": "cam1", "track_id": "track:cam1:9", "status": "rejected"},
                ],
            },
        ]
    }


def test_interaction_stats_resolve_stage8_camera_candidate_tracks():
    segments = [
        {"speaker": "speaker-a", "start": 0.0, "end": 1.5},
        {"speaker": "speaker-b", "start": 2.0, "end": 3.0},
    ]

    assert build_speaker_track_map(identity_map(), "cam1") == {
        "speaker-a": "track:cam1:7"
    }
    stats = compute_speaker_stats(segments, identity_map(), "cam1")
    assert stats["speaker-a"]["visual_track"] == "track:cam1:7"
    assert stats["speaker-b"]["visual_track"] is None


def test_overlay_uses_identity_map_for_tracks_and_stage3_for_segment_camera():
    best_angles = {
        "segments": [
            {
                "transcript_segment_id": "segment-a",
                "speaker_id": "speaker-a",
                "start_seconds": 0.0,
                "end_seconds": 1.0,
                "selected_camera_id": "cam2",
                "selected_track_id": "track:cam2:4",
            },
            {
                "transcript_segment_id": "segment-b",
                "speaker_id": "speaker-a",
                "start_seconds": 1.0,
                "end_seconds": 2.0,
                "selected_camera_id": "cam1",
                "selected_track_id": "track:cam1:7",
            },
        ]
    }

    assert build_speaker_map(identity_map(), "cam1") == {
        "speaker-a": "track:cam1:7"
    }
    intervals = build_selected_speaking_intervals(best_angles, "cam1")
    assert [item["transcript_segment_id"] for item in intervals] == ["segment-b"]
    assert get_active_speaking_tracks(0.5, intervals) == set()
    assert get_active_speaking_tracks(1.0, intervals) == {"track:cam1:7"}
    assert get_active_speaking_tracks(2.0, intervals) == set()

    attention_segments = build_selected_attention_segments(best_angles, "cam1")
    assert attention_segments == [{
        "speaker": "speaker-a",
        "start": 1.0,
        "end": 2.0,
        "selected_track_id": "track:cam1:7",
    }]
