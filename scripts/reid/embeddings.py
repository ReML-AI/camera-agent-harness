"""OSNet appearance embeddings with deterministic temporal crop selection."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from scripts.core.records import sha256_file

from .config import EmbeddingConfig


def l2_normalize(values: Sequence[float]) -> tuple[float, ...]:
    """Return a finite L2-normalized vector, or an all-zero vector unchanged."""
    import math

    vector = tuple(float(value) for value in values)
    if any(not math.isfinite(value) for value in vector):
        raise ValueError("embedding contains a non-finite value")
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        return vector
    return tuple(value / norm for value in vector)


def average_then_l2_normalize(vectors: Sequence[Sequence[float]]) -> tuple[float, ...]:
    """Average equal-length OSNet outputs and then normalize exactly once."""
    if not vectors:
        raise ValueError("at least one embedding vector is required")
    width = len(vectors[0])
    if width == 0 or any(len(vector) != width for vector in vectors):
        raise ValueError("embedding vectors must have one common non-zero length")
    count = float(len(vectors))
    average = [sum(float(vector[index]) for vector in vectors) / count for index in range(width)]
    return l2_normalize(average)


def select_temporally_stratified(
    observations: Iterable[Mapping[str, Any]], maximum_crops: int
) -> list[Mapping[str, Any]]:
    """Select one deterministic representative from each equal-duration stratum.

    Confidence is deliberately not part of the ordering or tie break, so a run
    cannot collapse all appearance samples onto one high-confidence pose.
    """
    if maximum_crops <= 0:
        raise ValueError("maximum_crops must be positive")
    ordered = sorted(
        observations,
        key=lambda item: (
            float(item["presentation_timestamp_seconds"]),
            int(item["frame_index"]),
        ),
    )
    if not ordered:
        return []
    count = min(maximum_crops, len(ordered))
    start = float(ordered[0]["presentation_timestamp_seconds"])
    end = float(ordered[-1]["presentation_timestamp_seconds"])

    # Some containers expose repeated PTS values. Rank strata are the stable
    # fallback; no frame-rate-derived timestamp is fabricated.
    if end <= start:
        return [ordered[min(len(ordered) - 1, ((2 * i + 1) * len(ordered)) // (2 * count))]
                for i in range(count)]

    chosen: list[Mapping[str, Any]] = []
    used_frames: set[int] = set()
    span = end - start
    for index in range(count):
        lower = start + span * index / count
        upper = start + span * (index + 1) / count
        center = (lower + upper) / 2.0
        candidates = [
            item for item in ordered
            if int(item["frame_index"]) not in used_frames
            and float(item["presentation_timestamp_seconds"]) >= lower
            and (
                index == count - 1
                or float(item["presentation_timestamp_seconds"]) < upper
            )
        ]
        if not candidates:
            candidates = [
                item for item in ordered if int(item["frame_index"]) not in used_frames
            ]
        selected = min(
            candidates,
            key=lambda item: (
                abs(float(item["presentation_timestamp_seconds"]) - center),
                int(item["frame_index"]),
            ),
        )
        chosen.append(selected)
        used_frames.add(int(selected["frame_index"]))
    return sorted(chosen, key=lambda item: int(item["frame_index"]))


class OSNetEncoder:
    """CPU ONNX Runtime wrapper for the pinned OSNet x0.25 MSMT17 export."""

    def __init__(
        self,
        model_path: str | Path,
        expected_sha256: str,
        config: EmbeddingConfig,
    ) -> None:
        weights = Path(model_path)
        if not weights.is_file():
            raise FileNotFoundError(f"Local OSNet ONNX weights are required: {weights}")
        actual_sha256 = sha256_file(weights)
        if actual_sha256 != expected_sha256:
            raise ValueError(
                f"OSNet weights checksum mismatch: expected {expected_sha256}, got {actual_sha256}"
            )

        import onnxruntime as ort

        options = ort.SessionOptions()
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        self._session = ort.InferenceSession(
            str(weights),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        self._input_name = self._session.get_inputs()[0].name
        self.model_path = str(weights.resolve())
        self.model_sha256 = actual_sha256
        self.config = config

    def _preprocess(self, crop_bgr: Any) -> Any:
        import cv2
        import numpy as np

        resized = cv2.resize(
            crop_bgr,
            (self.config.input_width, self.config.input_height),
            interpolation=cv2.INTER_LINEAR,
        )
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype("float32") / 255.0
        mean = np.asarray([0.485, 0.456, 0.406], dtype="float32")
        std = np.asarray([0.229, 0.224, 0.225], dtype="float32")
        return ((rgb - mean) / std).transpose(2, 0, 1)[None, ...]

    def encode_crops(self, crops_bgr: Sequence[Any]) -> tuple[float, ...]:
        """Infer every selected crop, average raw outputs, then L2-normalize."""
        vectors: list[list[float]] = []
        for crop in crops_bgr:
            output = self._session.run(None, {self._input_name: self._preprocess(crop)})[0]
            vectors.append(output.reshape(-1).astype(float).tolist())
        return average_then_l2_normalize(vectors)


def extract_tracklet_embeddings(
    video_path: str | Path,
    observations_by_tracklet: Mapping[str, Sequence[Mapping[str, Any]]],
    encoder: OSNetEncoder,
    config: EmbeddingConfig,
) -> tuple[dict[str, tuple[float, ...]], dict[str, list[dict[str, Any]]]]:
    """Decode forward once, crop stratified samples, and return embeddings + lineage."""
    import cv2

    selected_by_frame: dict[int, list[tuple[str, Mapping[str, Any]]]] = defaultdict(list)
    selections: dict[str, list[dict[str, Any]]] = {}
    for tracklet_id in sorted(observations_by_tracklet):
        selected = select_temporally_stratified(
            observations_by_tracklet[tracklet_id], config.maximum_crops_per_tracklet
        )
        selections[tracklet_id] = [
            {
                "frame_index": int(item["frame_index"]),
                "presentation_timestamp_seconds": float(
                    item["presentation_timestamp_seconds"]
                ),
            }
            for item in selected
        ]
        for item in selected:
            selected_by_frame[int(item["frame_index"])].append((tracklet_id, item))

    crops: dict[str, list[Any]] = defaultdict(list)
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        capture.release()
        raise RuntimeError(f"OpenCV could not open video for OSNet crops: {video_path}")
    frame_index = 0
    try:
        while selected_by_frame:
            ok, frame = capture.read()
            if not ok:
                break
            requested = selected_by_frame.pop(frame_index, [])
            height, width = frame.shape[:2]
            for tracklet_id, observation in requested:
                x1, y1, x2, y2 = (
                    int(round(value)) for value in observation["bbox_xyxy_pixels"]
                )
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(width, x2), min(height, y2)
                if (
                    x2 - x1 < config.minimum_crop_width_pixels
                    or y2 - y1 < config.minimum_crop_height_pixels
                ):
                    continue
                crop = frame[y1:y2, x1:x2]
                if crop.size:
                    crops[tracklet_id].append(crop)
            frame_index += 1
    finally:
        capture.release()

    if selected_by_frame:
        missing = sorted(selected_by_frame)
        raise RuntimeError(f"video ended before selected OSNet frames were decoded: {missing[:5]}")

    embeddings = {
        tracklet_id: encoder.encode_crops(crops[tracklet_id])
        for tracklet_id in sorted(crops)
        if crops[tracklet_id]
    }
    return embeddings, selections
