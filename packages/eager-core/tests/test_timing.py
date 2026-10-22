import pytest

from eager_core.timing import FrameClock


def test_frame_clock_ticks():
    clock = FrameClock(rolling_window=5)
    assert clock.tick(now=0.0) == 0.0
    assert clock.dt == 0.0
    assert clock.frame_count == 1

    dt1 = clock.tick(now=0.016)
    assert dt1 == pytest.approx(0.016)
    assert clock.dt == pytest.approx(0.016)
    assert clock.frame_count == 2
    assert clock.fps == pytest.approx(1.0 / 0.016)

    clock.tick(now=0.032)
    assert clock.elapsed == pytest.approx(0.032)
    assert clock.fps_overall > 0.0
    assert clock.fps_avg > 0.0


def test_frame_clock_reset():
    clock = FrameClock(rolling_window=5)
    clock.tick(now=1.0)
    clock.tick(now=2.0)
    clock.reset()
    assert clock.frame_count == 0
    assert clock.dt == 0.0
    assert clock.fps == 0.0


def test_frame_clock_invalid_window():
    with pytest.raises(ValueError):
        FrameClock(rolling_window=1)
