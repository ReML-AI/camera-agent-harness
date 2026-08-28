from scripts.analytics.assemble_multimodal_windows import (
    SEMANTIC_FIELDS,
    condition_context,
)
from scripts.focal.prompt import PromptArtifacts, render_prompt
from tests.test_multimodal_windows import sample_window


def test_t_m_use_same_checked_template_and_ordered_headings():
    artifacts = PromptArtifacts.load()
    window = sample_window()
    prompts = {
        condition: render_prompt(
            artifacts, condition=condition, windows=[window],
            session_duration_seconds=600, speakers=[{"speaker_id": "speaker-1"}],
            category_taxonomy=[f"synthetic-{i}" for i in range(7)],
        )
        for condition in ("T", "M")
    }
    # Derived from the declared render order rather than hardcoded, so this test checks
    # that T and M share one order -- the symmetry the T/M contract rests on -- instead of
    # pinning whichever order happened to be in use. The order itself is a methodological
    # choice evaluated by the field-order sensitivity diagnostic.
    from scripts.analytics.assemble_multimodal_windows import PROMPT_FIELD_ORDER

    headings = {
        "transcript": "Transcript:", "speaker_dynamics": "Speaker dynamics:",
        "visual_scene": "Visual scene:", "visual_attention": "Visual attention:",
        "modality_coverage": "Modality coverage:",
    }
    expected = [headings[field] for field in PROMPT_FIELD_ORDER]
    for prompt in prompts.values():
        positions = [prompt.index(heading) for heading in expected]
        assert positions == sorted(positions)
    assert "synthetic scene" not in prompts["T"]
    assert "synthetic scene" in prompts["M"]
    assert '"evidence_id":"coverage-window-0032"' in prompts["T"]


def test_only_visual_values_and_their_coverage_indicators_differ():
    window = sample_window()
    t = condition_context(window, "T")
    m = condition_context(window, "M")
    differing = {field for field in SEMANTIC_FIELDS if t[field] != m[field]}
    assert differing == {"visual_scene", "visual_attention", "modality_coverage"}
    for field in ("transcript", "speaker_dynamics"):
        assert t["modality_coverage"][field] == m["modality_coverage"][field]
    assert t["modality_coverage"]["evidence_id"] == m["modality_coverage"]["evidence_id"]
