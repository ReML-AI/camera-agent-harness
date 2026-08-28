"""Compatibility import for the canonical CLIP urgency policy interface.

No templates, thresholds, sampling policy, model revision, or temporal merge
policy is defined here.
"""

from scripts.flags.clip_urgency import (
    ClipUrgencyAdapter,
    ClipUrgencyInterval,
    ClipUrgencyPolicy,
)
from scripts.core.errors import ContractError


class VideoHighlightDetector:
    """Fail-closed boundary for callers of the removed legacy constructor."""

    def __init__(self, model_path, policy, device="cuda", *, paper_mode=True):
        raise ContractError(
            "legacy video-highlight construction is unsupported; provide a ClipUrgencyPolicy to ClipUrgencyAdapter"
        )

__all__ = [
    "ClipUrgencyAdapter",
    "ClipUrgencyInterval",
    "ClipUrgencyPolicy",
    "VideoHighlightDetector",
]
