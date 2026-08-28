#!/usr/bin/env python3
"""
Extract Critical Moments from Transcription
Identifies key clinical actions and decision points from audio transcription
"""

import json
import argparse
from typing import List, Dict


class MomentExtractor:
    """Extract critical clinical moments from transcription"""

    def __init__(self):
        # Define clinical action patterns
        self.patterns = {
            'hand_hygiene': {
                'keywords': ['hand hygiene', 'wash hands', 'sanitize', 'clean hands'],
                'category': 'Infection Control',
                'importance': 'high'
            },
            'vital_signs': {
                'keywords': ['blood pressure', 'oxygen', 'pulse', 'temperature', 'heart rate',
                           'respiratory rate', 'saturation', 'BP', 'O2', 'sats'],
                'category': 'Patient Assessment',
                'importance': 'high'
            },
            'auscultation': {
                'keywords': ['listen', 'chest', 'lungs', 'breath sounds', 'wheezy', 'wheeze',
                           'auscultate', 'stethoscope'],
                'category': 'Physical Examination',
                'importance': 'medium'
            },
            'medication_admin': {
                'keywords': ['antibiotic', 'medication', 'dose', 'prescribe', 'administer',
                           'injection', 'IV', 'nebulizer', 'patch', 'adrenaline', 'epinephrine'],
                'category': 'Medication Management',
                'importance': 'high'
            },
            'patient_history': {
                'keywords': ['medical history', 'condition', 'smoking', 'allergies', 'asthma',
                           'COPD', 'how long', 'symptoms'],
                'category': 'Patient History Taking',
                'importance': 'medium'
            },
            'communication': {
                'keywords': ['hello', 'hi', 'my name is', 'how are you', 'introduce',
                           'explain', 'consent'],
                'category': 'Communication Skills',
                'importance': 'low'
            },
            'emergency_recognition': {
                'keywords': ['reaction', 'anaphylactic', 'anaphylaxis', 'allergic', 'emergency',
                           'cardiac arrest', 'code', 'MET', 'crash'],
                'category': 'Emergency Recognition',
                'importance': 'critical'
            },
            'emergency_response': {
                'keywords': ['call', 'help', 'emergency', 'CPR', 'compressions', 'rescue',
                           'resuscitation', 'crash team', 'code blue'],
                'category': 'Emergency Management',
                'importance': 'critical'
            },
            'patient_positioning': {
                'keywords': ['lie down', 'sit up', 'position', 'bed', 'elevate', 'raise'],
                'category': 'Patient Safety',
                'importance': 'low'
            },
            'oxygen_therapy': {
                'keywords': ['oxygen', 'O2', 'mask', 'non-rebreather', 'nasal cannula',
                           'ventilation', 'breathing'],
                'category': 'Respiratory Support',
                'importance': 'high'
            },
            'iv_access': {
                'keywords': ['IV', 'cannula', 'line', 'access', 'vein', 'flush'],
                'category': 'Vascular Access',
                'importance': 'medium'
            },
            'fluid_admin': {
                'keywords': ['fluids', 'saline', 'IV fluid', 'bolus', 'fluid resuscitation'],
                'category': 'Fluid Management',
                'importance': 'high'
            }
        }

    def extract_moments(self, transcript: Dict) -> List[Dict]:
        """
        Extract critical moments from transcript

        Args:
            transcript: Transcript data with segments

        Returns:
            List of critical moments with timestamps
        """
        segments = transcript.get('segments', [])
        transcript.get('text', '').lower()

        moments = []

        # Process each segment
        for segment in segments:
            text = segment.get('text', '').lower().strip()
            start_time = segment.get('start', 0)
            end_time = segment.get('end', 0)

            if len(text) < 5:  # Skip very short segments
                continue

            # Check for pattern matches
            for action_type, pattern_info in self.patterns.items():
                for keyword in pattern_info['keywords']:
                    if keyword.lower() in text:
                        moment = {
                            'timestamp': start_time,
                            'end_timestamp': end_time,
                            'duration': end_time - start_time,
                            'action_type': action_type,
                            'category': pattern_info['category'],
                            'importance': pattern_info['importance'],
                            'text': segment.get('text', '').strip(),
                            'keyword_matched': keyword,
                            'confidence': self._calculate_confidence(text, pattern_info['keywords'])
                        }
                        moments.append(moment)
                        break  # Only match once per segment

        # Deduplicate and merge nearby moments
        moments = self._deduplicate_moments(moments)

        # Sort by timestamp
        moments.sort(key=lambda x: x['timestamp'])

        # Add sequence numbers
        for i, moment in enumerate(moments, 1):
            moment['sequence_id'] = i

        return moments

    def _calculate_confidence(self, text: str, keywords: List[str]) -> float:
        """Calculate confidence score based on keyword matches"""
        matches = sum(1 for kw in keywords if kw.lower() in text)
        return min(1.0, 0.5 + (matches * 0.2))

    def _deduplicate_moments(self, moments: List[Dict], time_window: float = 10.0) -> List[Dict]:
        """
        Deduplicate moments that occur within time window

        Args:
            moments: List of moments
            time_window: Time window in seconds to consider as same moment

        Returns:
            Deduplicated list of moments
        """
        if not moments:
            return []

        # Sort by timestamp
        moments.sort(key=lambda x: x['timestamp'])

        deduplicated = []
        current_group = [moments[0]]

        for moment in moments[1:]:
            # Check if within time window and same action type
            if (moment['timestamp'] - current_group[-1]['timestamp'] <= time_window and
                moment['action_type'] == current_group[0]['action_type']):
                current_group.append(moment)
            else:
                # Merge current group
                merged = self._merge_moment_group(current_group)
                deduplicated.append(merged)
                current_group = [moment]

        # Don't forget last group
        if current_group:
            merged = self._merge_moment_group(current_group)
            deduplicated.append(merged)

        return deduplicated

    def _merge_moment_group(self, group: List[Dict]) -> Dict:
        """Merge a group of similar moments"""
        if len(group) == 1:
            return group[0]

        # Take earliest timestamp and latest end_timestamp
        merged = group[0].copy()
        merged['timestamp'] = min(m['timestamp'] for m in group)
        merged['end_timestamp'] = max(m['end_timestamp'] for m in group)
        merged['duration'] = merged['end_timestamp'] - merged['timestamp']

        # Combine text
        merged['text'] = ' '.join(set(m['text'] for m in group))

        # Average confidence
        merged['confidence'] = sum(m['confidence'] for m in group) / len(group)

        # Track merged count
        merged['merged_segments'] = len(group)

        return merged

    def identify_critical_sequence(self, moments: List[Dict]) -> List[Dict]:
        """
        Identify critical clinical sequences (e.g., anaphylaxis recognition and response)

        Args:
            moments: List of extracted moments

        Returns:
            List of critical sequences
        """
        sequences = []

        # Look for anaphylaxis sequence
        emergency_moments = [m for m in moments if m['importance'] == 'critical']

        if emergency_moments:
            # Find emergency recognition
            recognition_moments = [m for m in emergency_moments
                                 if m['action_type'] == 'emergency_recognition']

            # Find emergency response
            response_moments = [m for m in emergency_moments
                              if m['action_type'] == 'emergency_response']

            if recognition_moments and response_moments:
                recognition_time = recognition_moments[0]['timestamp']
                response_time = response_moments[0]['timestamp']

                # Calculate response time
                response_delay = response_time - recognition_time

                sequence = {
                    'sequence_type': 'anaphylaxis_response',
                    'recognition_time': recognition_time,
                    'response_time': response_time,
                    'response_delay_seconds': response_delay,
                    'recognition_moments': recognition_moments,
                    'response_moments': response_moments,
                    'assessment': self._assess_response_time(response_delay)
                }
                sequences.append(sequence)

        return sequences

    def _assess_response_time(self, delay: float) -> str:
        """Assess quality of emergency response time"""
        if delay < 30:
            return 'excellent'
        elif delay < 60:
            return 'good'
        elif delay < 120:
            return 'acceptable'
        else:
            return 'needs_improvement'

    def generate_summary(self, moments: List[Dict], sequences: List[Dict]) -> Dict:
        """Generate summary statistics"""
        summary = {
            'total_moments': len(moments),
            'by_category': {},
            'by_importance': {},
            'critical_sequences': len(sequences),
            'timeline_start': moments[0]['timestamp'] if moments else 0,
            'timeline_end': moments[-1]['end_timestamp'] if moments else 0
        }

        # Count by category
        for moment in moments:
            category = moment['category']
            if category not in summary['by_category']:
                summary['by_category'][category] = 0
            summary['by_category'][category] += 1

            # Count by importance
            importance = moment['importance']
            if importance not in summary['by_importance']:
                summary['by_importance'][importance] = 0
            summary['by_importance'][importance] += 1

        return summary


