"""Deterministic, feed-forward person re-identification primitives."""

from .config import IdentityStackConfig, load_identity_config
from .identity_graph import (
    CanonicalTrack,
    Tracklet,
    build_global_identities,
    merge_within_camera,
)

__all__ = [
    "CanonicalTrack",
    "IdentityStackConfig",
    "Tracklet",
    "build_global_identities",
    "load_identity_config",
    "merge_within_camera",
]
