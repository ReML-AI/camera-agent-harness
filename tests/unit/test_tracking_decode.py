from __future__ import annotations

import pytest

from scripts.person_tracking.track_persons import (
    _DecodedFrameStream,
    grab_preserves_presentation_timestamps,
)


class _FakeCapture:
    def __init__(
        self,
        timestamps: list[float],
        *,
        grabbed_timestamps: list[float] | None = None,
    ) -> None:
        self.timestamps = timestamps
        self.grabbed_timestamps = grabbed_timestamps or timestamps
        self.position = -1
        self.retrieved = False
        self.grab_calls = 0
        self.retrieve_calls = 0
        self.read_calls = 0
        self.released = False

    def isOpened(self) -> bool:
        return True

    def grab(self) -> bool:
        if self.position + 1 >= len(self.timestamps):
            return False
        self.position += 1
        self.retrieved = False
        self.grab_calls += 1
        return True

    def retrieve(self):
        self.retrieve_calls += 1
        self.retrieved = True
        return True, f"frame-{self.position}"

    def read(self):
        self.read_calls += 1
        if not self.grab():
            return False, None
        return self.retrieve()

    def get(self, _property: int) -> float:
        timestamps = self.timestamps if self.retrieved else self.grabbed_timestamps
        return timestamps[self.position] * 1000.0

    def release(self) -> None:
        self.released = True


class _FakeCv2:
    CAP_PROP_POS_MSEC = 0

    def __init__(
        self,
        timestamps: list[float],
        *,
        grabbed_timestamps: list[float] | None = None,
    ) -> None:
        self.timestamps = timestamps
        self.grabbed_timestamps = grabbed_timestamps
        self.captures: list[_FakeCapture] = []

    def VideoCapture(self, _path: str) -> _FakeCapture:
        capture = _FakeCapture(
            self.timestamps, grabbed_timestamps=self.grabbed_timestamps
        )
        self.captures.append(capture)
        return capture


def _drain(stream: _DecodedFrameStream) -> list[tuple[int, float, str]]:
    kept = []
    while True:
        decoded = stream.read_next_kept()
        if decoded is None:
            return kept
        kept.append(decoded)


def test_grab_decimation_keeps_exact_read_timestamps_and_frame_indexes():
    """The optimized path must select exactly the frames selected by full read()."""
    timestamps = [index * 1001.0 / 30000.0 for index in range(30)]
    cv2_module = _FakeCv2(timestamps)
    baseline_capture = _FakeCapture(timestamps)
    optimized_capture = _FakeCapture(timestamps)

    baseline = _drain(
        _DecodedFrameStream(
            baseline_capture,
            cv2_module,
            5.0,
            grab_discarded_frames=False,
        )
    )
    optimized = _drain(
        _DecodedFrameStream(
            optimized_capture,
            cv2_module,
            5.0,
            grab_discarded_frames=True,
        )
    )

    assert optimized == baseline
    assert [item[0] for item in optimized] == [0, 6, 12, 18, 24]
    assert [item[1] for item in optimized] == [
        timestamps[index] for index in (0, 6, 12, 18, 24)
    ]
    assert baseline_capture.retrieve_calls == len(timestamps)
    assert optimized_capture.retrieve_calls == len(optimized)
    assert optimized_capture.read_calls == 0
    assert optimized_capture.grab_calls == len(timestamps)
    assert baseline_capture.position == optimized_capture.position == len(timestamps) - 1


def test_grab_timestamp_probe_accepts_pts_available_before_retrieve():
    timestamps = [0.0, 0.033, 0.067]
    cv2_module = _FakeCv2(timestamps)

    assert grab_preserves_presentation_timestamps("video.mp4", cv2_module)
    assert cv2_module.captures[0].released


def test_grab_timestamp_probe_rejects_backend_that_updates_pts_on_retrieve():
    timestamps = [0.0, 0.033, 0.067]
    delayed_grab_timestamps = [0.0, 0.0, 0.033]
    cv2_module = _FakeCv2(
        timestamps, grabbed_timestamps=delayed_grab_timestamps
    )

    assert not grab_preserves_presentation_timestamps("video.mp4", cv2_module)
    assert cv2_module.captures[0].released


def test_monotonicity_check_also_covers_grabbed_discarded_frames():
    timestamps = [0.0, 0.04, 0.03]
    capture = _FakeCapture(timestamps)
    stream = _DecodedFrameStream(
        capture,
        _FakeCv2(timestamps),
        1.0,
        grab_discarded_frames=True,
    )

    assert stream.read_next_kept() == (0, 0.0, "frame-0")
    with pytest.raises(RuntimeError, match="moved backwards at frame 2"):
        stream.read_next_kept()
