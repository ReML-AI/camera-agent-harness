import pytest

from scripts.core.errors import ContractError
from scripts.core.records import canonical_track_id
from scripts.diarization.link_speakers_multicam import (
    build_best_angle_artifact,
    build_identity_map,
)


def segment(speaker="speaker-a"):
    return {
        "transcript_segment_id": "segment-001",
        "speaker_id": speaker,
        "start_seconds": 0.0,
        "end_seconds": 1.0,
    }


def camera(camera_id, score=None, *, track="7"):
    if score is None:
        return {"tracks": []}
    return {
        "tracks": [{
            "track_id": canonical_track_id(camera_id, track),
            "samples": [
                {"frame_index": 0, "aligned_timestamp_seconds": 0.0, "score": score},
                {"frame_index": 1, "aligned_timestamp_seconds": 0.5, "score": score},
                # Half-open end: this sample must not affect the mean.
                {"frame_index": 2, "aligned_timestamp_seconds": 1.0, "score": -100.0},
            ],
        }]
    }


@pytest.mark.parametrize(
    ("scores", "expected"),
    [
        ((0.2, -0.9, None), "fully_linked"),  # any camera, not every camera
        ((-0.2, -0.9, None), "partially_linked"),
        ((-0.9, -0.7, None), "unlinked"),
        ((0.0, -0.9, None), "partially_linked"),  # equality does not pass tau_link
        ((-0.5, -0.9, None), "unlinked"),  # equality does not pass tau_weak
        ((None, None, None), "unlinked"),  # no vacuous all/no-data link
    ],
)
def test_contract_3_status_semantics(scores, expected):
    asd = {
        camera_id: (None if score is None else camera(camera_id, score))
        for camera_id, score in zip(("cam1", "cam2", "cam3"), scores)
    }
    result = build_identity_map([segment()], asd, session_id="session-001")
    assert result["speakers"][0]["link_status"] == expected
    assert result["summary"][expected] == 1


def test_selects_highest_track_per_camera_and_retains_counts():
    cam = camera("cam1", 0.2, track="low")
    cam["tracks"].append(camera("cam1", 0.8, track="high")["tracks"][0])
    result = build_identity_map([segment()], {"cam1": cam}, session_id="session-001")
    candidate = result["speakers"][0]["camera_candidates"][0]
    assert candidate["track_id"] == "track:cam1:high"
    assert candidate["mean_asd"] == pytest.approx(0.8)
    assert candidate["eligible_frame_count"] == 2


def test_rejects_legacy_ambiguous_track_identifier():
    with pytest.raises(ContractError, match="non-canonical|ambiguous"):
        build_identity_map(
            [segment()],
            {"cam1": {"tracks": [{"track_id": "person_0", "samples": []}]}},
            session_id="session-001",
        )


def test_segment_with_no_diarized_speaker_is_reported_not_fatal():
    """WhisperX speakerless segments are reported without inventing an identity."""
    segments = [
        {"transcript_segment_id": "segment-000000", "speaker_id": "SPEAKER_00",
         "start_seconds": 0.0, "end_seconds": 1.0},
        {"transcript_segment_id": "segment-000001",
         "start_seconds": 308.662, "end_seconds": 309.1},
    ]

    identity = build_identity_map(segments, {}, session_id="session_001")

    unassigned = identity["segments_without_diarized_speaker"]
    assert unassigned["count"] == 1
    assert unassigned["transcript_segment_ids"] == ["segment-000001"]
    # The speakerless segment contributes no speaker, so it cannot inflate the denominator.
    assert [speaker["speaker_id"] for speaker in identity["speakers"]] == ["SPEAKER_00"]


def test_best_angle_artifact_omits_segments_with_no_diarized_speaker():
    """A segment with no speaker cannot anchor a camera choice."""
    segments = [
        {"transcript_segment_id": "segment-000000", "speaker_id": "SPEAKER_00",
         "start_seconds": 0.0, "end_seconds": 1.0},
        {"transcript_segment_id": "segment-000001",
         "start_seconds": 308.662, "end_seconds": 309.1},
    ]
    identity = build_identity_map(segments, {}, session_id="session_001")

    artifact = build_best_angle_artifact("session_001", segments, identity, {})

    ids = [segment["transcript_segment_id"] for segment in artifact["segments"]]
    assert ids == ["segment-000000"]


