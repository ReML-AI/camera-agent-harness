#!/usr/bin/env python3
"""
Associate Moments with Persons
Links critical moments to specific persons using spatial and temporal overlap
"""

import json
import argparse
import numpy as np
from typing import List, Dict, Optional


class PersonMomentAssociator:
    """Associate moments with persons using spatiotemporal analysis"""

    def __init__(self, camera_id='cam1'):
        self.camera_id = camera_id

    def load_person_tracks(self, tracks_file: str) -> Dict:
        """Load person tracking data for specific camera"""
        with open(tracks_file, 'r') as f:
            return json.load(f)

    def load_person_roles(self, roles_file: str) -> Dict:
        """Load person role predictions if available"""
        try:
            with open(roles_file, 'r') as f:
                data = json.load(f)
                return data.get('predictions', {})
        except FileNotFoundError:
            return {}

    def get_persons_at_time(
        self,
        timestamp: float,
        tracks_data: Dict,
        time_tolerance: float = 2.0
    ) -> List[Dict]:
        """
        Get all persons present at given timestamp

        Args:
            timestamp: Time in seconds
            tracks_data: Person tracking data
            time_tolerance: Tolerance window in seconds

        Returns:
            List of persons present at timestamp with their bounding boxes
        """
        persons_present = []

        for person in tracks_data.get('persons', []):
            person_id = person['person_id']
            track_id = person['track_id']

            # Check each appearance
            for appearance in person.get('appearances', []):
                start_time = appearance['start_time']
                end_time = appearance['end_time']

                # Check if timestamp falls within appearance window (with tolerance)
                if start_time - time_tolerance <= timestamp <= end_time + time_tolerance:
                    # Find closest bounding box to timestamp
                    bbox_data = self._get_closest_bbox(
                        appearance['bounding_boxes'],
                        timestamp
                    )

                    if bbox_data:
                        persons_present.append({
                            'person_id': person_id,
                            'track_id': track_id,
                            'bbox': bbox_data['bbox'],
                            'confidence': bbox_data['confidence'],
                            'frame_time': bbox_data['timestamp'],
                            'time_diff': abs(bbox_data['timestamp'] - timestamp)
                        })
                    break  # Found matching appearance

        return persons_present

    def _get_closest_bbox(
        self,
        bboxes: List[Dict],
        timestamp: float
    ) -> Optional[Dict]:
        """Get bounding box closest to timestamp"""
        if not bboxes:
            return None

        closest = min(bboxes, key=lambda b: abs(b['timestamp'] - timestamp))
        return closest

    def calculate_activity_score(
        self,
        person_bbox: Dict,
        moment: Dict,
        person_role: Optional[str] = None
    ) -> float:
        """
        Calculate likelihood that person is performing the action

        Factors:
        - Role relevance (students more likely to perform actions)
        - Spatial location (center of frame vs edges)
        - Bounding box size (larger = closer/more prominent)
        - Confidence score

        Args:
            person_bbox: Person bounding box data
            moment: Moment data
            person_role: Person's role if known

        Returns:
            Activity score (0-1)
        """
        score = 0.5  # Base score

        # Role-based scoring
        if person_role:
            if person_role in ['Student Nurse (Primary)', 'Supervising Nurse/Doctor']:
                score += 0.3
            elif person_role == 'Patient/Mannequin':
                # Patients don't perform actions (usually)
                if moment['action_type'] not in ['patient_positioning', 'communication']:
                    score -= 0.4
            elif person_role in ['Observer/Other', 'Background/False Detection']:
                score -= 0.2

        # Spatial scoring (center of frame more likely to be active)
        bbox = person_bbox['bbox']  # [x1, y1, x2, y2] normalized
        center_x = (bbox[0] + bbox[2]) / 2
        center_y = (bbox[1] + bbox[3]) / 2

        # Distance from frame center
        dist_from_center = np.sqrt((center_x - 0.5)**2 + (center_y - 0.5)**2)
        spatial_score = max(0, 1 - dist_from_center)  # 0 at corners, 1 at center
        score += spatial_score * 0.15

        # Bounding box size (larger = more prominent)
        bbox_width = bbox[2] - bbox[0]
        bbox_height = bbox[3] - bbox[1]
        bbox_area = bbox_width * bbox_height
        size_score = min(1.0, bbox_area / 0.25)  # Normalize to 0-1
        score += size_score * 0.1

        # Confidence from detection
        score += person_bbox['confidence'] * 0.05

        # Time proximity
        time_diff = person_bbox['time_diff']
        time_score = max(0, 1 - (time_diff / 5.0))  # Decay over 5 seconds
        score += time_score * 0.1

        return max(0, min(1, score))  # Clamp to [0, 1]

    def associate_moment(
        self,
        moment: Dict,
        tracks_data: Dict,
        person_roles: Dict
    ) -> Dict:
        """
        Associate a moment with the most likely person

        Args:
            moment: Moment data
            tracks_data: Person tracking data
            person_roles: Person role predictions

        Returns:
            Moment with person association
        """
        timestamp = moment['timestamp']

        # Get all persons present at this time
        persons_present = self.get_persons_at_time(timestamp, tracks_data)

        if not persons_present:
            # No persons detected at this time
            moment['person_association'] = {
                'primary_actor': None,
                'confidence': 0.0,
                'all_present': [],
                'note': 'No persons detected at this timestamp'
            }
            return moment

        # Calculate activity score for each person
        person_scores = []
        for person_data in persons_present:
            person_id = str(person_data['person_id'])

            # Get role if available
            role = None
            if person_id in person_roles:
                role = person_roles[person_id].get('role')

            # Calculate activity score
            activity_score = self.calculate_activity_score(
                person_data,
                moment,
                role
            )

            person_scores.append({
                'person_id': person_data['person_id'],
                'track_id': person_data['track_id'],
                'role': role,
                'activity_score': activity_score,
                'bbox': person_data['bbox'],
                'detection_confidence': person_data['confidence']
            })

        # Sort by activity score
        person_scores.sort(key=lambda x: x['activity_score'], reverse=True)

        # Primary actor is highest scoring person
        primary_actor = person_scores[0]

        # Associate moment with person
        moment['person_association'] = {
            'primary_actor': {
                'person_id': primary_actor['person_id'],
                'track_id': primary_actor['track_id'],
                'role': primary_actor['role'],
                'confidence': primary_actor['activity_score'],
                'bbox': primary_actor['bbox']
            },
            'all_present': [
                {
                    'person_id': p['person_id'],
                    'role': p['role'],
                    'activity_score': p['activity_score']
                }
                for p in person_scores
            ],
            'num_persons_present': len(persons_present)
        }

        return moment

    def generate_person_timeline(
        self,
        moments: List[Dict],
        person_roles: Dict
    ) -> Dict:
        """
        Generate timeline of actions for each person

        Args:
            moments: List of moments with person associations
            person_roles: Person role predictions

        Returns:
            Timeline grouped by person
        """
        person_timelines = {}

        for moment in moments:
            association = moment.get('person_association', {})
            primary_actor = association.get('primary_actor')

            if not primary_actor:
                continue

            person_id = str(primary_actor['person_id'])

            if person_id not in person_timelines:
                role = person_roles.get(person_id, {}).get('role', 'Unknown')
                person_timelines[person_id] = {
                    'person_id': person_id,
                    'role': role,
                    'actions': [],
                    'categories': {},
                    'critical_actions': 0,
                    'total_actions': 0
                }

            # Add action to timeline
            action_summary = {
                'sequence_id': moment['sequence_id'],
                'timestamp': moment['timestamp'],
                'action_type': moment['action_type'],
                'category': moment['category'],
                'importance': moment['importance'],
                'confidence': primary_actor['confidence'],
                'text': moment['text']
            }

            person_timelines[person_id]['actions'].append(action_summary)
            person_timelines[person_id]['total_actions'] += 1

            # Count by category
            category = moment['category']
            if category not in person_timelines[person_id]['categories']:
                person_timelines[person_id]['categories'][category] = 0
            person_timelines[person_id]['categories'][category] += 1

            # Count critical actions
            if moment['importance'] in ['critical', 'high']:
                person_timelines[person_id]['critical_actions'] += 1

        # Sort actions by timestamp for each person
        for person_id in person_timelines:
            person_timelines[person_id]['actions'].sort(key=lambda x: x['timestamp'])

        return person_timelines


