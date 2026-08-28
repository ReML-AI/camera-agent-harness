from scripts.analytics.compute_speaker_dynamics import (
    compute_dynamics_for_window,
    classify_pattern,
    compute_all_windows,
)

SAMPLE_SEGMENTS = [
    {"speaker": "SPEAKER_00", "start": 0.0, "end": 3.0, "text": "Check the airway"},
    {"speaker": "SPEAKER_01", "start": 3.5, "end": 5.0, "text": "Airway is clear"},
    {"speaker": "SPEAKER_00", "start": 5.2, "end": 7.0, "text": "OK starting assessment"},
    {"speaker": "SPEAKER_02", "start": 6.8, "end": 9.0, "text": "I see the monitor changing"},
    {"speaker": "SPEAKER_01", "start": 9.5, "end": 12.0, "text": "Let me check vitals"},
    {"speaker": "SPEAKER_00", "start": 12.5, "end": 15.0, "text": "Pulse is weak"},
]

def test_compute_dynamics_basic():
    result = compute_dynamics_for_window(SAMPLE_SEGMENTS, 0.0, 30.0)
    assert result["turn_count"] >= 5
    assert result["speaker_count"] == 3
    assert "dominant_speaker" in result
    assert 0 <= result["overlap_pct"] <= 100

def test_classify_pattern_rapid_exchange():
    assert classify_pattern(turn_count=6, speaker_count=3, overlap_pct=5, silence_before=1.0, dominant_pct=40) == "rapid_exchange"

def test_classify_pattern_monologue():
    assert classify_pattern(turn_count=1, speaker_count=1, overlap_pct=0, silence_before=1.0, dominant_pct=95) == "monologue"

def test_classify_pattern_silence_break():
    assert classify_pattern(turn_count=2, speaker_count=1, overlap_pct=0, silence_before=10.0, dominant_pct=80) == "silence_break"

def test_classify_pattern_overlapping():
    assert classify_pattern(turn_count=3, speaker_count=2, overlap_pct=25, silence_before=1.0, dominant_pct=50) == "overlapping"

def test_compute_all_windows():
    windows = compute_all_windows(SAMPLE_SEGMENTS, window_sec=30, slide_sec=15)
    assert len(windows) >= 1
    assert "start" in windows[0]
    assert "end" in windows[0]
    assert "pattern" in windows[0]

def test_three_speaker_overlap_counts_wall_clock_time_once():
    segments = [
        {"speaker": "A", "start": 0.0, "end": 5.0, "text": "a"},
        {"speaker": "B", "start": 1.0, "end": 4.0, "text": "b"},
        {"speaker": "C", "start": 2.0, "end": 3.0, "text": "c"},
    ]
    result = compute_dynamics_for_window(segments, 0.0, 5.0)
    assert result["overlap_pct"] == 60.0
