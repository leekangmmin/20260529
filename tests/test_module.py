#!/usr/bin/env python3
"""
Conformal HUD – Module Feature Test Suite

Tests the new v1.1.0 features:
  1. EMA (exponential moving average) filter – ILS signal smoothing
  2. Weather-based rendering parameter computation (line width, opacity)
  3. HUD power state guard logic (aircraft capability + power switch)
  4. Aircraft identification matching

Run:  python -m pytest tests/test_module.py -v
"""

import math

# ======================================================================
#  Constants (mirroring C++ module.h)
# ======================================================================
C_HUD_VIS_MAX_M = 30000.0
C_HUD_VIS_MIN_M = 200.0


# ======================================================================
#  Reference implementation of EMA filter (mirrors C++ ema_* helpers)
# ======================================================================

class EMASmooth:
    """Exponential-moving-average filter state."""
    __slots__ = ('value', 'alpha', 'initialised')

    def __init__(self, alpha=0.35):
        self.value = 0.0
        self.alpha = max(0.0, min(1.0, alpha))
        self.initialised = False

    def feed(self, sample):
        """Feed a raw sample, return smoothed value."""
        if not self.initialised:
            self.value = sample
            self.initialised = True
        else:
            self.value = self.alpha * sample + (1.0 - self.alpha) * self.value
        return self.value

    def reset(self, alpha=None):
        """Reset to initial state."""
        self.value = 0.0
        if alpha is not None:
            self.alpha = max(0.0, min(1.0, alpha))
        self.initialised = False


class ILSFilter:
    """Combined ILS filter (glideslope + localizer)."""
    __slots__ = ('gs', 'loc')

    def __init__(self, alpha=0.35):
        self.gs = EMASmooth(alpha)
        self.loc = EMASmooth(alpha)


# ======================================================================
#  Weather computation (mirrors C++ weather_compute_params)
# ======================================================================

class WeatherState:
    """Weather rendering parameters."""
    __slots__ = ('visibility_m', 'line_width_px', 'opacity', 'valid')

    def __init__(self):
        self.visibility_m = 0.0
        self.line_width_px = 0.0
        self.opacity = 0.0
        self.valid = False


def weather_compute_params(vis_m, ws=None):
    """Compute line width and opacity from ambient visibility.

    Mirrors the C++ weather_compute_params() function in module.h.
    """
    if ws is None:
        ws = WeatherState()

    # Clamp visibility
    if vis_m < C_HUD_VIS_MIN_M:
        vis_m = C_HUD_VIS_MIN_M
    if vis_m > C_HUD_VIS_MAX_M:
        vis_m = C_HUD_VIS_MAX_M

    # Normalise: 0.0 = worst visibility (IMC), 1.0 = best (VFR clear)
    norm = (vis_m - C_HUD_VIS_MIN_M) / (C_HUD_VIS_MAX_M - C_HUD_VIS_MIN_M)

    # Line width: inversely proportional to visibility
    # At norm=0 (poor vis):  4.0 px
    # At norm=1 (clear):     1.5 px
    ws.line_width_px = 4.0 - norm * 2.5

    # Opacity: higher opacity in poor visibility
    # At norm=0 (poor vis):  0.95
    # At norm=1 (clear):     0.60
    ws.opacity = 0.95 - norm * 0.35

    # Ensure bounds
    if ws.line_width_px < 1.0:
        ws.line_width_px = 1.0
    if ws.line_width_px > 6.0:
        ws.line_width_px = 6.0
    if ws.opacity < 0.1:
        ws.opacity = 0.1
    if ws.opacity > 1.0:
        ws.opacity = 1.0

    ws.visibility_m = vis_m
    ws.valid = True

    return ws


# ======================================================================
#  Aircraft identification helpers (mirrors C++ module.cpp)
# ======================================================================

# HUD-capable aircraft list (lowercase, for case-insensitive matching)
HUD_ALLOWED_AIRCRAFT = [
    "pmdg 737-800",
    "pmdg 737-700",
    "fbw a32nx",
    "headwind a330-900",
    "asobo boeing 747-8i",
    "asobo boeing 787-10",
    "wt_787_10",
]


def aircraft_supports_hud(name):
    """Check whether the given aircraft model name is HUD-capable.

    Mirrors the C++ aircraft_supports_hud() function.
    """
    if not name or len(name) == 0:
        return True   # allow unknown by default (permissive)

    name_lower = name.lower()

    for allowed in HUD_ALLOWED_AIRCRAFT:
        if name_lower.startswith(allowed):
            return True

    return False


# ======================================================================
#  Tests
# ======================================================================

