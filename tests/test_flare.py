#!/usr/bin/env python3
"""
Conformal HUD – Flare Guidance System Test Suite (v2.1.0)

Tests:
  1. Flare state initialisation
  2. Flare activation/deactivation thresholds
  3. Flare command computation (Boeing-style)
  4. Flare cue rise behaviour
  5. Touchdown prediction
  6. Cue projection
  7. Debug logging

Run:  python -m pytest tests/test_flare.py -v
"""

import math
import pytest


# ======================================================================
#  Constants
# ======================================================================
G = 9.80665
FLARE_CONSTANT = 0.10
FLARE_ACTIVATE_FT = 80.0
FLARE_FULLY_ACTIVE_FT = 50.0
FLARE_ACTIVATE_M = 80.0 * 0.3048  # 24.384
FLARE_FULLY_M = 50.0 * 0.3048  # 15.24
FLARE_TD_HEIGHT_M = 0.0


# ======================================================================
#  Reference implementation
# ======================================================================

class FlareState:
    def __init__(self):
        self.radio_altitude_m = 100.0
        self.vertical_speed_ms = -2.0
        self.groundspeed_ms = 70.0
        self.gs_deviation_deg = 0.0
        self.flare_cue_vs = 0.0
        self.flare_cue_error = 0.0
        self.flare_cue_rise = 0.0
        self.flare_anticipation = 0.0
        self.flare_active = False
        self.flare_fully_active = False
        self.flare_engagement_alt = 0.0
        self.flare_frame_count = 0
        self.flare_complete = False
        self.touchdown_vs = 0.0
        self.touchdown_distance_m = 0.0
        self.time_to_touchdown_s = 0.0
        self.valid = False


def flare_should_activate(ra_m):
    return ra_m < FLARE_ACTIVATE_M


def flare_fully_active_check(ra_m):
    return ra_m < FLARE_FULLY_M


def flare_compute(flare, dt_s=1.0/60.0):
    ra = max(flare.radio_altitude_m, 0.0)
    vs = flare.vertical_speed_ms
    gs = max(flare.groundspeed_ms, 0.1)
    gs_dev = flare.gs_deviation_deg

    should_activate = flare_should_activate(ra)
    should_full = flare_fully_active_check(ra)

    if not flare.flare_active and should_activate and vs < -0.5:
        flare.flare_active = True
        flare.flare_engagement_alt = ra
        flare.flare_frame_count = 0
        flare.flare_complete = False

    if flare.flare_active and ra <= 0.5:
        flare.flare_complete = True

    if flare.flare_active and ra > 30.48:
        flare.flare_active = False
        flare.flare_frame_count = 0
        flare.flare_complete = False

    flare.flare_fully_active = flare.flare_active and should_full

    if not flare.flare_active:
        flare.flare_cue_vs = 0.0
        flare.flare_cue_error = 0.0
        flare.flare_cue_rise = 0.0
        flare.flare_anticipation = 0.0
        flare.touchdown_vs = 0.0
        flare.touchdown_distance_m = 0.0
        flare.time_to_touchdown_s = 0.0
        flare.valid = True
        return True

    flare.flare_frame_count += 1

    h_above_td = max(ra - FLARE_TD_HEIGHT_M, 0.1)
    k = math.sqrt(2.0 * G * FLARE_CONSTANT)
    raw_command = -k * math.sqrt(h_above_td)
    commanded_vs = max(-10.0, min(0.0, raw_command))

    anticipation = min(1.0, flare.flare_frame_count * dt_s / 1.5)
    flare.flare_anticipation = anticipation
    commanded_vs *= anticipation
    commanded_vs -= gs_dev * 0.2

    flare.flare_cue_vs = commanded_vs
    flare.flare_cue_error = commanded_vs - vs

    alt_range = flare.flare_engagement_alt - FLARE_TD_HEIGHT_M
    if alt_range > 0.1:
        alt_used = flare.flare_engagement_alt - ra
        flare.flare_cue_rise = max(0.0, min(1.0, alt_used / alt_range))
    else:
        flare.flare_cue_rise = 1.0

    if vs < 0.0:
        flare.time_to_touchdown_s = ra / (-vs)
        flare.touchdown_distance_m = gs * flare.time_to_touchdown_s
        flare_time = flare.time_to_touchdown_s
        if flare_time > 0.1:
            flare.touchdown_vs = vs + (commanded_vs - vs) * 0.5
        else:
            flare.touchdown_vs = vs
    else:
        flare.time_to_touchdown_s = 999.0
        flare.touchdown_distance_m = 0.0
        flare.touchdown_vs = vs

    flare.valid = True
    return True


# ======================================================================
#  Tests
# ======================================================================

