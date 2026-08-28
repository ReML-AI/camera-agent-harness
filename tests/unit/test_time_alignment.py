import pytest

from scripts.core.errors import ContractError
from scripts.core.records import Interval, StreamMetadata, SynchronizationTransform


def stream(*, fps=True):
    return StreamMetadata(
        stream_id="cam1", session_id="session-001",
        time_base_numerator=1, time_base_denominator=90000,
        fps_numerator=30000 if fps else None,
        fps_denominator=1001 if fps else None,
        duration_seconds=20.0,
        synchronization=SynchronizationTransform("sync-v1", 0.25, 1.001),
    )


def test_rational_native_timestamp_and_alignment():
    native, aligned = stream().frame_timestamp(30)
    assert native == pytest.approx(1.001)
    assert aligned == pytest.approx(1.252001)


def test_no_default_fps_when_stream_has_none():
    with pytest.raises(ContractError, match="no declared FPS"):
        stream(fps=False).frame_timestamp(1)


def test_half_open_boundary_does_not_overlap():
    assert not Interval(0, 1).overlaps(Interval(1, 2))
    assert Interval(0, 1.1).overlaps(Interval(1, 2))


@pytest.mark.parametrize("start,end", [(-1, 1), (1, 1), (2, 1)])
def test_invalid_intervals_fail(start, end):
    with pytest.raises(ContractError):
        Interval(start, end)

