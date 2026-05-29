#!/usr/bin/env python3
"""
Conformal HUD – Advanced Symbology Test Suite (v2.1.0)

Tests:
  1. Acceleration caret computation
  2. Energy trend vector
  3. Flare anticipation bracket
  4. Touchdown predictor
  5. Velocity trend cue

Run:  python -m pytest tests/test_advanced_symbology.py -v
"""

import math
import pytest


# ======================================================================
#  Reference implementations
# ======================================================================

class AccelCaret:
    def __init__(self):
        self.ias_ms = 70.0
        self.tas_ms = 75.0
        self.gs_ms = 70.0
        self.accel_ms2 = 0.0
        self.target_speed_ms = 70.0
        self.speed_error_ms = 0.0
        self.accel_dots = 0.0
        self.screen_x = 0.0
        self.screen_y = 0.0
        self.valid = False
        self.on_screen = False


def accel_compute(ac, ref_x=400.0, ref_y=500.0):
    accel = ac.accel_ms2
    ac.speed_error_ms = ac.ias_ms - ac.target_speed_ms
    ac.accel_dots = max(-3.0, min(3.0, accel / 0.49))
    ac.screen_x = ref_x + ac.accel_dots * 20.0
    ac.screen_y = ref_y
    ac.on_screen = True
    ac.valid = True


class EnergyTrend:
    def __init__(self):
        self.tas_ms = 75.0
        self.vs_ms = 0.0
        self.accel_ms2 = 0.0
        self.specific_energy_rate = 0.0
        self.energy_rate_dots = 0.0
        self.vector_length_px = 0.0
        self.screen_x = 0.0
        self.screen_y = 0.0
        self.valid = False
        self.on_screen = False


def energy_compute(et, ref_x=400.0, ref_y=500.0):
    V = max(et.tas_ms, 1.0)
    V_dot = et.accel_ms2
    h_dot = et.vs_ms
    g = 9.80665

    et.specific_energy_rate = V * V_dot + g * h_dot
    et.energy_rate_dots = max(-3.0, min(3.0, et.specific_energy_rate / 50.0))
    et.screen_x = ref_x
    et.screen_y = ref_y - et.energy_rate_dots * 12.0
    et.on_screen = True
    et.valid = True


class FlareBracket:
    def __init__(self):
        self.radio_altitude_m = 50.0
        self.vertical_speed_ms = -3.0
        self.groundspeed_ms = 70.0
        self.flare_initiate_alt_m = 10.0
        self.flare_altitude_error = 0.0
        self.bracket_visibility = 0.0
        self.screen_x = 0.0
        self.screen_y = 0.0
        self.bracket_size_px = 30.0
        self.should_draw = False
        self.valid = False


def flare_bracket_compute(fb, screen_w=1024, screen_h=800, ref_y=450.0):
    ra = max(fb.radio_altitude_m, 0.0)
    vs = fb.vertical_speed_ms
    gs = max(fb.groundspeed_ms, 1.0)

    sink_rate = max(-vs, 0.1)
    flare_alt = 6.0 + sink_rate * 3.0 + gs * 0.05
    fb.flare_initiate_alt_m = max(4.0, min(25.0, flare_alt))
    fb.flare_altitude_error = ra - fb.flare_initiate_alt_m

    error_ft = fb.flare_altitude_error / 0.3048
    if error_ft > 10.0:
        fb.bracket_visibility = 0.0
    elif error_ft < -5.0:
        fb.bracket_visibility = 0.0
    else:
        fb.bracket_visibility = 1.0 - abs(error_ft) / 10.0
        fb.bracket_visibility = max(0.0, min(1.0, fb.bracket_visibility))
        fb.bracket_visibility *= fb.bracket_visibility

    fb.screen_x = screen_w / 2
    fb.screen_y = ref_y
    fb.bracket_size_px = min(50.0, 20.0 + gs * 0.15)

    fb.should_draw = (fb.bracket_visibility > 0.01 and
                      ra < 40.0 and ra > 1.0 and vs < 0.0)
    fb.valid = True


class TDPredictor:
    def __init__(self):
        self.groundspeed_ms = 70.0
        self.vertical_speed_ms = -3.0
        self.radio_altitude_m = 100.0
        self.predicted_range_m = 0.0
        self.screen_x = 0.0
        self.screen_y = 0.0
        self.time_to_touchdown_s = 0.0
        self.confidence = 0.0
        self.valid = False
        self.on_screen = False