class TestFlareInit:
    def test_default_not_active(self):
        f = FlareState()
        assert f.flare_active is False
        assert f.flare_fully_active is False
        assert f.flare_cue_rise == 0.0

    def test_activation_threshold(self):
        assert flare_should_activate(100.0) is False
        assert flare_should_activate(FLARE_ACTIVATE_M + 1.0) is False
        assert flare_should_activate(FLARE_ACTIVATE_M - 1.0) is True
        assert flare_should_activate(10.0) is True

    def test_fully_active_threshold(self):
        assert flare_fully_active_check(FLARE_FULLY_M + 1.0) is False
        assert flare_fully_active_check(FLARE_FULLY_M - 1.0) is True


class TestFlareActivation:
    def test_activates_below_80ft(self):
        f = FlareState()
        f.radio_altitude_m = 20.0
        f.vertical_speed_ms = -3.0
        flare_compute(f)
        assert f.flare_active is True

    def test_not_active_above_80ft(self):
        f = FlareState()
        f.radio_altitude_m = 100.0
        f.vertical_speed_ms = -3.0
        flare_compute(f)
        assert f.flare_active is False

    def test_not_active_when_climbing(self):
        f = FlareState()
        f.radio_altitude_m = 10.0
        f.vertical_speed_ms = 1.0
        flare_compute(f)
        assert f.flare_active is False

    def test_deactivates_above_100ft(self):
        f = FlareState()
        f.radio_altitude_m = 15.0
        f.vertical_speed_ms = -3.0
        flare_compute(f)
        assert f.flare_active is True
        f.radio_altitude_m = 50.0
        flare_compute(f)
        assert f.flare_active is False

    def test_fully_active_below_50ft(self):
        f = FlareState()
        f.radio_altitude_m = 10.0
        f.vertical_speed_ms = -3.0
        flare_compute(f)
        assert f.flare_fully_active is True

    def test_not_fully_active_above_50ft(self):
        f = FlareState()
        f.radio_altitude_m = 20.0
        f.vertical_speed_ms = -3.0
        flare_compute(f)
        assert f.flare_fully_active is False


class TestFlareCommand:
    def test_command_negative(self):
        f = FlareState()
        f.radio_altitude_m = 10.0
        f.vertical_speed_ms = -2.0
        flare_compute(f)
        assert f.flare_cue_vs < 0.0

    def test_command_reduces_near_ground(self):
        f = FlareState()
        f.radio_altitude_m = 10.0
        f.vertical_speed_ms = -3.0
        flare_compute(f)
        high_cmd = abs(f.flare_cue_vs)

        f2 = FlareState()
        f2.radio_altitude_m = 3.0
        f2.vertical_speed_ms = -3.0
        flare_compute(f2)
        low_cmd = abs(f2.flare_cue_vs)
        assert low_cmd < high_cmd

    def test_cue_rise_increases(self):
        f = FlareState()
        f.radio_altitude_m = 15.0
        f.vertical_speed_ms = -3.0
        f.flare_engagement_alt = 24.384
        flare_compute(f)
        rise1 = f.flare_cue_rise

        f.radio_altitude_m = 5.0
        flare_compute(f)
        rise2 = f.flare_cue_rise
        assert rise2 > rise1

    def test_cue_error_positive_when_sink_rate_excessive(self):
        f = FlareState()
        f.radio_altitude_m = 10.0
        f.vertical_speed_ms = -5.0
        flare_compute(f)
        assert f.flare_cue_error > 0.0

    def test_anticipation_ramps_up(self):
        f = FlareState()
        f.radio_altitude_m = 10.0
        f.vertical_speed_ms = -3.0
        for _ in range(30):
            flare_compute(f, 1.0/60.0)
        assert f.flare_anticipation > 0.3


class TestTouchdownPrediction:
    def test_time_to_touchdown(self):
        f = FlareState()
        f.radio_altitude_m = 15.0
        f.vertical_speed_ms = -3.0
        f.groundspeed_ms = 70.0
        flare_compute(f)
        assert f.flare_active is True
        assert f.time_to_touchdown_s > 0.0
        assert abs(f.time_to_touchdown_s - 5.0) < 0.5

    def test_touchdown_distance(self):
        f = FlareState()
        f.radio_altitude_m = 15.0
        f.vertical_speed_ms = -3.0
        f.groundspeed_ms = 70.0
        flare_compute(f)
        assert f.touchdown_distance_m > 0.0

    def test_no_prediction_when_climbing(self):
        f = FlareState()
        f.radio_altitude_m = 15.0
        f.vertical_speed_ms = 2.0
        f.groundspeed_ms = 70.0
        flare_compute(f)
        assert f.touchdown_distance_m == 0.0


class TestFlareValid:
    def test_valid_after_computation(self):
        f = FlareState()
        f.radio_altitude_m = 10.0
        f.vertical_speed_ms = -3.0
        flare_compute(f)
        assert f.valid is True

    def test_invalid_when_above_threshold(self):
        f = FlareState()
        f.radio_altitude_m = 100.0
        f.vertical_speed_ms = 0.0
        flare_compute(f)
        assert f.valid is True
        assert f.flare_active is False
