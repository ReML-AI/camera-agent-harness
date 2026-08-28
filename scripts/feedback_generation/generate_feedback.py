#!/usr/bin/env python3
"""Generate structured educational feedback using a local LLM (Qwen 7B)."""

import json
import argparse
import os
import sys
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.llm_client import chat, get_model

from feedback_prompts import (
    SYSTEM_PROMPT,
    build_feedback_prompt,
)


class FeedbackGenerator:
    def __init__(self, model: str = None):
        self.model = get_model(model)

    def generate_feedback(
        self,
        person_timeline: Dict,
        scenario_context: str = None,
        max_tokens: int = 4000,
    ) -> Dict:
        prompt = build_feedback_prompt(person_timeline, scenario_context)

        print(f"Generating feedback for Person {person_timeline['person_id']} "
              f"({person_timeline['role']})...")

        try:
            resp = chat(
                prompt=prompt,
                system=SYSTEM_PROMPT,
                model=self.model,
                max_tokens=max_tokens,
            )
            return {
                'person_id': person_timeline['person_id'],
                'role': person_timeline['role'],
                'feedback_text': resp['text'],
                'metadata': {
                    'model': resp['model'],
                    'total_actions': person_timeline['total_actions'],
                    'critical_actions': person_timeline['critical_actions'],
                    'categories': person_timeline['categories'],
                    'tokens_used': resp['output_tokens'],
                    'stop_reason': resp['finish_reason'],
                },
            }
        except Exception as e:
            print(f"  Error generating feedback: {e}")
            return {
                'person_id': person_timeline['person_id'],
                'role': person_timeline['role'],
                'feedback_text': None,
                'error': str(e),
            }

    def generate_all_feedback(
        self,
        person_timelines: Dict,
        role_filter: List[str] = None,
    ) -> List[Dict]:
        all_feedback = []
        for person_id, timeline in person_timelines.items():
            if role_filter and timeline['role'] not in role_filter:
                print(f"Skipping Person {person_id} (role: {timeline['role']})")
                continue
            if timeline['total_actions'] == 0:
                print(f"Skipping Person {person_id} (no actions)")
                continue
            all_feedback.append(self.generate_feedback(timeline))
        return all_feedback


def main():
    parser = argparse.ArgumentParser(description="Generate AI feedback for student performance")
    parser.add_argument('--associations', type=str, required=True,
                        help="Path to moment-person associations JSON")
    parser.add_argument('--output', type=str, required=True,
                        help="Output path for feedback JSON")
    parser.add_argument('--model', type=str, default=None,
                        help="Model identifier (default: $LLM_MODEL or qwen2.5:7b)")
    parser.add_argument('--students-only', action='store_true',
                        help="Only generate feedback for students")
    args = parser.parse_args()

    print("=" * 80)
    print("AI FEEDBACK GENERATION")
    print("=" * 80)

    print(f"\nLoading associations from: {args.associations}")
    with open(args.associations, 'r') as f:
        associations_data = json.load(f)

    person_timelines = associations_data['person_timelines']
    print(f"  Loaded timelines for {len(person_timelines)} persons")

    generator = FeedbackGenerator(model=args.model)
    print(f"\nModel: {generator.model}")

    role_filter = None
    if args.students_only:
        role_filter = ['Student Nurse (Primary)', 'Supervising Nurse/Doctor']
        print("\nGenerating feedback for students only...")
    else:
        print("\nGenerating feedback for all persons...")

    all_feedback = generator.generate_all_feedback(person_timelines, role_filter)

    print(f"\n{'=' * 80}")
    print(f"Generated feedback for {len(all_feedback)} persons")
    print(f"{'=' * 80}")

    output_data = {
        'source_associations': args.associations,
        'model': generator.model,
        'feedback': all_feedback,
        'summary': {
            'total_persons': len(person_timelines),
            'feedback_generated': len(all_feedback),
            'total_tokens_used': sum(
                f['metadata'].get('tokens_used', 0)
                for f in all_feedback if 'metadata' in f
            ),
        },
    }

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, 'w') as f:
        json.dump(output_data, f, indent=2)

    print(f"\nFeedback saved: {args.output}")
    print(f"Total tokens used: {output_data['summary']['total_tokens_used']}")


if __name__ == "__main__":
    main()
