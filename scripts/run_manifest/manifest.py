"""Atomic run-manifest storage and feed-forward artifact guards."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any, Iterable

from scripts.core.errors import MissingArtifactError, RunManifestError, StaleArtifactError
from scripts.core.records import sha256_file


SCHEMA_VERSION = "1.0.0"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_artifact(path: Path) -> tuple[str, int, str]:
    """Return a deterministic content digest, byte count, and kind."""
    path = path.resolve()
    if path.is_file():
        return sha256_file(path), path.stat().st_size, "file"
    if not path.is_dir():
        raise FileNotFoundError(path)
    digest = sha256()
    total_bytes = 0
    for child in sorted(
        candidate
        for candidate in path.rglob("*")
        if candidate.is_file() and ".git" not in candidate.relative_to(path).parts
    ):
        relative = child.relative_to(path).as_posix().encode("utf-8")
        child_digest = sha256_file(child)
        child_size = child.stat().st_size
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(bytes.fromhex(child_digest))
        digest.update(child_size.to_bytes(8, "big"))
        total_bytes += child_size
    return digest.hexdigest(), total_bytes, "directory"


class RunManifest:
    """Mutable-in-memory manifest persisted atomically after each transition."""

    def __init__(self, path: Path, project_root: Path, document: dict[str, Any]):
        self.path = path.resolve()
        self.project_root = project_root.resolve()
        self.document = document
        # Parsed once per artifact: lineage checks re-visit the same producer repeatedly.
        self._quantity_declarations: dict[Path, tuple[str, ...]] = {}

    @classmethod
    def create(
        cls,
        path: Path,
        project_root: Path,
        *,
        run_id: str,
        alignment_tolerance_seconds: float,
        tracking_sample_fps: float | None = None,
        project: dict[str, Any],
        environment: dict[str, Any],
        third_party: dict[str, Any],
    ) -> "RunManifest":
        if alignment_tolerance_seconds < 0:
            raise RunManifestError("alignment tolerance must be non-negative")
        document = {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "status": "running",
            "created_at": utc_now(),
            "alignment_tolerance_seconds": alignment_tolerance_seconds,
            # None means native cadence. Recorded because two runs sampled
            # differently are not comparable, and the difference must never be
            # invisible when their numbers are read side by side.
            "tracking_sample_fps": tracking_sample_fps,
            "project": project,
            "environment": environment,
            "third_party": third_party,
            "sessions": {},
            "artifacts": {},
            "reported_quantities": {},
        }
        manifest = cls(path, project_root, document)
        manifest.save()
        return manifest

    @classmethod
    def load(cls, path: Path, project_root: Path) -> "RunManifest":
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != SCHEMA_VERSION:
            raise RunManifestError(f"unsupported run manifest: {path}")
        # Resuming skips any stage the manifest already recorded as passed, verifying only
        # that its output hash still matches. That is a hash of an artifact produced by
        # WHATEVER code ran then, so a resume across a code change silently mixes artifact
        # shapes -- a pre-cut six-field context window would be reused under the five-field
        # contract and only fail much later, somewhere unrelated.
        # Imported here: measurement imports this module, so a module-level import cycles.
        from scripts.run_manifest.measurement import measure_project

        recorded = (document.get("project") or {}).get("git_commit")
        current = measure_project(project_root).get("git_commit")
        if recorded and current and recorded != current:
            raise RunManifestError(
                f"refusing to resume {path}: it recorded project revision {recorded} but "
                f"the tree is now {current}. Start a new run, or check out {recorded}."
            )
        return cls(path, project_root, document)

    @property
    def run_id(self) -> str:
        return str(self.document["run_id"])

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        temporary.write_text(
            json.dumps(self.document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)

    def _key(self, path: Path) -> str:
        resolved = path.resolve()
        try:
            return resolved.relative_to(self.project_root).as_posix()
        except ValueError:
            return str(resolved)

    def ensure_session(self, session_id: str) -> dict[str, Any]:
        return self.document["sessions"].setdefault(
            session_id,
            {
                "status": "running",
                "cameras": {},
                "stages": {},
                "alignment_checks": [],
                "alignment_within_tolerance": None,
            },
        )

    def record_camera_probe(self, session_id: str, record: dict[str, Any]) -> None:
        session = self.ensure_session(session_id)
        session["cameras"][record["camera_id"]] = record
        self.save()

    def register_artifact(
        self,
        path: Path,
        *,
        session_id: str,
        producer_stage: str,
    ) -> dict[str, Any]:
        key = self._key(path)
        content_hash, byte_count, kind = hash_artifact(path)
        record = {
            "run_id": self.run_id,
            "session_id": session_id,
            "producer_stage": producer_stage,
            "path": key,
            "sha256": content_hash,
            "bytes": byte_count,
            "kind": kind,
            "captured_at": utc_now(),
            "measurement": "capture_at_run",
        }
        self.document["artifacts"][key] = record
        self.save()
        return record

    def is_registered(self, path: Path) -> bool:
        """Whether this run has already hashed `path`, under the same key registration uses."""
        return self._key(path) in self.document["artifacts"]

    def verify_artifact(self, path: Path) -> dict[str, Any]:
        key = self._key(path)
        record = self.document["artifacts"].get(key)
        if record is None:
            # Distinguish "never produced" from "produced by another run": the file not
            # existing at all means its producer did not run, not that a leftover is
            # being rejected.
            if not path.exists():
                raise MissingArtifactError(
                    key,
                    "not produced in this run and absent on disk; its producing stage "
                    "did not run",
                )
            raise StaleArtifactError(key, "not listed in the current run manifest")
        if record.get("run_id") != self.run_id:
            raise StaleArtifactError(key, f"belongs to run {record.get('run_id')!r}")
        if not path.exists():
            raise StaleArtifactError(
                key, "listed artifact is missing", expected_sha256=record.get("sha256")
            )
        actual_sha256, _byte_count, _kind = hash_artifact(path)
        if actual_sha256 != record.get("sha256"):
            raise StaleArtifactError(
                key,
                "content hash does not match the current run manifest",
                expected_sha256=record.get("sha256"),
                actual_sha256=actual_sha256,
            )
        return record

    def verify_inputs(self, paths: Iterable[Path]) -> list[dict[str, Any]]:
        return [self.verify_artifact(path) for path in paths]

    def start_stage(
        self,
        session_id: str,
        stage_name: str,
        *,
        commands: list[list[str]],
        inputs: list[dict[str, Any]],
    ) -> None:
        session = self.ensure_session(session_id)
        session["stages"][stage_name] = {
            "status": "running",
            "started_at": utc_now(),
            "ended_at": None,
            "exit_status": None,
            "commands": commands,
            "inputs": [record["path"] for record in inputs],
            "outputs": [],
        }
        self.save()

    def record_stage_inputs(
        self, session_id: str, stage_name: str, inputs: list[dict[str, Any]]
    ) -> None:
        self.ensure_session(session_id)["stages"][stage_name]["inputs"] = [
            record["path"] for record in inputs
        ]
        self.save()

    def record_stage_command_results(
        self,
        session_id: str,
        stage_name: str,
        results: list[dict[str, Any]],
        *,
        execution: dict[str, Any],
    ) -> None:
        """Persist child timings once, from the manifest-owning parent process.

        Per-camera subprocesses never receive this object. Keeping this write on the
        parent side prevents concurrent register/save operations from replacing the
        manifest with stale in-memory documents and losing artifact records.
        """
        stage = self.ensure_session(session_id)["stages"][stage_name]
        stage["command_execution"] = execution
        stage["command_results"] = results
        self.save()

    def finish_stage(
        self,
        session_id: str,
        stage_name: str,
        *,
        exit_status: int,
        outputs: Iterable[Path] = (),
        failure_reason: str | None = None,
    ) -> None:
        stage = self.ensure_session(session_id)["stages"][stage_name]
        stage["exit_status"] = int(exit_status)
        stage["status"] = "passed" if exit_status == 0 and failure_reason is None else "failed"
        if failure_reason is not None:
            stage["failure_reason"] = failure_reason
        output_paths = list(outputs)
        if output_paths:
            stage["outputs"] = [
                self.register_artifact(
                    path, session_id=session_id, producer_stage=stage_name
                )["path"]
                for path in output_paths
            ]
        # A stage is not finished until its declared outputs have been hashed and
        # registered. Recording this afterward keeps wall-clock intervals truthful,
        # especially for directory artifacts such as per-camera Light-ASD pywork.
        stage["ended_at"] = utc_now()
        self.save()

    def skip_stage(self, session_id: str, stage_name: str, *, reason: str) -> None:
        self.ensure_session(session_id)["stages"][stage_name] = {
            "status": "skipped",
            "reason": reason,
            "recorded_at": utc_now(),
            "exit_status": None,
            "inputs": [],
            "outputs": [],
        }
        self.save()

    def record_alignment(
        self, session_id: str, records: list[dict[str, Any]], *, passed: bool
    ) -> None:
        session = self.ensure_session(session_id)
        session["alignment_checks"] = records
        session["alignment_within_tolerance"] = passed
        self.save()

    def _declared_quantities(self, path: Path) -> set[str] | None:
        """The quantities an artifact says it carries, or None if it makes no such claim.

        Producers of reported quantities write a ``quantity_artifact_map``. Source artifacts
        do not, and their lineage is a "this quantity came from here" statement rather than a
        claim about their own contents, so they are left alone.
        """
        if path.suffix != ".json" or not path.is_file():
            return None
        cached = self._quantity_declarations.get(path)
        if cached is not None:
            return None if cached == () else set(cached)
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        declared = document.get("quantity_artifact_map") if isinstance(document, dict) else None
        if not isinstance(declared, dict):
            self._quantity_declarations[path] = ()
            return None
        self._quantity_declarations[path] = tuple(sorted(declared))
        return set(declared)

    def set_reported_quantities(self, mapping: dict[str, list[Path]]) -> None:
        recorded: dict[str, list[str]] = {}
        for quantity, paths in mapping.items():
            keys = []
            for path in paths:
                key = self._key(path)
                if key not in self.document["artifacts"]:
                    continue
                # A producer that declares its quantities must actually declare THIS one.
                # Recording lineage from the static source map alone let the summary state
                # that a quantity came from an artifact that does not contain it — which is
                # how a paper number could be written with no producer behind it.
                declared = self._declared_quantities(path)
                if declared is not None and quantity not in declared:
                    continue
                keys.append(key)
            recorded[quantity] = keys
        self.document["reported_quantities"] = recorded
        self.save()

    def finish_session(self, session_id: str, *, passed: bool) -> None:
        session = self.ensure_session(session_id)
        session["status"] = "passed" if passed else "failed"
        session["completed_at"] = utc_now()
        self.save()

    def finish_run(self, *, passed: bool) -> None:
        self.document["status"] = "completed" if passed else "failed"
        self.document["completed_at"] = utc_now()
        self.save()
