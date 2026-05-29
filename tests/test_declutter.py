#!/usr/bin/env python3
"""
Conformal HUD – Declutter Test Suite (v2.4.0)

Tests:
  1. Declutter initialisation
  2. Phase-based priority computation
  3. Symbol suppression in different phases
  4. Low-visibility enhancement
  5. Per-symbol alpha/dimming output

Run:  python -m pytest tests/test_declutter.py -v
"""

import math
import pytest


# ======================================================================
#  Reference implementation
# ======================================================================

SYM_PRIO_CRITICAL = 100
SYM_PRIO_HIGH = 80
SYM_PRIO_NORMAL = 60
SYM_PRIO_LOW = 40
SYM_PRIO_BACKGROUND = 20

SYM_TYPE_FPV = 0
SYM_TYPE_HORIZON = 1
SYM_TYPE_PITCH_LADDER = 2
SYM_TYPE_RUNWAY_BOX = 3
SYM_TYPE_LOCALIZER_BAR = 4
SYM_TYPE_GLIDESLOPE_BAR = 5
SYM_TYPE_DRIFT_CUE = 6
SYM_TYPE_CENTERLINE = 7
SYM_TYPE_ILS_CROSSHAIR = 8
SYM_TYPE_FLARE_CUE = 9
SYM_TYPE_TOUCHDOWN_ZONE = 10
SYM_TYPE_ACCEL_CARET = 11
SYM_TYPE_ENERGY_TREND = 12
SYM_TYPE_FLARE_BRACKET = 13
SYM_TYPE_TD_PREDICTOR = 14
SYM_TYPE_VELOCITY_TREND = 15
SYM_TYPE_ROLLOUT_CENTER = 16
SYM_TYPE_ROLLOUT_DECEL = 17
SYM_TYPE_SPEED_TAPE = 18
SYM_TYPE_ALTITUDE_TAPE = 19
SYM_TYPE_HEADING_SCALE = 20
SYM_TYPE_COUNT = 21

PHASE_CRUISE = 0
PHASE_APPROACH = 1
PHASE_FLARE = 2
PHASE_ROLLOUT = 3
PHASE_TAXI = 4


def declutter_build_priority_table():
    """Build the phase-based priority table."""
    table = [[SYM_PRIO_NORMAL] * SYM_TYPE_COUNT for _ in range(5)]

    # CRUISE
    table[PHASE_CRUISE][SYM_TYPE_FPV] = SYM_PRIO_CRITICAL
    table[PHASE_CRUISE][SYM_TYPE_HORIZON] = SYM_PRIO_HIGH
    table[PHASE_CRUISE][SYM_TYPE_PITCH_LADDER] = SYM_PRIO_HIGH
    table[PHASE_CRUISE][SYM_TYPE_SPEED_TAPE] = SYM_PRIO_HIGH
    table[PHASE_CRUISE][SYM_TYPE_ALTITUDE_TAPE] = SYM_PRIO_HIGH

    # APPROACH
    table[PHASE_APPROACH][SYM_TYPE_FPV] = SYM_PRIO_CRITICAL
    table[PHASE_APPROACH][SYM_TYPE_RUNWAY_BOX] = SYM_PRIO_CRITICAL
    table[PHASE_APPROACH][SYM_TYPE_LOCALIZER_BAR] = SYM_PRIO_CRITICAL
    table[PHASE_APPROACH][SYM_TYPE_GLIDESLOPE_BAR] = SYM_PRIO_CRITICAL
    table[PHASE_APPROACH][SYM_TYPE_HORIZON] = SYM_PRIO_HIGH
    table[PHASE_APPROACH][SYM_TYPE_PITCH_LADDER] = SYM_PRIO_HIGH
    table[PHASE_APPROACH][SYM_TYPE_CENTERLINE] = SYM_PRIO_HIGH
    table[PHASE_APPROACH][SYM_TYPE_TOUCHDOWN_ZONE] = SYM_PRIO_HIGH
    table[PHASE_APPROACH][SYM_TYPE_HEADING_SCALE] = SYM_PRIO_BACKGROUND

    # FLARE
    table[PHASE_FLARE][SYM_TYPE_FLARE_CUE] = SYM_PRIO_CRITICAL
    table[PHASE_FLARE][SYM_TYPE_FPV] = SYM_PRIO_HIGH
    table[PHASE_FLARE][SYM_TYPE_RUNWAY_BOX] = SYM_PRIO_HIGH
    table[PHASE_FLARE][SYM_TYPE_TOUCHDOWN_ZONE] = SYM_PRIO_HIGH
    table[PHASE_FLARE][SYM_TYPE_FLARE_BRACKET] = SYM_PRIO_HIGH
    table[PHASE_FLARE][SYM_TYPE_PITCH_LADDER] = SYM_PRIO_LOW
    table[PHASE_FLARE][SYM_TYPE_LOCALIZER_BAR] = SYM_PRIO_LOW
    table[PHASE_FLARE][SYM_TYPE_GLIDESLOPE_BAR] = SYM_PRIO_LOW
    table[PHASE_FLARE][SYM_TYPE_ACCEL_CARET] = SYM_PRIO_BACKGROUND
    table[PHASE_FLARE][SYM_TYPE_ENERGY_TREND] = SYM_PRIO_BACKGROUND
    table[PHASE_FLARE][SYM_TYPE_DRIFT_CUE] = SYM_PRIO_BACKGROUND
    table[PHASE_FLARE][SYM_TYPE_ILS_CROSSHAIR] = SYM_PRIO_BACKGROUND
    table[PHASE_FLARE][SYM_TYPE_VELOCITY_TREND] = SYM_PRIO_BACKGROUND
    table[PHASE_FLARE][SYM_TYPE_TD_PREDICTOR] = SYM_PRIO_BACKGROUND

    # ROLLOUT
    table[PHASE_ROLLOUT][SYM_TYPE_ROLLOUT_CENTER] = SYM_PRIO_CRITICAL
    table[PHASE_ROLLOUT][SYM_TYPE_ROLLOUT_DECEL] = SYM_PRIO_HIGH
    table[PHASE_ROLLOUT][SYM_TYPE_FPV] = SYM_PRIO_HIGH
    table[PHASE_ROLLOUT][SYM_TYPE_RUNWAY_BOX] = SYM_PRIO_HIGH
    table[PHASE_ROLLOUT][SYM_TYPE_CENTERLINE] = SYM_PRIO_HIGH
    table[PHASE_ROLLOUT][SYM_TYPE_PITCH_LADDER] = SYM_PRIO_LOW
    table[PHASE_ROLLOUT][SYM_TYPE_LOCALIZER_BAR] = SYM_PRIO_BACKGROUND
    table[PHASE_ROLLOUT][SYM_TYPE_GLIDESLOPE_BAR] = SYM_PRIO_BACKGROUND
    table[PHASE_ROLLOUT][SYM_TYPE_FLARE_CUE] = SYM_PRIO_BACKGROUND
    table[PHASE_ROLLOUT][SYM_TYPE_TOUCHDOWN_ZONE] = SYM_PRIO_BACKGROUND
    table[PHASE_ROLLOUT][SYM_TYPE_FLARE_BRACKET] = SYM_PRIO_BACKGROUND

    # TAXI - minimal
    table[PHASE_TAXI][SYM_TYPE_RUNWAY_BOX] = SYM_PRIO_HIGH
    for s in range(SYM_TYPE_COUNT):
        if table[PHASE_TAXI][s] >= SYM_PRIO_NORMAL:
            continue
        table[PHASE_TAXI][s] = SYM_PRIO_BACKGROUND

    return table