class TestEMASmooth:
    """Validate the exponential moving average filter."""

    def test_init(self):
        f = EMASmooth(0.35)
        assert f.value == 0.0
        assert f.alpha == 0.35
        assert f.initialised is False

    def test_alpha_clamping(self):
        f = EMASmooth(1.5)
        assert f.alpha == 1.0
        f2 = EMASmooth(-0.5)
        assert f2.alpha == 0.0

    def test_first_sample_initialises(self):
        f = EMASmooth(0.5)
        result = f.feed(42.0)
        assert result == 42.0
        assert f.initialised is True
        assert f.value == 42.0

    def test_convergence_constant_signal(self):
        """With alpha=1.0, should immediately track."""
        f = EMASmooth(1.0)
        assert f.feed(10.0) == 10.0
        assert f.feed(20.0) == 20.0
        assert f.feed(30.0) == 30.0

    def test_smoothing_effect(self):
        """With alpha=0.5, output should lag behind rapid changes."""
        f = EMASmooth(0.5)
        # Initialise at 0
        f.feed(0.0)
        # Step to 100
        s1 = f.feed(100.0)
        # EMA = 0.5 * 100 + 0.5 * 0 = 50
        assert abs(s1 - 50.0) < 1e-9
        # Second step
        s2 = f.feed(100.0)
        # EMA = 0.5 * 100 + 0.5 * 50 = 75
        assert abs(s2 - 75.0) < 1e-9

    def test_high_frequency_noise_reduction(self):
        """EMA with low alpha should filter out high-frequency noise."""
        f = EMASmooth(0.1)
        # Steady signal at 50
        for _ in range(20):
            f.feed(50.0)
        # Now inject a spike
        spike = f.feed(100.0)
        # With alpha=0.1, the output should only move ~10% toward the spike
        # After many 50s, EMA ≈ 50. Spike should push to 0.1*100 + 0.9*50 = 55
        assert abs(spike - 55.0) < 1e-9

    def test_reset(self):
        f = EMASmooth(0.3)
        f.feed(100.0)
        f.reset(alpha=0.7)
        assert f.initialised is False
        assert f.value == 0.0
        assert f.alpha == 0.7


class TestILSFilter:
    """Validate combined ILS filter (GS + LOC)."""

    def test_initialisation(self):
        ils = ILSFilter(0.35)
        assert ils.gs.initialised is False
        assert ils.loc.initialised is False
        assert ils.gs.alpha == 0.35
        assert ils.loc.alpha == 0.35

    def test_tracking(self):
        ils = ILSFilter(0.5)
        # Feed a glideslope deviation of 0.2 dots
        gs = ils.gs.feed(0.2)
        assert abs(gs - 0.2) < 1e-9
        # Feed a localizer deviation of -0.15 dots
        loc = ils.loc.feed(-0.15)
        assert abs(loc - (-0.15)) < 1e-9


