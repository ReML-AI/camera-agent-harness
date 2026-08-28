from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest
import yaml

from scripts.diarization import run_whisperx
from scripts import run_pipeline
from scripts.core.errors import RunManifestError


ALIGNMENT_NAME = "WAV2VEC2_ASR_BASE_960H"
ALIGNMENT_FILE = "wav2vec2_fairseq_base_ls960_asr_ls960.pth"
DIARIZATION_NAME = "pyannote/speaker-diarization-3.1"


def _staged_models(tmp_path: Path) -> dict[str, Path]:
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"audio")
    asr = tmp_path / "faster-whisper-large-v2"
    asr.mkdir()
    (asr / "model.bin").write_bytes(b"asr")
    torch_home = tmp_path / "torch"
    alignment = torch_home / "hub" / "checkpoints" / ALIGNMENT_FILE
    alignment.parent.mkdir(parents=True)
    alignment.write_bytes(b"alignment")
    pyannote_cache = torch_home / "pyannote"
    (pyannote_cache / "models--pyannote--speaker-diarization-3.1").mkdir(parents=True)
    return {
        "audio": audio,
        "asr": asr,
        "torch_home": torch_home,
        "alignment": alignment,
        "pyannote_cache": pyannote_cache,
    }


def test_adapter_loads_three_explicit_local_model_types(tmp_path, monkeypatch):
    staged = _staged_models(tmp_path)
    calls = {}

    class FakeAsr:
        def transcribe(self, audio, *, batch_size, language):
            calls["transcribe"] = (audio, batch_size, language)
            return {"language": language, "segments": [{"start": 0, "end": 1}]}

    def load_model(path, device, **kwargs):
        calls["asr"] = (path, device, kwargs)
        return FakeAsr()

    def load_align_model(**kwargs):
        calls["alignment"] = kwargs
        return object(), {"type": "torchaudio", "language": "en", "dictionary": {}}

    def align(segments, _model, _metadata, _audio, _device, **_kwargs):
        return {"language": "en", "segments": segments}

    def assign_word_speakers(_diarization, result):
        calls["assigned"] = True
        return result

    fake_whisperx = types.ModuleType("whisperx")
    fake_whisperx.load_model = load_model
    fake_whisperx.load_audio = lambda path: f"loaded:{path}"
    fake_whisperx.load_align_model = load_align_model
    fake_whisperx.align = align
    fake_whisperx.assign_word_speakers = assign_word_speakers

    class FakeDiarizationPipeline:
        def __init__(self, **kwargs):
            calls["diarization"] = kwargs

        def __call__(self, audio):
            return f"diarized:{audio}"

    fake_diarize = types.ModuleType("whisperx.diarize")
    fake_diarize.DiarizationPipeline = FakeDiarizationPipeline
    fake_bundle = types.SimpleNamespace(_path=ALIGNMENT_FILE)
    fake_pipelines = types.SimpleNamespace(
        __all__=[ALIGNMENT_NAME], **{ALIGNMENT_NAME: fake_bundle}
    )
    monkeypatch.setitem(sys.modules, "whisperx", fake_whisperx)
    monkeypatch.setitem(sys.modules, "whisperx.diarize", fake_diarize)
    monkeypatch.setitem(sys.modules, "torchaudio", types.SimpleNamespace(pipelines=fake_pipelines))

    output = tmp_path / "transcript.json"
    result = run_whisperx.run(
        staged["audio"], output, staged["asr"], ALIGNMENT_NAME,
        staged["alignment"], staged["torch_home"], DIARIZATION_NAME,
        staged["pyannote_cache"], device="cpu", batch_size=2,
    )

    assert calls["asr"][0] == str(staged["asr"].resolve())
    assert calls["asr"][2]["local_files_only"] is True
    assert calls["alignment"]["model_name"] == ALIGNMENT_NAME
    assert calls["alignment"]["model_dir"] == str(staged["alignment"].parent.resolve())
    assert calls["diarization"] == {"model_name": DIARIZATION_NAME, "device": "cpu"}
    assert calls["assigned"] is True
    assert result["model_resolution"]["alignment"]["resolved_type"] == "torchaudio"
    assert result["model_resolution"]["diarization"]["name"] == DIARIZATION_NAME
    assert json.loads(output.read_text())["model_resolution"] == result["model_resolution"]
    assert run_whisperx.os.environ["TORCH_HOME"] == str(staged["torch_home"].resolve())
    assert run_whisperx.os.environ["PYANNOTE_CACHE"] == str(
        staged["pyannote_cache"].resolve()
    )
    assert run_whisperx.os.environ["HF_HUB_OFFLINE"] == "1"


def test_adapter_fails_closed_when_stated_diarization_repo_is_not_cached(tmp_path):
    staged = _staged_models(tmp_path)
    missing_name = "pyannote/not-cached"
    with pytest.raises(FileNotFoundError, match="stated diarization repository"):
        run_whisperx.run(
            staged["audio"], tmp_path / "out.json", staged["asr"], ALIGNMENT_NAME,
            staged["alignment"], staged["torch_home"], missing_name,
            staged["pyannote_cache"], device="cpu",
        )


def test_stage_one_forwards_every_explicit_model_reference():
    inputs = {
        "asr_model_path": "/models/asr",
        "alignment_model_name": ALIGNMENT_NAME,
        "alignment_model_path": f"/cache/torch/hub/checkpoints/{ALIGNMENT_FILE}",
        "alignment_cache_path": "/cache/torch",
        "diarization_model_name": DIARIZATION_NAME,
        "diarization_cache_path": "/cache/torch/pyannote",
    }
    manifest = types.SimpleNamespace(document={"operator_inputs": inputs})
    command = run_pipeline._augment_command("1_diarization", ["python", "adapter.py"], manifest)

    for name, value in inputs.items():
        flag = "--" + name.replace("_", "-")
        assert command[command.index(flag) + 1] == value
    assert "--model-path" not in command
    assert "--diarization-model-path" not in command


def test_stage_one_refuses_an_unstated_model_reference():
    manifest = types.SimpleNamespace(document={"operator_inputs": {}})
    with pytest.raises(RunManifestError, match="requires --asr-model-path"):
        run_pipeline._augment_command("1_diarization", ["python", "adapter.py"], manifest)


def test_manifest_separates_asr_alignment_and_diarization_components():
    manifest = yaml.safe_load((run_pipeline.PROJECT_ROOT / "third_party/manifest.yaml").read_text())
    components = {item["component_id"]: item for item in manifest["components"]}

    assert components["whisperx"]["role"] == "automatic_speech_recognition"
    alignment = components["whisperx_alignment_en"]
    assert alignment["source"]["bundle"] == ALIGNMENT_NAME
    assert alignment["sha256"] == (
        "488fd4f16de84438ffc945334278c1b9fb9b7159a806c1080b16111a958c945d"
    )
    assert alignment["bytes"] == 377664473
    diarization = components["pyannote_speaker_diarization_3_1"]
    assert diarization["source"]["repo_id"] == DIARIZATION_NAME
    assert diarization["sha256"] == "capture_at_run"
