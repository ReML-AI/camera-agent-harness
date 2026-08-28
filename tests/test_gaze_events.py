from scripts.analytics.compute_gaze_events import (
    detect_convergence_events,
    detect_divergence_events,
    detect_sustained_patient,
)

SAMPLE_GAZE = {
    "tracks": [
        {"speaker": "SPEAKER_00", "frames": [
            {"frame": 100, "timestamp": 4.0, "target": "patient"},
            {"frame": 125, "timestamp": 5.0, "target": "patient"},
            {"frame": 150, "timestamp": 6.0, "target": "patient"},
        ]},
        {"speaker": "SPEAKER_01", "frames": [
            {"frame": 100, "timestamp": 4.0, "target": "other"},
            {"frame": 125, "timestamp": 5.0, "target": "patient"},
            {"frame": 150, "timestamp": 6.0, "target": "patient"},
        ]},
        {"speaker": "SPEAKER_02", "frames": [
            {"frame": 100, "timestamp": 4.0, "target": "person"},
            {"frame": 125, "timestamp": 5.0, "target": "patient"},
            {"frame": 150, "timestamp": 6.0, "target": "patient"},
        ]},
    ]
}

def test_detect_convergence():
    events = detect_convergence_events(SAMPLE_GAZE["tracks"], min_speakers=3, time_window_sec=5.0)
    assert len(events) >= 1
    assert events[0]["type"] == "convergence"
    assert events[0]["target"] == "patient"


def test_detect_sustained_patient():
    patient_gaze = {
        "tracks": [
            {"speaker": f"SPEAKER_0{i}", "frames": [
                {"frame": f, "timestamp": f / 25.0, "target": "patient"}
                for f in range(0, 300, 25)
            ]}
            for i in range(3)
        ]
    }
    events = detect_sustained_patient(patient_gaze["tracks"], min_duration_sec=10.0)
    assert len(events) >= 1
    assert events[0]["type"] == "sustained_patient"


def test_detect_divergence():
    """Gaze aligned at t=4-5, then fully scattered at t=7-8."""
    tracks = [
        {"speaker": "SPEAKER_00", "frames": [
            {"frame": 100, "timestamp": 4.0, "target": "patient"},
            {"frame": 125, "timestamp": 5.0, "target": "patient"},
            {"frame": 175, "timestamp": 7.0, "target": "patient"},
            {"frame": 200, "timestamp": 8.0, "target": "patient"},
        ]},
        {"speaker": "SPEAKER_01", "frames": [
            {"frame": 100, "timestamp": 4.0, "target": "patient"},
            {"frame": 125, "timestamp": 5.0, "target": "patient"},
            {"frame": 175, "timestamp": 7.0, "target": "other"},
            {"frame": 200, "timestamp": 8.0, "target": "other"},
        ]},
        {"speaker": "SPEAKER_02", "frames": [
            {"frame": 100, "timestamp": 4.0, "target": "patient"},
            {"frame": 125, "timestamp": 5.0, "target": "patient"},
            {"frame": 175, "timestamp": 7.0, "target": "person"},
            {"frame": 200, "timestamp": 8.0, "target": "person"},
        ]},
    ]
    events = detect_divergence_events(tracks, min_speakers=3)
    assert len(events) >= 1
    assert events[0]["type"] == "divergence"