def td_predictor_compute(td):
    gs = max(td.groundspeed_ms, 0.1)
    vs = td.vertical_speed_ms
    ra = max(td.radio_altitude_m, 0.0)

    if vs >= 0.0:
        return

    sink_rate = -vs
    if sink_rate < 0.1:
        return

    td.time_to_touchdown_s = ra / sink_rate
    td.predicted_range_m = gs * td.time_to_touchdown_s
    td.confidence = max(0.1, min(0.95, 1.0 - ra / 300.0))
    td.screen_x = 512.0
    td.screen_y = 400.0 - td.confidence * 50.0
    td.on_screen = True
    td.valid = True


class VelocityTrend:
    def __init__(self):
        self.ias_ms = 70.0
        self.accel_ms2 = 0.0
        self.target_speed_ms = 70.0
        self.trend_direction = 0.0
        self.trend_magnitude_dots = 0.0
        self.screen_x = 0.0
        self.screen_y = 0.0
        self.valid = False
        self.on_screen = False


def velocity_trend_compute(vt, ref_x=400.0, ref_y=500.0):
    accel = vt.accel_ms2
    if abs(accel) < 0.1:
        vt.trend_direction = 0.0
        vt.trend_magnitude_dots = 0.0
    else:
        vt.trend_direction = 1.0 if accel > 0.0 else -1.0
        vt.trend_magnitude_dots = min(3.0, abs(accel) / 0.5)

    vt.screen_x = ref_x + 30.0
    vt.screen_y = ref_y
    vt.on_screen = True
    vt.valid = True


# ======================================================================
#  Tests
# ======================================================================

class TestAccelCaret:
    def test_zero_accel(self):
        ac = AccelCaret()
        ac.accel_ms2 = 0.0
        accel_compute(ac)
        assert abs(ac.accel_dots) < 0.01

    def test_positive_accel(self):
        ac = AccelCaret()
        ac.accel_ms2 = 2.0
        accel_compute(ac)
        assert ac.accel_dots > 0.0

    def test_negative_accel(self):
        ac = AccelCaret()
        ac.accel_ms2 = -1.0
        accel_compute(ac)
        assert ac.accel_dots < 0.0

    def test_speed_error(self):
        ac = AccelCaret()
        ac.ias_ms = 80.0
        ac.target_speed_ms = 70.0
        accel_compute(ac)
        assert ac.speed_error_ms == 10.0

    def test_dots_clamped(self):
        ac = AccelCaret()
        ac.accel_ms2 = 10.0
        accel_compute(ac)
        assert abs(ac.accel_dots) <= 3.0

    def test_on_screen(self):
        ac = AccelCaret()
        accel_compute(ac)
        assert ac.on_screen is True
        assert ac.valid is True


class TestEnergyTrend:
    def test_zero_energy(self):
        et = EnergyTrend()
        energy_compute(et)
        assert abs(et.specific_energy_rate) < 0.01

    def test_climbing_increases_energy(self):
        et = EnergyTrend()
        et.vs_ms = 5.0
        energy_compute(et)
        assert et.specific_energy_rate > 0.0

    def test_accelerating_increases_energy(self):
        et = EnergyTrend()
        et.accel_ms2 = 2.0
        energy_compute(et)
        assert et.specific_energy_rate > 0.0

    def test_descending_decreases_energy(self):
        et = EnergyTrend()
        et.vs_ms = -3.0
        energy_compute(et)
        assert et.specific_energy_rate < 0.0

    def test_dots_clamped(self):
        et = EnergyTrend()
        et.vs_ms = -50.0
        energy_compute(et)
        assert abs(et.energy_rate_dots) <= 3.0


