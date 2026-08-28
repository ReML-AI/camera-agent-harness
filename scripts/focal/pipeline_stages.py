#!/usr/bin/env python3
"""Fail-closed command-line producers used by the master paper run graph."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import pickle
import sys
import unicodedata
from typing import Any, Mapping, Sequence

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.core.errors import ContractError
from scripts.core.records import LIGHT_ASD_ANALYSIS_FPS, light_asd_index_to_seconds
from scripts.core.schema import validate_record
from scripts.flags.clip_urgency import (
    EMERGENCY_TEMPLATES,
    ROUTINE_TEMPLATES,
    ClipUrgencyAdapter,
)
from scripts.flags.fusion import fuse_flags_fixed, run_independent_sources
from scripts.flags.keyword import KBaseline, KeywordMatch
from scripts.flags.models import FlagSource
from scripts.flags.vitals import VitalThresholdFlagger, VitalThresholds
from scripts.focal.runner import run_ktm
from scripts.focal.runtime import FocalRequest, FocalRuntime
from scripts.utils.llm_client import get_client


CAMERAS = ("cam1", "cam2", "cam3")
K_POLICY_ID = "k-policy-v1.0.0"
K_CATEGORIES = {
    "urgency": (3, (
        "stat", "now", "hurry", "emergency", "code blue", "urgent", "quickly",
        "fast", "immediately", "deteriorating", "crashing", "cardiac arrest",
    )),
    "assessment": (2, (
        "check", "pulse", "rhythm", "breathing", "responsive", "unresponsive",
        "airway", "saturation", "blood pressure", "heart rate", "consciousness",
        "pupils", "capillary refill",
    )),
    "intervention": (3, (
        "intubate", "defibrillate", "adrenaline", "compressions", "ventilate",
        "suction", "cannulate", "bolus", "shock", "epinephrine", "amiodarone",
        "atropine", "oxygen", "bag valve mask", "chest compressions", "cpr",
    )),
    "communication": (1, (
        "confirmed", "understood", "repeat back", "handover", "closed loop",
        "acknowledged", "received", "copy that", "i confirm", "read back", "sbar",
    )),
    "concern": (2, (
        "worried", "concerned", "not sure", "help", "uncertain",
        "doesn't look right", "something wrong", "changed", "worsening", "no response",
    )),
}
K_TIE_ORDER = tuple(K_CATEGORIES)
FOCAL_CATEGORIES = (
    "communication", "clinical_decision", "team_coordination", "patient_assessment",
    "procedural_skill", "situational_awareness", "leadership",
)


def _load_json(path: Path, description: str) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"required {description} artifact is missing: {path}")
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ContractError(f"{description} artifact must contain a JSON object: {path}")
    return value


def _write_json(path: Path, value: Mapping) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _assignments(values: Sequence[str], *, numeric: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for value in values:
        camera, separator, raw = value.partition("=")
        if not separator or camera not in CAMERAS or camera in result or not raw:
            raise ContractError(f"expected one unique CAMERA=VALUE assignment, got {value!r}")
        result[camera] = float(raw) if numeric else Path(raw)
    if set(result) != set(CAMERAS):
        raise ContractError("exactly cam1, cam2, and cam3 assignments are required")
    return result


def assemble_asd_artifact(
    camera_pywork: Mapping[str, Path], fps_by_camera: Mapping[str, float]
) -> dict:
    """Convert all Light-ASD pickle outputs into the canonical JSON consumer format."""
    if set(camera_pywork) != set(CAMERAS) or set(fps_by_camera) != set(CAMERAS):
        raise ContractError("ASD assembly requires exactly three camera inputs and FPS values")
    output: dict[str, dict] = {}
    for camera in CAMERAS:
        fps = float(fps_by_camera[camera])
        if fps <= 0:
            raise ContractError(f"ASD assembly requires positive FPS for {camera}")
        pywork = Path(camera_pywork[camera])
        tracks_path = pywork / "tracks.pckl"
        scores_path = pywork / "scores.pckl"
        for path in (tracks_path, scores_path):
            if not path.is_file():
                raise FileNotFoundError(f"required Light-ASD artifact is missing: {path}")
        with tracks_path.open("rb") as handle:
            tracks = pickle.load(handle)  # trusted output from the pinned in-run producer
        with scores_path.open("rb") as handle:
            scores = pickle.load(handle)  # trusted output from the pinned in-run producer
        if not isinstance(tracks, Sequence) or not isinstance(scores, Sequence):
            raise ContractError(f"Light-ASD output for {camera} must contain sequences")
        if len(tracks) != len(scores):
            raise ContractError(f"Light-ASD track/score count mismatch for {camera}")
        canonical_tracks = []
        for index, (track, track_scores) in enumerate(zip(tracks, scores)):
            try:
                frames = list(track["track"]["frame"])
                boxes = list(track["track"]["bbox"])
                score_values = list(track_scores)
            except (KeyError, TypeError) as error:
                raise ContractError(f"malformed Light-ASD track {camera}/{index}") from error
            if len(frames) != len(boxes):
                raise ContractError(f"Light-ASD frame/bbox mismatch for {camera}/{index}")
            # Light-ASD scores a truncated PREFIX of each track: in Columbia_test.py the
            # video features are sliced [:round(length*25)] where length is capped by the
            # audio duration, so it emits N-1 (or fewer) scores for N frames and score[i]
            # pairs with frame[i]. Pair by index and drop the unscored tail rather than
            # shifting scores onto the wrong frames.
            if len(score_values) > len(frames):
                raise ContractError(
                    f"Light-ASD produced more scores than frames for {camera}/{index}"
                )
            unscored_tail = len(frames) - len(score_values)
            if unscored_tail:
                frames = frames[: len(score_values)]
                boxes = boxes[: len(score_values)]
            samples = [
                {
                    "evidence_id": f"asd-{camera}-{index}-{int(frame)}",
                    "camera_id": camera,
                    "track_id": f"track:{camera}:{index}",
                    "frame_index": int(frame),
                    "aligned_timestamp_seconds": light_asd_index_to_seconds(frame),
                    "score": float(score),
                    "bbox": [float(item) for item in box],
                    "face_detected": True,
                }
                for frame, box, score in zip(frames, boxes, score_values)
            ]
            canonical_tracks.append({"track_id": f"track:{camera}:{index}", "samples": samples})
        output[camera] = {
            "schema_version": "asd-camera/1.0.0",
            "camera_id": camera,
            # Two rates, deliberately both recorded. Timestamps above divide the frame
            # index by the ANALYSIS rate because Light-ASD numbered them on its own 25 Hz
            # re-encode; the source rate is kept so a reader can map back to the original
            # video. A single "fps" field here previously implied the source rate governed
            # the timestamps, which is what produced a 17% timeline compression.
            "analysis_fps": LIGHT_ASD_ANALYSIS_FPS,
            "source_fps": fps,
            "fps": LIGHT_ASD_ANALYSIS_FPS,
            "tracks": canonical_tracks,
        }
    return output


def score_clip_urgency(
    *, session_id: str, session_end_seconds: float, video_paths: Mapping[str, Path], model_path: Path
) -> dict:
    """Decode every camera and emit fixed-policy raw logits at one sample per second."""
    if session_end_seconds <= 0 or set(video_paths) != set(CAMERAS):
        raise ContractError("CLIP urgency scoring requires duration and all three cameras")
    if not model_path.is_dir():
        raise FileNotFoundError(f"required local CLIP model is missing: {model_path}")
    for path in video_paths.values():
        if not path.is_file():
            raise FileNotFoundError(f"required camera video is missing: {path}")

    import cv2
    import torch
    from transformers import CLIPModel, CLIPProcessor

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = CLIPModel.from_pretrained(
        str(model_path), use_safetensors=True, local_files_only=True
    ).to(device)
    processor = CLIPProcessor.from_pretrained(str(model_path), local_files_only=True)
    templates = list(ROUTINE_TEMPLATES + EMERGENCY_TEMPLATES)
    records = []
    for camera in CAMERAS:
        capture = cv2.VideoCapture(str(video_paths[camera]))
        if not capture.isOpened():
            raise RuntimeError(f"could not decode camera video: {video_paths[camera]}")
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        if fps <= 0:
            capture.release()
            raise RuntimeError(f"camera video has invalid FPS: {video_paths[camera]}")
        candidates: dict[int, tuple[float, int, float, Any]] = {}
        frame_index = 0
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            timestamp = float(capture.get(cv2.CAP_PROP_POS_MSEC)) / 1000.0
            if timestamp <= 0 and frame_index:
                timestamp = frame_index / fps
            bin_index = int(timestamp)
            if 0 <= timestamp < session_end_seconds:
                distance = abs(timestamp - (bin_index + 0.5))
                prior = candidates.get(bin_index)
                if prior is None or (distance, timestamp) < (prior[0], prior[2]):
                    candidates[bin_index] = (distance, frame_index, timestamp, frame.copy())
            frame_index += 1
        capture.release()
        for bin_index, (_distance, native_index, timestamp, frame) in sorted(candidates.items()):
            image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            inputs = processor(text=templates, images=[image], return_tensors="pt", padding=True)
            inputs = {key: value.to(device) for key, value in inputs.items()}
            with torch.no_grad():
                logits = model(**inputs).logits_per_image[0].detach().cpu().tolist()
            records.append({
                "evidence_id": f"clip-urgency-{camera}-{bin_index}",
                "session_id": session_id,
                "camera_id": camera,
                "bin_index": bin_index,
                "native_frame_index": native_index,
                "aligned_timestamp_seconds": timestamp,
                "routine_logits": logits[:len(ROUTINE_TEMPLATES)],
                "emergency_logits": logits[len(ROUTINE_TEMPLATES):],
            })
    return {
        "schema_version": "clip-urgency-records/1.0.0",
        "session_id": session_id,
        "sampling_rate_hz": 1.0,
        "records": records,
    }


def _normalise_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = "".join(" " if unicodedata.category(char).startswith("P") else char for char in normalized)
    return " ".join(normalized.split())


def _contains_tokens(tokens: Sequence[str], phrase: Sequence[str]) -> bool:
    width = len(phrase)
    return any(tuple(tokens[index:index + width]) == tuple(phrase) for index in range(len(tokens) - width + 1))


class FixedKeywordMatcher:
    """The versioned whole-token, transitive ten-second K/flag policy."""

    policy_id = K_POLICY_ID

    def find_matches(self, transcript: Sequence[Mapping]):
        matched_segments = []
        for index, segment in enumerate(transcript):
            text = segment.get("text")
            if not isinstance(text, str):
                raise ContractError("keyword policy requires transcript text")
            tokens = _normalise_text(text).split()
            terms = []
            scores = {category: 0 for category in K_CATEGORIES}
            for category, (weight, category_terms) in K_CATEGORIES.items():
                for term_index, term in enumerate(category_terms):
                    if _contains_tokens(tokens, _normalise_text(term).split()):
                        term_id = f"{category}-{term_index:02d}"
                        terms.append(term_id)
                        scores[category] += weight
            if not terms:
                continue
            start = float(segment.get("start_seconds", segment.get("start")))
            end = float(segment.get("end_seconds", segment.get("end")))
            segment_id = str(
                segment.get("transcript_segment_id")
                or segment.get("evidence_id")
                or f"segment-{index:06d}"
            )
            evidence_id = str(segment.get("evidence_id") or segment_id)
            matched_segments.append({
                "start": start, "end": end, "segment_id": segment_id,
                "evidence_id": evidence_id, "terms": tuple(sorted(terms)), "scores": scores,
            })
        matched_segments.sort(key=lambda item: (item["start"], item["end"], item["segment_id"]))
        clusters: list[list[dict]] = []
        for segment in matched_segments:
            if not clusters or segment["start"] - max(item["end"] for item in clusters[-1]) > 10.0:
                clusters.append([segment])
            else:
                clusters[-1].append(segment)
        for cluster in clusters:
            segment_ids = [item["segment_id"] for item in cluster]
            term_ids = sorted({term for item in cluster for term in item["terms"]})
            digest = sha256(json.dumps(
                [self.policy_id, segment_ids, term_ids], separators=(",", ":")
            ).encode("utf-8")).hexdigest()
            category_scores = {
                category: sum(item["scores"][category] for item in cluster)
                for category in K_CATEGORIES
            }
            category = min(
                K_TIE_ORDER,
                key=lambda name: (-category_scores[name], K_TIE_ORDER.index(name)),
            )
            yield KeywordMatch(
                match_id=f"k-{digest}",
                start_seconds=min(item["start"] for item in cluster),
                end_seconds=max(item["end"] for item in cluster),
                evidence_ids=tuple(dict.fromkeys(item["evidence_id"] for item in cluster)),
                category=category,
                matched_policy_term_id="+".join(term_ids),
            )


def produce_flags(
    *, session_id: str, transcript: Mapping, clip_records: Mapping,
    monitor_vitals: Mapping, monitor_config: Mapping,
) -> tuple[dict[str, dict], dict]:
    segments = transcript.get("segments")
    records = clip_records.get("records")
    timeline = monitor_vitals.get("timeline")
    threshold_values = monitor_config.get("thresholds")
    if not isinstance(segments, list) or not isinstance(records, list):
        raise ContractError("flag inputs require transcript segments and CLIP records")
    if not isinstance(timeline, list) or not isinstance(threshold_values, Mapping):
        raise ContractError("flag inputs require monitor timeline and configured thresholds")
    if clip_records.get("session_id") != session_id:
        raise ContractError("CLIP urgency records belong to a different session")
    thresholds = {
        name: VitalThresholds(**value)
        for name, value in threshold_values.items()
        if isinstance(value, Mapping)
    }
    vital_records = []
    for index, value in enumerate(timeline):
        if not isinstance(value, Mapping):
            raise ContractError("monitor timeline records must be objects")
        timestamp = float(value["timestamp"])
        values = dict(value)
        values["nbp_sys"] = value.get("nbp_sys", value.get("bp_sys"))
        values["nbp_dia"] = value.get("nbp_dia", value.get("bp_dia"))
        vital_records.append({
            "evidence_id": f"monitor-vital-{index:06d}",
            "start_seconds": timestamp,
            "end_seconds": timestamp + 1.0,
            "values": values,
            "raw_ocr_text": {},
            "source_frame": value.get("frame_num"),
        })
    matcher = FixedKeywordMatcher()
    producers = {
        FlagSource.CLIP_URGENCY: lambda: ClipUrgencyAdapter().run(session_id, records),
        FlagSource.VITALS_THRESHOLD: lambda: VitalThresholdFlagger(
            thresholds, policy_id="monitor-vital-thresholds-v1.0.0"
        ).run(session_id, vital_records),
        FlagSource.TRANSCRIPT_KEYWORD: lambda: KBaseline(matcher).flag_artifact(
            session_id, segments
        ),
    }
    source_artifacts = run_independent_sources(session_id, producers)
    fused = fuse_flags_fixed(source_artifacts)
    serialized_sources = {
        source.value: artifact.to_dict() for source, artifact in source_artifacts.items()
    }
    for artifact in (*serialized_sources.values(), fused.to_dict()):
        validate_record("flag_artifact", artifact)
    return serialized_sources, fused.to_dict()


def _reject_truncated_prompt(response: Any, request: FocalRequest) -> None:
    """Fail when the backend silently dropped part of the prompt.

    Ollama truncates an over-long prompt to the context window and keeps the TAIL, logging
    only a warning: an 85,713-token prompt became 32,768 tokens with the instructions and the
    earliest windows discarded, and the run would otherwise have recorded the resulting
    moments as if the model had seen everything. A reported prompt length at or above the
    context window means the prompt was cut, since a prompt filling the whole window leaves
    no room for the completion either way.
    """
    usage = getattr(response, "usage", None)
    prompt_tokens = getattr(usage, "prompt_tokens", None)
    if not isinstance(prompt_tokens, int):
        return
    context_length = request.runtime.context_length
    if prompt_tokens >= context_length:
        raise ContractError(
            f"focal prompt was truncated by the backend: {prompt_tokens} prompt tokens "
            f"against a context window of {context_length}. The model did not see the whole "
            f"prompt, so this result would not describe the session it claims to."
        )


class OpenAICompatibleEndpoint:
    def __init__(self, *, base_url: str, api_key: str) -> None:
        self.base_url = base_url
        self.api_key = api_key

    def complete(self, request: FocalRequest) -> str:
        client = get_client(
            self.base_url, self.api_key,
            timeout_seconds=request.runtime.timeout_seconds,
            paper_mode=True,
        )
        response = client.chat.completions.create(
            model=request.runtime.model_id,
            messages=[{"role": "user", "content": request.prompt}],
            max_tokens=request.runtime.maximum_output_tokens,
            temperature=request.runtime.temperature,
            response_format={"type": "json_object"},
            extra_body=request.runtime.json_parameters,
            seed=request.runtime.seed,
            stop=list(request.runtime.stop_sequences) or None,
            stream=False,
        )
        _reject_truncated_prompt(response, request)
        content = response.choices[0].message.content
        if not isinstance(content, str) or not content:
            raise ContractError("focal endpoint returned an empty response")
        return content


def _runtime(document: Mapping) -> FocalRuntime:
    values = dict(document)
    values["stop_sequences"] = tuple(values.get("stop_sequences", ()))
    values["request_order"] = tuple(values.get("request_order", ()))
    return FocalRuntime.checked(paper_mode=True, **values)


def run_focal_stage(
    *, session_id: str, transcript: Mapping, windows_artifact: Mapping,
    runtime_document: Mapping, base_url: str, api_key: str,
    windows_artifact_sha256: str | None = None,
) -> dict:
    if windows_artifact.get("session_id") != session_id:
        raise ContractError("context windows belong to a different session")
    segments = transcript.get("segments")
    windows = windows_artifact.get("windows")
    if not isinstance(segments, list) or not isinstance(windows, list):
        raise ContractError("focal stage requires transcript segments and context windows")
    # Stage 13 decides which windows fit the focal context budget and records the
    # decision. Honour it here rather than re-deriving: sending everything would let the
    # backend truncate the prompt tail silently, dropping the instructions rather than
    # the least-corroborated evidence.
    delivery = windows_artifact.get("focal_delivery")
    if isinstance(delivery, Mapping):
        allowed = set(delivery.get("delivered_window_ids") or ())
        windows = [window for window in windows if window["window_id"] in allowed]
        if not windows:
            raise ContractError(
                "focal delivery selected no windows; the context budget cannot fit even "
                "one assembled window"
            )
    # The session's true span comes from the manifest, recorded by Stage 13. Deriving it
    # from windows measured only where flags landed: over the delivered subset that told
    # the model session_001 lasted 450s of 960s, and over assembled windows it is still
    # short whenever the tail carries no flag.
    duration = windows_artifact.get("session_end_seconds")
    if duration is None:
        raise ContractError(
            "multimodal_windows artifact has no session_end_seconds; reassemble with the "
            "current Stage 13 so the stated session span comes from the session manifest"
        )
    duration = float(duration)
    if duration <= 0:
        raise ContractError("focal stage requires at least one fused-flag-selected window")
    speaker_ids = sorted({
        str(segment.get("speaker_id", segment.get("speaker")))
        for segment in segments
        if segment.get("speaker_id", segment.get("speaker")) is not None
    })
    return run_ktm(
        session_id=session_id,
        transcript=segments,
        windows=windows,
        session_duration_seconds=duration,
        speakers=[{"speaker_id": speaker_id} for speaker_id in speaker_ids],
        k_baseline=KBaseline(FixedKeywordMatcher()),
        runtime=_runtime(runtime_document),
        endpoint=OpenAICompatibleEndpoint(base_url=base_url, api_key=api_key),
        category_taxonomy=FOCAL_CATEGORIES,
        delivered_artifact_sha256=windows_artifact_sha256,
        paper_mode=True,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    asd = subparsers.add_parser("assemble-asd")
    asd.add_argument("--input", action="append", required=True, metavar="CAMERA=PYWORK")
    asd.add_argument("--fps", action="append", required=True, metavar="CAMERA=FPS")
    asd.add_argument("--output", type=Path, required=True)

    clip = subparsers.add_parser("score-clip")
    clip.add_argument("--session-id", required=True)
    clip.add_argument("--session-manifest", type=Path, required=True)
    clip.add_argument("--video", action="append", required=True, metavar="CAMERA=VIDEO")
    clip.add_argument("--model-path", type=Path, required=True)
    clip.add_argument("--output", type=Path, required=True)

    flags = subparsers.add_parser("produce-flags")
    flags.add_argument("--session-id", required=True)
    flags.add_argument("--transcript", type=Path, required=True)
    flags.add_argument("--clip-records", type=Path, required=True)
    flags.add_argument("--monitor-vitals", type=Path, required=True)
    flags.add_argument("--monitor-config", type=Path, required=True)
    flags.add_argument("--output-dir", type=Path, required=True)

    focal = subparsers.add_parser("run-focal")
    focal.add_argument("--session-id", required=True)
    focal.add_argument("--transcript", type=Path, required=True)
    focal.add_argument("--windows", type=Path, required=True)
    focal.add_argument("--runtime-config", type=Path, required=True)
    focal.add_argument("--base-url", default=os.environ.get("LLM_BASE_URL"))
    focal.add_argument("--api-key", default=os.environ.get("LLM_API_KEY"))
    focal.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    parser = _parser()
    args = parser.parse_args()
    if args.command == "assemble-asd":
        result = assemble_asd_artifact(
            _assignments(args.input), _assignments(args.fps, numeric=True)
        )
        _write_json(args.output, result)
    elif args.command == "score-clip":
        manifest = _load_json(args.session_manifest, "session manifest")
        if manifest.get("session_id") != args.session_id:
            raise ContractError("session manifest belongs to a different session")
        result = score_clip_urgency(
            session_id=args.session_id,
            session_end_seconds=float(manifest.get("session_end_seconds", 0)),
            video_paths=_assignments(args.video),
            model_path=args.model_path,
        )
        _write_json(args.output, result)
    elif args.command == "produce-flags":
        sources, fused = produce_flags(
            session_id=args.session_id,
            transcript=_load_json(args.transcript, "transcript"),
            clip_records=_load_json(args.clip_records, "CLIP urgency"),
            monitor_vitals=_load_json(args.monitor_vitals, "monitor vitals"),
            monitor_config=_load_json(args.monitor_config, "monitor configuration"),
        )
        filenames = {
            "clip_urgency": "flags_clip_urgency.json",
            "vitals_threshold": "flags_vitals_threshold.json",
            "transcript_keyword": "flags_transcript_keyword.json",
        }
        for source, artifact in sources.items():
            _write_json(args.output_dir / filenames[source], artifact)
        _write_json(args.output_dir / "fused_flags.json", fused)
    else:
        if not args.base_url or not args.api_key:
            parser.error("run-focal requires --base-url/LLM_BASE_URL and --api-key/LLM_API_KEY")
        result = run_focal_stage(
            session_id=args.session_id,
            transcript=_load_json(args.transcript, "transcript"),
            windows_artifact=_load_json(args.windows, "context windows"),
            runtime_document=_load_json(args.runtime_config, "focal runtime configuration"),
            base_url=args.base_url,
            api_key=args.api_key,
            windows_artifact_sha256=sha256(args.windows.read_bytes()).hexdigest(),
        )
        _write_json(args.output, result)
    print(args.output_dir if args.command == "produce-flags" else args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
