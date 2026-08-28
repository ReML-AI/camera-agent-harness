#!/usr/bin/env python3
"""Pinned, local-only WhisperX transcription, alignment, and diarization adapter."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def _require_file(path: Path, description: str) -> Path:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"{description} is required: {path}")
    return path


def _require_directory(path: Path, description: str) -> Path:
    path = path.expanduser().resolve()
    if not path.is_dir():
        raise FileNotFoundError(f"{description} is required: {path}")
    return path


def _huggingface_repo_cache(cache_dir: Path, repo_id: str) -> Path:
    """Return the on-disk Hugging Face cache directory for one model repo."""
    if repo_id.count("/") != 1 or any(part in {"", ".", ".."} for part in repo_id.split("/")):
        raise ValueError(f"A Hugging Face owner/repository ID is required: {repo_id!r}")
    return cache_dir / f"models--{repo_id.replace('/', '--')}"


def run(
    audio_file,
    output_file,
    asr_model_path,
    alignment_model_name,
    alignment_model_path,
    alignment_cache_path,
    diarization_model_name,
    diarization_cache_path,
    *,
    device="cuda",
    batch_size=16,
    language="en",
):
    """Run three explicitly named, locally staged models without network access."""
    audio_file = _require_file(Path(audio_file), "Audio input")
    asr_model_path = _require_directory(Path(asr_model_path), "Local ASR model directory")
    alignment_model_path = _require_file(
        Path(alignment_model_path), "Local alignment model checkpoint"
    )
    alignment_cache_path = _require_directory(
        Path(alignment_cache_path), "Local torch model cache"
    )
    expected_alignment_path = (
        alignment_cache_path / "hub" / "checkpoints" / alignment_model_path.name
    ).resolve()
    if alignment_model_path != expected_alignment_path:
        raise ValueError(
            "Alignment checkpoint must be staged under "
            f"{alignment_cache_path}/hub/checkpoints so TORCH_HOME resolves it: "
            f"{alignment_model_path}"
        )

    diarization_cache_path = _require_directory(
        Path(diarization_cache_path), "Local pyannote model cache"
    )
    diarization_repo_cache = _huggingface_repo_cache(
        diarization_cache_path, diarization_model_name
    )
    if not diarization_repo_cache.is_dir():
        raise FileNotFoundError(
            "The stated diarization repository is absent from the local pyannote cache: "
            f"{diarization_repo_cache}"
        )

    # These variables are consumed while torch/pyannote modules are imported, so pin
    # them before importing WhisperX. Offline mode turns a cache miss into an error.
    os.environ["TORCH_HOME"] = str(alignment_cache_path)
    os.environ["PYANNOTE_CACHE"] = str(diarization_cache_path)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"

    import torchaudio
    import whisperx
    from whisperx.diarize import DiarizationPipeline

    if alignment_model_name not in torchaudio.pipelines.__all__:
        raise ValueError(
            "The explicit alignment model is not a torchaudio pipeline bundle: "
            f"{alignment_model_name}"
        )
    bundle = getattr(torchaudio.pipelines, alignment_model_name)
    bundle_asset = getattr(bundle, "_path", None)
    if bundle_asset and Path(bundle_asset).name != alignment_model_path.name:
        raise ValueError(
            f"Alignment bundle {alignment_model_name} expects {Path(bundle_asset).name}, "
            f"not {alignment_model_path.name}"
        )

    resolution = {
        "runtime_downloads_allowed": False,
        "asr": {
            "loader": "faster-whisper local directory",
            "path": str(asr_model_path),
        },
        "alignment": {
            "loader": "torchaudio",
            "name": alignment_model_name,
            "path": str(alignment_model_path),
            "torch_home": str(alignment_cache_path),
        },
        "diarization": {
            "loader": "pyannote.audio.Pipeline.from_pretrained",
            "name": diarization_model_name,
            "cache_path": str(diarization_cache_path),
            "repository_cache": str(diarization_repo_cache.resolve()),
        },
    }
    compute_type = "float16" if device == "cuda" else "int8"
    model = whisperx.load_model(
        str(asr_model_path),
        device,
        compute_type=compute_type,
        language=language,
        local_files_only=True,
    )
    audio = whisperx.load_audio(str(audio_file))
    result = model.transcribe(audio, batch_size=batch_size, language=language)

    model_a, metadata = whisperx.load_align_model(
        language_code=result["language"],
        device=device,
        model_name=alignment_model_name,
        model_dir=str(alignment_model_path.parent),
    )
    if metadata.get("type") != "torchaudio":
        raise RuntimeError(
            f"Alignment loader resolved {alignment_model_name} as {metadata.get('type')!r}, "
            "not torchaudio"
        )
    resolution["alignment"]["resolved_type"] = metadata["type"]
    result = whisperx.align(
        result["segments"], model_a, metadata, audio, device,
        return_char_alignments=False,
    )

    # WhisperX 3.7.4 expects a Hugging Face repo ID here. pyannote resolves it
    # against PYANNOTE_CACHE, and HF_HUB_OFFLINE prevents a cache miss downloading.
    diarize_model = DiarizationPipeline(model_name=diarization_model_name, device=device)
    print("WhisperX loaded model resolution: " + json.dumps(resolution, sort_keys=True))
    diarize_segments = diarize_model(audio)
    result = whisperx.assign_word_speakers(diarize_segments, result)

    # Normalise to the canonical transcript shape at the adapter boundary. WhisperX
    # emits start/end/speaker and no segment identity; this project's consumers and
    # schemas expect start_seconds/end_seconds/speaker_id plus a stable
    # transcript_segment_id. Translating once here is correct — teaching a dozen
    # consumers to accept both spellings would spread an upstream naming detail through
    # the pipeline, and every one of them would be a place to get it wrong.
    #
    # The original keys are retained as aliases because several consumers still read
    # them. Both spellings are written from the same value in the same pass, so they
    # cannot disagree within a run.
    for index, segment in enumerate(result.get("segments") or []):
        segment.setdefault("transcript_segment_id", f"segment-{index:06d}")
        if "speaker" in segment:
            segment.setdefault("speaker_id", segment["speaker"])
        if "start" in segment:
            segment.setdefault("start_seconds", float(segment["start"]))
        if "end" in segment:
            segment.setdefault("end_seconds", float(segment["end"]))
    for word in result.get("word_segments") or []:
        if "speaker" in word:
            word.setdefault("speaker_id", word["speaker"])
        if "start" in word:
            word.setdefault("start_seconds", float(word["start"]))
        if "end" in word:
            word.setdefault("end_seconds", float(word["end"]))

    result["model_resolution"] = resolution

    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--asr-model-path", required=True)
    parser.add_argument("--alignment-model-name", required=True)
    parser.add_argument("--alignment-model-path", required=True)
    parser.add_argument("--alignment-cache-path", required=True)
    parser.add_argument("--diarization-model-name", required=True)
    parser.add_argument("--diarization-cache-path", required=True)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--language", default="en")
    args = parser.parse_args()
    run(
        args.audio,
        args.output,
        args.asr_model_path,
        args.alignment_model_name,
        args.alignment_model_path,
        args.alignment_cache_path,
        args.diarization_model_name,
        args.diarization_cache_path,
        device=args.device,
        batch_size=args.batch_size,
        language=args.language,
    )


if __name__ == "__main__":
    main()
