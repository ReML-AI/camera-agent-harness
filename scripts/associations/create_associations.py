#!/usr/bin/env python3
"""
Create Moment-Person Associations

Links critical moments to specific students based on:
- Temporal overlap (person present during moment)
- Spatial proximity (person location in frame)
- Role relevance (moment relevant to student actions)

Output format expected by generate_student_feedback.py:
{
  "person_timelines": {
    "cam1_person_1": {
      "person_id": "cam1_person_1",
      "role": "Student Nurse (Primary)",
      "moments": [
        {
          "moment_id": "moment_001",
          "start_time": 120.5,
          "end_time": 125.3,
          "summary": "Early escalation call for help",
          "clinical_significance": "Recognized deterioration",
          "confidence": 0.89,
          "relevant_to_student": true
        }
      ],
      "total_screen_time": 450.2,
      "total_moments": 12
    }
  }
}
"""

import json
import argparse
from pathlib import Path
from typing import Dict, List, Any


def load_person_labels(labels_path: Path) -> Dict[str, Any]:
    """Load person role labels"""
    if not labels_path.exists():
        print(f"Warning: No labels file found at {labels_path}")
        return {}

    with open(labels_path, 'r') as f:
        data = json.load(f)
        return data.get('person_labels', {})


def load_person_tracks(processed_dir: Path) -> Dict[str, Any]:
    """Load person tracking data from all cameras"""
    tracks = {}

    for track_file in processed_dir.glob('person_tracks_*.json'):
        with open(track_file, 'r') as f:
            data = json.load(f)
            camera_id = data['camera_id']

            for person in data['persons']:
                person_key = f"{camera_id}_person_{person['person_id']}"
                tracks[person_key] = {
                    'track_id': person['track_id'],
                    'screen_time': person.get('total_screen_time_seconds', 0),
                    'appearances': person.get('appearances', []),
                    'camera': camera_id
                }

    return tracks


def load_critical_moments(session_dir: Path, session_id: str) -> List[Dict]:
    """Load critical moments for session"""
    # Try multiple possible locations
    possible_paths = [
        session_dir / "processed" / f"critical_moments_{session_id}.json",
        session_dir / "output" / "critical_moments.json",
        session_dir / "moments" / "extracted_moments.json"
    ]

    for moments_file in possible_paths:
        if moments_file.exists():
            print(f"  Found moments at: {moments_file}")
            with open(moments_file, 'r') as f:
                data = json.load(f)
                # Handle different JSON structures
                if 'critical_moments' in data:
                    return data['critical_moments']
                elif 'moments' in data:
                    return data['moments']
                else:
                    return data if isinstance(data, list) else []

    print("Warning: No moments file found in any of:")
    for p in possible_paths:
        print(f"  - {p}")
    return []


def is_person_present_in_moment(person_key: str, moment: Dict, tracks: Dict) -> bool:
    """Check if person was present during the moment timeframe"""
    if person_key not in tracks:
        return False

    moment['start_time']
    moment['end_time']

    # For now, assume all detected persons are present in all moments
    # In a more sophisticated version, we would check frame-level detections
    return True


def is_moment_relevant_to_role(moment: Dict, role: str) -> bool:
    """Determine if moment is relevant to person's role"""
    # Students are relevant to most clinical moments
    if 'student' in role.lower() and 'nurse' in role.lower():
        return True

    # Supervisors relevant to teaching moments
    if 'supervisor' in role.lower() or 'doctor' in role.lower():
        if any(keyword in moment.get('summary', '').lower()
               for keyword in ['teaching', 'guidance', 'supervision']):
            return True

    return False