class SymPriorityState:
    def __init__(self):
        self.base_priority = SYM_PRIO_NORMAL
        self.phase_modifier = 1.0
        self.visibility_modifier = 1.0
        self.alpha = 1.0
        self.dimming_factor = 1.0
        self.suppressed = False


class DeclutterState:
    def __init__(self):
        self.current_phase = PHASE_CRUISE
        self.symbols = [SymPriorityState() for _ in range(SYM_TYPE_COUNT)]
        self.phase_base_priorities = declutter_build_priority_table()
        self.low_visibility = False
        self.visibility_factor = 1.0
        self.global_dimming = 1.0
        self.visible_symbol_count = SYM_TYPE_COUNT
        self.active = False
        self.debug_force_all = False


def declutter_compute(ds, phase, low_visibility, visibility_m):
    ds.current_phase = phase
    vis = max(200.0, min(10000.0, visibility_m))
    ds.visibility_factor = (vis - 200.0) / (10000.0 - 200.0)
    ds.low_visibility = low_visibility

    p = phase
    visible_count = 0

    for s in range(SYM_TYPE_COUNT):
        base_prio = ds.phase_base_priorities[p][s]

        # Phase modifier
        phase_mod = 1.0
        if s == SYM_TYPE_FLARE_CUE and phase == PHASE_FLARE:
            phase_mod = 1.5
        elif s == SYM_TYPE_ROLLOUT_CENTER and phase == PHASE_ROLLOUT:
            phase_mod = 1.5
        elif s in (SYM_TYPE_FPV,) and phase in (PHASE_APPROACH, PHASE_FLARE):
            phase_mod = 1.3
        elif s == SYM_TYPE_RUNWAY_BOX and phase == PHASE_APPROACH:
            phase_mod = 1.2

        # Visibility modifier
        vis_mod = 1.0
        if low_visibility:
            if base_prio >= SYM_PRIO_HIGH:
                vis_mod = 1.2
            elif base_prio <= SYM_PRIO_LOW:
                vis_mod = 0.6

        ds.symbols[s].phase_modifier = max(0.0, min(2.0, phase_mod))
        ds.symbols[s].visibility_modifier = max(0.0, min(2.0, vis_mod))

        effective_priority = base_prio * phase_mod * vis_mod

        if effective_priority >= SYM_PRIO_CRITICAL:
            ds.symbols[s].alpha = 1.0
            ds.symbols[s].dimming_factor = 1.0
            ds.symbols[s].suppressed = False
        elif effective_priority >= SYM_PRIO_HIGH:
            ds.symbols[s].alpha = 0.9
            ds.symbols[s].dimming_factor = 0.9
            ds.symbols[s].suppressed = False
        elif effective_priority >= SYM_PRIO_NORMAL:
            ds.symbols[s].alpha = 0.7
            ds.symbols[s].dimming_factor = 0.8
            ds.symbols[s].suppressed = False
        elif effective_priority >= SYM_PRIO_LOW:
            ds.symbols[s].alpha = 0.4
            ds.symbols[s].dimming_factor = 0.6
            ds.symbols[s].suppressed = False
        else:
            ds.symbols[s].alpha = 0.0
            ds.symbols[s].dimming_factor = 0.0
            ds.symbols[s].suppressed = True

        if not ds.symbols[s].suppressed:
            visible_count += 1

    ds.visible_symbol_count = visible_count
    ds.active = ds.visible_symbol_count < SYM_TYPE_COUNT


