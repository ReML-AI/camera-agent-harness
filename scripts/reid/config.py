"""Validated configuration loading for the identity stack."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parents[1] / "person_tracking" / "identity_stack.yaml"
)


@dataclass(frozen=True)
class DetectionConfig:
    confidence_threshold: float
    iou_threshold: float
    minimum_box_area_fraction: float
    minimum_height_width_ratio: float
    maximum_height_width_ratio: float


@dataclass(frozen=True)
class EmbeddingConfig:
    input_height: int
    input_width: int
    maximum_crops_per_tracklet: int
    minimum_crop_width_pixels: int
    minimum_crop_height_pixels: int


@dataclass(frozen=True)
class WithinCameraConfig:
    similarity_threshold: float
    maximum_gap_seconds: float


@dataclass(frozen=True)
class CrossCameraConfig:
    similarity_threshold: float
    minimum_copresence_seconds: float


@dataclass(frozen=True)
class IdentityStackConfig:
    schema_version: str
    detection: DetectionConfig
    embedding: EmbeddingConfig
    within_camera: WithinCameraConfig
    cross_camera: CrossCameraConfig


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping")
    return value


def _probability(value: Any, name: str) -> float:
    result = float(value)
    if not 0.0 <= result <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1")
    return result


def _positive_int(value: Any, name: str) -> int:
    result = int(value)
    if result <= 0:
        raise ValueError(f"{name} must be positive")
    return result


def load_identity_config(path: str | Path = DEFAULT_CONFIG_PATH) -> IdentityStackConfig:
    """Load the one declared set of identity thresholds and crop settings."""
    source = Path(path)
    raw = _mapping(yaml.safe_load(source.read_text(encoding="utf-8")), "config")
    if raw.get("schema_version") != "identity-stack-config/1.0":
        raise ValueError("unsupported identity-stack configuration schema")

    detection = _mapping(raw.get("detection"), "detection")
    embedding = _mapping(raw.get("embedding"), "embedding")
    within = _mapping(raw.get("within_camera"), "within_camera")
    cross = _mapping(raw.get("cross_camera"), "cross_camera")

    min_ratio = float(detection["minimum_height_width_ratio"])
    max_ratio = float(detection["maximum_height_width_ratio"])
    if min_ratio <= 0 or max_ratio < min_ratio:
        raise ValueError("detection aspect-ratio bounds are invalid")

    maximum_gap = float(within["maximum_gap_seconds"])
    minimum_copresence = float(cross["minimum_copresence_seconds"])
    if maximum_gap < 0 or minimum_copresence < 0:
        raise ValueError("temporal thresholds cannot be negative")

    return IdentityStackConfig(
        schema_version=raw["schema_version"],
        detection=DetectionConfig(
            confidence_threshold=_probability(
                detection["confidence_threshold"], "detection.confidence_threshold"
            ),
            iou_threshold=_probability(detection["iou_threshold"], "detection.iou_threshold"),
            minimum_box_area_fraction=_probability(
                detection["minimum_box_area_fraction"],
                "detection.minimum_box_area_fraction",
            ),
            minimum_height_width_ratio=min_ratio,
            maximum_height_width_ratio=max_ratio,
        ),
        embedding=EmbeddingConfig(
            input_height=_positive_int(embedding["input_height"], "embedding.input_height"),
            input_width=_positive_int(embedding["input_width"], "embedding.input_width"),
            maximum_crops_per_tracklet=_positive_int(
                embedding["maximum_crops_per_tracklet"],
                "embedding.maximum_crops_per_tracklet",
            ),
            minimum_crop_width_pixels=_positive_int(
                embedding["minimum_crop_width_pixels"],
                "embedding.minimum_crop_width_pixels",
            ),
            minimum_crop_height_pixels=_positive_int(
                embedding["minimum_crop_height_pixels"],
                "embedding.minimum_crop_height_pixels",
            ),
        ),
        within_camera=WithinCameraConfig(
            similarity_threshold=_probability(
                within["similarity_threshold"], "within_camera.similarity_threshold"
            ),
            maximum_gap_seconds=maximum_gap,
        ),
        cross_camera=CrossCameraConfig(
            similarity_threshold=_probability(
                cross["similarity_threshold"], "cross_camera.similarity_threshold"
            ),
            minimum_copresence_seconds=minimum_copresence,
        ),
    )
