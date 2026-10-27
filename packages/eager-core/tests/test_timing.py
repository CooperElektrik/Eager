import time

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


class TestFrameClock:
    """Unit tests for the standalone FrameClock utility."""

    def test_first_tick_returns_zero_dt(self) -> None:
        clock = FrameClock()
        assert clock.tick() == 0.0
        assert clock.frame_count == 1

    def test_fps_zero_until_two_ticks(self) -> None:
        clock = FrameClock()
        clock.tick()
        assert clock.fps == 0.0
        assert clock.fps_avg == 0.0

    def test_fps_uses_explicit_timestamps(self) -> None:
        clock = FrameClock()
        clock.tick(now=10.0)
        clock.tick(now=10.5)  # 0.5s interval
        assert clock.dt == pytest.approx(0.5)
        assert clock.fps == pytest.approx(2.0)  # 1 / 0.5

    def test_fps_avg_rolling_window(self) -> None:
        """fps_avg should only use the last ``rolling_window`` frames."""
        clock = FrameClock(rolling_window=3)
        # 5 frames at 0.1s intervals → overall would be 10 FPS
        for i in range(5):
            clock.tick(now=float(i) * 0.1)
        # Rolling window = 3 frames → last 3 frames span 0.3s → 10 FPS
        assert clock.fps == pytest.approx(10.0)
        assert clock.fps_avg == pytest.approx(10.0)

    def test_fps_avg_trims_old_timestamps(self) -> None:
        clock = FrameClock(rolling_window=3)
        # 5 frames at 0.1s intervals, then 1 frame at 1.0s (slow)
        for i in range(5):
            clock.tick(now=float(i) * 0.1)
        clock.tick(now=1.5)  # 1.1s gap from previous (0.4)

        # Rolling window = 3 → keep last 4 timestamps: [0.2, 0.3, 0.4, 1.5]
        # dt = 1.5 - 0.4 = 1.1 → fps = 1/1.1 ≈ 0.909
        assert clock.fps == pytest.approx(1.0 / 1.1, abs=0.01)
        # fps_avg = 3 intervals / (1.5 - 0.2) = 3/1.3 ≈ 2.308
        assert clock.fps_avg == pytest.approx(3.0 / 1.3, abs=0.01)

    def test_fps_overall_total(self) -> None:
        clock = FrameClock()
        # 10 frames at 0.1s intervals → start=0.0, end=0.9, elapsed=0.9
        for i in range(10):
            clock.tick(now=float(i) * 0.1)
        assert clock.frame_count == 10
        assert clock.fps_overall == pytest.approx(10.0 / 0.9, abs=0.01)
        assert clock.elapsed == pytest.approx(0.9)

    def test_reset_clears_state(self) -> None:
        clock = FrameClock()
        for i in range(5):
            clock.tick(now=float(i))
        assert clock.frame_count == 5
        clock.reset()
        assert clock.frame_count == 0
        assert clock.fps == 0.0
        assert clock.fps_avg == 0.0
        assert clock.elapsed == 0.0

    def test_real_time_perf_counter(self) -> None:
        """Without explicit timestamps, uses time.perf_counter (smoke test)."""
        clock = FrameClock()
        clock.tick()
        time.sleep(0.02)
        dt = clock.tick()
        assert dt > 0.0
        assert clock.fps > 0.0

    def test_rolling_window_must_be_at_least_2(self) -> None:
        with pytest.raises(ValueError, match="rolling_window"):
            FrameClock(rolling_window=1)

    def test_tick_returns_dt(self) -> None:
        clock = FrameClock()
        clock.tick(now=0.0)
        dt = clock.tick(now=0.016)
        assert dt == pytest.approx(0.016)


class TestFrameClockEdgeCases:
    """Edge-case tests for FrameClock."""

    def test_zero_dt_on_identical_timestamps(self) -> None:
        clock = FrameClock()
        clock.tick(now=1.0)
        dt = clock.tick(now=1.0)  # same timestamp
        assert dt == 0.0
        # fps should be 0 because dt is 0
        assert clock.fps == 0.0

    def test_negative_dt_guarded(self) -> None:
        clock = FrameClock()
        clock.tick(now=1.0)
        # Simulate a backwards clock
        dt = clock.tick(now=0.5)
        assert dt == 0.0
        assert clock.fps == 0.0

    def test_large_rolling_window(self) -> None:
        """With a large window, all timestamps are kept."""
        clock = FrameClock(rolling_window=1000)
        for i in range(200):
            clock.tick(now=float(i))
        assert clock.fps == pytest.approx(1.0)
        assert clock.fps_avg == pytest.approx(1.0)
        # fps_overall = 200 frames / 199.0s (start at 0.0, end at 199.0)
        assert clock.fps_overall == pytest.approx(200.0 / 199.0, abs=0.01)

