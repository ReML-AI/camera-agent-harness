#!/usr/bin/env python3
"""Stage 4: Light-ASD wrapper per camera.

Usage (GPU required):
    srun --gres=gpu:1 python3 scripts/run_light_asd.py --session-id session_001 --camera cam1
"""
import subprocess
import argparse
import sys
from pathlib import Path

from scripts.core.records import sha256_file

try:
    from scripts.utils.session_paths import raw_dir, videos_dir
except ImportError:
    from pathlib import Path as _P
    _ROOT = _P(__file__).resolve().parent.parent
    def raw_dir(sid): return _ROOT / "data" / "sessions" / sid / "raw"
    def videos_dir(sid): return _ROOT / "data" / "sessions" / sid / "videos"

def main():
    parser = argparse.ArgumentParser(description="Run Light-ASD for a camera")
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--camera", required=True, choices=["cam1", "cam2", "cam3"])
    parser.add_argument("--repository-path", required=True,
                        help="Existing pinned Light-ASD checkout")
    parser.add_argument("--weights-path", required=True,
                        help="Existing local Light-ASD weights")
    parser.add_argument("--weights-sha256", required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    video_path = videos_dir(args.session_id) / f"{args.camera}.mp4"
    if not video_path.exists():
        print(f"ERROR: Video not found: {video_path}")
        sys.exit(1)

    asd_dir = raw_dir(args.session_id) / f"asd_{args.camera}"
    asd_dir.mkdir(parents=True, exist_ok=True)

    scores_path = asd_dir / "pywork" / "scores.pckl"
    if scores_path.exists() and not args.force:
        print(f"ASD already completed for {args.camera}. Use --force to rerun.")
        return

    light_asd_dir = Path(args.repository_path).resolve()
    weights_path = Path(args.weights_path).resolve()
    if not (light_asd_dir / "Columbia_test.py").is_file():
        print(f"ERROR: Light-ASD checkout not found at {light_asd_dir}")
        sys.exit(1)
    if not weights_path.is_file():
        print(f"ERROR: Light-ASD weights not found at {weights_path}")
        sys.exit(1)
    if sha256_file(weights_path) != args.weights_sha256:
        print("ERROR: Light-ASD weights checksum mismatch")
        sys.exit(1)

    # Columbia_test.py expects --videoFolder (parent dir) and --videoName (stem).
    # It looks for videoFolder/videoName.mp4 and saves to videoFolder/videoName/.
    # Symlink the video into asd_dir so the paths work.
    symlink_path = asd_dir / f"{args.camera}.mp4"
    if not symlink_path.exists():
        import os
        os.symlink(str(video_path.resolve()), str(symlink_path))

    print(f"Running Light-ASD for {args.session_id}/{args.camera}...")
    cmd = [sys.executable, str(light_asd_dir / "Columbia_test.py"),
           "--videoFolder", str(asd_dir), "--videoName", args.camera,
           "--pretrainModel", str(weights_path)]
    # Isolate Light-ASD's `import model.*` from the repo root. When the pipeline
    # exports PYTHONPATH=<repo> (so stages can import scripts.*), a top-level
    # model/ dir shadows third_party/Light-ASD/model and breaks the S3FD import.
    import os
    env = os.environ.copy()
    env["PYTHONPATH"] = str(light_asd_dir)
    result = subprocess.run(cmd, cwd=str(light_asd_dir), env=env)
    if result.returncode != 0:
        print(f"Light-ASD failed for {args.camera}")
        sys.exit(1)

    # Columbia_test.py saves to asd_dir/camera/pywork/. Move pywork up to asd_dir/pywork/.
    inner_pywork = asd_dir / args.camera / "pywork"
    target_pywork = asd_dir / "pywork"
    if inner_pywork.exists() and not target_pywork.exists():
        import shutil as _shutil
        _shutil.move(str(inner_pywork), str(target_pywork))

    # Clean up large temp dirs (pyframes, pyavi, pycrop). Keep all of pywork:
    # faces.pckl is the raw S3FD ceiling used by Table 3, tracks.pckl feeds head pose,
    # and scores.pckl feeds canonical ASD assembly.
    import shutil
    # Check both asd_dir/ and asd_dir/camera/ (Columbia_test.py nests under videoName)
    for base in [asd_dir, asd_dir / args.camera]:
        for temp_dir in ["pyframes", "pyavi", "pycrop"]:
            p = base / temp_dir
            if p.exists():
                size_mb = sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) / (1024 * 1024)
                shutil.rmtree(p)
                print(f"  Cleaned {base.name}/{temp_dir}/ ({size_mb:.0f} MB freed)")
    # Remove symlink
    symlink_path = asd_dir / f"{args.camera}.mp4"
    if symlink_path.is_symlink():
        symlink_path.unlink()

    print(f"Light-ASD complete for {args.camera}")


if __name__ == "__main__":
    main()