def main():
    parser = argparse.ArgumentParser(description="Extract critical moments from transcription")
    parser.add_argument('--transcript', type=str, required=True, help="Path to transcript JSON")
    parser.add_argument('--output', type=str, required=True, help="Output path for moments JSON")

    args = parser.parse_args()

    print("="*80)
    print("CRITICAL MOMENT EXTRACTION")
    print("="*80)

    # Load transcript
    print(f"\nLoading transcript: {args.transcript}")
    with open(args.transcript, 'r') as f:
        transcript = json.load(f)

    # Extract moments
    extractor = MomentExtractor()
    print("\nExtracting critical moments...")
    moments = extractor.extract_moments(transcript)

    print(f"  Found {len(moments)} critical moments")

    # Identify critical sequences
    print("\nIdentifying critical sequences...")
    sequences = extractor.identify_critical_sequence(moments)
    print(f"  Found {len(sequences)} critical sequences")

    # Generate summary
    summary = extractor.generate_summary(moments, sequences)

    # Print summary
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    print(f"Total moments: {summary['total_moments']}")
    print("\nBy category:")
    for category, count in sorted(summary['by_category'].items(), key=lambda x: x[1], reverse=True):
        print(f"  {category}: {count}")
    print("\nBy importance:")
    for importance, count in sorted(summary['by_importance'].items()):
        print(f"  {importance}: {count}")

    # Print top moments
    print(f"\n{'='*80}")
    print("TOP CRITICAL MOMENTS")
    print(f"{'='*80}")
    critical_moments = [m for m in moments if m['importance'] in ['critical', 'high']][:10]
    for moment in critical_moments:
        timestamp_min = int(moment['timestamp'] // 60)
        timestamp_sec = int(moment['timestamp'] % 60)
        print(f"\n[{timestamp_min}:{timestamp_sec:02d}] {moment['category']}")
        print(f"  Action: {moment['action_type']}")
        print(f"  Text: {moment['text'][:100]}...")
        print(f"  Confidence: {moment['confidence']:.2f}")

    # Save output
    output_data = {
        'source_transcript': args.transcript,
        'moments': moments,
        'critical_sequences': sequences,
        'summary': summary
    }

    with open(args.output, 'w') as f:
        json.dump(output_data, f, indent=2)

    print(f"\n{'='*80}")
    print(f"✓ Moments saved: {args.output}")
    print(f"{'='*80}")


if __name__ == "__main__":
    main()
