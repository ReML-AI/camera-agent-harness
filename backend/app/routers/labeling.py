"""Labeling endpoints for person role annotation"""
from fastapi import APIRouter, HTTPException
from pathlib import Path
import json
from typing import Dict, List

router = APIRouter()

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
PROCESSED_DIR = DATA_DIR / "processed"
LABELED_DIR = DATA_DIR / "labeled"
LABELS_FILE = LABELED_DIR / "person_roles_per_camera.json"


def load_per_camera_tracks() -> List[Dict]:
    """Load all per-camera tracking results - only frames that exist after deduplication"""
    track_files = sorted(PROCESSED_DIR.glob('person_tracks_*.json'))
    thumbnails_dir = PROCESSED_DIR / "thumbnails"

    all_persons = []

    for track_file in track_files:
        with open(track_file, 'r') as f:
            data = json.load(f)

        camera_id = data['camera_id']

        for person in data['persons']:
            # Get all thumbnail paths (new format) or fall back to single thumbnail
            all_thumbnails = person.get('all_thumbnail_paths', [])
            if not all_thumbnails and person.get('thumbnail_path'):
                all_thumbnails = [person.get('thumbnail_path')]

            # Create a separate entry for each thumbnail frame
            # BUT only if the thumbnail file actually exists (after deduplication)
            for frame_idx, thumbnail_path in enumerate(all_thumbnails):
                # Check if thumbnail exists
                thumbnail_file = Path(thumbnail_path)
                if not thumbnail_file.exists():
                    # Try relative to thumbnails_dir
                    thumbnail_file = thumbnails_dir / thumbnail_file.name
                    if not thumbnail_file.exists():
                        continue  # Skip frames that were removed by deduplication

                person_entry = {
                    'unique_id': f"{camera_id}_person_{person['person_id']}_frame_{frame_idx}",
                    'camera_id': camera_id,
                    'person_id': person['person_id'],
                    'frame_idx': frame_idx,
                    'track_id': person['track_id'],
                    'thumbnail_path': thumbnail_path,
                    'screen_time': person['total_screen_time_seconds'],
                    'num_appearances': person.get('num_appearances', 0),
                    'avg_confidence': person.get('average_confidence', 0.0)
                }
                all_persons.append(person_entry)

    # Sort by camera, person, then frame
    all_persons.sort(key=lambda x: (x['camera_id'], x['person_id'], x['frame_idx']))

    return all_persons


@router.get("/persons")
def get_persons():
    """Get all detected persons for labeling"""
    try:
        persons = load_per_camera_tracks()
        return {
            "persons": persons,
            "total": len(persons)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/labels")
def get_labels():
    """Get existing labels"""
    if LABELS_FILE.exists():
        with open(LABELS_FILE, 'r') as f:
            return json.load(f)
    return {"person_labels": {}}


@router.post("/labels")
def save_labels(data: Dict):
    """Save person role labels"""
    try:
        # Ensure directory exists
        LABELED_DIR.mkdir(parents=True, exist_ok=True)

        # Save labels
        with open(LABELS_FILE, 'w') as f:
            json.dump(data, f, indent=2)

        return {"status": "success", "message": "Labels saved successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
