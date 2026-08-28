"""Canonical three-source fusion exports.

The former global-path, four-source confidence and ten-second-default pipeline
was removed because it did not implement the paper contract.
"""

from scripts.flags.fusion import FusedFlag, FusedFlagArtifact, fuse_flags, run_independent_sources

__all__ = ["FusedFlag", "FusedFlagArtifact", "fuse_flags", "run_independent_sources"]