class TestFlareBracket:
    def test_not_drawn_at_high_alt(self):
        fb = FlareBracket()
        fb.radio_altitude_m = 100.0
        fb.vertical_speed_ms = -3.0
        flare_bracket_compute(fb)
        assert fb.should_draw is False

    def test_drawn_near_flare_alt(self):
        fb = FlareBracket()
        # Compute the expected initiation altitude first
        sink_rate = max(-(-3.0), 0.1)
        gs = 70.0
        expected_flare_alt = 6.0 + sink_rate * 3.0 + gs * 0.05
        expected_flare_alt = max(4.0, min(25.0, expected_flare_alt))

        fb.radio_altitude_m = expected_flare_alt  # exactly at initiation
        fb.vertical_speed_ms = -3.0
        flare_bracket_compute(fb)
        assert fb.should_draw is True
        assert fb.bracket_visibility > 0.5  # should be highly visible at initiation

    def test_not_drawn_when_climbing(self):
        fb = FlareBracket()
        fb.radio_altitude_m = 15.0
        fb.vertical_speed_ms = 2.0  # climbing
        flare_bracket_compute(fb)
        assert fb.should_draw is False

    def test_visibility_peaks_at_initiation(self):
        """Bracket visibility should be highest at initiation altitude."""
        # Compute expected initiation
        sink_rate = max(-(-3.0), 0.1)
        gs = 70.0
        init_alt = max(4.0, min(25.0, 6.0 + sink_rate * 3.0 + gs * 0.05))

        fb = FlareBracket()
        fb.vertical_speed_ms = -3.0
        fb.radio_altitude_m = init_alt
        flare_bracket_compute(fb)
        assert fb.bracket_visibility > 0.9  # ~1.0 at zero error

    def test_bracket_size_scales(self):
        fb = FlareBracket()
        fb.groundspeed_ms = 150.0  # fast
        flare_bracket_compute(fb)
        size_fast = fb.bracket_size_px

        fb2 = FlareBracket()
        fb2.groundspeed_ms = 50.0  # slow
        flare_bracket_compute(fb2)
        size_slow = fb2.bracket_size_px
        assert size_fast >= size_slow


class TestTDPredictor:
    def test_valid_descending(self):
        td = TDPredictor()
        td.vertical_speed_ms = -3.0
        td.radio_altitude_m = 100.0
        td_predictor_compute(td)
        assert td.valid is True
        assert td.on_screen is True

    def test_invalid_climbing(self):
        td = TDPredictor()
        td.vertical_speed_ms = 3.0  # climbing
        td.radio_altitude_m = 100.0
        td_predictor_compute(td)
        assert td.valid is False

    def test_range_computed(self):
        td = TDPredictor()
        td.vertical_speed_ms = -3.0
        td.radio_altitude_m = 60.0
        td.groundspeed_ms = 70.0
        td_predictor_compute(td)
        # Time to TD = 60/3 = 20 sec, range = 70 * 20 = 1400 m
        assert abs(td.predicted_range_m - 1400.0) < 50.0
        assert abs(td.time_to_touchdown_s - 20.0) < 1.0

    def test_confidence_increases_lower(self):
        td_high = TDPredictor()
        td_high.vertical_speed_ms = -3.0
        td_high.radio_altitude_m = 200.0
        td_predictor_compute(td_high)

        td_low = TDPredictor()
        td_low.vertical_speed_ms = -3.0
        td_low.radio_altitude_m = 50.0
        td_predictor_compute(td_low)

        assert td_low.confidence > td_high.confidence

    def test_zero_sink_rate_invalid(self):
        td = TDPredictor()
        td.vertical_speed_ms = -0.05  # nearly zero
        td.radio_altitude_m = 100.0
        td_predictor_compute(td)
        assert td.valid is False


class TestVelocityTrend:
    def test_steady_no_trend(self):
        vt = VelocityTrend()
        vt.accel_ms2 = 0.0
        velocity_trend_compute(vt)
        assert vt.trend_direction == 0.0
        assert vt.trend_magnitude_dots == 0.0

    def test_accelerating_positive(self):
        vt = VelocityTrend()
        vt.accel_ms2 = 1.0
        velocity_trend_compute(vt)
        assert vt.trend_direction == 1.0
        assert vt.trend_magnitude_dots > 0.0

    def test_decelerating_negative(self):
        vt = VelocityTrend()
        vt.accel_ms2 = -1.0
        velocity_trend_compute(vt)
        assert vt.trend_direction == -1.0
        assert vt.trend_magnitude_dots > 0.0

    def test_magnitude_clamped(self):
        vt = VelocityTrend()
        vt.accel_ms2 = 10.0
        velocity_trend_compute(vt)
        assert vt.trend_magnitude_dots <= 3.0
        assert vt.trend_direction == 1.0

    def test_valid(self):
        vt = VelocityTrend()
        vt.accel_ms2 = 2.0
        velocity_trend_compute(vt)
        assert vt.valid is True
        assert vt.on_screen is True
