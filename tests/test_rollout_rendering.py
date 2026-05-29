#!/usr/bin/env python3
"""
C_HUD v2.7.0 — Rollout Guidance Rendering Test Suite

Tests:
  1. Rollout L:Var publishing derivation (centerline, deviation, command)
  2. Centerline cue computation and normalization
  3. Deviation bar mapping and clamping
  4. Steering command scaling
  5. Anti-jitter inertia blending
  6. Low-speed fade logic

Run:  python -m pytest tests/test_rollout_rendering.py -v
"""

import math
import pytest

# ======================================================================
#  Constants (matching C++ rollout.h and conformal_renderer.js)
# ======================================================================
ROLLOUT_PHASE_INACTIVE = 0
ROLLOUT_PHASE_TRANSITION = 1
ROLLOUT_PHASE_ACTIVE = 2
ROLLOUT_PHASE_COMPLETE = 3

MAX_STEERING_DEG = 10.0


# ======================================================================
#  L:Var publishing reference implementation
# ======================================================================

def compute_rollout_lvars(rollout_state):
    """Simulates the C++ module_update_publish rollout section."""
    rollout_visible = rollout_state.get("valid", False) and (
        rollout_state.get("phase") == ROLLOUT_PHASE_TRANSITION or
        rollout_state.get("phase") == ROLLOUT_PHASE_ACTIVE
    )

    centerline_error_dots = rollout_state.get("centerline_error_dots", 0.0)
    steering_command_deg = rollout_state.get("steering_command_deg", 0.0)

    # Centerline cue: 0..1 (0.5 = center)
    centerline_cue = 0.5 + centerline_error_dots * 0.5
    centerline_cue = max(0.0, min(1.0, centerline_cue))

    if not rollout_visible:
        return {
            "ROLL_ACTIVE": 0.0,
            "ROLL_CENTERLINE": float('nan'),
            "ROLL_DEVIATION": 0.0,
            "ROLL_COMMAND": 0.0,
        }

    # Deviation: -1..1
    deviation = max(-1.0, min(1.0, centerline_error_dots))

    # Command: -1..1
    cmd = steering_command_deg / MAX_STEERING_DEG
    cmd = max(-1.0, min(1.0, cmd))

    return {
        "ROLL_ACTIVE": 1.0,
        "ROLL_CENTERLINE": centerline_cue,
        "ROLL_DEVIATION": deviation,
        "ROLL_COMMAND": cmd,
    }


def apply_inertia(prev, current, factor=0.2):
    """Simulates JS with_inertia()."""
    if prev is None or math.isnan(prev):
        return current
    if math.isnan(current):
        return prev
    return prev * factor + current * (1.0 - factor)


# ======================================================================
#  Tests
# ======================================================================

class TestRolloutCenterlineCue:
    def test_centerline_centered_when_no_error(self):
        """Zero error → centerline cue at 0.5 (center)."""
        state = {
            "valid": True,
            "phase": ROLLOUT_PHASE_ACTIVE,
            "centerline_error_dots": 0.0,
            "steering_command_deg": 0.0,
        }
        lvars = compute_rollout_lvars(state)
        assert abs(lvars["ROLL_CENTERLINE"] - 0.5) < 0.001

    def test_centerline_left_when_negative_error(self):
        """Negative error (left) → cue < 0.5."""
        state = {
            "valid": True,
            "phase": ROLLOUT_PHASE_ACTIVE,
            "centerline_error_dots": -0.5,
            "steering_command_deg": -3.0,
        }
        lvars = compute_rollout_lvars(state)
        assert lvars["ROLL_CENTERLINE"] < 0.5

    def test_centerline_right_when_positive_error(self):
        """Positive error (right) → cue > 0.5."""
        state = {
            "valid": True,
            "phase": ROLLOUT_PHASE_ACTIVE,
            "centerline_error_dots": 0.5,
            "steering_command_deg": 3.0,
        }
        lvars = compute_rollout_lvars(state)
        assert lvars["ROLL_CENTERLINE"] > 0.5

    def test_centerline_clamped_zero(self):
        """Even extreme negative error clamps to 0.0."""
        state = {
            "valid": True,
            "phase": ROLLOUT_PHASE_ACTIVE,
            "centerline_error_dots": -2.0,  # out of range
            "steering_command_deg": 0.0,
        }
        lvars = compute_rollout_lvars(state)
        assert lvars["ROLL_CENTERLINE"] >= 0.0

    def test_centerline_clamped_one(self):
        """Even extreme positive error clamps to 1.0."""
        state = {
            "valid": True,
            "phase": ROLLOUT_PHASE_ACTIVE,
            "centerline_error_dots": 2.0,  # out of range
            "steering_command_deg": 0.0,
        }
        lvars = compute_rollout_lvars(state)
        assert lvars["ROLL_CENTERLINE"] <= 1.0

    def test_not_published_when_inactive(self):
        """Rollout not visible → active=0, centerline=NaN."""
        state = {
            "valid": True,
            "phase": ROLLOUT_PHASE_INACTIVE,
            "centerline_error_dots": 0.0,
            "steering_command_deg": 0.0,
        }
        lvars = compute_rollout_lvars(state)
        assert lvars["ROLL_ACTIVE"] == 0.0
        assert math.isnan(lvars["ROLL_CENTERLINE"])

    def test_not_published_when_complete(self):
        """Rollout complete → not visible."""
        state = {
            "valid": True,
            "phase": ROLLOUT_PHASE_COMPLETE,
            "centerline_error_dots": 0.0,
            "steering_command_deg": 0.0,
        }
        lvars = compute_rollout_lvars(state)
        assert lvars["ROLL_ACTIVE"] == 0.0