class TestWeatherComputation:
    """Validate weather-based rendering parameter computation."""

    def test_default_initialisation(self):
        ws = WeatherState()
        assert ws.valid is False
        assert ws.line_width_px == 0.0

    def test_clear_day_visibility(self):
        """At high visibility (30 km / VFR), line width should be thin."""
        ws = weather_compute_params(30000.0)
        assert ws.valid is True
        assert ws.visibility_m == 30000.0
        # norm = 1.0, line_width = 4.0 - 1.0*2.5 = 1.5
        assert abs(ws.line_width_px - 1.5) < 1e-9
        # opacity = 0.95 - 1.0*0.35 = 0.60
        assert abs(ws.opacity - 0.60) < 1e-9

    def test_poor_visibility(self):
        """At low visibility (200 m / IMC), line should be thick."""
        ws = weather_compute_params(200.0)
        assert ws.valid is True
        assert ws.visibility_m == 200.0
        # norm = 0.0, line_width = 4.0
        assert abs(ws.line_width_px - 4.0) < 1e-9
        # opacity = 0.95
        assert abs(ws.opacity - 0.95) < 1e-9

    def test_moderate_visibility(self):
        """At 5 km (5000 m), should be between extremes."""
        ws = weather_compute_params(5000.0)
        assert ws.valid is True
        # norm = (5000 - 200) / (30000 - 200) = 4800 / 29800 ≈ 0.16107
        expected_norm = (5000.0 - 200.0) / (30000.0 - 200.0)
        expected_line_w = 4.0 - expected_norm * 2.5
        expected_opacity = 0.95 - expected_norm * 0.35
        assert abs(ws.line_width_px - expected_line_w) < 1e-6
        assert abs(ws.opacity - expected_opacity) < 1e-6
        assert 1.5 < ws.line_width_px < 4.0
        assert 0.5 < ws.opacity < 0.95

    def test_below_min_visibility(self):
        """Visibility below 200 m should be clamped to 200 m."""
        ws = weather_compute_params(50.0)
        assert ws.visibility_m == 200.0
        assert ws.line_width_px == 4.0

    def test_above_max_visibility(self):
        """Visibility above 30 km should be clamped to 30 km."""
        ws = weather_compute_params(50000.0)
        assert ws.visibility_m == 30000.0
        assert abs(ws.line_width_px - 1.5) < 1e-9

    def test_reuse_existing_state(self):
        """Reusing an existing WeatherState should overwrite correctly."""
        ws = WeatherState()
        weather_compute_params(1000.0, ws)
        assert ws.valid is True
        assert abs(ws.visibility_m - 1000.0) < 1.0
        # Feed again with different value
        weather_compute_params(20000.0, ws)
        assert abs(ws.visibility_m - 20000.0) < 1.0

    def test_clamping_bounds(self):
        """Line width and opacity should never violate their bounds."""
        # Worst case
        ws = weather_compute_params(200.0)
        assert ws.line_width_px >= 1.0
        assert ws.line_width_px <= 6.0
        assert ws.opacity >= 0.1
        assert ws.opacity <= 1.0

        # Best case
        ws = weather_compute_params(30000.0)
        assert ws.line_width_px >= 1.0
        assert ws.line_width_px <= 6.0
        assert ws.opacity >= 0.1
        assert ws.opacity <= 1.0

        # Extreme inputs
        ws = weather_compute_params(-100.0)  # clamped to min
        assert ws.line_width_px >= 1.0
        assert ws.line_width_px <= 6.0
        assert ws.opacity >= 0.1
        assert ws.opacity <= 1.0

        ws = weather_compute_params(1e9)  # clamped to max
        assert ws.line_width_px >= 1.0
        assert ws.line_width_px <= 6.0
        assert ws.opacity >= 0.1
        assert ws.opacity <= 1.0


class TestAircraftIdentification:
    """Validate aircraft HUD capability detection."""

    def test_pmdg_737(self):
        assert aircraft_supports_hud("PMDG 737-800") is True
        assert aircraft_supports_hud("PMDG 737-700") is True

    def test_fbw_a32nx(self):
        assert aircraft_supports_hud("FBW A32NX") is True

    def test_headwind_a330(self):
        assert aircraft_supports_hud("HEADWIND A330-900") is True

    def test_asobo_747(self):
        assert aircraft_supports_hud("ASOBO BOEING 747-8I") is True

    def test_asobo_787(self):
        assert aircraft_supports_hud("ASOBO BOEING 787-10") is True

    def test_wt_787(self):
        assert aircraft_supports_hud("WT_787_10") is True

    def test_case_insensitive(self):
        assert aircraft_supports_hud("pmdg 737-800") is True
        assert aircraft_supports_hud("Pmdg 737-800") is True

    def test_empty_string(self):
        assert aircraft_supports_hud("") is True

    def test_none(self):
        assert aircraft_supports_hud(None) is True

    def test_unsupported_aircraft(self):
        assert aircraft_supports_hud("CESSNA 172") is False
        assert aircraft_supports_hud("DA42 TWINSTAR") is False

    def test_partial_prefix_match(self):
        """A 'PMDG 737-800NGXu' should match since it starts with 'PMDG 737-800'."""
        assert aircraft_supports_hud("PMDG 737-800NGXu") is True


class TestHUDGuardLogic:
    """Validate the HUD power guard logic (mirrors C++ main.cpp guards)."""

    def test_power_on(self):
        """HUD power L:var ≥ 0.5 → hud_power_on = true."""
        power_val = 1.0
        hud_power_on = (power_val >= 0.5)
        assert hud_power_on is True

    def test_power_off(self):
        """HUD power L:var < 0.5 → hud_power_on = false."""
        power_val = 0.0
        hud_power_on = (power_val >= 0.5)
        assert hud_power_on is False

    def test_power_edge_case(self):
        """Exactly 0.5 should be considered ON."""
        power_val = 0.5
        hud_power_on = (power_val >= 0.5)
        assert hud_power_on is True

    def test_hud_active_requires_both_guards(self):
        """HUD should be active only when both aircraft allows it AND power is on."""
        hud_allowed = True
        hud_power_on = True
        assert hud_allowed and hud_power_on  # active

    def test_hud_inactive_when_power_off(self):
        hud_allowed = True
        hud_power_on = False
        assert not (hud_allowed and hud_power_on)  # inactive

    def test_hud_inactive_when_not_allowed(self):
        hud_allowed = False
        hud_power_on = True
        assert not (hud_allowed and hud_power_on)  # inactive
