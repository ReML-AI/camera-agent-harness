import pytest

from scripts.flags.vitals import VitalThresholdFlagger, VitalThresholds


@pytest.fixture
def flagger():
    return VitalThresholdFlagger(
        {"synthetic_vital": VitalThresholds(40, 100, 30, 120)},
        policy_id="synthetic-vitals-policy",
    )


def record(value):
    return {
        "evidence_id": f"ocr-{value}", "start_seconds": 1, "end_seconds": 2,
        "raw_ocr_text": {"synthetic_vital": str(value)},
        "values": {"synthetic_vital": value}, "source_frame": 25,
    }


@pytest.mark.parametrize("value", [40, 100])
def test_warning_threshold_boundaries_are_non_anomalous(flagger, value):
    assert flagger.run("session-1", [record(value)]).status.value == "success_empty"


@pytest.mark.parametrize(
    ("value", "severity"), [
        (29, "critical"), (30, "warning"), (39, "warning"),
        (101, "warning"), (120, "warning"), (121, "critical"),
    ]
)
def test_threshold_records_retain_raw_ocr_thresholds_and_source_frame(flagger, value, severity):
    flag = flagger.run("session-1", [record(value)]).flags[0]
    assert flag.payload["severity"] == severity
    assert flag.payload["raw_ocr_text"] == str(value)
    assert flag.payload["source_frame"] == 25
    assert flag.payload["thresholds"] == {
        "low": 40, "high": 100, "critical_low": 30, "critical_high": 120,
    }
