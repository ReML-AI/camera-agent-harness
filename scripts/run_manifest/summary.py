"""Human-readable completed-run validation summary."""

from __future__ import annotations

from typing import Any, Mapping

from scripts.core.errors import RunManifestError


def format_run_summary(document: Mapping[str, Any]) -> str:
    if document.get("status") not in {"completed", "failed"}:
        raise RunManifestError("run summary requires a completed or failed run")
    stages = [
        stage
        for session in document.get("sessions", {}).values()
        for stage in session.get("stages", {}).values()
    ]
    # A stage that dies before it is recorded (for example on argument validation)
    # never enters `stages`, so an all() over the survivors would report success for a
    # run that failed. The run status is authoritative: a failed run cannot have had
    # every stage pass, whatever the recorded subset says.
    every_stage_passed = (
        document.get("status") == "completed"
        and bool(stages)
        and all(
            stage.get("status") == "passed" and stage.get("exit_status") == 0
            for stage in stages
        )
    )
    sessions = list(document.get("sessions", {}).values())
    drift_passed = bool(sessions) and all(
        session.get("alignment_within_tolerance") is True for session in sessions
    )
    lines = [
        f"Run: {document.get('run_id')}",
        f"Run status: {document.get('status')}",
        f"Every stage passed: {'yes' if every_stage_passed else 'no'}",
        (
            "Alignment drift within "
            f"{document.get('alignment_tolerance_seconds')} seconds: "
            f"{'yes' if drift_passed else 'no'}"
        ),
        "Reported quantity lineage:",
    ]
    quantities = document.get("reported_quantities", {})
    if not quantities:
        lines.append("  (none recorded)")
    for quantity in sorted(quantities):
        artifacts = quantities[quantity]
        lines.append(f"  {quantity}:")
        if artifacts:
            lines.extend(f"    - {artifact}" for artifact in artifacts)
        else:
            lines.append("    - (no artifact produced in this run)")
    return "\n".join(lines)
