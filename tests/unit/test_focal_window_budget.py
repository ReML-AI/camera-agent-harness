"""Windows are selected to fit the focal context, never truncated by the backend."""
from types import SimpleNamespace

import pytest

from scripts.analytics.assemble_multimodal_windows import (
    WINDOW_SECONDS,
    assemble_window,
    WINDOW_SLIDE_SECONDS,
    focal_window_budget_chars,
    select_windows_within_budget,
)


def _flag(flag_id, sources, criticals=0):
    contributions = []
    for index, source in enumerate(sources):
        payload = {"severity": "critical"} if index < criticals else {}
        contributions.append(SimpleNamespace(source=source, payload=payload))
    return SimpleNamespace(flag_id=flag_id, contributions=contributions)


def _window(window_id, start, flag_ids):
    """Build through the real constructor so the schema contract is exercised."""
    return assemble_window(
        session_id="session_001",
        window_id=window_id,
        start_seconds=float(start),
        end_seconds=float(start) + WINDOW_SECONDS,
        flag_ids=list(flag_ids),
        transcript=[{
            "evidence_id": f"transcript-{window_id}",
            "speaker_id": "SPEAKER_00",
            "start_seconds": float(start) + 1.0,
            "end_seconds": float(start) + 2.0,
            "text": "synthetic utterance",
        }],
        speaker_dynamics={"evidence_id": f"dynamics-{window_id}", "turn_count": 1},
        visual_scene=None,
        attention_records=[],
        attention_events=[],
        provenance={},
    )


def test_windows_tile_without_overlap():
    """A 15s slide on 30s windows delivered every transcript segment twice."""
    assert WINDOW_SLIDE_SECONDS == WINDOW_SECONDS


def test_everything_is_delivered_when_it_fits():
    windows = [_window("window-0000", 0, ["f1"]), _window("window-0001", 30, ["f1"])]
    flags = [_flag("f1", ["vitals_threshold"])]

    delivered, accounting = select_windows_within_budget(windows, flags)

    assert len(delivered) == 2
    assert accounting["withheld_window_count"] == 0


def test_multi_source_corroboration_outranks_a_single_noisy_source():
    """Vitals alone emits hundreds of one-second flags in a deteriorating scenario.

    A window three independent sources implicate is better evidence than one flagged
    many times by vitals only, so it must survive a budget that cannot hold both.
    """
    windows = [_window("window-0000", 0, ["noisy"]), _window("window-0001", 30, ["broad"])]
    flags = [
        _flag("noisy", ["vitals_threshold"] * 50),
        _flag("broad", ["vitals_threshold", "transcript_keyword", "clip_urgency"]),
    ]
    # Budget for exactly one window, so the ranking alone decides which survives.
    from scripts.analytics.assemble_multimodal_windows import format_window_text
    cost = max(
        len(format_window_text(window, condition=condition))
        for window in windows
        for condition in ("T", "M")
    )

    delivered, accounting = select_windows_within_budget(windows, flags, budget_chars=cost)

    assert [window["window_id"] for window in delivered] == ["window-0001"]
    assert accounting["withheld_window_ids"] == ["window-0000"]


def test_withheld_windows_are_accounted_not_silently_dropped():
    windows = [_window(f"window-{n:04d}", n * 30, ["f1"]) for n in range(6)]
    flags = [_flag("f1", ["vitals_threshold"])]

    delivered, accounting = select_windows_within_budget(windows, flags, budget_chars=1)

    assert delivered == []
    assert accounting["withheld_window_count"] == 6
    assert accounting["assembled_window_count"] == 6
    assert accounting["delivered_seconds"] == 0
    assert accounting["assembled_seconds"] == pytest.approx(6 * WINDOW_SECONDS)


def test_delivered_windows_are_returned_in_session_order():
    windows = [_window(f"window-{n:04d}", n * 30, ["f1"]) for n in range(4)]
    flags = [_flag("f1", ["vitals_threshold"])]

    delivered, _ = select_windows_within_budget(windows, flags)

    assert [w["start_seconds"] for w in delivered] == sorted(w["start_seconds"] for w in delivered)


def test_budget_reserves_room_for_the_completion():
    """A prompt filling the whole context leaves nothing for the model to answer with."""
    assert focal_window_budget_chars() < 32768 * 2.5


def test_attention_records_are_projected_for_the_prompt():
    """Attention records repeated calibration provenance on every sample.

    On session_001 that made visual_attention 68,751 characters in one window --
    larger than the entire focal budget -- so windows carrying attention crowded out
    the rest of the session and delivery fell from 23 windows to 8.
    """
    from scripts.analytics.assemble_multimodal_windows import _prompt_attention

    value = {
        "labels": ["patient", "person", "other"],
        "distribution": {"patient": 1.0, "person": 0.0, "other": 0.0},
        "events": [{"evidence_id": "attention-event-000005"}],
        "records": [{
            "evidence_id": "attention-segment-000134-cam3-9004",
            "aligned_timestamp_seconds": 360.16,
            "label": "patient",
            "camera_id": "cam3",
            "angular_distance_degrees": 58.78,
            "assignment_procedure_id": "image-box-attention-assignment-v2.0.0",
            "calibration_session_id": "session_001",
            "calibration_version": "1.0.0",
            "raw_label": "patient",
        }],
    }

    projected = _prompt_attention(value)

    assert projected["records"] == [{
        "evidence_id": "attention-segment-000134-cam3-9004",
        "aligned_timestamp_seconds": 360.16,
        "label": "patient",
        "camera_id": "cam3",
    }]
    # The compact summary and events are already small and pass through untouched.
    assert projected["distribution"] == value["distribution"]
    assert projected["events"] == value["events"]