def main():
    parser = argparse.ArgumentParser(description="Associate moments with persons")
    parser.add_argument('--moments', type=str, required=True, help="Path to moments JSON")
    parser.add_argument('--tracks', type=str, required=True, help="Path to person tracks JSON")
    parser.add_argument('--roles', type=str, help="Path to person roles JSON (optional)")
    parser.add_argument('--camera', type=str, default='cam1', help="Camera ID")
    parser.add_argument('--output', type=str, required=True, help="Output path")

    args = parser.parse_args()

    print("="*80)
    print("MOMENT-PERSON ASSOCIATION")
    print("="*80)

    # Load data
    print(f"\nLoading moments from: {args.moments}")
    with open(args.moments, 'r') as f:
        moments_data = json.load(f)
    moments = moments_data['moments']
    print(f"  Loaded {len(moments)} moments")

    print(f"\nLoading person tracks from: {args.tracks}")
    with open(args.tracks, 'r') as f:
        tracks_data = json.load(f)
    print(f"  Loaded {len(tracks_data['persons'])} persons")

    # Load roles if available
    person_roles = {}
    if args.roles:
        print(f"\nLoading person roles from: {args.roles}")
        with open(args.roles, 'r') as f:
            roles_data = json.load(f)
            person_roles = roles_data.get('predictions', {})
        print(f"  Loaded roles for {len(person_roles)} persons")

    # Associate moments with persons
    associator = PersonMomentAssociator(camera_id=args.camera)

    print("\nAssociating moments with persons...")
    associated_moments = []
    for moment in moments:
        associated_moment = associator.associate_moment(moment, tracks_data, person_roles)
        associated_moments.append(associated_moment)

    # Count associations
    with_association = sum(1 for m in associated_moments
                          if m.get('person_association', {}).get('primary_actor'))
    print(f"  Associated {with_association}/{len(moments)} moments with persons")

    # Generate person timelines
    print("\nGenerating person timelines...")
    person_timelines = associator.generate_person_timeline(associated_moments, person_roles)
    print(f"  Created timelines for {len(person_timelines)} persons")

    # Print summary
    print(f"\n{'='*80}")
    print("PERSON ACTIVITY SUMMARY")
    print(f"{'='*80}")
    for person_id, timeline in sorted(person_timelines.items(),
                                      key=lambda x: x[1]['total_actions'],
                                      reverse=True):
        role = timeline['role']
        total = timeline['total_actions']
        critical = timeline['critical_actions']
        print(f"\nPerson {person_id} ({role}):")
        print(f"  Total actions: {total}")
        print(f"  Critical actions: {critical}")
        print("  Top categories:")
        for cat, count in sorted(timeline['categories'].items(),
                                key=lambda x: x[1], reverse=True)[:3]:
            print(f"    - {cat}: {count}")

    # Save output
    output_data = {
        'camera_id': args.camera,
        'source_moments': args.moments,
        'source_tracks': args.tracks,
        'moments_with_associations': associated_moments,
        'person_timelines': person_timelines,
        'summary': {
            'total_moments': len(associated_moments),
            'associated_moments': with_association,
            'unassociated_moments': len(associated_moments) - with_association,
            'num_persons_active': len(person_timelines)
        }
    }

    with open(args.output, 'w') as f:
        json.dump(output_data, f, indent=2)

    print(f"\n{'='*80}")
    print(f"✓ Output saved: {args.output}")
    print(f"{'='*80}")


if __name__ == "__main__":
    main()
