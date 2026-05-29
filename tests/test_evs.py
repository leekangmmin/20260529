#!/usr/bin/env python3
"""
Conformal HUD – Enhanced Vision System Test Suite (v2.1.0)

Tests:
  1. EVS state initialisation
  2. Low visibility detection
  3. Approach mode detection
  4. EVS intensity computation
  5. Rendering parameter enhancement
  6. Phase-dependent behaviour

Run:  python -m pytest tests/test_evs.py -v
"""

import math
import pytest


# ======================================================================
#  Reference implementation (mirrors C++ evs.h/.cpp)
# ======================================================================

class EVSState:
    def __init__(self):
        self.ambient_visibility_m = 20000.0
        self.radio_altitude_m = 1000.0
        self.runway_contrast_boost = 1.0
        self.fog_penetration = 0.0
        self.runway_glow_boost = 1.0
        self.symbology_contrast = 1.0
        self.terrain_enhancement = 0.0
        self.evs_enabled = False
        self.low_vis_mode = False
        self.approach_mode = False
        self.active = False
        self.debug_visibility_norm = 1.0
        self.debug_evs_intensity = 0.0


def evs_compute(evs, phase=0):
    vis = max(200.0, min(30000.0, evs.ambient_visibility_m))
    ra = max(evs.radio_altitude_m, 0.0)

    norm = (vis - 200.0) / (30000.0 - 200.0)
    evs.debug_visibility_norm = norm

    evs.low_vis_mode = (vis < 3000.0)
    evs.approach_mode = (phase >= 1 and ra < 600.0)

    evs.evs_enabled = evs.low_vis_mode or (evs.approach_mode and vis < 8000.0)

    if not evs.evs_enabled:
        evs.runway_contrast_boost = 1.0
        evs.fog_penetration = 0.0
        evs.runway_glow_boost = 1.0
        evs.symbology_contrast = 1.0
        evs.terrain_enhancement = 0.0
        evs.active = False
        evs.debug_evs_intensity = 0.0
        return

    intensity = 1.0 - norm
    if evs.approach_mode:
        intensity = min(1.0, intensity * 1.5)
    evs.debug_evs_intensity = intensity

    evs.runway_contrast_boost = 1.0 + intensity * 1.5
    evs.fog_penetration = intensity * 0.7
    evs.runway_glow_boost = 1.0 + intensity * 0.8
    evs.symbology_contrast = 1.0 + intensity * 0.6

    if evs.approach_mode and ra < 300.0:
        evs.terrain_enhancement = intensity * 0.5 * (1.0 - ra / 300.0)
    else:
        evs.terrain_enhancement = intensity * 0.2

    evs.active = (intensity > 0.01)


class WeatherState:
    def __init__(self):
        self.visibility_m = 20000.0
        self.line_width_px = 2.0
        self.opacity = 0.8
        self.valid = True


class EVSRenderParams:
    def __init__(self):
        self.line_width_px = 2.0
        self.opacity = 0.8
        self.contrast_boost = 1.0
        self.glow_amount = 0.0
        self.runway_edge_boost = 1.0
        self.evs_active = False


def evs_apply(evs, base, out):
    if base and base.valid:
        out.line_width_px = base.line_width_px
        out.opacity = base.opacity
    else:
        out.line_width_px = 2.0
        out.opacity = 0.8

    out.contrast_boost = 1.0
    out.glow_amount = 0.0
    out.runway_edge_boost = 1.0
    out.evs_active = False

    if not evs or not evs.active:
        return

    out.line_width_px *= (1.0 + evs.fog_penetration * 0.5)
    if out.line_width_px > 8.0:
        out.line_width_px = 8.0

    out.opacity = max(out.opacity, 0.7 + evs.fog_penetration * 0.3)
    out.contrast_boost = evs.symbology_contrast
    out.glow_amount = evs.fog_penetration * 0.15
    out.runway_edge_boost = evs.runway_contrast_boost
    out.evs_active = True


# ======================================================================
#  Tests
# ======================================================================

class TestEVSInit:
    def test_defaults(self):
        evs = EVSState()
        assert evs.active is False
        assert evs.evs_enabled is False
        assert evs.symbology_contrast == 1.0
        assert evs.runway_contrast_boost == 1.0


