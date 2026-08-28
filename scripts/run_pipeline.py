#!/usr/bin/env python3
"""Run the paper pipeline with measured timing and feed-forward provenance.

Examples:
    python3 scripts/run_pipeline.py --session-id session_001 \
        --alignment-tolerance-seconds 0.05
    python3 scripts/run_pipeline.py --session-id all \
        --alignment-tolerance-seconds 0.05
    python3 scripts/run_pipeline.py --summary data/runs/RUN_ID/run_manifest.json
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time
from typing import Iterable, Sequence

try:
    from scripts.core.errors import RunManifestError
    from scripts.analytics.compute_paper_metrics import COHORT_QUANTITY_IDS, SESSION_QUANTITY_IDS
    from scripts.run_manifest import (
        RunManifest,
        build_alignment_records,
        decode_presentation_timestamps,
        derived_frame_index,
        format_run_summary,
        measure_environment,
        measure_project,
        measure_third_party,
        probe_video,
        select_transcript_timestamps,
        validate_alignment_records,
    )
    from scripts.utils.session_paths import (
        PROJECT_ROOT,
        metrics_dir,
        prerequisites_dir,
        processed_dir,
        raw_dir,
        session_dir,
        videos_dir,
    )
except ImportError:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(PROJECT_ROOT))
    from scripts.core.errors import RunManifestError
    from scripts.analytics.compute_paper_metrics import COHORT_QUANTITY_IDS, SESSION_QUANTITY_IDS
    from scripts.run_manifest import (
        RunManifest,
        build_alignment_records,
        decode_presentation_timestamps,
        derived_frame_index,
        format_run_summary,
        measure_environment,
        measure_project,
        measure_third_party,
        probe_video,
        select_transcript_timestamps,
        validate_alignment_records,
    )
    from scripts.utils.session_paths import (
        metrics_dir,
        prerequisites_dir,
        processed_dir,
        raw_dir,
        session_dir,
        videos_dir,
    )


_VENV_PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python3"
PYTHON = str(_VENV_PYTHON) if _VENV_PYTHON.exists() else sys.executable
CAMERAS = ("cam1", "cam2", "cam3")
SBATCH_DEFAULTS = {
    "gres": "gpu:1",
    "cpus_per_task": 12,
    "time": "12:00:00",
}


STAGES = [
    ("1_diarization", True, [
        PYTHON, "scripts/diarization/run_whisperx.py", "--audio", "{videos_dir}/cam1.mp4",
        "--output", "{raw_dir}/diarized_transcript_full.json",
    ]),
    ("2_person_tracking", True, "PER_CAMERA"),
    ("2_cross_camera_identity", False, [
        PYTHON, "scripts/reid/match_cameras.py",
        "--input", "cam1={raw_dir}/person_tracks_cam1.json",
        "--input", "cam2={raw_dir}/person_tracks_cam2.json",
        "--input", "cam3={raw_dir}/person_tracks_cam3.json",
        "--output", "{processed_dir}/global_visual_identities.json",
    ]),
    ("4_asd", True, "PER_CAMERA"),
    ("4_asd_artifact", False, "ASD_ASSEMBLY"),
    ("3_head_pose", True, "PER_CAMERA"),
    ("5_clip_scenes", True, [
        PYTHON, "scripts/analytics/compute_clip_scenes.py", "--session-id", "{sid}",
    ]),
    ("6_monitor_ocr", False, [
        PYTHON, "scripts/extract_monitor_vitals.py", "--session-id", "{sid}", "--device", "cpu",
    ]),
    ("7_clip_urgency_scoring", True, [
        PYTHON, "scripts/focal/pipeline_stages.py", "score-clip",
        "--session-id", "{sid}",
        "--session-manifest", "{prerequisites_dir}/session_manifest.json",
        "--video", "cam1={videos_dir}/cam1.mp4",
        "--video", "cam2={videos_dir}/cam2.mp4",
        "--video", "cam3={videos_dir}/cam3.mp4",
        "--output", "{raw_dir}/clip_urgency_records.json",
    ]),
    ("7_flag_production", False, [
        PYTHON, "scripts/focal/pipeline_stages.py", "produce-flags",
        "--session-id", "{sid}",
        "--transcript", "{raw_dir}/diarized_transcript_full.json",
        "--clip-records", "{raw_dir}/clip_urgency_records.json",
        "--monitor-vitals", "{raw_dir}/monitor_vitals.json",
        "--output-dir", "{processed_dir}",
    ]),
    ("8_speaker_link_multi", False, [
        PYTHON, "scripts/diarization/link_speakers_multicam.py", "--session-id", "{sid}",
        "--transcript", "{raw_dir}/diarized_transcript_full.json",
        "--asd", "{raw_dir}/asd_tracks.json",
    ]),
    ("9_gaze_classification", False, [
        PYTHON, "scripts/gaze/classify_gaze_targets.py", "--session-id", "{sid}",
        # Attention is gated per frame against the selected view's ASD score, so this
        # stage requires the ASD artifact to enforce the declared per-frame gate.
        "--asd", "{raw_dir}/asd_tracks.json",
    ]),
    ("10_speaker_dynamics", False, [
        PYTHON, "scripts/analytics/compute_speaker_dynamics.py", "--session-id", "{sid}",
    ]),
    ("11_gaze_events", False, [
        PYTHON, "scripts/analytics/compute_gaze_events.py", "--session-id", "{sid}",
    ]),
    ("12_interaction_analytics", False, [
        PYTHON, "scripts/diarization/compute_interaction_analytics.py", "--session-id", "{sid}",
    ]),
    ("13_multimodal_context", False, [
        PYTHON, "scripts/analytics/assemble_multimodal_windows.py", "--session-id", "{sid}",
    ]),
    ("14_moment_detection", False, [
        PYTHON, "scripts/focal/pipeline_stages.py", "run-focal",
        "--session-id", "{sid}",
        "--transcript", "{raw_dir}/diarized_transcript_full.json",
        "--windows", "{processed_dir}/multimodal_windows.json",
        "--output", "{processed_dir}/moments_multimodal.json",
    ]),
    ("15_moment_context", False, [
        PYTHON, "scripts/analytics/compute_moment_context.py", "--session-id", "{sid}",
    ]),
    ("16_moment_narratives", False, [
        PYTHON, "scripts/analytics/generate_moment_narratives.py", "--session-id", "{sid}",
    ]),
    ("17_video_overlay", False, [
        PYTHON, "scripts/analytics/compute_video_overlay.py", "--session-id", "{sid}",
    ]),
    ("18_paper_metrics", False, [
        PYTHON, "scripts/analytics/compute_paper_metrics.py", "--session-id", "{sid}",
        "--run-manifest", "{run_manifest}",
    ]),
]
COHORT_METRICS_STAGE = "19_aggregate_paper_metrics"

# Hand-authored inputs that decide reported values. The patient zones fix every
# attention label, so they belong in run provenance exactly like a model checkpoint.
CHECKED_IN_RUN_INPUTS = (
    PROJECT_ROOT / "scripts" / "gaze" / "patient_zone_calibrations.json",
)


def _component(manifest: RunManifest, component_id: str) -> dict:
    for component in manifest.document["third_party"]["components"]:
        if component.get("component_id") == component_id:
            if not component.get("present"):
                raise RunManifestError(
                    f"required component {component_id} was not present when the run was captured"
                )
            return component
    raise RunManifestError(f"required component is absent from third-party manifest: {component_id}")


def _operator_path(manifest: RunManifest, name: str) -> str:
    value = manifest.document.get("operator_inputs", {}).get(name)
    if not value:
        raise RunManifestError(f"this stage requires --{name.replace('_', '-')}")
    return str(value)


def _per_camera_command(
    stage_name: str,
    sid: str,
    camera: str,
    fps: str,
    manifest: RunManifest,
) -> list[str]:
    if stage_name == "2_person_tracking":
        detector = _component(manifest, "yolov8_seg")
        osnet = _component(manifest, "osnet_x0_25_msmt17")
        command = [
            PYTHON, "scripts/person_tracking/track_persons.py", "--video",
            str(videos_dir(sid) / f"{camera}.mp4"), "--camera-id", camera, "--output",
            str(raw_dir(sid) / f"person_tracks_{camera}.json"), "--model-path",
            detector["resolved_path"], "--model-sha256", detector["sha256"],
            "--osnet-model-path", osnet["resolved_path"], "--osnet-model-sha256",
            osnet["sha256"], "--gpu",
        ]
        # Decimation is opt-in. Omitting it keeps native cadence, which is what BoT-SORT
        # needs for reliable association; passing a rate is an explicit cost/quality trade
        # and the chosen value is recorded in the tracking artifact.
        sample_fps = manifest.document.get("tracking_sample_fps")
        if sample_fps is not None:
            command += ["--sample-fps", str(sample_fps)]
        return command
    if stage_name == "4_asd":
        light_asd = _component(manifest, "light_asd")
        return [
            PYTHON, "scripts/run_light_asd.py", "--session-id", sid, "--camera", camera,
            "--repository-path", light_asd["checkout_path"], "--weights-path",
            light_asd["resolved_path"], "--weights-sha256", light_asd["sha256"], "--force",
        ]
    if stage_name == "3_head_pose":
        model = _component(manifest, "6drepnet360")
        return [
            PYTHON, "scripts/diarization/run_head_pose.py", "--video",
            str(videos_dir(sid) / f"{camera}.mp4"), "--asd-pywork",
            str(raw_dir(sid) / f"asd_{camera}" / "pywork"), "--output",
            str(raw_dir(sid) / f"head_pose_{camera}.json"), "--camera", camera,
            "--repository-path", _operator_path(manifest, "head_pose_repository_path"),
            "--weights-path", model["resolved_path"], "--weights-sha256", model["sha256"],
            "--fps", fps,
        ]
    raise KeyError(stage_name)


def _resolve_command(
    template: Iterable[str], sid: str, manifest: RunManifest | None = None
) -> list[str]:
    replacements = {
        "{sid}": sid,
        "{videos_dir}": str(videos_dir(sid)),
        "{raw_dir}": str(raw_dir(sid)),
        "{processed_dir}": str(processed_dir(sid)),
        "{prerequisites_dir}": str(prerequisites_dir(sid)),
        "{run_manifest}": str(manifest.path) if manifest is not None else "{run_manifest}",
    }
    return [
        next((part.replace(token, value) for token, value in replacements.items() if token in part), part)
        for part in template
    ]


def _augment_command(stage_name: str, command: list[str], manifest: RunManifest) -> list[str]:
    if stage_name == "1_diarization":
        return [
            *command,
            "--asr-model-path", _operator_path(manifest, "asr_model_path"),
            "--alignment-model-name", _operator_path(manifest, "alignment_model_name"),
            "--alignment-model-path", _operator_path(manifest, "alignment_model_path"),
            "--alignment-cache-path", _operator_path(manifest, "alignment_cache_path"),
            "--diarization-model-name", _operator_path(manifest, "diarization_model_name"),
            "--diarization-cache-path", _operator_path(manifest, "diarization_cache_path"),
        ]
    if stage_name == "5_clip_scenes":
        model = _component(manifest, "clip")
        return [*command, "--model-path", model["resolved_path"]]
    if stage_name == "6_monitor_ocr":
        sample_rate = manifest.document.get("operator_inputs", {}).get("monitor_sample_rate")
        if sample_rate is None:
            raise RunManifestError("this stage requires --monitor-sample-rate")
        return [
            *command, "--config", _operator_path(manifest, "monitor_config"),
            "--sample-rate", str(sample_rate),
        ]
    if stage_name == "7_clip_urgency_scoring":
        model = _component(manifest, "clip")
        return [*command, "--model-path", model["resolved_path"]]
    if stage_name == "7_flag_production":
        return [*command, "--monitor-config", _operator_path(manifest, "monitor_config")]
    if stage_name == "14_moment_detection":
        return [
            *command,
            "--runtime-config", _operator_path(manifest, "focal_runtime_config"),
        ]
    return command


def _stage_inputs(sid: str, stage_name: str, manifest: RunManifest) -> list[Path]:
    video = lambda camera: videos_dir(sid) / f"{camera}.mp4"
    raw = raw_dir(sid)
    processed = processed_dir(sid)
    mapping = {
        "1_diarization": [video("cam1")],
        "2_person_tracking": [video(camera) for camera in CAMERAS],
        "2_cross_camera_identity": [
            raw / f"person_tracks_{camera}.json" for camera in CAMERAS
        ],
        "4_asd": [video(camera) for camera in CAMERAS],
        "4_asd_artifact": [raw / f"asd_{camera}" / "pywork" for camera in CAMERAS],
        "3_head_pose": [
            *[video(camera) for camera in CAMERAS],
            *[raw / f"asd_{camera}" / "pywork" for camera in CAMERAS],
        ],
        "5_clip_scenes": [video(camera) for camera in CAMERAS],
        "6_monitor_ocr": [video("monitor")],
        "7_clip_urgency_scoring": [
            prerequisites_dir(sid) / "session_manifest.json",
            *[video(camera) for camera in CAMERAS],
        ],
        "7_flag_production": [
            raw / "diarized_transcript_full.json", raw / "clip_urgency_records.json",
            raw / "monitor_vitals.json",
        ],
        "8_speaker_link_multi": [
            raw / "diarized_transcript_full.json", raw / "asd_tracks.json",
            # global_visual_identities.json is deliberately NOT listed. Stage 8 links
            # speakers to per-camera tracks from ASD scores alone and never opens the
            # cross-camera visual identity artifact. Declaring it made the manifest assert
            # a dependency that does not exist, so changing that artifact would appear to
            # affect identity_map and best_angles when it cannot. The artifact is still
            # produced and registered; it is simply not an input here.
        ],
        "9_gaze_classification": [
            processed / "identity_map.json", processed / "best_angles.json",
            raw / "asd_tracks.json",
            *[raw / f"head_pose_{camera}.json" for camera in CAMERAS],
            # The patient zones are hand-authored coordinates that decide every attention
            # label, so they are a first-class input. Without this declaration, correcting
            # a box would leave Stage 9 looking fresh and the gaze artifact could not show
            # which coordinates produced its labels.
            PROJECT_ROOT / "scripts" / "gaze" / "patient_zone_calibrations.json",
        ],
        "10_speaker_dynamics": [raw / "diarized_transcript_full.json"],
        "11_gaze_events": [raw / "gaze_tracks.json", raw / "diarized_transcript_full.json"],
        "12_interaction_analytics": [
            raw / "diarized_transcript_full.json", processed / "identity_map.json",
            processed / "best_angles.json", raw / "head_pose_cam1.json", raw / "gaze_tracks.json",
        ],
        "13_multimodal_context": [
            prerequisites_dir(sid) / "session_manifest.json",
            raw / "diarized_transcript_full.json", raw / "clip_scene_descriptions.json",
            raw / "gaze_tracks.json", processed / "speaker_dynamics.json",
            processed / "gaze_events.json", processed / "fused_flags.json",
        ],
        "14_moment_detection": [
            raw / "diarized_transcript_full.json", processed / "multimodal_windows.json",
        ],
        "15_moment_context": [
            processed / "moments_multimodal.json", raw / "diarized_transcript_full.json",
            raw / "gaze_tracks.json", raw / "monitor_vitals.json",
            processed / "interaction_analytics.json",
        ],
        "16_moment_narratives": [processed / "moment_contexts.json"],
        "17_video_overlay": [
            raw / "person_tracks_cam1.json", raw / "head_pose_cam1.json",
            processed / "identity_map.json", processed / "best_angles.json",
            processed / "moment_contexts.json",
            # person_roles.json is deliberately absent: the overlay labels people by the
            # tracker's own identities, so it needs no hand-labelled prerequisite.
        ],
        "18_paper_metrics": [
            prerequisites_dir(sid) / "session_manifest.json", raw / "asd_tracks.json",
            processed / "best_angles.json", processed / "identity_map.json",
            raw / "diarized_transcript_full.json", processed / "moments_multimodal.json",
            raw / "gaze_tracks.json", processed / "multimodal_windows.json",
            *[raw / f"asd_{camera}" / "pywork" / "faces.pckl" for camera in CAMERAS],
            *[raw / f"head_pose_{camera}.json" for camera in CAMERAS],
        ],
    }
    dependencies: list[Path] = []
    if stage_name == "1_diarization":
        dependencies = [
            Path(_operator_path(manifest, "asr_model_path")),
            Path(_operator_path(manifest, "alignment_model_path")),
            Path(_operator_path(manifest, "alignment_cache_path")),
            Path(_operator_path(manifest, "diarization_cache_path")),
        ]
    elif stage_name == "2_person_tracking":
        dependencies = [
            Path(_component(manifest, "yolov8_seg")["resolved_path"]),
            Path(_component(manifest, "osnet_x0_25_msmt17")["resolved_path"]),
        ]
    elif stage_name == "4_asd":
        dependencies = [
            Path(_component(manifest, "light_asd")["resolved_path"]),
            Path(_component(manifest, "light_asd")["checkout_path"]),
        ]
    elif stage_name == "3_head_pose":
        dependencies = [
            Path(_component(manifest, "6drepnet360")["resolved_path"]),
            Path(_operator_path(manifest, "head_pose_repository_path")),
        ]
    elif stage_name == "5_clip_scenes":
        dependencies = [Path(_component(manifest, "clip")["resolved_path"])]
    elif stage_name == "6_monitor_ocr":
        dependencies = [Path(_operator_path(manifest, "monitor_config"))]
    elif stage_name == "7_clip_urgency_scoring":
        dependencies = [Path(_component(manifest, "clip")["resolved_path"])]
    elif stage_name == "7_flag_production":
        dependencies = [Path(_operator_path(manifest, "monitor_config"))]
    elif stage_name == "14_moment_detection":
        dependencies = [Path(_operator_path(manifest, "focal_runtime_config"))]
    return [*mapping[stage_name], *dependencies]


def _stage_outputs(sid: str, stage_name: str) -> list[Path]:
    raw = raw_dir(sid)
    processed = processed_dir(sid)
    mapping = {
        "1_diarization": [raw / "diarized_transcript_full.json"],
        "2_person_tracking": [raw / f"person_tracks_{camera}.json" for camera in CAMERAS],
        "2_cross_camera_identity": [processed / "global_visual_identities.json"],
        "4_asd": [
            *[raw / f"asd_{camera}" / "pywork" for camera in CAMERAS],
            *[raw / f"asd_{camera}" / "pywork" / "faces.pckl" for camera in CAMERAS],
        ],
        "4_asd_artifact": [raw / "asd_tracks.json"],
        "3_head_pose": [raw / f"head_pose_{camera}.json" for camera in CAMERAS],
        "5_clip_scenes": [raw / "clip_scene_descriptions.json"],
        "6_monitor_ocr": [raw / "monitor_vitals.json"],
        "7_clip_urgency_scoring": [raw / "clip_urgency_records.json"],
        "7_flag_production": [
            processed / "flags_clip_urgency.json",
            processed / "flags_vitals_threshold.json",
            processed / "flags_transcript_keyword.json",
            processed / "fused_flags.json",
        ],
        "8_speaker_link_multi": [processed / "identity_map.json", processed / "best_angles.json"],
        "9_gaze_classification": [raw / "gaze_tracks.json"],
        "10_speaker_dynamics": [processed / "speaker_dynamics.json"],
        "11_gaze_events": [processed / "gaze_events.json"],
        "12_interaction_analytics": [processed / "interaction_analytics.json"],
        "13_multimodal_context": [processed / "multimodal_windows.json"],
        "14_moment_detection": [processed / "moments_multimodal.json"],
        "15_moment_context": [processed / "moment_contexts.json"],
        "16_moment_narratives": [processed / "moment_narratives.json"],
        "17_video_overlay": [processed / "video_overlay_data.json"],
        "18_paper_metrics": [metrics_dir(sid) / "paper_metrics.json"],
    }
    return mapping[stage_name]


def _submit_sbatch(command: list[str], stage_name: str, sid: str) -> int:
    """Submit and wait; the returned status is sbatch's measured job exit status."""
    log_dir = session_dir(sid) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{stage_name}_%j.log"
    quoted_command = shlex.join(command)
    script = f"""#!/bin/bash
#SBATCH --job-name={sid}_{stage_name}
#SBATCH --gres={SBATCH_DEFAULTS['gres']}
#SBATCH --cpus-per-task={SBATCH_DEFAULTS['cpus_per_task']}
#SBATCH --time={SBATCH_DEFAULTS['time']}
#SBATCH --output={log_file}
#SBATCH --error={log_file}

export PATH={shlex.quote(str(PROJECT_ROOT / '.venv' / 'bin'))}:$PATH
export PYTHONPATH={shlex.quote(str(PROJECT_ROOT))}:${{PYTHONPATH:-}}
cd {shlex.quote(str(PROJECT_ROOT))}
{quoted_command}
"""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".sh", prefix=f"slurm_{stage_name}_", dir=log_dir, delete=False
    ) as handle:
        handle.write(script)
        script_path = Path(handle.name)
    result = subprocess.run(
        ["sbatch", "--wait", "--parsable", str(script_path)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    if result.stdout.strip():
        print(f"  SLURM {result.stdout.strip()}")
    if result.stderr.strip():
        print(f"  SLURM: {result.stderr.strip()}")
    return result.returncode


def _run_command(
    command: list[str],
    *,
    requires_gpu: bool,
    local: bool,
    stage_name: str,
    sid: str,
    cpu_threads: int | None = None,
) -> int:
    print(f"  RUN: {shlex.join(command)}")
    if requires_gpu and not local:
        return _submit_sbatch(command, stage_name, sid)
    environment = os.environ.copy()
    current_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        str(PROJECT_ROOT) if not current_pythonpath
        else f"{PROJECT_ROOT}{os.pathsep}{current_pythonpath}"
    )
    if cpu_threads is not None:
        # Per-camera processes otherwise each discover the whole node and create their
        # own full-sized BLAS/OpenMP pools. Partition the allocated CPUs explicitly so
        # concurrency does not become oversubscription. These control execution only;
        # they do not change model inputs or output policies.
        thread_text = str(max(1, cpu_threads))
        for variable in (
            "OMP_NUM_THREADS",
            "MKL_NUM_THREADS",
            "OPENBLAS_NUM_THREADS",
            "NUMEXPR_NUM_THREADS",
            "OPENCV_FOR_THREADS_NUM",
            "PIPELINE_COMMAND_THREADS",
        ):
            environment[variable] = thread_text
    return subprocess.run(command, cwd=PROJECT_ROOT, env=environment).returncode


def _allocated_cpu_count() -> int:
    """Return the scheduler allocation, falling back to the visible host CPUs."""
    value = os.environ.get("SLURM_CPUS_PER_TASK")
    if value is not None:
        try:
            allocated = int(value)
        except ValueError:
            allocated = 0
        if allocated > 0:
            return allocated
    return os.cpu_count() or 1


def _timed_run_command(
    command_index: int,
    command: list[str],
    *,
    requires_gpu: bool,
    local: bool,
    stage_name: str,
    sid: str,
    cpu_threads: int,
) -> dict:
    started_at = datetime.now(timezone.utc).isoformat()
    started_clock = time.monotonic()
    failure_reason = None
    try:
        exit_status = _run_command(
            command,
            requires_gpu=requires_gpu,
            local=local,
            stage_name=stage_name,
            sid=sid,
            cpu_threads=cpu_threads,
        )
    except Exception as error:  # Preserve a truthful failed-stage transition.
        exit_status = 1
        failure_reason = f"{type(error).__name__}: {error}"
    result = {
        "command_index": command_index,
        "started_at": started_at,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": time.monotonic() - started_clock,
        "exit_status": int(exit_status),
    }
    if failure_reason is not None:
        result["failure_reason"] = failure_reason
    return result


def _run_stage_commands(
    commands: list[list[str]],
    *,
    parallel: bool,
    max_workers: int,
    requires_gpu: bool,
    local: bool,
    stage_name: str,
    sid: str,
) -> tuple[int, list[dict], dict]:
    """Run independent commands and return a deterministic aggregate status.

    This function never receives the manifest. Workers only touch their declared
    per-camera outputs; all manifest mutation remains serialized in the parent.
    """
    worker_count = min(max_workers, len(commands)) if parallel else 1
    cpu_threads = max(1, _allocated_cpu_count() // worker_count)
    if worker_count > 1:
        print(
            f"  PARALLEL: {worker_count} camera commands, "
            f"{cpu_threads} CPU threads per command"
        )
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [
                executor.submit(
                    _timed_run_command,
                    index,
                    command,
                    requires_gpu=requires_gpu,
                    local=local,
                    stage_name=stage_name,
                    sid=sid,
                    cpu_threads=cpu_threads,
                )
                for index, command in enumerate(commands)
            ]
            results = [future.result() for future in futures]
    else:
        results = []
        for index, command in enumerate(commands):
            result = _timed_run_command(
                index,
                command,
                requires_gpu=requires_gpu,
                local=local,
                stage_name=stage_name,
                sid=sid,
                cpu_threads=cpu_threads,
            )
            results.append(result)
            if result["exit_status"] != 0:
                break
    results.sort(key=lambda result: result["command_index"])
    exit_status = next(
        (result["exit_status"] for result in results if result["exit_status"] != 0),
        0,
    )
    execution = {
        "mode": "parallel" if worker_count > 1 else "serial",
        "worker_count": worker_count,
        "allocated_cpu_count": _allocated_cpu_count(),
        "cpu_threads_per_command": cpu_threads,
    }
    return exit_status, results, execution


def _commands_for_stage(stage_name: str, template, sid: str, manifest: RunManifest) -> list[list[str]]:
    if template == "ASD_ASSEMBLY":
        probes = manifest.document["sessions"][sid]["cameras"]
        missing = [camera for camera in CAMERAS if camera not in probes]
        if missing:
            raise RunManifestError(f"no measured camera timing for {sid}/{missing[0]}")
        command = [PYTHON, "scripts/focal/pipeline_stages.py", "assemble-asd"]
        for camera in CAMERAS:
            probe = probes[camera]
            fps = f"{probe['fps_numerator'] / probe['fps_denominator']:.12g}"
            command.extend([
                "--input", f"{camera}={raw_dir(sid) / f'asd_{camera}' / 'pywork'}",
                "--fps", f"{camera}={fps}",
            ])
        command.extend(["--output", str(raw_dir(sid) / "asd_tracks.json")])
        return [command]
    if template != "PER_CAMERA":
        return [
            _augment_command(
                stage_name, _resolve_command(template, sid, manifest), manifest
            )
        ]
    probes = manifest.document["sessions"][sid]["cameras"]
    commands = []
    for camera in CAMERAS:
        if camera not in probes:
            raise RunManifestError(f"no measured camera timing for {sid}/{camera}")
        probe = probes[camera]
        fps = f"{probe['fps_numerator'] / probe['fps_denominator']:.12g}"
        commands.append(_per_camera_command(stage_name, sid, camera, fps, manifest))
    return commands


def _register_session_sources(manifest: RunManifest, sid: str) -> None:
    session = manifest.ensure_session(sid)
    video_files = sorted(videos_dir(sid).glob("*.mp4"))
    if not video_files:
        raise RunManifestError(f"no session videos found for {sid}")
    for video_path in video_files:
        relative = video_path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
        if relative in manifest.document["artifacts"]:
            manifest.verify_artifact(video_path)
        else:
            manifest.register_artifact(video_path, session_id=sid, producer_stage="source_video")
        if video_path.stem not in session["cameras"]:
            manifest.record_camera_probe(sid, probe_video(video_path, video_path.stem).to_dict())
    prereq_root = prerequisites_dir(sid)
    if prereq_root.exists():
        for source in sorted(path for path in prereq_root.rglob("*") if path.is_file()):
            relative = source.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
            if relative in manifest.document["artifacts"]:
                manifest.verify_artifact(source)
            else:
                manifest.register_artifact(
                    source, session_id=sid, producer_stage="source_prerequisite"
                )


def _validate_session_alignment(manifest: RunManifest, sid: str) -> bool:
    transcript_path = raw_dir(sid) / "diarized_transcript_full.json"
    camera_paths = [Path(value["video_path"]) for value in manifest.document["sessions"][sid]["cameras"].values()]
    inputs = manifest.verify_inputs([transcript_path, *camera_paths])
    manifest.start_stage(
        sid, "timing_validation", commands=[["internal:temporal_alignment"]], inputs=inputs
    )
    all_records = []
    alignment_path = manifest.path.parent / "sessions" / sid / "temporal_alignment.json"
    try:
        transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
        for payload in manifest.document["sessions"][sid]["cameras"].values():
            from scripts.core.records import CameraTimingProbe
            probe = CameraTimingProbe(**payload)
            samples = select_transcript_timestamps(transcript, probe.duration_seconds)
            frame_indices = [derived_frame_index(timestamp, probe) for _position, timestamp in samples]
            decoded = decode_presentation_timestamps(Path(probe.video_path), frame_indices)
            all_records.extend(build_alignment_records(
                session_id=sid,
                probe=probe,
                samples=samples,
                decoded_timestamps=decoded,
                tolerance_seconds=manifest.document["alignment_tolerance_seconds"],
            ))
        alignment_document = {
            "schema_version": "1.0.0",
            "run_id": manifest.run_id,
            "session_id": sid,
            "measurement": "capture_at_run",
            "records": [record.to_dict() for record in all_records],
        }
        alignment_path.parent.mkdir(parents=True, exist_ok=True)
        alignment_path.write_text(
            json.dumps(alignment_document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        validate_alignment_records(all_records)
    except Exception as error:
        manifest.record_alignment(sid, [record.to_dict() for record in all_records], passed=False)
        outputs = [alignment_path] if alignment_path.exists() else []
        manifest.finish_stage(
            sid,
            "timing_validation",
            exit_status=1,
            outputs=outputs,
            failure_reason=str(error),
        )
        print(f"  FAIL timing_validation: {error}")
        return False
    manifest.record_alignment(sid, [record.to_dict() for record in all_records], passed=True)
    manifest.finish_stage(sid, "timing_validation", exit_status=0, outputs=[alignment_path])
    return True


def run_stage(
    stage_name: str,
    requires_gpu: bool,
    template,
    sid: str,
    manifest: RunManifest,
    *,
    force: bool = False,
    local: bool = False,
    per_camera_workers: int = 3,
) -> bool:
    previous = manifest.ensure_session(sid)["stages"].get(stage_name)
    if previous and previous.get("status") == "passed" and not force:
        manifest.verify_inputs(PROJECT_ROOT / path for path in previous.get("outputs", []))
        print(f"  SKIP {stage_name} (already passed in run {manifest.run_id})")
        return True
    try:
        commands = _commands_for_stage(stage_name, template, sid, manifest)
    except Exception as error:
        print(f"  FAIL {stage_name}: {error}")
        return False
    manifest.start_stage(sid, stage_name, commands=commands, inputs=[])
    try:
        inputs = manifest.verify_inputs(_stage_inputs(sid, stage_name, manifest))
        manifest.record_stage_inputs(sid, stage_name, inputs)
    except Exception as error:
        manifest.finish_stage(sid, stage_name, exit_status=1, failure_reason=str(error))
        print(f"  FAIL {stage_name}: {error}")
        return False
    # A non-local GPU stage submits one Slurm job per command. Keep that mode
    # serial so this process cannot unexpectedly consume three GPU allocations. The
    # normal run_session.sbatch path passes --local and shares its one allocated GPU.
    parallel = template == "PER_CAMERA" and (local or not requires_gpu)
    exit_status, command_results, command_execution = _run_stage_commands(
        commands,
        parallel=parallel,
        max_workers=per_camera_workers,
        requires_gpu=requires_gpu,
        local=local,
        stage_name=stage_name,
        sid=sid,
    )
    manifest.record_stage_command_results(
        sid, stage_name, command_results, execution=command_execution
    )
    if exit_status != 0:
        manifest.finish_stage(sid, stage_name, exit_status=exit_status)
        print(f"  FAIL {stage_name} (exit status {exit_status})")
        return False
    outputs = _stage_outputs(sid, stage_name)
    missing = [str(path) for path in outputs if not path.exists()]
    if missing:
        reason = f"stage exited successfully but did not produce: {', '.join(missing)}"
        manifest.finish_stage(sid, stage_name, exit_status=exit_status, failure_reason=reason)
        print(f"  FAIL {stage_name}: {reason}")
        return False
    try:
        manifest.finish_stage(sid, stage_name, exit_status=exit_status, outputs=outputs)
    except Exception as error:
        manifest.finish_stage(sid, stage_name, exit_status=1, failure_reason=str(error))
        print(f"  FAIL {stage_name}: could not capture outputs: {error}")
        return False
    return True


def _quantity_lineage(session_ids: Iterable[str]) -> dict[str, list[Path]]:
    mapping: dict[str, list[Path]] = {}
    for sid in session_ids:
        raw = raw_dir(sid)
        processed = processed_dir(sid)
        mapping.update({
            f"speaker_identity[{sid}]": [processed / "identity_map.json"],
            f"best_angle_selection[{sid}]": [processed / "best_angles.json"],
            f"visual_attention[{sid}]": [raw / "gaze_tracks.json", processed / "gaze_events.json"],
            f"global_visual_identity[{sid}]": [processed / "global_visual_identities.json"],
            f"active_speaker_detection[{sid}]": [raw / "asd_tracks.json"],
            f"fused_flags[{sid}]": [processed / "fused_flags.json"],
            f"speaker_dynamics[{sid}]": [processed / "speaker_dynamics.json"],
            f"interaction_analytics[{sid}]": [processed / "interaction_analytics.json"],
            f"reported_moments[{sid}]": [processed / "moments_multimodal.json", processed / "moment_contexts.json"],
            f"reported_narratives[{sid}]": [processed / "moment_narratives.json"],
            f"paper_metrics[{sid}]": [metrics_dir(sid) / "paper_metrics.json"],
        })
        mapping.update({
            f"{quantity_id}[{sid}]": [metrics_dir(sid) / "paper_metrics.json"]
            for quantity_id in SESSION_QUANTITY_IDS
        })
    return mapping


def _cohort_quantity_lineage(output: Path) -> dict[str, list[Path]]:
    return {
        f"{quantity_id}[cohort]": [output]
        for quantity_id in COHORT_QUANTITY_IDS
    }


def run_cohort_metrics(
    session_ids: Sequence[str], manifest: RunManifest, *, local: bool = False
) -> bool:
    """Aggregate only after every requested session metric artifact passed."""
    inputs = [metrics_dir(sid) / "paper_metrics.json" for sid in session_ids]
    output = manifest.path.parent / "paper_metrics.json"
    command = [
        PYTHON, "scripts/analytics/aggregate_paper_metrics.py",
        "--output", str(output),
        "--expected-session-count", str(len(session_ids)),
    ]
    for sid, path in zip(session_ids, inputs):
        command.extend(["--input", str(path), "--expected-session-id", sid])
    stage = {
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "ended_at": None,
        "exit_status": None,
        "commands": [command],
        "inputs": [],
        "outputs": [],
    }
    manifest.document["cohort_metrics_stage"] = stage
    manifest.save()
    try:
        records = manifest.verify_inputs(inputs)
        stage["inputs"] = [record["path"] for record in records]
        manifest.save()
    except Exception as error:
        stage.update({
            "status": "failed", "exit_status": 1,
            "ended_at": datetime.now(timezone.utc).isoformat(),
            "failure_reason": str(error),
        })
        manifest.save()
        print(f"  FAIL {COHORT_METRICS_STAGE}: {error}")
        return False
    exit_status = _run_command(
        command, requires_gpu=False, local=local,
        stage_name=COHORT_METRICS_STAGE, sid="cohort",
    )
    if exit_status != 0 or not output.is_file():
        reason = (
            f"exit status {exit_status}" if exit_status != 0
            else f"stage exited successfully but did not produce: {output}"
        )
        stage.update({
            "status": "failed", "exit_status": exit_status or 1,
            "ended_at": datetime.now(timezone.utc).isoformat(),
            "failure_reason": reason,
        })
        manifest.save()
        print(f"  FAIL {COHORT_METRICS_STAGE}: {reason}")
        return False
    record = manifest.register_artifact(
        output, session_id="cohort", producer_stage=COHORT_METRICS_STAGE
    )
    stage.update({
        "status": "passed", "exit_status": 0,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "outputs": [record["path"]],
    })
    manifest.save()
    return True


def run_pipeline(
    sid: str,
    manifest: RunManifest,
    *,
    from_stage: str | None = None,
    force: bool = False,
    gpu_only: bool = False,
    local: bool = False,
    skip_stages: set[str] | None = None,
    per_camera_workers: int = 3,
) -> bool:
    skip_stages = skip_stages or set()
    print(f"\nPipeline: {sid} [run {manifest.run_id}]")
    stage_names = {stage_name for stage_name, _gpu, _template in STAGES}
    if from_stage is not None and from_stage not in stage_names:
        print(f"  FAIL: unknown --from-stage {from_stage}")
        manifest.finish_session(sid, passed=False)
        return False
    unknown_skips = skip_stages - stage_names
    if unknown_skips:
        print(f"  FAIL: unknown --skip-stages values: {', '.join(sorted(unknown_skips))}")
        manifest.finish_session(sid, passed=False)
        return False
    try:
        _register_session_sources(manifest, sid)
    except Exception as error:
        print(f"  FAIL source capture: {error}")
        manifest.finish_session(sid, passed=False)
        return False
    started = from_stage is None
    incomplete = False
    for stage_name, requires_gpu, template in STAGES:
        if not started and stage_name == from_stage:
            started = True
        if not started:
            continue
        if stage_name in skip_stages or (gpu_only and not requires_gpu):
            reason = "--skip-stages" if stage_name in skip_stages else "--gpu-only"
            manifest.skip_stage(sid, stage_name, reason=reason)
            incomplete = True
            continue
        if not run_stage(
            stage_name,
            requires_gpu,
            template,
            sid,
            manifest,
            force=force,
            local=local,
            per_camera_workers=per_camera_workers,
        ):
            manifest.finish_session(sid, passed=False)
            return False
        if stage_name == "1_diarization" and not _validate_session_alignment(manifest, sid):
            manifest.finish_session(sid, passed=False)
            return False
    # Explicit partial execution is useful for scheduling, but it is not a successful
    # paper run and must never be represented as one in the manifest.
    manifest.finish_session(sid, passed=not incomplete)
    return not incomplete


def _find_all_sessions() -> list[str]:
    root = PROJECT_ROOT / "data" / "sessions"
    return sorted(path.name for path in root.iterdir() if path.is_dir()) if root.exists() else []


def _new_run_id() -> str:
    captured = datetime.now(timezone.utc)
    return "run-" + captured.strftime("%Y%m%dT%H%M%S.%fZ")




def _operator_input_values(args) -> dict:
    """The operator-supplied inputs a run records. One definition, used by create and resume."""
    return {
        "asr_model_path": args.asr_model_path,
        "alignment_model_name": args.alignment_model_name,
        "alignment_model_path": args.alignment_model_path,
        "alignment_cache_path": args.alignment_cache_path,
        "diarization_model_name": args.diarization_model_name,
        "diarization_cache_path": args.diarization_cache_path,
        "head_pose_repository_path": args.head_pose_repository_path,
        "monitor_config": args.monitor_config,
        "monitor_sample_rate": args.monitor_sample_rate,
        "focal_runtime_config": args.focal_runtime_config,
    }


def _operator_input_text(value) -> str:
    """The one textual form of an operator input, whichever side it arrived from.

    Both the freshly parsed flag and the value read back out of the manifest go through
    this, so the resume check compares inputs rather than JSON types. `--monitor-sample-rate
    1.0` parses to a float and older manifests stored it as the JSON number 1.0, so a
    str-vs-float comparison rejected a resume that supplied exactly the recorded value.
    """
    return str(value.resolve()) if isinstance(value, Path) else str(value)


def _register_operator_input_dependencies(manifest: RunManifest, inputs: dict) -> None:
    """Record the hash of every operator input that names a real file on disk.

    Membership is decided by resolving the value rather than by a list of field names. The
    list this replaced covered `*_path` and `monitor_config`, so the focal runtime config was
    never registered and the stage that requires it rejected its own input as "not listed in
    the current run manifest". Model names and numbers do not exist as paths and are skipped,
    so the check stays as tight as the list was without needing to be kept in step with it.
    """
    for _name, value in sorted(inputs.items()):
        path = Path(str(value))
        # Registering only what is not already registered keeps this idempotent, so it can
        # repair a manifest that recorded an input without ever hashing its file. Re-hashing
        # an input that IS registered would quietly bless a config edited between runs,
        # which is exactly the substitution the stale-artifact check exists to catch.
        if path.exists() and not manifest.is_registered(path):
            manifest.register_artifact(
                path, session_id="run-input", producer_stage="run_input_capture"
            )


def _merge_resumed_operator_inputs(args, manifest: RunManifest) -> None:
    """Allow a resumed run to supply operator inputs it never had, but never to change one.

    Operator inputs are recorded when the manifest is created. A run that stopped before a
    stage existed has no entry for that stage's inputs, and supplying one on resume rewrites
    nothing — the stage never ran. Silently ignoring it, which is what happened here, makes
    the stage fail again with the same "requires --x" message while the flag sits unused on
    the command line.

    Changing an input that IS recorded is different: earlier stages already consumed it, so
    the run would no longer describe one coherent configuration. That is refused.
    """
    recorded = manifest.document.setdefault("operator_inputs", {})
    added = {}
    for name, value in _operator_input_values(args).items():
        if value is None:
            continue
        text = _operator_input_text(value)
        current = recorded.get(name)
        if current in (None, ""):
            recorded[name] = text
            added[name] = text
        elif _operator_input_text(current) != text:
            raise RunManifestError(
                f"cannot change operator input {name!r} while resuming a run: "
                f"recorded {current!r}, supplied {text!r}"
            )
    # Registration runs over every recorded input, not just the ones added here. An earlier
    # resume could record an input without hashing its file, and that manifest then failed
    # its own stage on every subsequent attempt with no way to recover; the registration is
    # idempotent, so sweeping all of them repairs that state and is a no-op otherwise.
    _register_operator_input_dependencies(manifest, recorded)
    manifest.save()
    for name in sorted(added):
        print(f"  resumed run gained operator input: --{name.replace('_', '-')}")


def _create_or_load_manifest(args) -> RunManifest:
    if args.run_manifest and args.run_manifest.exists():
        manifest = RunManifest.load(args.run_manifest, PROJECT_ROOT)
        if args.alignment_tolerance_seconds is not None and (
            args.alignment_tolerance_seconds != manifest.document["alignment_tolerance_seconds"]
        ):
            raise RunManifestError("cannot change alignment tolerance while resuming a run")
        _merge_resumed_operator_inputs(args, manifest)
        # A checked-in input added to the graph after this run started was never hashed,
        # so the stage declaring it would reject it as unlisted and the run could not be
        # resumed at all. Registering it here is idempotent and never re-hashes a file
        # already recorded, so a genuinely altered input is still caught.
        for path in CHECKED_IN_RUN_INPUTS:
            if path.is_file() and not manifest.is_registered(path):
                manifest.register_artifact(
                    path, session_id="run-input", producer_stage="run_input_capture"
                )
                print(f"  resumed run gained checked-in input: {path.name}")
        return manifest
    if args.alignment_tolerance_seconds is None:
        raise RunManifestError("--alignment-tolerance-seconds is required for a new run")
    run_id = _new_run_id()
    path = args.run_manifest or PROJECT_ROOT / "data" / "runs" / run_id / "run_manifest.json"
    manifest = RunManifest.create(
        path,
        PROJECT_ROOT,
        run_id=run_id,
        alignment_tolerance_seconds=args.alignment_tolerance_seconds,
        tracking_sample_fps=args.tracking_sample_fps,
        project=measure_project(PROJECT_ROOT),
        environment=measure_environment(),
        third_party=measure_third_party(PROJECT_ROOT, PROJECT_ROOT / "third_party" / "manifest.yaml"),
    )
    operator_inputs = {
        name: _operator_input_text(value)
        for name, value in _operator_input_values(args).items()
        if value is not None
    }
    manifest.document["operator_inputs"] = operator_inputs
    dependency_paths = {
        Path(component[field])
        for component in manifest.document["third_party"]["components"]
        for field in ("resolved_path", "checkout_path")
        if component.get(field)
    }
    # Checked-in inputs that no stage produces but stages depend on. They are hashed at
    # run creation so a stage declaring one can verify it, and so editing one invalidates
    # the stages that consumed it rather than leaving stale results looking fresh.
    dependency_paths.update(CHECKED_IN_RUN_INPUTS)
    for dependency in sorted(dependency_paths):
        if dependency.exists():
            manifest.register_artifact(
                dependency, session_id="run-input", producer_stage="run_input_capture"
            )
    _register_operator_input_dependencies(manifest, operator_inputs)
    manifest.save()
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-id", help="session ID or 'all'")
    parser.add_argument("--summary", type=Path, help="print a completed run manifest summary")
    parser.add_argument("--run-manifest", type=Path, help="manifest path for a new or resumed run")
    parser.add_argument("--alignment-tolerance-seconds", type=float)
    parser.add_argument(
        "--tracking-sample-fps", type=float, default=None,
        help="decimate person tracking to this rate; omit for native cadence",
    )
    parser.add_argument("--asr-model-path", type=Path)
    parser.add_argument("--alignment-model-name")
    parser.add_argument("--alignment-model-path", type=Path)
    parser.add_argument("--alignment-cache-path", type=Path)
    parser.add_argument("--diarization-model-name")
    parser.add_argument("--diarization-cache-path", type=Path)
    parser.add_argument("--head-pose-repository-path", type=Path)
    parser.add_argument("--monitor-config", type=Path)
    parser.add_argument("--monitor-sample-rate", type=float)
    parser.add_argument("--focal-runtime-config", type=Path)
    parser.add_argument("--from-stage")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--gpu-only", action="store_true")
    parser.add_argument("--local", action="store_true")
    parser.add_argument(
        "--per-camera-workers",
        type=int,
        default=3,
        help="maximum independent per-camera commands to run concurrently (default: 3)",
    )
    parser.add_argument("--skip-stages", default="")
    args = parser.parse_args()
    if args.per_camera_workers < 1:
        parser.error("--per-camera-workers must be at least 1")
    if args.summary:
        document = json.loads(args.summary.read_text(encoding="utf-8"))
        print(format_run_summary(document))
        return
    if not args.session_id:
        parser.error("--session-id is required unless --summary is used")
    if args.dry_run:
        session_ids = _find_all_sessions() if args.session_id == "all" else [args.session_id]
        for sid in session_ids:
            print(f"Pipeline: {sid} [dry run; no manifest written]")
            for stage_name, _gpu, template in STAGES:
                if isinstance(template, str) and template in {"PER_CAMERA", "ASD_ASSEMBLY"}:
                    print(f"  {stage_name}: per-camera command requires captured FPS")
                else:
                    print(f"  {stage_name}: {shlex.join(_resolve_command(template, sid))}")
        return
    try:
        manifest = _create_or_load_manifest(args)
        session_ids = _find_all_sessions() if args.session_id == "all" else [args.session_id]
        if not session_ids:
            raise RunManifestError("no sessions found")
        skip_stages = {value.strip() for value in args.skip_stages.split(",") if value.strip()}
        passed = True
        for sid in session_ids:
            if not run_pipeline(
                sid,
                manifest,
                from_stage=args.from_stage,
                force=args.force,
                gpu_only=args.gpu_only,
                local=args.local,
                skip_stages=skip_stages,
                per_camera_workers=args.per_camera_workers,
            ):
                passed = False
                break
        if passed and args.session_id == "all":
            passed = run_cohort_metrics(session_ids, manifest, local=args.local)
        quantity_lineage = _quantity_lineage(session_ids)
        if args.session_id == "all":
            quantity_lineage["paper_metrics[cohort]"] = [
                manifest.path.parent / "paper_metrics.json"
            ]
            quantity_lineage.update(
                _cohort_quantity_lineage(manifest.path.parent / "paper_metrics.json")
            )
        manifest.set_reported_quantities(quantity_lineage)
        manifest.finish_run(passed=passed)
        print(f"Run manifest: {manifest.path}")
        print(format_run_summary(manifest.document))
        if not passed:
            raise SystemExit(1)
    except RunManifestError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
