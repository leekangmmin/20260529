#!/usr/bin/env python3
"""
Conformal HUD – Symbol Stabilisation Test Suite (v2.1.0)

Tests:
  1. Adaptive EMA filter (rate-adaptive smoothing)
  2. 2-D position stabiliser
  3. Temporal damper (critically damped 2nd order)
  4. Runway corner EMA
  5. FPV anti-jitter filtering

Run:  python -m pytest tests/test_stabilization.py -v
"""

import math
import pytest


# ======================================================================
#  Reference implementations
# ======================================================================

class AdaptiveEMAFilter:
    def __init__(self, alpha_min=0.05, alpha_max=0.95, rate_threshold=1.0):
        self.value = 0.0
        self.alpha = alpha_min
        self.alpha_min = max(0.0, alpha_min)
        self.alpha_max = min(1.0, alpha_max)
        self.rate_threshold = max(0.0, rate_threshold)
        self.prev_raw = 0.0
        self.initialised = False

    def feed(self, sample, dt_s=1.0/60.0):
        if not self.initialised:
            self.value = sample
            self.prev_raw = sample
            self.initialised = True
            return self.value

        rate = abs(sample - self.prev_raw)
        self.prev_raw = sample

        if rate > self.rate_threshold:
            self.alpha = self.alpha + (self.alpha_max - self.alpha) * 0.2
        else:
            self.alpha = self.alpha_min + (self.alpha - self.alpha_min) * 0.9

        self.alpha = max(self.alpha_min, min(self.alpha_max, self.alpha))
        self.value = self.alpha * sample + (1.0 - self.alpha) * self.value
        return self.value

    def reset(self):
        self.value = 0.0
        self.alpha = self.alpha_min
        self.prev_raw = 0.0
        self.initialised = False


class TemporalDamper:
    def __init__(self, damping_ratio=1.0, natural_freq_hz=3.0):
        self.value = 0.0
        self.velocity = 0.0
        self.damping_ratio = max(0.0, damping_ratio)
        self.natural_freq = max(0.0, natural_freq_hz) * 2.0 * math.pi
        self.initialised = False

    def feed(self, target, dt_s=1.0/60.0):
        if not self.initialised:
            self.value = target
            self.velocity = 0.0
            self.initialised = True
            return self.value

        w = self.natural_freq
        z = self.damping_ratio
        dt = dt_s

        error = target - self.value
        accel = w * w * error - 2.0 * z * w * self.velocity

        self.velocity += accel * dt
        self.value += self.velocity * dt
        return self.value

    def reset(self, value):
        self.value = value
        self.velocity = 0.0
        self.initialised = True


class PosStabiliser:
    def __init__(self, alpha_min=0.15, alpha_max=0.85, rate_threshold=10.0):
        self.fx = AdaptiveEMAFilter(alpha_min, alpha_max, rate_threshold)
        self.fy = AdaptiveEMAFilter(alpha_min, alpha_max, rate_threshold)
        self.smoothed_x = 0.0
        self.smoothed_y = 0.0
        self.initialised = False

    def feed(self, raw_x, raw_y, dt_s=1.0/60.0):
        sx = self.fx.feed(raw_x, dt_s)
        sy = self.fy.feed(raw_y, dt_s)
        self.smoothed_x = sx
        self.smoothed_y = sy
        self.initialised = True
        return sx, sy

    def reset(self):
        self.fx.reset()
        self.fy.reset()
        self.smoothed_x = 0.0
        self.smoothed_y = 0.0
        self.initialised = False


# ======================================================================
#  Tests
# ======================================================================

