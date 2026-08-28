from __future__ import annotations

import hashlib
import sys
import types
from pathlib import Path

import yaml

from scripts.setup import fetch_models


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_state_verifies_primary_and_alternate_files(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch_models, "ROOT", tmp_path)
    primary = tmp_path / "vendor" / "primary.bin"
    alternate = tmp_path / "vendor" / "alternate.bin"
    primary.parent.mkdir()
    primary.write_bytes(b"primary")
    alternate.write_bytes(b"alternate")
    component = {
        "install_path": "vendor/primary.bin",
        "sha256": _digest(b"primary"),
        "source": {"type": "git"},
        "alternates": [
            {"install_path": "vendor/alternate.bin", "sha256": _digest(b"alternate")}
        ],
    }

    assert fetch_models.state_of(component) == ("OK", "all declared artifacts verified")
    alternate.write_bytes(b"changed")
    state, detail = fetch_models.state_of(component)
    assert state == "MISMATCH"
    assert "alternate.bin" in detail


def test_ultralytics_resolution_moves_named_checkpoint(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch_models, "ROOT", tmp_path)

    class FakeYOLO:
        def __init__(self, model_name):
            Path(model_name).write_bytes(b"checkpoint")
            self.ckpt_path = model_name

    monkeypatch.setitem(sys.modules, "ultralytics", types.SimpleNamespace(YOLO=FakeYOLO))
    component = {
        "component_id": "yolo",
        "source": {"type": "ultralytics_auto", "model": "named.pt"},
        "install_path": "models/named.pt",
        "sha256": _digest(b"checkpoint"),
    }

    assert fetch_models.fetch(component) is True
    assert (tmp_path / "models" / "named.pt").read_bytes() == b"checkpoint"
    assert fetch_models.state_of(component)[0] == "OK"


def test_easyocr_fetch_records_each_measured_weight_hash(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch_models, "ROOT", tmp_path)
    manifest_path = tmp_path / "third_party" / "manifest.yaml"
    manifest_path.parent.mkdir()
    manifest_path.write_text(
        """manifest_version: 1
components:
  - component_id: easyocr
    source:
      type: easyocr_auto
    install_path: models/easyocr
    sha256: capture_at_run
    license: Apache-2.0
  - component_id: next
    source:
      type: local_training
    install_path: models/next.bin
    sha256: capture_at_run
    license: test
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(fetch_models, "MANIFEST", manifest_path)

    class FakeReader:
        calls = 0

        def __init__(self, _languages, *, gpu, model_storage_directory, download_enabled):
            assert gpu is False
            assert download_enabled is True
            type(self).calls += 1
            cache = Path(model_storage_directory)
            (cache / "craft.pth").write_bytes(b"detector")
            (cache / "english.pth").write_bytes(b"recognizer")

    monkeypatch.setitem(sys.modules, "easyocr", types.SimpleNamespace(Reader=FakeReader))
    component = yaml.safe_load(manifest_path.read_text())["components"][0]

    assert fetch_models.fetch(component) is True
    assert FakeReader.calls == 1
    recorded = yaml.safe_load(manifest_path.read_text())["components"][0]
    assert recorded["sha256"] == fetch_models.tree_sha256(tmp_path / "models" / "easyocr")
    assert {item["path"] for item in recorded["artifacts"]} == {"craft.pth", "english.pth"}
    assert all(len(item["sha256"]) == 64 for item in recorded["artifacts"])
    assert fetch_models.state_of(component)[0] == "OK"


def test_unresolved_hash_is_staged_but_blocks_verification(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch_models, "ROOT", tmp_path)
    target = tmp_path / "models" / "manual.onnx"
    target.parent.mkdir()
    target.write_bytes(b"operator export")
    component = {
        "component_id": "manual",
        "source": {"type": "manual_onnx_export"},
        "install_path": "models/manual.onnx",
        "sha256": "capture_at_run",
    }
    assert fetch_models.state_of(component)[0] == "STAGED"
    assert fetch_models.blocking_components([component])[0][0] == "manual"
