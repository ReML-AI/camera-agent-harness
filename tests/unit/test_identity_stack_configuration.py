from pathlib import Path

import re

import yaml

from scripts.reid.config import DEFAULT_CONFIG_PATH, load_identity_config


ROOT = Path(__file__).resolve().parents[2]


def test_thresholds_are_declared_as_unvalidated_configuration():
    text = DEFAULT_CONFIG_PATH.read_text(encoding="utf-8")
    assert "UNVALIDATED DEFAULTS PENDING CALIBRATION" in text
    config = load_identity_config()
    assert config.within_camera.similarity_threshold > config.cross_camera.similarity_threshold


def test_pinned_botsort_config_and_model_manifest_entries_exist():
    tracker_path = ROOT / "scripts/person_tracking/botsort_identity_stack.yaml"
    tracker = yaml.safe_load(tracker_path.read_text(encoding="utf-8"))
    assert tracker["tracker_type"] == "botsort"
    assert tracker["with_reid"] is False

    manifest = yaml.safe_load((ROOT / "third_party/manifest.yaml").read_text(encoding="utf-8"))
    components = {item["component_id"]: item for item in manifest["components"]}
    assert components["yolov8_seg"]["install_path"] == "models/yolov8s-seg.pt"
    # The point is that no digest is ever fabricated, not that osnet stays unstaged.
    # Once a real graph is staged the hash is legitimately a measured 64-hex value.
    osnet_sha = str(components["osnet_x0_25_msmt17"]["sha256"])
    assert osnet_sha == "capture_at_run" or re.fullmatch(r"[0-9a-f]{64}", osnet_sha), (
        f"osnet sha256 must be capture_at_run or a measured 64-hex digest, got {osnet_sha!r}"
    )
    assert manifest["runtime_downloads_allowed"] is False


def test_tracker_defaults_to_native_cadence_and_explicit_tracker_path():
    """Native cadence must remain the DEFAULT; decimation is opt-in and recorded.

    Sampling may exist only as an explicit cost/quality trade whose chosen rate is
    written into the artifact, never as a silent default.
    """
    import inspect
    from scripts.person_tracking.track_persons import PersonTracker

    source = (ROOT / "scripts/person_tracking/track_persons.py").read_text(encoding="utf-8")
    assert "tracker=self.tracker_config_path" in source
    assert "CAP_PROP_POS_MSEC" in source

    default = inspect.signature(PersonTracker.__init__).parameters["sample_fps"].default
    assert default is None, "tracking must default to native cadence"
    # the rate actually used has to reach the artifact, so two runs cannot be compared
    # without knowing they were sampled the same way
    assert '"tracking_sample_fps": self.sample_fps' in source
