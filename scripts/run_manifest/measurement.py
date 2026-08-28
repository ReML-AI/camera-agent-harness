"""Runtime, repository, and third-party measurements captured for a run."""

from __future__ import annotations

import importlib.metadata
import os
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any

import yaml

from scripts.core.errors import RunManifestError
from .manifest import hash_artifact, utc_now


PACKAGE_NAMES = {
    "torch": "torch",
    "ultralytics": "ultralytics",
    "whisperx": "whisperx",
    "onnxruntime": "onnxruntime",
}


DEPLOYED_COMMIT_FILE = "DEPLOYED_COMMIT"


def _git_commit(path: Path) -> str:
    """Return the commit this tree was built from.

    A deployed copy has no .git — scripts/setup/deploy.sh excludes it so the payload
    stays small — so deploy.sh records the source commit in DEPLOYED_COMMIT instead.
    Read git first, fall back to that file, and fail if neither is present: provenance
    stays mandatory, it just no longer requires shipping the repository.
    """
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()

    recorded = path / DEPLOYED_COMMIT_FILE
    if recorded.is_file():
        commit = recorded.read_text(encoding="utf-8").strip()
        if commit:
            return commit

    raise RunManifestError(
        f"cannot measure git commit for {path}: not a git checkout and no "
        f"{DEPLOYED_COMMIT_FILE} file written by deploy.sh ({result.stderr.strip()})"
    )


def measure_project(project_root: Path) -> dict[str, Any]:
    return {
        "root": str(project_root.resolve()),
        "git_commit": _git_commit(project_root),
        "captured_at": utc_now(),
        "measurement": "capture_at_run",
    }


def measure_environment() -> dict[str, Any]:
    packages: dict[str, dict[str, Any]] = {}
    for label, distribution in PACKAGE_NAMES.items():
        try:
            version = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            packages[label] = {"installed": False, "measurement": "capture_at_run"}
        else:
            packages[label] = {
                "installed": True,
                "version": version,
                "measurement": "capture_at_run",
            }
    return {
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "executable": sys.executable,
            "measurement": "capture_at_run",
        },
        "packages": packages,
        "captured_at": utc_now(),
    }


def _resolved_path(raw_path: Any, project_root: Path) -> Path | None:
    if not isinstance(raw_path, str) or not raw_path or raw_path == "capture_at_run":
        return None
    expanded = os.path.expandvars(raw_path)
    if "$" in expanded:
        return None
    path = Path(expanded)
    return path.resolve() if path.is_absolute() else (project_root / path).resolve()


def measure_third_party(project_root: Path, manifest_path: Path) -> dict[str, Any]:
    """Capture only facts observable from the current checkout and staged bytes."""
    manifest_hash, manifest_bytes, _kind = hash_artifact(manifest_path)
    payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    components = []
    for configured in payload.get("components", []):
        component_id = configured.get("component_id")
        install_path = _resolved_path(configured.get("install_path"), project_root)
        record: dict[str, Any] = {
            "component_id": component_id,
            "present": bool(install_path and install_path.exists()),
            "captured_at": utc_now(),
            "measurement": "capture_at_run",
        }
        if install_path is not None:
            record["resolved_path"] = str(install_path)
        if install_path is not None and install_path.exists():
            digest, byte_count, kind = hash_artifact(install_path)
            record.update({
                "sha256": digest,
                "bytes": byte_count,
                "kind": kind,
                "resolved_version": f"sha256:{digest}",
            })
        checkout = _resolved_path(configured.get("source", {}).get("checkout_path"), project_root)
        if checkout is not None and (checkout / ".git").exists():
            record["checkout_path"] = str(checkout)
            record["git_commit"] = _git_commit(checkout)
            record["resolved_version"] = f"git:{record['git_commit']}"
        components.append(record)
    return {
        "manifest_path": str(manifest_path.resolve()),
        "manifest_sha256": manifest_hash,
        "manifest_bytes": manifest_bytes,
        "components": components,
        "captured_at": utc_now(),
        "measurement": "capture_at_run",
    }
