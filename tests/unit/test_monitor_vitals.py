import pytest

from scripts.extract_monitor_vitals import MonitorVitalsExtractor, iter_sampled_frames


@pytest.fixture
def extractor():
    instance = MonitorVitalsExtractor.__new__(MonitorVitalsExtractor)
    instance.thresholds = {
        "hr": {"low": 40, "high": 150, "critical_low": 35, "critical_high": 180},
        "spo2": {"low": 90, "high": 100, "critical_low": 85, "critical_high": 100},
    }
    return instance


@pytest.mark.parametrize(
    ("text", "kind", "expected"),
    [("HR 72", "hr", 72.0), ("SpO2: 88%", "spo2", 88.0), ("noise", "hr", None), ("SpO2 102", "spo2", None)],
)
def test_parse_vital_value(extractor, text, kind, expected):
    assert extractor.parse_vital_value(text, kind) == expected


def test_threshold_boundaries_are_not_anomalies(extractor):
    assert extractor.detect_anomalies({"hr": 40, "spo2": 90}) == []


def test_warning_and_critical_are_counted_from_explicit_config(extractor):
    anomalies = extractor.detect_anomalies({"hr": 39, "spo2": 84})
    assert [(item["vital"], item["severity"]) for item in anomalies] == [
        ("hr", "warning"), ("spo2", "critical")
    ]


def test_constructor_refuses_missing_config_before_importing_easyocr():
    with pytest.raises(ValueError, match="explicit rois and thresholds"):
        MonitorVitalsExtractor({"schema_version": "1.0.0"}, device="cpu")


class _Capture:
    def __init__(self, frame_count):
        self.frame_count = frame_count
        self.position = -1
        self.grab_calls = 0
        self.retrieve_calls = 0

    def isOpened(self):
        return True

    def grab(self):
        if self.position + 1 >= self.frame_count:
            return False
        self.position += 1
        self.grab_calls += 1
        return True

    def retrieve(self):
        self.retrieve_calls += 1
        return True, f"frame-{self.position}"


def test_monitor_sampling_advances_all_frames_but_retrieves_only_samples():
    capture = _Capture(31)

    sampled = list(iter_sampled_frames(capture, 6))

    assert sampled == [(index, f"frame-{index}") for index in (0, 6, 12, 18, 24, 30)]
    assert capture.grab_calls == 31
    assert capture.retrieve_calls == len(sampled)
