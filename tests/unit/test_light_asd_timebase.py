"""Light-ASD indices are 25 Hz. Consuming them at the source rate corrupted everything."""
import pytest

from scripts.core.errors import ContractError
from scripts.core.records import (
    LIGHT_ASD_ANALYSIS_FPS,
    light_asd_index_to_seconds,
    light_asd_index_to_source_frame,
)

SOURCE_FPS = 30000 / 1001  # 29.97002997, the rate of this study's cameras


def test_analysis_index_maps_to_true_session_time():
    """A 180.00s smoke clip yields max index 4500: 4500/25 == 180.00 exactly.

    Dividing the same index by the 29.97 source rate gives 150.15s, which would claim
    the clip is 30 seconds shorter than it is.
    """
    assert light_asd_index_to_seconds(4500) == pytest.approx(180.0)
    assert light_asd_index_to_seconds(4500) != pytest.approx(4500 / SOURCE_FPS)


def test_analysis_index_maps_to_the_source_frame_at_the_same_instant():
    """Seeking the source video with a raw analysis index reads the wrong moment."""
    source_frame = light_asd_index_to_source_frame(4500, SOURCE_FPS)

    assert source_frame == 5395
    assert source_frame / SOURCE_FPS == pytest.approx(180.0, abs=0.02)


def test_identity_holds_when_the_source_is_already_25_fps():
    assert light_asd_index_to_source_frame(1234, LIGHT_ASD_ANALYSIS_FPS) == 1234


def test_non_positive_source_fps_is_refused():
    with pytest.raises(ContractError, match="source fps must be positive"):
        light_asd_index_to_source_frame(10, 0.0)


def test_asd_assembly_timestamps_use_the_analysis_rate():
    """Pins the assembled artifact's contract, not just the helper."""
    import inspect

    from scripts.focal import pipeline_stages

    source = inspect.getsource(pipeline_stages)
    assert '"aligned_timestamp_seconds": light_asd_index_to_seconds(frame)' in source
    assert '"aligned_timestamp_seconds": float(frame) / fps' not in source


def test_windows_never_invent_a_speaker_for_an_undiarized_segment():
    """Stage 13 defaulted the speaker id to the literal string "UNKNOWN".

    That fabricated speaker was delivered to the focal model as though diarization had
    identified someone, and anything grouping on the field would count it as a person.
    """
    from scripts.analytics.assemble_multimodal_windows import _normalise_transcript

    normalised = _normalise_transcript({"segments": [
        {"transcript_segment_id": "segment-000000", "speaker": "SPEAKER_00",
         "start_seconds": 0.0, "end_seconds": 1.0},
        {"transcript_segment_id": "segment-000001",
         "start_seconds": 308.662, "end_seconds": 309.1},
    ]})

    assert normalised[0]["speaker_id"] == "SPEAKER_00"
    assert "speaker_id" not in normalised[1]


def test_head_pose_covers_every_track_selection_can_choose():
    """Head pose and best-angle selection must share one track universe.

    A 10s minimum-duration floor left pose available for 42 of 538 tracks on
    session_001, so 161 of 242 selected segments had no pose for their selected track
    and Stage 9 classified nothing at all. Selection considers any linked fragment,
    so pose cannot be restricted to long tracks.
    """
    import argparse
    import inspect

    from scripts.diarization import run_head_pose

    source = inspect.getsource(run_head_pose.main)
    parser = argparse.ArgumentParser()
    for line in source.splitlines():
        if "--min-track-duration" in line and "add_argument" in line:
            exec(line.strip().replace("parser.", "parser."), {"parser": parser})
    parsed = parser.parse_args([])

    assert parsed.min_track_duration == 0.0