def _multi_camera(camera_id, fragments):
    """Several tracks on one camera, each observed over its own interval."""
    return {"tracks": [
        {
            "track_id": canonical_track_id(camera_id, str(index + 1)),
            "samples": [
                {"frame_index": n, "aligned_timestamp_seconds": ts, "score": score}
                for n, (ts, score) in enumerate(samples)
            ],
        }
        for index, samples in enumerate(fragments)
    ]}


def test_speaker_links_to_every_qualifying_fragment_not_just_the_strongest():
    """Light-ASD restarts a track whenever a face is lost, so one person is many
    fragments. Every temporally qualifying fragment must remain available for selection.
    """
    segments = [
        {"transcript_segment_id": "segment-000000", "speaker_id": "SPEAKER_00",
         "start_seconds": 0.0, "end_seconds": 2.0},
        {"transcript_segment_id": "segment-000001", "speaker_id": "SPEAKER_00",
         "start_seconds": 100.0, "end_seconds": 102.0},
    ]
    asd = {
        "cam1": _multi_camera("cam1", [
            [(0.5, 0.9), (1.5, 0.9)],       # early fragment, strongest
            [(100.5, 0.4), (101.5, 0.4)],   # later fragment, weaker but real
        ]),
        "cam2": None,
        "cam3": None,
    }

    identity = build_identity_map(segments, asd, session_id="session_001")

    cam1 = next(c for c in identity["speakers"][0]["camera_candidates"]
                if c["camera_id"] == "cam1")
    assert len(cam1["linked_fragments"]) == 2
    assert cam1["track_id"] == canonical_track_id("cam1", "1")  # summary unchanged


def test_a_later_segment_selects_the_fragment_that_overlaps_it():
    """Later segments select the linked fragment that overlaps their interval."""
    segments = [
        {"transcript_segment_id": "segment-000000", "speaker_id": "SPEAKER_00",
         "start_seconds": 0.0, "end_seconds": 2.0},
        {"transcript_segment_id": "segment-000001", "speaker_id": "SPEAKER_00",
         "start_seconds": 100.0, "end_seconds": 102.0},
    ]
    asd = {
        "cam1": _multi_camera("cam1", [
            [(0.5, 0.9), (1.5, 0.9)],
            [(100.5, 0.4), (101.5, 0.4)],
        ]),
        "cam2": None,
        "cam3": None,
    }
    identity = build_identity_map(segments, asd, session_id="session_001")

    artifact = build_best_angle_artifact("session_001", segments, identity, asd)

    rows = {r["transcript_segment_id"]: r for r in artifact["segments"]}
    assert rows["segment-000000"]["selected_track_id"] == canonical_track_id("cam1", "1")
    assert rows["segment-000001"]["selected_track_id"] == canonical_track_id("cam1", "2")


def test_a_fragment_from_another_time_never_grounds_a_segment():
    """Fragments are not merged. Visual evidence recorded elsewhere in the session
    must not be offered as evidence for this segment.
    """
    segments = [
        {"transcript_segment_id": "segment-000000", "speaker_id": "SPEAKER_00",
         "start_seconds": 0.0, "end_seconds": 2.0},
        {"transcript_segment_id": "segment-000001", "speaker_id": "SPEAKER_00",
         "start_seconds": 500.0, "end_seconds": 502.0},
    ]
    asd = {"cam1": _multi_camera("cam1", [[(0.5, 0.9), (1.5, 0.9)]]), "cam2": None, "cam3": None}
    identity = build_identity_map(segments, asd, session_id="session_001")

    artifact = build_best_angle_artifact("session_001", segments, identity, asd)

    rows = {r["transcript_segment_id"]: r for r in artifact["segments"]}
    assert rows["segment-000001"]["selected_camera_id"] is None
    reasons = {s["reason"] for s in rows["segment-000001"]["camera_scores"]}
    assert "no_linked_fragment_overlaps_segment" in reasons


def test_a_segment_starting_on_the_fragment_last_sample_still_overlaps():
    """first_seen/last_seen are sample timestamps, not an exclusive interval end.

    Treating last_seen as exclusive made the prefilter reject a segment beginning exactly
    on that sample while _eligible_scores, testing start <= t < end, still scored it --
    the prefilter and the scorer disagreeing about the same sample.
    """
    from scripts.core.records import Interval
    from scripts.diarization.link_speakers_multicam import _fragment_overlaps

    fragment = {"first_seen_seconds": 10.0, "last_seen_seconds": 20.0}

    assert _fragment_overlaps(fragment, Interval(20.0, 22.0)) is True
    assert _fragment_overlaps(fragment, Interval(20.5, 22.0)) is False
