"""Config/code contract for monitor OCR. Every fault here shipped undetected."""
import json
import re

import pytest

from scripts.extract_monitor_vitals import (
    PLAUSIBLE_VITAL_RANGE,
    UNTHRESHOLDED_VITALS,
    MonitorVitalsExtractor,
)

CONFIG_PATH = "configs/monitor_ocr_1920x1080.json"


def _config():
    with open(CONFIG_PATH, encoding="utf-8") as handle:
        return json.load(handle)


def test_every_roi_the_extractor_requests_exists_in_the_config():
    """The extractor asked for bp_sys/bp_dia while the config defined nbp_sys/nbp_dia.

    A missing name returned "", indistinguishable from "OCR found nothing", so blood
    pressure was silently never extracted across every session.
    """
    import inspect

    from scripts import extract_monitor_vitals

    source = inspect.getsource(extract_monitor_vitals.MonitorVitalsExtractor)
    requested = set(re.findall(r'extract_text_from_roi\(frame, "([a-z0-9_]+)"\)', source))
    configured = set(_config()["rois"])

    assert requested <= configured, f"requested but not configured: {requested - configured}"


def test_unknown_roi_name_raises_rather_than_returning_empty():
    extractor = MonitorVitalsExtractor.__new__(MonitorVitalsExtractor)
    extractor.rois = {"hr": [0, 0, 10, 10]}

    with pytest.raises(KeyError, match="no ROI named"):
        MonitorVitalsExtractor.extract_text_from_roi(extractor, None, "does_not_exist")


def test_every_extracted_vital_is_thresholded_or_declared_unthresholded():
    """A vital with neither an alarm band nor a declaration is a config mismatch."""
    config = _config()
    thresholded = set(config["thresholds"])
    extractable = set(config["rois"]) - {"alert_banner"}

    unchecked = extractable - thresholded - UNTHRESHOLDED_VITALS

    assert not unchecked, f"extracted but never alarm-checked: {sorted(unchecked)}"


def test_plausibility_bounds_are_wider_than_every_alarm_threshold():
    """These answer different questions: a misread is discarded, a real finding is not.

    If a plausibility bound were tighter than an alarm band, genuine deterioration
    would be silently thrown away as an OCR error.
    """
    thresholds = _config()["thresholds"]
    for vital, band in thresholds.items():
        bounds = PLAUSIBLE_VITAL_RANGE.get(vital)
        if bounds is None:
            continue
        low, high = bounds
        assert low <= band["critical_low"], f"{vital}: plausibility low clips the alarm band"
        assert high >= band["critical_high"], f"{vital}: plausibility high clips the alarm band"


def test_detect_anomalies_tolerates_the_metadata_the_caller_attaches():
    """process_video adds timestamp and frame_num before calling detect_anomalies.

    Treating every mapping key as a vital made the strict threshold check raise on the
    first sampled frame of every session, so stage 6 produced no artifact at all.
    """
    extractor = MonitorVitalsExtractor.__new__(MonitorVitalsExtractor)
    extractor.thresholds = {
        "hr": {"low": 50, "high": 120, "critical_low": 40, "critical_high": 150}
    }

    anomalies = MonitorVitalsExtractor.detect_anomalies(
        extractor, {"hr": 72.0, "timestamp": 0.0, "frame_num": 0, "alert": "x"}
    )

    assert anomalies == []


def test_a_vital_with_no_threshold_and_no_declaration_still_raises():
    extractor = MonitorVitalsExtractor.__new__(MonitorVitalsExtractor)
    extractor.thresholds = {}

    with pytest.raises(KeyError, match="no configured threshold"):
        MonitorVitalsExtractor.detect_anomalies(extractor, {"hr": 72.0})