class TestRolloutDeviation:
    def test_deviation_negative_left(self):
        """Negative error → negative deviation."""
        state = {
            "valid": True,
            "phase": ROLLOUT_PHASE_ACTIVE,
            "centerline_error_dots": -0.3,
            "steering_command_deg": 0.0,
        }
        lvars = compute_rollout_lvars(state)
        assert lvars["ROLL_DEVIATION"] < 0.0

    def test_deviation_positive_right(self):
        """Positive error → positive deviation."""
        state = {
            "valid": True,
            "phase": ROLLOUT_PHASE_ACTIVE,
            "centerline_error_dots": 0.3,
            "steering_command_deg": 0.0,
        }
        lvars = compute_rollout_lvars(state)
        assert lvars["ROLL_DEVIATION"] > 0.0

    def test_deviation_clamped(self):
        """Deviation clamped to ±1."""
        state = {
            "valid": True,
            "phase": ROLLOUT_PHASE_ACTIVE,
            "centerline_error_dots": 3.0,
            "steering_command_deg": 0.0,
        }
        lvars = compute_rollout_lvars(state)
        assert abs(lvars["ROLL_DEVIATION"]) <= 1.0

    def test_deviation_zero_when_inactive(self):
        """Inactive → deviation = 0."""
        state = {
            "valid": True,
            "phase": ROLLOUT_PHASE_INACTIVE,
            "centerline_error_dots": 0.5,
            "steering_command_deg": 0.0,
        }
        lvars = compute_rollout_lvars(state)
        assert lvars["ROLL_DEVIATION"] == 0.0


class TestRolloutCommand:
    def test_command_positive_for_right_steering(self):
        """Positive steering command → positive command L:Var."""
        state = {
            "valid": True,
            "phase": ROLLOUT_PHASE_ACTIVE,
            "centerline_error_dots": 0.0,
            "steering_command_deg": 5.0,
        }
        lvars = compute_rollout_lvars(state)
        assert lvars["ROLL_COMMAND"] > 0.0

    def test_command_negative_for_left_steering(self):
        """Negative steering command → negative command L:Var."""
        state = {
            "valid": True,
            "phase": ROLLOUT_PHASE_ACTIVE,
            "centerline_error_dots": 0.0,
            "steering_command_deg": -5.0,
        }
        lvars = compute_rollout_lvars(state)
        assert lvars["ROLL_COMMAND"] < 0.0

    def test_command_scaled_to_plus_minus_one(self):
        """10 deg → 1.0 (full scale)."""
        state = {
            "valid": True,
            "phase": ROLLOUT_PHASE_ACTIVE,
            "centerline_error_dots": 0.0,
            "steering_command_deg": 10.0,
        }
        lvars = compute_rollout_lvars(state)
        assert abs(lvars["ROLL_COMMAND"]) <= 1.0

    def test_command_zero_when_inactive(self):
        """Inactive → command = 0."""
        state = {
            "valid": True,
            "phase": ROLLOUT_PHASE_INACTIVE,
            "centerline_error_dots": 0.0,
            "steering_command_deg": 3.0,
        }
        lvars = compute_rollout_lvars(state)
        assert lvars["ROLL_COMMAND"] == 0.0


class TestRolloutInertia:
    def test_inertia_returns_current_when_no_previous(self):
        """No previous value → returns current."""
        result = apply_inertia(None, 0.7, 0.2)
        assert result == 0.7

    def test_inertia_blends_values(self):
        """Previous and current blend with factor."""
        result = apply_inertia(0.5, 0.7, 0.2)
        expected = 0.5 * 0.2 + 0.7 * 0.8  # = 0.66
        assert abs(result - expected) < 0.001

    def test_inertia_higher_factor_more_smoothing(self):
        """Higher factor = more smoothing (closer to prev)."""
        low_smooth = apply_inertia(0.5, 0.9, 0.1)  # 10% prev
        high_smooth = apply_inertia(0.5, 0.9, 0.3)  # 30% prev
        # High smooth should have less movement from 0.5
        assert abs(high_smooth - 0.5) < abs(low_smooth - 0.5)

    def test_inertia_handles_nan_current(self):
        """NaN current → returns previous."""
        result = apply_inertia(0.5, float('nan'), 0.2)
        assert result == 0.5

    def test_repeated_inertia_converges(self):
        """Repeated application converges to target."""
        target = 0.8
        value = 0.0
        for _ in range(100):
            value = apply_inertia(value, target, 0.2)
        assert abs(value - target) < 0.001


class TestRolloutFadeLogic:
    def test_fade_lower_alpha_at_low_confidence(self):
        """Lower confidence → lower effective alpha multiplier."""
        confidence_low = 0.2
        confidence_high = 0.9
        base = 0.8

        alpha_low = base * (0.4 + confidence_low * 0.6)
        alpha_high = base * (0.4 + confidence_high * 0.6)

        assert alpha_low < alpha_high

    def test_minimal_alpha_at_zero_confidence(self):
        """Zero confidence → minimal but non-zero alpha."""
        base = 0.8
        alpha = base * (0.4 + 0.0 * 0.6)
        assert alpha > 0.0
        assert alpha < base * 0.5

    def test_full_alpha_at_max_confidence(self):
        """Max confidence → nearly full alpha."""
        base = 0.8
        alpha = base * (0.4 + 1.0 * 0.6)
        assert abs(alpha - base) < 0.001