# ======================================================================
#  Tests
# ======================================================================

class TestDeclutterInit:
    def test_default_phase_cruise(self):
        ds = DeclutterState()
        assert ds.current_phase == PHASE_CRUISE
        assert ds.active is False

    def test_all_symbols_visible_initially(self):
        ds = DeclutterState()
        assert ds.visible_symbol_count == SYM_TYPE_COUNT


class TestDeclutterApproach:
    def test_critical_symbols_full_in_approach(self):
        ds = DeclutterState()
        declutter_compute(ds, PHASE_APPROACH, False, 10000.0)
        assert ds.symbols[SYM_TYPE_FPV].alpha == 1.0
        assert ds.symbols[SYM_TYPE_RUNWAY_BOX].alpha == 1.0
        assert ds.symbols[SYM_TYPE_LOCALIZER_BAR].alpha == 1.0

    def test_background_suppressed_in_approach(self):
        ds = DeclutterState()
        declutter_compute(ds, PHASE_APPROACH, False, 10000.0)
        assert ds.symbols[SYM_TYPE_HEADING_SCALE].suppressed is True
        assert ds.symbols[SYM_TYPE_HEADING_SCALE].alpha == 0.0


class TestDeclutterFlare:
    def test_flare_cue_critical_in_flare(self):
        ds = DeclutterState()
        declutter_compute(ds, PHASE_FLARE, False, 10000.0)
        assert ds.symbols[SYM_TYPE_FLARE_CUE].alpha == 1.0

    def test_non_essential_suppressed_in_flare(self):
        ds = DeclutterState()
        declutter_compute(ds, PHASE_FLARE, False, 10000.0)
        assert ds.symbols[SYM_TYPE_DRIFT_CUE].suppressed is True
        assert ds.symbols[SYM_TYPE_ACCEL_CARET].suppressed is True
        assert ds.symbols[SYM_TYPE_TD_PREDICTOR].suppressed is True


class TestDeclutterRollout:
    def test_rollout_centerline_critical(self):
        ds = DeclutterState()
        declutter_compute(ds, PHASE_ROLLOUT, False, 10000.0)
        assert ds.symbols[SYM_TYPE_ROLLOUT_CENTER].alpha == 1.0
        assert ds.symbols[SYM_TYPE_ROLLOUT_DECEL].alpha == 0.9

    def test_flare_suppressed_in_rollout(self):
        ds = DeclutterState()
        declutter_compute(ds, PHASE_ROLLOUT, False, 10000.0)
        assert ds.symbols[SYM_TYPE_FLARE_CUE].suppressed is True
        assert ds.symbols[SYM_TYPE_LOCALIZER_BAR].suppressed is True


class TestDeclutterLowVis:
    def test_low_vis_boosts_critical(self):
        ds = DeclutterState()
        declutter_compute(ds, PHASE_APPROACH, True, 500.0)
        # Critical symbols should still be at full alpha
        assert ds.symbols[SYM_TYPE_FPV].alpha == 1.0

    def test_low_vis_suppresses_background(self):
        ds = DeclutterState()
        declutter_compute(ds, PHASE_APPROACH, True, 500.0)
        # In low vis, background-priority symbols should be suppressed
        # SYM_TYPE_ENERGY_TREND has NORMAL priority in approach, but the
        # visibility modifier for LOW/BACKGROUND reduces it further
        # SYM_TYPE_HEADING_SCALE is BACKGROUND in approach, always suppressed
        assert ds.symbols[SYM_TYPE_HEADING_SCALE].suppressed is True

    def test_visibility_factor_low_in_poor_vis(self):
        ds = DeclutterState()
        declutter_compute(ds, PHASE_APPROACH, True, 500.0)
        assert ds.visibility_factor < 0.5


class TestDeclutterAlpha:
    def test_alpha_ranges(self):
        ds = DeclutterState()
        declutter_compute(ds, PHASE_CRUISE, False, 10000.0)
        for s in range(SYM_TYPE_COUNT):
            if ds.symbols[s].suppressed:
                assert ds.symbols[s].alpha == 0.0
            else:
                assert 0.0 < ds.symbols[s].alpha <= 1.0