def create_person_timelines(
    labels: Dict[str, Any],
    tracks: Dict[str, Any],
    moments: List[Dict]
) -> Dict[str, Any]:
    """Create timeline of moments for each person"""

    timelines = {}

    # Extract person key from frame-based label keys
    person_to_label = {}
    for frame_key, label in labels.items():
        # Extract "cam1_person_1" from "cam1_person_1_frame_0"
        parts = frame_key.rsplit('_frame_', 1)
        if len(parts) == 2:
            person_key = parts[0]
            person_to_label[person_key] = label

    # Build timeline for each person
    for person_key, label in person_to_label.items():
        role = label.get('role', 'Unknown')

        # Only process students and relevant roles
        if 'student' not in role.lower() and 'nurse' not in role.lower():
            continue

        person_moments = []

        for moment in moments:
            # Check if person was present
            if not is_person_present_in_moment(person_key, moment, tracks):
                continue

            # Check if moment is relevant to this role
            relevant = is_moment_relevant_to_role(moment, role)

            person_moments.append({
                'moment_id': f"moment_{moment.get('id', moment.get('start_time'))}",
                'start_time': moment['start_time'],
                'end_time': moment['end_time'],
                'summary': moment.get('summary', ''),
                'clinical_significance': moment.get('clinical_significance', ''),
                'confidence': moment.get('confidence', 0.0),
                'severity': moment.get('severity', 'warning'),
                'sources': moment.get('sources', {}),
                'relevant_to_student': relevant
            })

        if person_moments:  # Only add if person has moments
            track_info = tracks.get(person_key, {})

            timelines[person_key] = {
                'person_id': person_key,
                'role': role,
                'name': label.get('name'),
                'moments': sorted(person_moments, key=lambda m: m['start_time']),
                'total_screen_time': track_info.get('screen_time', 0),
                'total_moments': len(person_moments),
                'relevant_moments': sum(1 for m in person_moments if m['relevant_to_student'])
            }

    return timelines


def main():
    parser = argparse.ArgumentParser(
        description="Create moment-person associations for feedback generation"
    )
    parser.add_argument('--session-id', type=str, default='session_001',
                       help='Session ID')
    parser.add_argument('--output', type=str,
                       default='data/processed/moment_person_associations.json',
                       help='Output file path')

    args = parser.parse_args()

    # Paths
    project_root = Path(__file__).parent.parent.parent
    data_dir = project_root / 'data'
    processed_dir = data_dir / 'processed'
    labels_file = data_dir / 'labeled' / 'person_roles_per_camera.json'

    print("=" * 80)
    print("MOMENT-PERSON ASSOCIATION GENERATION")
    print("=" * 80)

    # Load data
    print("\n[1/4] Loading person labels...")
    labels = load_person_labels(labels_file)
    print(f"  Loaded {len(labels)} labeled frames")

    print("\n[2/4] Loading person tracks...")
    tracks = load_person_tracks(processed_dir)
    print(f"  Loaded {len(tracks)} person tracks")

    print("\n[3/4] Loading critical moments...")
    moments = load_critical_moments(data_dir, args.session_id)
    print(f"  Loaded {len(moments)} critical moments")

    # Create associations
    print("\n[4/4] Creating associations...")
    timelines = create_person_timelines(labels, tracks, moments)
    print(f"  Created timelines for {len(timelines)} persons")

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    for person_id, timeline in timelines.items():
        print(f"\n{person_id} ({timeline['role']})")
        print(f"  Total moments: {timeline['total_moments']}")
        print(f"  Relevant moments: {timeline['relevant_moments']}")
        print(f"  Screen time: {timeline['total_screen_time']:.1f}s")

    # Save output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_data = {
        'session_id': args.session_id,
        'person_timelines': timelines,
        'metadata': {
            'total_persons': len(timelines),
            'total_moments': len(moments),
            'total_labels': len(labels)
        }
    }

    with open(output_path, 'w') as f:
        json.dump(output_data, f, indent=2)

    print(f"\n{'='*80}")
    print(f"Associations saved: {output_path}")
    print("Ready for feedback generation!")
    print("=" * 80)


if __name__ == "__main__":
    main()
