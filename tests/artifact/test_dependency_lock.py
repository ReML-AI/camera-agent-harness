from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]


def test_cpu_test_dependencies_are_exactly_pinned():
    lines = [
        line.strip() for line in (ROOT / "requirements-test.lock").read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert lines
    assert all(re.fullmatch(r"[A-Za-z0-9_.-]+(?:\[[A-Za-z0-9_,.-]+\])?==[^\s]+", line) for line in lines)


def test_runtime_downloads_are_forbidden_in_manifest():
    import yaml
    manifest = yaml.safe_load((ROOT / "third_party" / "manifest.yaml").read_text())
    assert manifest["runtime_downloads_allowed"] is False
    for component in manifest["components"]:
        assert {"component_id", "source", "install_path", "sha256", "license"} <= set(component)
        assert isinstance(component["source"], dict)
        assert component["source"].get("type")


def test_every_named_paper_component_has_a_provenance_manifest_entry():
    import yaml
    manifest = yaml.safe_load((ROOT / "third_party" / "manifest.yaml").read_text())
    component_ids = {component["component_id"] for component in manifest["components"]}
    assert {
        "yolov8", "whisperx", "whisperx_alignment_en",
        "pyannote_speaker_diarization_3_1", "light_asd", "s3fd", "6drepnet360", "clip",
        "easyocr", "qwen2_5_7b_instruct_ollama",
    } <= component_ids


def test_upstream_wrappers_have_no_runtime_weight_download_calls_or_mutable_model_names():
    paths = [
        "scripts/person_tracking/track_persons.py", "scripts/diarization/run_whisperx.py",
        "scripts/run_light_asd.py", "scripts/diarization/run_head_pose.py",
        "scripts/analytics/compute_clip_scenes.py", "scripts/detect_highlights.py",
    ]
    text = "\n".join((ROOT / path).read_text(encoding="utf-8") for path in paths)
    for forbidden in [
        "load_state_dict_from_url", 'YOLO(f\'yolov8', 'load_model("large-v2"',
        'from_pretrained("openai/clip-vit-base-patch32"',
    ]:
        assert forbidden not in text
    assert "local_files_only=True" in text
