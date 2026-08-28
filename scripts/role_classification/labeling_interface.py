#!/usr/bin/env python3
"""
Person Role Labeling Interface (Per-Camera)
Interactive web UI for labeling detected persons with clinical roles
Uses per-camera tracks instead of cross-camera matching
"""

import os
import json
import streamlit as st
from pathlib import Path
import base64
from typing import Dict, List

# Page configuration
st.set_page_config(
    page_title="Person Role Labeling",
    page_icon="👥",
    layout="wide"
)

# Role options
ROLE_OPTIONS = [
    "Not Labeled",
    "Student Nurse (Primary)",
    "Supervising Nurse/Doctor",
    "Patient/Mannequin",
    "Observer/Other",
    "Background/False Detection"
]

ROLE_COLORS = {
    "Not Labeled": "#666666",
    "Student Nurse (Primary)": "#2196F3",
    "Supervising Nurse/Doctor": "#4CAF50",
    "Patient/Mannequin": "#FF9800",
    "Observer/Other": "#9C27B0",
    "Background/False Detection": "#F44336"
}


def load_per_camera_tracks(tracks_dir: str) -> List[Dict]:
    """Load all per-camera tracking results"""
    tracks_dir = Path(tracks_dir)
    track_files = sorted(tracks_dir.glob('person_tracks_*.json'))

    all_persons = []

    for track_file in track_files:
        with open(track_file, 'r') as f:
            data = json.load(f)

        camera_id = data['camera_id']

        for person in data['persons']:
            # Create unique person entry
            person_entry = {
                'unique_id': f"{camera_id}_person_{person['person_id']}",
                'camera_id': camera_id,
                'person_id': person['person_id'],
                'track_id': person['track_id'],
                'thumbnail_path': person.get('thumbnail_path'),
                'screen_time': person['total_screen_time_seconds'],
                'num_appearances': person.get('num_appearances', 0),
                'avg_confidence': person.get('average_confidence', 0.0)
            }
            all_persons.append(person_entry)

    # Sort by screen time (most visible first)
    all_persons.sort(key=lambda x: x['screen_time'], reverse=True)

    return all_persons


def load_existing_labels(file_path: str) -> Dict:
    """Load existing role labels if available"""
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            return json.load(f)
    return {}


def save_labels(labels: Dict, file_path: str):
    """Save role labels to JSON"""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'w') as f:
        json.dump(labels, f, indent=2)


def get_image_base64(image_path: str) -> str:
    """Convert image to base64 for display"""
    try:
        with open(image_path, 'rb') as f:
            return base64.b64encode(f.read()).decode()
    except:
        return None


def format_time(seconds: float) -> str:
    """Format seconds to MM:SS"""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}:{secs:02d}"


