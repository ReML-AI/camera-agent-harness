from copy import deepcopy

import pytest
from jsonschema import ValidationError

from scripts.analytics.assemble_multimodal_windows import (
    ATTENTION_LABELS,
    SEMANTIC_FIELDS,
    assemble_window,
    condition_context,
    format_window_text,
)
from scripts.core.errors import ContractError


def sample_window():
    return assemble_window(
        session_id="session-001", window_id="window-0032",
        start_seconds=480.0, end_seconds=510.0, flag_ids=["fused-1"],
        transcript=[{
            "evidence_id": "transcript-1", "speaker_id": "speaker-1",
            "role": "synthetic-role", "start_seconds": 481.2,
            "end_seconds": 484.5, "text": "synthetic utterance",
        }],
        speaker_dynamics={"evidence_id": "dynamics-1", "turn_count": 2},
        visual_scene={
            "evidence_id": "scene-1", "description": "synthetic scene", "camera_id": "cam2",
        },
        attention_records=[{
            "evidence_id": "attention-1", "aligned_timestamp_seconds": 486.0,
            "label": "patient", "camera_id": "cam2", "track_id": "track:cam2:1",
        }],
        attention_events=[],
        provenance={"source_artifact_sha256": "0" * 64},
    )


def test_assemble_window_has_exact_ordered_five_fields_and_coverage():
    window = sample_window()
    assert tuple(window["context"]) == SEMANTIC_FIELDS
    assert ATTENTION_LABELS == ("patient", "person", "other")
    assert window["context"]["visual_attention"]["labels"] == list(ATTENTION_LABELS)
    assert set(window["context"]["visual_attention"]["distribution"]) == set(ATTENTION_LABELS)
    assert set(window["context"]["modality_coverage"]) == {
        "evidence_id", "transcript", "speaker_dynamics", "visual_scene", "visual_attention"
    }


def test_t_and_m_only_differ_in_two_visual_fields_and_visual_coverage():
    window = sample_window()
    t_context = condition_context(window, "T")
    m_context = condition_context(window, "M")
    assert t_context["transcript"] == m_context["transcript"]
    assert t_context["speaker_dynamics"] == m_context["speaker_dynamics"]
    assert t_context["visual_scene"] == "not available"
    assert t_context["visual_attention"] == "not available"
    for field in ("transcript", "speaker_dynamics", "modality_coverage"):
        if field != "modality_coverage":
            assert t_context[field] == m_context[field]
    for field in ("transcript", "speaker_dynamics"):
        assert t_context["modality_coverage"][field] == m_context["modality_coverage"][field]


def test_render_includes_all_headings_and_modality_coverage_reaches_prompt():
    window = sample_window()
    for condition in ("T", "M"):
        text = format_window_text(window, condition=condition)
        assert "Transcript:" in text
        assert "Speaker dynamics:" in text
        assert "Visual scene:" in text
        assert "Visual attention:" in text
        assert "Modality coverage:" in text
        assert '"delivered"' in text
    assert "synthetic scene" not in format_window_text(window, condition="T")
    assert "synthetic scene" in format_window_text(window, condition="M")


def test_monitor_attention_cannot_reach_either_symmetric_renderer():
    stale = deepcopy(sample_window())
    stale["context"]["visual_attention"]["labels"] = [
        "patient", "monitor", "person", "other"
    ]
    stale["context"]["visual_attention"]["distribution"]["monitor"] = 0.0
    for condition in ("T", "M"):
        with pytest.raises(ValidationError):
            format_window_text(stale, condition=condition)

    with pytest.raises(ContractError, match="unsupported attention label"):
        assemble_window(
            session_id="session-001", window_id="window-monitor",
            start_seconds=0.0, end_seconds=30.0, flag_ids=["fused-1"],
            transcript=[], speaker_dynamics=None, visual_scene=None,
            attention_records=[{
                "evidence_id": "attention-monitor",
                "aligned_timestamp_seconds": 1.0,
                "label": "monitor",
            }],
            attention_events=[], provenance={},
        )


def _window_with_two_records_in_one_second():
    """Two attention records inside the same one-second thinning bucket."""
    return assemble_window(
        session_id="session-001", window_id="window-0032",
        start_seconds=480.0, end_seconds=510.0, flag_ids=["fused-1"],
        transcript=[],
        speaker_dynamics={"evidence_id": "dynamics-1", "turn_count": 2},
        visual_scene={
            "evidence_id": "scene-1", "description": "synthetic scene", "camera_id": "cam2",
        },
        attention_records=[
            {"evidence_id": "attention-kept", "aligned_timestamp_seconds": 486.10,
             "label": "patient", "camera_id": "cam2", "track_id": "track:cam2:1",
             "exact_frame_gate": "exact_frame_asd_positive"},
            {"evidence_id": "attention-thinned", "aligned_timestamp_seconds": 486.40,
             "label": "patient", "camera_id": "cam2", "track_id": "track:cam2:1",
             "exact_frame_gate": "exact_frame_asd_positive"},
        ],
        attention_events=[],
        provenance={"source_artifact_sha256": "0" * 64},
    )


def test_an_id_thinned_out_of_the_prompt_is_not_delivered_evidence():
    """Delivery must mean "reached the model", not "was stored in the envelope".

    Rendering applied the one-per-second attention thinning while citation validation
    indexed the unprojected context, so a record the model never saw still resolved as a
    delivered citation -- the provenance claim was audited against the wrong set.
    """
    from scripts.focal.evidence import delivered_evidence_index

    window = _window_with_two_records_in_one_second()
    prompt = format_window_text(window, condition="M")
    index = delivered_evidence_index([window], "M")

    assert "attention-thinned" not in prompt
    assert "attention-thinned" not in index
    # The surviving record must still be delivered, or the fix has emptied the stream.
    assert "attention-kept" in prompt
    assert "attention-kept" in index
