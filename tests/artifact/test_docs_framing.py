from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PAPER_TITLE = (
    "Expert Vision Agent Harness: Verifiable Multi-View Evidence for "
    "Clinical Simulation Debriefing"
)


def _normalized_readme() -> str:
    return " ".join((ROOT / "README.md").read_text(encoding="utf-8").split())


def test_readme_opens_with_the_current_scope_and_governance_boundary():
    opening = _normalized_readme()[:2200].lower()
    for phrase in (
        PAPER_TITLE.lower(),
        "expert vision",
        "agent harness",
        "nine-session governed-data evaluation",
        "participant-protecting governance",
        "authorized environment",
        "clinician assessments",
        "independent human evaluation",
    ):
        assert phrase in opening, f"README opening no longer states: {phrase!r}"


def test_readme_locks_recurring_architecture_facts():
    text = _normalized_readme()
    assert "21 per-session stages plus one cohort aggregation stage" in text
    assert "five semantic context fields" in text
    assert "`patient`, `person`, `other`" in text


def test_readme_states_governance_and_local_prototype_limit():
    text = _normalized_readme().lower()
    assert "no raw clinical recording" in text
    assert "trusted-workstation use" in text
    assert "production deployment" in text
    assert "authentication" in text
    assert "127.0.0.1" in text


def test_public_pipeline_distributes_no_session_role_defaults():
    assert not (ROOT / "scripts" / "analytics" / "speaker_config.py").exists()
    context_source = (ROOT / "scripts" / "analytics" / "compute_moment_context.py").read_text(
        encoding="utf-8"
    )
    assert "speaker_roles = {}" in context_source


def test_readme_declares_release_license():
    text = _normalized_readme()
    assert "AGPL-3.0-only" in text
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "GNU AFFERO GENERAL PUBLIC LICENSE" in license_text
    assert "Version 3, 19 November 2007" in license_text