def main():
    st.title("👥 Person Role Labeling Interface (Per-Camera)")
    st.markdown("Label detected persons with their clinical roles - **each camera track labeled separately**")

    st.info("💡 **Note:** Labeling per-camera tracks (not using cross-camera matching). Each person in each camera is labeled independently.")

    # File paths
    tracks_dir = "data/processed"
    labels_file = "data/labeled/person_roles_per_camera.json"

    # Check if tracks exist
    track_files = list(Path(tracks_dir).glob('person_tracks_*.json'))
    if not track_files:
        st.error(f"❌ No tracking files found in {tracks_dir}")
        st.info("Run Stage 1 (person tracking) first to generate these files.")
        return

    # Load data
    all_persons = load_per_camera_tracks(tracks_dir)
    labels_data = load_existing_labels(labels_file)

    # Initialize labels if needed
    if 'person_labels' not in labels_data:
        labels_data['person_labels'] = {}

    # Sidebar statistics
    st.sidebar.header("📊 Dataset Statistics")
    st.sidebar.metric("Total Person Tracks", len(all_persons))

    # Count by camera
    cameras = {}
    for person in all_persons:
        cam = person['camera_id']
        cameras[cam] = cameras.get(cam, 0) + 1

    st.sidebar.write("**By Camera:**")
    for cam, count in sorted(cameras.items()):
        st.sidebar.write(f"  - {cam}: {count} persons")

    labeled_count = sum(
        1 for person_id, label in labels_data['person_labels'].items()
        if label['role'] != "Not Labeled"
    )
    st.sidebar.metric("Labeled Persons", f"{labeled_count}/{len(all_persons)}")

    # Progress
    progress = labeled_count / len(all_persons) if all_persons else 0
    st.sidebar.progress(progress)

    # Filter options
    st.sidebar.header("🔍 Filters")
    show_unlabeled = st.sidebar.checkbox("Show only unlabeled", value=True)
    min_screen_time = st.sidebar.slider("Min screen time (seconds)", 0, 1000, 0)

    # Camera filter
    camera_filter = st.sidebar.multiselect(
        "Filter by camera",
        options=sorted(cameras.keys()),
        default=sorted(cameras.keys())
    )

    # Main content
    st.header("Label Persons")

    # Track changes
    changes_made = False

    # Display each person
    for person in all_persons:
        unique_id = person['unique_id']
        camera_id = person['camera_id']
        screen_time = person['screen_time']

        # Apply filters
        if camera_id not in camera_filter:
            continue

        if show_unlabeled and unique_id in labels_data['person_labels']:
            if labels_data['person_labels'][unique_id]['role'] != "Not Labeled":
                continue

        if screen_time < min_screen_time:
            continue

        # Get current label
        current_label = labels_data['person_labels'].get(
            unique_id,
            {'role': 'Not Labeled', 'confidence': 0, 'notes': ''}
        )

        # Person card
        role_color = ROLE_COLORS.get(current_label['role'], "#666666")

        with st.container():
            st.markdown(f"""
                <div style="border-left: 5px solid {role_color}; padding-left: 15px; margin-bottom: 20px;">
                    <h3>{camera_id.upper()} - Person #{person['person_id']}</h3>
                    <p style="color: #666; font-size: 14px;">Track ID: {person['track_id']}</p>
                </div>
            """, unsafe_allow_html=True)

            # Layout: thumbnail on left, info on right
            col1, col2 = st.columns([1, 2])

            with col1:
                st.subheader("Thumbnail")

                thumbnail_path = person['thumbnail_path']
                if thumbnail_path:
                    img_base64 = get_image_base64(thumbnail_path)
                    if img_base64:
                        st.markdown(f"""
                            <div style="margin-bottom: 10px;">
                                <p style="margin: 5px 0; font-size: 12px; color: #666;">
                                    {camera_id} ({format_time(screen_time)})
                                </p>
                                <img src="data:image/jpeg;base64,{img_base64}"
                                     style="width: 100%; border: 2px solid {role_color}; border-radius: 5px;">
                            </div>
                        """, unsafe_allow_html=True)
                    else:
                        st.warning(f"❌ Image not found: {thumbnail_path}")
                else:
                    st.warning("No thumbnail available")

            with col2:
                st.subheader("Information")

                # Statistics
                info_col1, info_col2, info_col3 = st.columns(3)
                with info_col1:
                    st.metric("Screen Time", format_time(screen_time))
                with info_col2:
                    st.metric("Appearances", person['num_appearances'])
                with info_col3:
                    st.metric("Avg Confidence", f"{person['avg_confidence']:.2f}")

                # Labeling interface
                st.subheader("🏷️ Role Label")

                label_col1, label_col2 = st.columns([2, 1])

                with label_col1:
                    selected_role = st.selectbox(
                        "Select Role",
                        options=ROLE_OPTIONS,
                        index=ROLE_OPTIONS.index(current_label['role']),
                        key=f"role_{unique_id}"
                    )

                with label_col2:
                    confidence = st.select_slider(
                        "Confidence",
                        options=[0, 1, 2, 3, 4, 5],
                        value=current_label.get('confidence', 0),
                        key=f"conf_{unique_id}",
                        help="0=Uncertain, 5=Very Certain"
                    )

                notes = st.text_area(
                    "Notes (optional)",
                    value=current_label.get('notes', ''),
                    key=f"notes_{unique_id}",
                    height=60
                )

                # Update label if changed
                new_label = {
                    'role': selected_role,
                    'confidence': confidence,
                    'notes': notes,
                    'camera_id': camera_id,
                    'person_id': person['person_id'],
                    'track_id': person['track_id'],
                    'screen_time': screen_time
                }

                if new_label != current_label:
                    labels_data['person_labels'][unique_id] = new_label
                    changes_made = True

            st.markdown("---")

    # Save button
    if st.button("💾 Save All Labels", type="primary", use_container_width=True):
        # Add metadata
        labels_data['metadata'] = {
            'total_persons': len(all_persons),
            'labeled_count': labeled_count,
            'mode': 'per_camera',
            'label_options': ROLE_OPTIONS
        }

        save_labels(labels_data, labels_file)
        st.success(f"✅ Labels saved to {labels_file}")
        st.balloons()

    # Auto-save notification
    if changes_made:
        st.info("💡 Changes detected. Click 'Save All Labels' to persist your work.")

    # Export summary
    st.sidebar.header("📥 Export")
    if st.sidebar.button("Export Summary"):
        summary = []
        for unique_id, label_info in labels_data.get('person_labels', {}).items():
            summary.append({
                'unique_id': unique_id,
                'camera_id': label_info.get('camera_id'),
                'person_id': label_info.get('person_id'),
                'role': label_info['role'],
                'confidence': label_info['confidence'],
                'screen_time': label_info.get('screen_time', 0),
                'notes': label_info.get('notes', '')
            })

        st.sidebar.json(summary)


if __name__ == "__main__":
    main()
