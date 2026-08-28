#!/usr/bin/env python3
"""Extract a time segment from the full transcript"""

import json
import argparse

def extract_segment(transcript_path, start_time, end_time, output_path):
    """Extract segments within time range"""
    with open(transcript_path) as f:
        data = json.load(f)

    segments = data['segments']

    # Filter segments that overlap with [start_time, end_time]
    extracted = []
    for seg in segments:
        seg_start = seg['start']
        seg_end = seg['end']

        # Check for overlap
        if seg_start <= end_time and seg_end >= start_time:
            # Adjust timestamps to be relative to start_time
            new_seg = seg.copy()
            new_seg['start'] = max(0, seg_start - start_time)
            new_seg['end'] = seg_end - start_time
            new_seg['original_start'] = seg_start
            new_seg['original_end'] = seg_end
            extracted.append(new_seg)

    output = {
        'source_video': data['source_video'],
        'language': data['language'],
        'time_range': {'start': start_time, 'end': end_time},
        'segments': extracted
    }

    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"Extracted {len(extracted)} segments from {start_time}s - {end_time}s")
    print(f"Saved to: {output_path}")

    return output

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--transcript', required=True)
    parser.add_argument('--start', type=float, required=True)
    parser.add_argument('--end', type=float, required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()

    extract_segment(args.transcript, args.start, args.end, args.output)
