#!/usr/bin/env python3
"""
C_HUD v2.7.0 — EVS Visualization Test Suite

Tests:
  1. EVS active box determination
  2. EVS contrast cue scaling
  3. EVS visibility indication (low vis mode)
  4. EVS intensity computation (already tested in test_evs.py)
  5. EVS rendering parameters for JS consumption

Run:  python -m pytest tests/test_evs_rendering.py -v
"""

import math
import pytest

# ======================================================================
#  Reference implementation
# ======================================================================

EVS_ACTIVE_BOX_ON_THRESHOLD = 0.5


def compute_evs_visualization_lvars(evs_active, evs_intensity, evs_contrast, low_vis_mode):
    """
    Simulate C++ publish for EVS visualization L:vars.
    
    Returns dict mimicking what the JS renderer reads.
    """
    # EVS Active Box: show when EVS is actively enhancing
    active_box = 1.0 if (evs_active and evs_intensity > 0.01) else 0.0
    
    # Contrast cue: 0 = normal, higher = more contrast boost
    # In C++ publish: symbology_contrast - 1.0
    contrast_cue = max(0.0, evs_contrast - 1.0)
    
    # Visibility indication: show when low visibility mode active
    vis_ind = 1.0 if low_vis_mode else 0.0
    
    return {
        "EVS_ACTIVE_BOX": active_box,
        "EVS_CONTRAST_CUE": contrast_cue,
        "EVS_VIS_IND": vis_ind,
        "EVS_ACTIVE": 1.0 if evs_active else 0.0,
        "EVS_INTENSITY": evs_intensity,
    }


# ======================================================================
#  Tests
# ======================================================================

class TestEVSActiveBox:
    def test_active_when_evs_enhancing(self):
        """EVS active with intensity → active box ON."""
        lvars = compute_evs_visualization_lvars(
            evs_active=True, evs_intensity=0.7,
            evs_contrast=1.8, low_vis_mode=True
        )
        assert lvars["EVS_ACTIVE_BOX"] == 1.0

    def test_inactive_when_evs_off(self):
        """EVS not active → active box OFF."""
        lvars = compute_evs_visualization_lvars(
            evs_active=False, evs_intensity=0.0,
            evs_contrast=1.0, low_vis_mode=False
        )
        assert lvars["EVS_ACTIVE_BOX"] == 0.0

    def test_inactive_when_zero_intensity(self):
        """EVS active but zero intensity → box OFF."""
        lvars = compute_evs_visualization_lvars(
            evs_active=True, evs_intensity=0.0,
            evs_contrast=1.0, low_vis_mode=False
        )
        assert lvars["EVS_ACTIVE_BOX"] == 0.0

    def test_active_only_above_threshold(self):
        """Very low but non-zero intensity → active_box threshold check."""
        # Below 0.01 threshold, should be off
        lvars = compute_evs_visualization_lvars(
            evs_active=True, evs_intensity=0.005,
            evs_contrast=1.0, low_vis_mode=True
        )
        assert lvars["EVS_ACTIVE_BOX"] == 0.0


class TestEVSContrastCue:
    def test_zero_when_normal_contrast(self):
        """Normal contrast (1.0) → cue = 0."""
        lvars = compute_evs_visualization_lvars(
            evs_active=False, evs_intensity=0.0,
            evs_contrast=1.0, low_vis_mode=False
        )
        assert lvars["EVS_CONTRAST_CUE"] == 0.0

    def test_positive_when_boosted(self):
        """Boosted contrast → positive cue value."""
        lvars = compute_evs_visualization_lvars(
            evs_active=True, evs_intensity=0.5,
            evs_contrast=1.6, low_vis_mode=True
        )
        assert lvars["EVS_CONTRAST_CUE"] > 0.0
        assert lvars["EVS_CONTRAST_CUE"] == pytest.approx(0.6, abs=0.01)

    def test_max_contrast_boost(self):
        """Maximum realistic contrast boost."""
        lvars = compute_evs_visualization_lvars(
            evs_active=True, evs_intensity=1.0,
            evs_contrast=2.0, low_vis_mode=True
        )
        assert lvars["EVS_CONTRAST_CUE"] == 1.0

    def test_cue_never_negative(self):
        """Contrast cue clamped to >= 0."""
        lvars = compute_evs_visualization_lvars(
            evs_active=False, evs_intensity=0.0,
            evs_contrast=0.8, low_vis_mode=False
        )
        assert lvars["EVS_CONTRAST_CUE"] >= 0.0


class TestEVSVisibilityInd:
    def test_on_in_low_vis(self):
        """Low visibility mode → visibility indication ON."""
        lvars = compute_evs_visualization_lvars(
            evs_active=True, evs_intensity=0.5,
            evs_contrast=1.5, low_vis_mode=True
        )
        assert lvars["EVS_VIS_IND"] == 1.0

    def test_off_in_clear(self):
        """Not in low vis → visibility indication OFF."""
        lvars = compute_evs_visualization_lvars(
            evs_active=False, evs_intensity=0.0,
            evs_contrast=1.0, low_vis_mode=False
        )
        assert lvars["EVS_VIS_IND"] == 0.0

    def test_on_in_approach_low_vis(self):
        """Approach with moderate vis → low_vis_mode may be off."""
        lvars = compute_evs_visualization_lvars(
            evs_active=True, evs_intensity=0.3,
            evs_contrast=1.3, low_vis_mode=True
        )
        assert lvars["EVS_VIS_IND"] == 1.0


class TestEVSIntegration:
    def test_typical_low_vis_cat_iiia(self):
        """Typical CAT IIIA scenario: all EVS indicators active."""
        lvars = compute_evs_visualization_lvars(
            evs_active=True, evs_intensity=0.8,
            evs_contrast=1.9, low_vis_mode=True
        )
        assert lvars["EVS_ACTIVE_BOX"] == 1.0
        assert lvars["EVS_CONTRAST_CUE"] > 0.5
        assert lvars["EVS_VIS_IND"] == 1.0
        assert lvars["EVS_ACTIVE"] == 1.0

    def test_typical_clear_day(self):
        """Clear day: all EVS indicators off/normal."""
        lvars = compute_evs_visualization_lvars(
            evs_active=False, evs_intensity=0.0,
            evs_contrast=1.0, low_vis_mode=False
        )
        assert lvars["EVS_ACTIVE_BOX"] == 0.0
        assert lvars["EVS_CONTRAST_CUE"] == 0.0
        assert lvars["EVS_VIS_IND"] == 0.0