def test_attention_projection_leaves_unexpected_shapes_alone():
    from scripts.analytics.assemble_multimodal_windows import _prompt_attention

    assert _prompt_attention("not available") == "not available"
    assert _prompt_attention({"distribution": {}}) == {"distribution": {}}


def test_attention_records_are_thinned_to_about_one_per_second():
    """Attention is sampled at the pose rate, ~110 records per 30s window.

    A finer trace than the question needs consumed most of the context budget, so
    delivered-window coverage collapsed. Unlike the field projection this loses
    resolution, so it is stated explicitly rather than folded in.
    """
    from scripts.analytics.assemble_multimodal_windows import _thin_attention_records

    records = [
        {"evidence_id": f"attention-{n}", "aligned_timestamp_seconds": 100.0 + n * 0.2}
        for n in range(25)
    ]

    kept = _thin_attention_records(records, per_second=1.0)

    assert len(kept) == 5
    assert [r["aligned_timestamp_seconds"] for r in kept] == [100.0, 101.0, 102.0, 103.0, 104.0]


def test_thinning_keeps_records_that_carry_no_timestamp():
    from scripts.analytics.assemble_multimodal_windows import _thin_attention_records

    records = [{"evidence_id": "attention-x"}]
    assert _thin_attention_records(records, per_second=1.0) == records


def test_coverage_does_not_repeat_ids_already_present_in_the_records():
    """Coverage recursed the whole window, repeating all ~110 attention ids."""
    from scripts.analytics.assemble_multimodal_windows import _prompt_coverage

    coverage = {
        "evidence_id": "coverage-window-0000",
        "visual_attention": {"present": True, "delivered": True,
                             "evidence_ids": ["attention-1", "attention-2"]},
        "transcript": {"present": True, "delivered": True, "evidence_ids": ["segment-1"]},
    }

    reduced = _prompt_coverage(coverage)

    assert reduced["evidence_id"] == "coverage-window-0000"
    assert reduced["visual_attention"] == {"present": True, "delivered": True}
    assert "evidence_ids" not in reduced["transcript"]


def test_visual_scene_is_citable():
    """Scene records carried no evidence_id, so coverage reported the channel present
    with an empty id list: delivered to the model but impossible to cite. That capped
    the cross-modal evidence metric at whatever attention alone could supply.
    """
    from scripts.analytics.assemble_multimodal_windows import _scene_with_evidence_id
    from scripts.core.records import ID_RE

    scene = _scene_with_evidence_id(
        {"start": 60.0, "end": 70.0, "description": "team repositioning patient"}
    )

    assert "evidence_id" in scene
    assert ID_RE.fullmatch(scene["evidence_id"]), "scene id must satisfy the id contract"
    # Stable across runs: derived from the interval, not from position or time of run.
    again = _scene_with_evidence_id({"start": 60.0, "end": 70.0, "description": "other"})
    assert again["evidence_id"] == scene["evidence_id"]


def test_an_existing_scene_evidence_id_is_left_alone():
    from scripts.analytics.assemble_multimodal_windows import _scene_with_evidence_id

    scene = {"start": 1.0, "end": 2.0, "evidence_id": "scene-supplied"}
    assert _scene_with_evidence_id(scene)["evidence_id"] == "scene-supplied"


def test_delivery_is_measured_over_delivered_windows_only():
    """Metrics scanned every assembled window, counting evidence never shown to the model.

    On session_001 that reported 371 of 820 bins delivered when the 14 windows that fit
    the context budget support 153 -- a 2.4x overstatement of the harness's own headline
    delivery number.
    """
    from scripts.analytics.compute_paper_metrics import _delivered_windows

    artifact = {
        "windows": [
            {"window_id": "window-0000"}, {"window_id": "window-0001"},
            {"window_id": "window-0002"},
        ],
        "focal_delivery": {"delivered_window_ids": ["window-0000", "window-0002"]},
    }

    kept = [w["window_id"] for w in _delivered_windows(artifact)]

    assert kept == ["window-0000", "window-0002"]


def test_windows_without_a_delivery_record_all_count():
    """An artifact predating budget selection delivered everything it assembled."""
    from scripts.analytics.compute_paper_metrics import _delivered_windows

    artifact = {"windows": [{"window_id": "window-0000"}, {"window_id": "window-0001"}]}

    assert len(_delivered_windows(artifact)) == 2
