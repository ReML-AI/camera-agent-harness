

def test_failed_run_never_reports_every_stage_passed():
    """A stage that dies before being recorded must not read as success.

    Stage 6 once failed on argument validation, so it never entered the manifest and an
    all() over the surviving stages reported "Every stage passed: yes" for a run that
    exited non-zero. Run status is authoritative.
    """
    from scripts.run_manifest.summary import format_run_summary

    document = {
        "run_id": "run-test",
        "status": "failed",
        "alignment_tolerance_seconds": 0.05,
        "sessions": {
            "session_001": {
                "alignment_within_tolerance": True,
                # only the stages that got far enough to be recorded
                "stages": {
                    "1_diarization": {"status": "passed", "exit_status": 0},
                    "2_person_tracking": {"status": "passed", "exit_status": 0},
                },
            }
        },
    }
    assert "Every stage passed: no" in format_run_summary(document)
