#!/usr/bin/env python3
"""Inspect Light-ASD output files to understand the data structure"""

import pickle
from pathlib import Path

# Load the output files
pywork_dir = Path("third_party/Light-ASD/demo/cam1_test/pywork")

print("=" * 80)
print("LIGHT-ASD OUTPUT INSPECTION")
print("=" * 80)

# 1. Scores
print("\n1. SCORES (Active Speaker Detection)")
print("-" * 80)
with open(pywork_dir / "scores.pckl", "rb") as f:
    scores = pickle.load(f)
print(f"Type: {type(scores)}")
print(f"Keys: {scores.keys() if isinstance(scores, dict) else 'N/A'}")
if isinstance(scores, dict):
    for key, value in list(scores.items())[:3]:  # First 3 items
        print(f"\nKey: {key}")
        print(f"  Type: {type(value)}")
        if hasattr(value, 'shape'):
            print(f"  Shape: {value.shape}")
        elif isinstance(value, list):
            print(f"  Length: {len(value)}")
            if len(value) > 0:
                print(f"  Sample: {value[:5]}")

# 2. Tracks
print("\n\n2. TRACKS (Face Tracking)")
print("-" * 80)
with open(pywork_dir / "tracks.pckl", "rb") as f:
    tracks = pickle.load(f)
print(f"Type: {type(tracks)}")
print(f"Num tracks: {len(tracks)}")
if len(tracks) > 0:
    print("\nSample track (first):")
    sample_track = tracks[0]
    print(f"  Keys: {sample_track.keys() if isinstance(sample_track, dict) else 'N/A'}")
    if isinstance(sample_track, dict):
        for k, v in sample_track.items():
            if hasattr(v, 'shape'):
                print(f"  {k}: shape={v.shape}")
            elif isinstance(v, list):
                print(f"  {k}: len={len(v)}, sample={v[:3]}")
            else:
                print(f"  {k}: {v}")

# 3. Faces
print("\n\n3. FACES (Face Detections)")
print("-" * 80)
with open(pywork_dir / "faces.pckl", "rb") as f:
    faces = pickle.load(f)
print(f"Type: {type(faces)}")
if isinstance(faces, list):
    print(f"Num frames: {len(faces)}")
    print(f"Sample (first frame): {faces[0][:2] if len(faces[0]) > 0 else 'empty'}")
elif isinstance(faces, dict):
    print(f"Keys: {list(faces.keys())[:10]}")

# 4. Scene
print("\n\n4. SCENE (Shot Boundaries)")
print("-" * 80)
with open(pywork_dir / "scene.pckl", "rb") as f:
    scene = pickle.load(f)
print(f"Type: {type(scene)}")
print(f"Content: {scene}")

# Summary
print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print(f"Detected {len(tracks)} face tracks in the 10-second clip")
print("Output video: Light-ASD/demo/cam1_test/pyavi/video_out.avi")
print("  - Green boxes = active speakers")
print("  - Red boxes = non-active speakers")
