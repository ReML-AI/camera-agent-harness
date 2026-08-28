#!/usr/bin/env python3
"""Native-cadence YOLOv8s-seg + BoT-SORT tracking and OSNet canonicalization."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.core.records import canonical_track_id, sha256_file
from scripts.reid.config import DEFAULT_CONFIG_PATH, IdentityStackConfig, load_identity_config
from scripts.reid.embeddings import OSNetEncoder, extract_tracklet_embeddings
from scripts.reid.identity_graph import Tracklet, merge_within_camera


DEFAULT_TRACKER_CONFIG = Path(__file__).resolve().with_name("botsort_identity_stack.yaml")
PINNED_ULTRALYTICS_VERSION = "8.4.8"
GRAB_TIMESTAMP_PROBE_FRAMES = 8


def decoded_presentation_timestamp_seconds(capture: Any, cv2_module: Any) -> float:
    """Read the decoder/backend presentation timestamp without FPS synthesis."""
    milliseconds = float(capture.get(cv2_module.CAP_PROP_POS_MSEC))
    if not math.isfinite(milliseconds) or milliseconds < 0.0:
        raise RuntimeError("video backend did not expose a valid decoded presentation timestamp")
    return milliseconds / 1000.0


def grab_preserves_presentation_timestamps(
    video_path: str | Path,
    cv2_module: Any,
    *,
    probe_frame_count: int = GRAB_TIMESTAMP_PROBE_FRAMES,
) -> bool:
    """Return whether this OpenCV backend exposes final frame PTS after ``grab``.

    OpenCV backends differ here.  Decimation may avoid ``retrieve`` only when the
    timestamp visible after ``grab`` is exactly the timestamp that ``read`` would
    have exposed after its implicit ``retrieve``.  Probe a few frames on a separate
    capture so a failed probe can safely retain the full-read path from frame zero.
    """
    probe = cv2_module.VideoCapture(str(video_path))
    if not probe.isOpened():
        probe.release()
        return False

    checked_frames = 0
    try:
        while checked_frames < probe_frame_count and probe.grab():
            try:
                grabbed_pts = decoded_presentation_timestamp_seconds(probe, cv2_module)
            except RuntimeError:
                return False
            retrieved, _frame = probe.retrieve()
            if not retrieved:
                return False
            try:
                retrieved_pts = decoded_presentation_timestamp_seconds(probe, cv2_module)
            except RuntimeError:
                return False
            if grabbed_pts != retrieved_pts:
                return False
            checked_frames += 1
    finally:
        probe.release()
    return checked_frames > 0


class _DecodedFrameStream:
    """Advance real frame positions while decoding pixels only when required."""

    def __init__(
        self,
        capture: Any,
        cv2_module: Any,
        sample_fps: float | None,
        *,
        grab_discarded_frames: bool,
    ) -> None:
        self.capture = capture
        self.cv2_module = cv2_module
        self.sample_fps = sample_fps
        self.grab_discarded_frames = grab_discarded_frames
        self.frame_index = 0
        self.previous_pts = -1.0
        self.next_sample_time = -1.0

    def _record_timestamp(self, pts_seconds: float, frame_index: int) -> None:
        if pts_seconds < self.previous_pts:
            raise RuntimeError(
                "decoded presentation timestamps moved backwards at frame "
                f"{frame_index}: {pts_seconds} < {self.previous_pts}"
            )
        self.previous_pts = pts_seconds

    def _keep(self, pts_seconds: float) -> bool:
        if self.sample_fps is None:
            return True
        if pts_seconds + 1e-9 < self.next_sample_time:
            return False
        self.next_sample_time = pts_seconds + (1.0 / self.sample_fps)
        return True

    def read_next_kept(self) -> tuple[int, float, Any] | None:
        """Return the next kept frame, or ``None`` at end of stream."""
        while True:
            frame_index = self.frame_index
            if self.grab_discarded_frames:
                if not self.capture.grab():
                    return None
                pts_seconds = decoded_presentation_timestamp_seconds(
                    self.capture, self.cv2_module
                )
                self._record_timestamp(pts_seconds, frame_index)
                if not self._keep(pts_seconds):
                    self.frame_index += 1
                    continue

                ok, frame = self.capture.retrieve()
                if not ok:
                    return None
                retrieved_pts = decoded_presentation_timestamp_seconds(
                    self.capture, self.cv2_module
                )
                if retrieved_pts != pts_seconds:
                    raise RuntimeError(
                        "video backend changed the presentation timestamp during retrieve at "
                        f"frame {frame_index}: {pts_seconds} -> {retrieved_pts}"
                    )
                # This is the same post-retrieve value used by capture.read().
                pts_seconds = retrieved_pts
            else:
                ok, frame = self.capture.read()
                if not ok:
                    return None
                pts_seconds = decoded_presentation_timestamp_seconds(
                    self.capture, self.cv2_module
                )
                self._record_timestamp(pts_seconds, frame_index)
                if not self._keep(pts_seconds):
                    self.frame_index += 1
                    continue

            self.frame_index += 1
            return frame_index, pts_seconds, frame


def _valid_detection(
    bbox_xyxy: Sequence[float], frame_width: int, frame_height: int, config: IdentityStackConfig
) -> bool:
    x1, y1, x2, y2 = (float(value) for value in bbox_xyxy)
    width, height = x2 - x1, y2 - y1
    if width <= 0.0 or height <= 0.0 or frame_width <= 0 or frame_height <= 0:
        return False
    area_fraction = width * height / float(frame_width * frame_height)
    height_width_ratio = height / width
    return (
        area_fraction >= config.detection.minimum_box_area_fraction
        and config.detection.minimum_height_width_ratio
        <= height_width_ratio
        <= config.detection.maximum_height_width_ratio
    )


def _appearance_from_observations(
    observations: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    ordered = sorted(
        observations,
        key=lambda item: (
            float(item["presentation_timestamp_seconds"]), int(item["frame_index"])
        ),
    )
    return {
        "start_frame": int(ordered[0]["frame_index"]),
        "end_frame": int(ordered[-1]["frame_index"]),
        "start_time": float(ordered[0]["presentation_timestamp_seconds"]),
        "end_time": float(ordered[-1]["presentation_timestamp_seconds"]),
        "bounding_boxes": [
            {
                "frame_num": int(item["frame_index"]),
                "timestamp": float(item["presentation_timestamp_seconds"]),
                "bbox": list(item["bbox_normalized"]),
                "confidence": float(item["confidence"]),
            }
            for item in ordered
        ],
    }


class PersonTracker:
    """Pinned local models and deterministic policies for one camera at a time."""

    def __init__(
        self,
        model_path: str | Path,
        model_sha256: str,
        osnet_model_path: str | Path,
        osnet_model_sha256: str,
        *,
        device: str = "cpu",
        config_path: str | Path = DEFAULT_CONFIG_PATH,
        tracker_config_path: str | Path = DEFAULT_TRACKER_CONFIG,
        sample_fps: float | None = None,
    ) -> None:
        if sample_fps is not None and sample_fps <= 0:
            raise ValueError("sample_fps must be positive when given")
        self.sample_fps = sample_fps
        weights = Path(model_path)
        tracker_config = Path(tracker_config_path)
        if not weights.is_file():
            raise FileNotFoundError(f"Local YOLOv8s-seg weights are required: {weights}")
        if not tracker_config.is_file():
            raise FileNotFoundError(f"Pinned BoT-SORT config is required: {tracker_config}")
        actual_sha256 = sha256_file(weights)
        if actual_sha256 != model_sha256:
            raise ValueError(
                f"YOLOv8s-seg weights checksum mismatch: expected {model_sha256}, "
                f"got {actual_sha256}"
            )

        import ultralytics
        from ultralytics import YOLO

        if ultralytics.__version__ != PINNED_ULTRALYTICS_VERSION:
            raise RuntimeError(
                "person tracking requires pinned ultralytics "
                f"{PINNED_ULTRALYTICS_VERSION}, got {ultralytics.__version__}"
            )

        self.model = YOLO(str(weights))
        if getattr(self.model, "task", None) != "segment":
            raise ValueError("person tracking requires a YOLO segmentation checkpoint")
        self.config = load_identity_config(config_path)
        self.encoder = OSNetEncoder(
            osnet_model_path, osnet_model_sha256, self.config.embedding
        )
        self.model_path = str(weights.resolve())
        self.model_sha256 = actual_sha256
        self.osnet_model_path = self.encoder.model_path
        self.osnet_model_sha256 = self.encoder.model_sha256
        self.device = device
        self.config_path = str(Path(config_path).resolve())
        self.config_sha256 = sha256_file(Path(config_path))
        self.tracker_config_path = str(tracker_config.resolve())
        self.tracker_config_sha256 = sha256_file(tracker_config)

    def reset_tracking_state(self) -> None:
        """Prevent BoT-SORT state from leaking from one camera into another."""
        self.model.predictor = None

    def _track_decoded_frames(
        self, video_path: str | Path, camera_id: str
    ) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]], dict[str, Any]]:
        import cv2

        grab_discarded_frames = self.sample_fps is not None and (
            grab_preserves_presentation_timestamps(video_path, cv2)
        )
        if self.sample_fps is not None and not grab_discarded_frames:
            print(
                "OpenCV does not expose stable post-grab presentation timestamps; "
                "decimation is retaining capture.read() for timestamp correctness.",
                file=sys.stderr,
            )

        capture = cv2.VideoCapture(str(video_path))
        if not capture.isOpened():
            capture.release()
            raise RuntimeError(f"OpenCV could not open video: {video_path}")

        reported_fps = float(capture.get(cv2.CAP_PROP_FPS))
        frame_count_hint = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        frames: list[dict[str, Any]] = []
        observations: dict[str, list[dict[str, Any]]] = {}
        self.reset_tracking_state()
        decoded_stream = _DecodedFrameStream(
            capture,
            cv2,
            self.sample_fps,
            grab_discarded_frames=grab_discarded_frames,
        )
        try:
            while True:
                decoded = decoded_stream.read_next_kept()
                if decoded is None:
                    break
                frame_index, pts_seconds, frame = decoded

                height, width = frame.shape[:2]

                results = self.model.track(
                    frame,
                    persist=True,
                    tracker=self.tracker_config_path,
                    classes=[0],
                    conf=self.config.detection.confidence_threshold,
                    iou=self.config.detection.iou_threshold,
                    device=self.device,
                    verbose=False,
                )
                detections: list[dict[str, Any]] = []
                boxes = results[0].boxes
                if boxes is not None:
                    bbox_rows = boxes.xyxy.cpu().tolist()
                    confidence_values = boxes.conf.cpu().tolist()
                    tracker_id_values = (
                        boxes.id.cpu().tolist() if boxes.id is not None else [None] * len(boxes)
                    )
                    for bbox_values, confidence_value, tracker_id_value in zip(
                        bbox_rows, confidence_values, tracker_id_values
                    ):
                        bbox = [float(value) for value in bbox_values]
                        if not _valid_detection(bbox, width, height, self.config):
                            continue
                        confidence = float(confidence_value)
                        tracker_id = (
                            int(tracker_id_value) if tracker_id_value is not None else None
                        )
                        normalized = [
                            bbox[0] / width,
                            bbox[1] / height,
                            bbox[2] / width,
                            bbox[3] / height,
                        ]
                        detection: dict[str, Any] = {
                            "tracker_id": tracker_id,
                            "bbox_xyxy_pixels": bbox,
                            "bbox_normalized": normalized,
                            "confidence": confidence,
                        }
                        detections.append(detection)
                        if tracker_id is not None:
                            tracklet_id = canonical_track_id(camera_id, tracker_id)
                            observation = {
                                "frame_index": frame_index,
                                "presentation_timestamp_seconds": pts_seconds,
                                "bbox_xyxy_pixels": bbox,
                                "bbox_normalized": normalized,
                                "confidence": confidence,
                            }
                            observations.setdefault(tracklet_id, []).append(observation)

                frames.append(
                    {
                        "frame_index": frame_index,
                        "presentation_timestamp_seconds": pts_seconds,
                        "detections": detections,
                    }
                )
        finally:
            capture.release()

        metadata = {
            "decoded_frame_count": decoded_stream.frame_index,
            "container_frame_count_hint": frame_count_hint,
            "container_reported_fps": reported_fps,
            "discarded_frame_advance": (
                "grab" if grab_discarded_frames else "read"
            ),
            "last_decoded_presentation_timestamp_seconds": (
                frames[-1]["presentation_timestamp_seconds"] if frames else None
            ),
        }
        return frames, observations, metadata

    def process_video(
        self, video_path: str | Path, output_path: str | Path, camera_id: str | None = None
    ) -> dict[str, Any]:
        source = Path(video_path)
        camera = camera_id or source.stem
        frames, observations, metadata = self._track_decoded_frames(source, camera)
        embeddings, crop_selections = extract_tracklet_embeddings(
            source, observations, self.encoder, self.config.embedding
        )

        tracklets = [
            Tracklet(
                camera_id=camera,
                tracklet_id=tracklet_id,
                start_seconds=float(items[0]["presentation_timestamp_seconds"]),
                end_seconds=float(items[-1]["presentation_timestamp_seconds"]),
                embedding=embeddings.get(tracklet_id),
            )
            for tracklet_id, items in sorted(observations.items())
        ]
        canonical_tracks, within_edges, cannot_links = merge_within_camera(
            tracklets,
            similarity_threshold=self.config.within_camera.similarity_threshold,
            maximum_gap_seconds=self.config.within_camera.maximum_gap_seconds,
        )

        canonical_by_member = {
            member: track.canonical_track_id
            for track in canonical_tracks
            for member in track.member_tracklet_ids
        }
        for frame in frames:
            for detection in frame["detections"]:
                tracker_id = detection["tracker_id"]
                detection["canonical_track_id"] = (
                    canonical_by_member.get(canonical_track_id(camera, tracker_id))
                    if tracker_id is not None
                    else None
                )

        raw_tracklets = [
            {
                "tracklet_id": tracklet.tracklet_id,
                "tracker_id": int(tracklet.tracklet_id.rsplit(":", 1)[1]),
                "start_presentation_timestamp_seconds": tracklet.start_seconds,
                "end_presentation_timestamp_seconds": tracklet.end_seconds,
                "observation_count": len(observations[tracklet.tracklet_id]),
                "embedding": list(tracklet.embedding) if tracklet.embedding is not None else None,
                "crop_selection": crop_selections.get(tracklet.tracklet_id, []),
            }
            for tracklet in tracklets
        ]

        canonical_payload: list[dict[str, Any]] = []
        persons: list[dict[str, Any]] = []
        for person_id, track in enumerate(canonical_tracks, start=1):
            appearances = [
                _appearance_from_observations(observations[member])
                for member in track.member_tracklet_ids
            ]
            confidences = [
                float(item["confidence"])
                for member in track.member_tracklet_ids
                for item in observations[member]
            ]
            active_intervals = [list(interval) for interval in track.active_intervals]
            canonical_payload.append(
                {
                    "canonical_track_id": track.canonical_track_id,
                    "member_tracklet_ids": list(track.member_tracklet_ids),
                    "active_intervals": active_intervals,
                    "embedding": list(track.embedding) if track.embedding is not None else None,
                }
            )
            persons.append(
                {
                    "person_id": person_id,
                    "track_id": track.canonical_track_id,
                    "thumbnail_path": None,
                    "all_thumbnail_paths": [],
                    "embedding": list(track.embedding) if track.embedding is not None else None,
                    "appearances": appearances,
                    "total_screen_time_seconds": round(
                        sum(end - start for start, end in track.active_intervals), 6
                    ),
                    "average_confidence": (
                        sum(confidences) / len(confidences) if confidences else 0.0
                    ),
                    "num_appearances": len(appearances),
                }
            )

        payload: dict[str, Any] = {
            "schema_version": "person-tracks/2.0",
            "video_source": str(source),
            "camera_id": camera,
            "processing_info": {
                **metadata,
                "native_cadence": self.sample_fps is None,
                "tracking_sample_fps": self.sample_fps,
                "timestamp_source": "decoded_presentation_timestamp",
                "detector": "YOLOv8s-seg person class only",
                "tracker": "BoT-SORT",
                "detector_model_path": self.model_path,
                "detector_model_sha256": self.model_sha256,
                "osnet_model_path": self.osnet_model_path,
                "osnet_model_sha256": self.osnet_model_sha256,
                "identity_config_path": self.config_path,
                "identity_config_sha256": self.config_sha256,
                "tracker_config_path": self.tracker_config_path,
                "tracker_config_sha256": self.tracker_config_sha256,
            },
            "frames": frames,
            "raw_tracklets": raw_tracklets,
            "canonical_tracks": canonical_payload,
            "within_camera_edges": within_edges,
            "cannot_links": [list(pair) for pair in sorted(cannot_links)],
            "persons": persons,
            "capture_at_run": {
                "raw_local_tracklet_count": len(raw_tracklets),
                "canonical_identity_count": len(canonical_payload),
                "accepted_merge_edge_count": sum(
                    bool(edge["accepted"]) for edge in within_edges
                ),
                "rejected_merge_edge_count": sum(
                    not bool(edge["accepted"]) for edge in within_edges
                ),
            },
            "quality_status": "not_evaluated_without_identity_ground_truth",
        }

        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", help="input video path")
    parser.add_argument("--camera-id", help="stable camera ID; defaults to video stem")
    parser.add_argument("--all-cameras", action="store_true")
    parser.add_argument("--output", help="output JSON path")
    parser.add_argument("--output-dir", default="data/processed")
    parser.add_argument("--model-path", required=True, help="local yolov8s-seg.pt")
    parser.add_argument("--model-sha256", required=True)
    parser.add_argument("--osnet-model-path", required=True, help="local OSNet ONNX model")
    parser.add_argument("--osnet-model-sha256", required=True)
    parser.add_argument(
        "--sample-fps", type=float, default=None,
        help="decimate tracking to this rate; omit for native cadence. Lower rates are\n"
             "cheaper but widen inter-frame motion, which fragments BoT-SORT tracks.",
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--tracker-config", default=str(DEFAULT_TRACKER_CONFIG))
    parser.add_argument("--gpu", action="store_true", help="run YOLO on CUDA when available")
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    if not args.all_cameras and not (args.video and args.output):
        parser.error("specify --video and --output, or --all-cameras")

    device = "cpu"
    if args.gpu:
        import torch

        if torch.cuda.is_available():
            device = "cuda"
    tracker = PersonTracker(
        args.model_path,
        args.model_sha256,
        args.osnet_model_path,
        args.osnet_model_sha256,
        device=device,
        config_path=args.config,
        tracker_config_path=args.tracker_config,
        sample_fps=args.sample_fps,
    )

    outputs: list[dict[str, Any]] = []
    if args.all_cameras:
        output_dir = Path(args.output_dir)
        for camera in ("cam1", "cam2", "cam3"):
            video = Path("data/videos") / f"{camera}.mp4"
            if video.is_file():
                outputs.append(
                    tracker.process_video(
                        video, output_dir / f"person_tracks_{camera}.json", camera
                    )
                )
    else:
        outputs.append(tracker.process_video(args.video, args.output, args.camera_id))

    for output in outputs:
        counts = output["capture_at_run"]
        print(
            f"{output['camera_id']}: capture_at_run raw_local_tracklets="
            f"{counts['raw_local_tracklet_count']} canonical_identities="
            f"{counts['canonical_identity_count']} (quality not evaluated)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
