from scripts.flags.fusion import FusedFlag
from scripts.flags.selection import select_flagged_windows


def flag(flag_id, start, end):
    return FusedFlag(flag_id, start, end, ())


def test_half_open_boundary_touch_does_not_select_a_window():
    windows = [
        {"window_id": "w0", "start_seconds": 0, "end_seconds": 30},
        {"window_id": "w1", "start_seconds": 30, "end_seconds": 60},
    ]
    selected = select_flagged_windows(windows, [flag("f1", 30, 31)])
    assert [window["window_id"] for window in selected] == ["w1"]


def test_positive_duration_intersection_selects_and_retains_all_matching_flag_ids():
    windows = [{"window_id": "w0", "start_seconds": 0, "end_seconds": 30}]
    selected = select_flagged_windows(
        windows, [flag("f1", 29.999, 31), flag("f2", 0, 0.001)]
    )
    assert selected[0]["flag_ids"] == ["f1", "f2"]
