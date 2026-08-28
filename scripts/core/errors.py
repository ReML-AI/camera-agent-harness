"""Errors used at paper-contract boundaries."""


class ContractError(ValueError):
    """Raised when an input violates a versioned interface contract."""


class RunManifestError(RuntimeError):
    """Base class for failures at a run-manifest boundary."""


class StaleArtifactError(RunManifestError):
    """Raised when a stage input is not an intact artifact of the current run."""

    code = "STALE_ARTIFACT"

    def __init__(
        self,
        artifact_path: str,
        reason: str,
        *,
        expected_sha256: str | None = None,
        actual_sha256: str | None = None,
    ) -> None:
        self.artifact_path = artifact_path
        self.reason = reason
        self.expected_sha256 = expected_sha256
        self.actual_sha256 = actual_sha256
        detail = f"{self.code}: {artifact_path}: {reason}"
        if expected_sha256 is not None:
            detail += f" (manifest sha256={expected_sha256}"
            if actual_sha256 is not None:
                detail += f", current sha256={actual_sha256}"
            detail += ")"
        super().__init__(detail)


class MissingArtifactError(RunManifestError):
    """Raised when a required stage input was never produced in this run.

    Deliberately distinct from StaleArtifactError: a stale artifact means "delete it
    and re-run", whereas a missing one means "its producing stage did not run" — often
    a stage absent from the run graph. Reporting both as STALE sends the reader to the
    wrong fix, which it did once here.
    """

    code = "MISSING_ARTIFACT"

    def __init__(self, artifact_path: str, reason: str) -> None:
        self.artifact_path = artifact_path
        self.reason = reason
        super().__init__(f"{self.code}: {artifact_path}: {reason}")


class TimingProbeError(RunManifestError):
    """Raised when authoritative media timing cannot be measured."""

    code = "TIMING_PROBE_FAILED"


class AlignmentDriftError(RunManifestError):
    """Raised when a decoded frame PTS exceeds the declared drift tolerance."""

    code = "ALIGNMENT_DRIFT_EXCEEDED"

    def __init__(
        self,
        camera_id: str,
        frame_index: int,
        difference_seconds: float,
        tolerance_seconds: float,
    ) -> None:
        self.camera_id = camera_id
        self.frame_index = frame_index
        self.difference_seconds = difference_seconds
        self.tolerance_seconds = tolerance_seconds
        super().__init__(
            f"{self.code}: {camera_id} frame {frame_index} differs by "
            f"{difference_seconds:.9f}s (tolerance {tolerance_seconds:.9f}s)"
        )


class MetricDefinitionUnresolvedError(ContractError):
    """Raised before an unresolved metric can emit a plausible value."""

    code = "METRIC_DEFINITION_UNRESOLVED"