class TestAdaptiveEMA:
    def test_init(self):
        f = AdaptiveEMAFilter(0.1, 0.9, 2.0)
        assert f.initialised is False
        assert f.alpha == 0.1

    def test_first_sample_initialises(self):
        f = AdaptiveEMAFilter(0.1, 0.9, 2.0)
        val = f.feed(42.0)
        assert val == 42.0
        assert f.initialised is True

    def test_smoothing_effect(self):
        f = AdaptiveEMAFilter(0.1, 0.9, 10.0)
        f.feed(0.0)
        # Step to 100 should be smoothed
        s1 = f.feed(100.0)
        # With low alpha, should be heavily smoothed
        assert s1 < 30.0
        assert s1 > 0.0

    def test_high_rate_increases_alpha(self):
        f = AdaptiveEMAFilter(0.1, 0.9, 5.0)
        f.feed(0.0)
        # Slow change
        f.feed(1.0)
        alpha_before = f.alpha
        # Rapid change
        f.feed(100.0)
        assert f.alpha > alpha_before

    def test_low_rate_decreases_alpha(self):
        f = AdaptiveEMAFilter(0.5, 0.9, 5.0)  # start with high alpha
        f.feed(50.0)
        # Several small changes
        for _ in range(20):
            f.feed(50.1)
        assert f.alpha < 0.55  # alpha should have dropped toward min

    def test_convergence_to_steady_value(self):
        f = AdaptiveEMAFilter(0.1, 0.9, 1.0)
        for _ in range(50):
            f.feed(100.0)
        assert abs(f.value - 100.0) < 1.0

    def test_reset(self):
        f = AdaptiveEMAFilter(0.1, 0.9, 1.0)
        f.feed(50.0)
        f.reset()
        assert f.initialised is False
        assert f.value == 0.0


class TestTemporalDamper:
    def test_init(self):
        d = TemporalDamper(1.0, 3.0)
        assert d.initialised is False

    def test_first_sample_initialises(self):
        d = TemporalDamper(1.0, 3.0)
        val = d.feed(42.0)
        assert val == 42.0
        assert d.initialised is True

    def test_no_overshoot_critically_damped(self):
        """Critically damped system should not overshoot."""
        d = TemporalDamper(1.0, 2.0)
        d.feed(0.0)
        values = []
        for _ in range(60):
            val = d.feed(100.0, 1.0/60.0)
            values.append(val)
        # Should converge without exceeding 100 (no overshoot)
        assert max(values) <= 100.0 + 1.0
        assert abs(values[-1] - 100.0) < 5.0

    def test_underdamped_overshoots(self):
        """Underdamped system should overshoot."""
        d = TemporalDamper(0.3, 2.0)
        d.feed(0.0)
        values = []
        for _ in range(60):
            val = d.feed(100.0, 1.0/60.0)
            values.append(val)
        # Should exceed 100 (overshoot)
        assert max(values) > 102.0

    def test_converges_to_target(self):
        d = TemporalDamper(1.0, 3.0)
        d.feed(0.0)
        for _ in range(120):
            d.feed(50.0, 1.0/60.0)
        assert abs(d.value - 50.0) < 1.0

    def test_reset(self):
        d = TemporalDamper(1.0, 3.0)
        d.feed(50.0)
        d.reset(25.0)
        assert d.value == 25.0
        assert d.velocity == 0.0
        assert d.initialised is True


class TestPosStabiliser:
    def test_first_frame(self):
        ps = PosStabiliser()
        sx, sy = ps.feed(100.0, 200.0)
        assert sx == 100.0
        assert sy == 200.0

    def test_smoothing_effect(self):
        ps = PosStabiliser(0.15, 0.85, 10.0)
        ps.feed(100.0, 200.0)

        # Large jump
        sx, sy = ps.feed(200.0, 300.0)
        # Should be smoothed toward old values
        assert sx < 200.0
        assert sy < 300.0
        assert sx > 100.0
        assert sy > 200.0

    def test_tracks_sustained_movement(self):
        ps = PosStabiliser(0.15, 0.85, 5.0)
        ps.feed(100.0, 200.0)

        # Move to new position and stay there
        for _ in range(30):
            ps.feed(300.0, 400.0)

        # Should converge to the new position
        assert abs(ps.smoothed_x - 300.0) < 10.0
        assert abs(ps.smoothed_y - 400.0) < 10.0