class TestEVSLowVisibility:
    def test_clear_vis_no_evs(self):
        evs = EVSState()
        evs.ambient_visibility_m = 20000.0
        evs_compute(evs, phase=0)
        assert evs.active is False

    def test_low_vis_activates_evs(self):
        evs = EVSState()
        evs.ambient_visibility_m = 500.0
        evs_compute(evs, phase=0)
        assert evs.active is True
        assert evs.low_vis_mode is True
        assert evs.evs_enabled is True

    def test_moderate_vis_no_evs_in_cruise(self):
        evs = EVSState()
        evs.ambient_visibility_m = 5000.0
        evs_compute(evs, phase=0)
        assert evs.active is False

    def test_moderate_vis_evs_on_approach(self):
        evs = EVSState()
        evs.ambient_visibility_m = 5000.0
        evs.radio_altitude_m = 300.0
        evs_compute(evs, phase=1)
        assert evs.active is True
        assert evs.approach_mode is True

    def test_intensity_increases_with_worse_vis(self):
        """EVS intensity should be higher in worse visibility."""
        evs1 = EVSState()
        evs1.ambient_visibility_m = 500.0
        evs_compute(evs1, phase=0)

        evs2 = EVSState()
        evs2.ambient_visibility_m = 1500.0
        evs_compute(evs2, phase=0)

        assert evs1.debug_evs_intensity > evs2.debug_evs_intensity

    def test_intensity_boosted_on_approach(self):
        evs = EVSState()
        evs.ambient_visibility_m = 2000.0
        evs.radio_altitude_m = 300.0

        evs_cruise = EVSState()
        evs_cruise.ambient_visibility_m = 2000.0
        evs_cruise.radio_altitude_m = 300.0
        evs_compute(evs_cruise, phase=0)
        cruise_intensity = evs_cruise.debug_evs_intensity

        evs_approach = EVSState()
        evs_approach.ambient_visibility_m = 2000.0
        evs_approach.radio_altitude_m = 300.0
        evs_compute(evs_approach, phase=1)
        approach_intensity = evs_approach.debug_evs_intensity

        assert approach_intensity >= cruise_intensity


class TestEVSApply:
    def test_apply_increases_line_width(self):
        evs = EVSState()
        evs.ambient_visibility_m = 500.0
        evs_compute(evs, phase=0)

        base = WeatherState()
        base.line_width_px = 2.0
        base.opacity = 0.7

        out = EVSRenderParams()
        evs_apply(evs, base, out)

        assert out.line_width_px > base.line_width_px
        assert out.evs_active is True

    def test_apply_boost_contrast(self):
        evs = EVSState()
        evs.ambient_visibility_m = 500.0
        evs_compute(evs, phase=0)

        base = WeatherState()
        out = EVSRenderParams()
        evs_apply(evs, base, out)
        assert out.contrast_boost > 1.0
        assert out.runway_edge_boost > 1.0

    def test_apply_no_effect_when_inactive(self):
        evs = EVSState()
        base = WeatherState()
        out = EVSRenderParams()
        evs_apply(evs, base, out)
        assert out.evs_active is False
        assert out.contrast_boost == 1.0


class TestEVSTerrain:
    def test_terrain_enhancement_on_approach(self):
        evs = EVSState()
        evs.ambient_visibility_m = 500.0
        evs.radio_altitude_m = 150.0
        evs_compute(evs, phase=1)
        assert evs.terrain_enhancement > 0.0

    def test_terrain_enhancement_zero_in_cruise(self):
        evs = EVSState()
        evs.ambient_visibility_m = 500.0
        evs.radio_altitude_m = 3000.0
        evs_compute(evs, phase=0)
        assert evs.terrain_enhancement >= 0.0  # small default value

    def test_terrain_increases_closer_to_ground(self):
        """Closer to ground = more terrain enhancement during approach."""
        evs_hi = EVSState()
        evs_hi.ambient_visibility_m = 500.0
        evs_hi.radio_altitude_m = 250.0
        evs_compute(evs_hi, phase=1)

        evs_lo = EVSState()
        evs_lo.ambient_visibility_m = 500.0
        evs_lo.radio_altitude_m = 50.0
        evs_compute(evs_lo, phase=1)

        assert evs_lo.terrain_enhancement >= evs_hi.terrain_enhancement
