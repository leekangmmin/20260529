#!/usr/bin/env python3
"""
C_HUD v2.7.0 — CAT III Annunciation Test Suite

Tests:
  1. CAT category determination from visibility
  2. LAND mode selection from CAT category
  3. FLARE annunciation when flare active
  4. ROLLOUT annunciation when rollout active
  5. NO DH annunciation in very low visibility
  6. Annunciation priority sorting

Run:  python -m pytest tests/test_cat3_annunciation.py -v
"""

import pytest

# ======================================================================
#  Annunciation reference implementation
# ======================================================================

# CAT category thresholds (from evs_compute in evs.cpp)
CAT_II_VIS_THRESHOLD = 1200.0    # vis < 1200m
CAT_IIIA_VIS_THRESHOLD = 600.0   # vis < 600m
CAT_IIIB_VIS_THRESHOLD = 400.0   # vis < 400m

CAT_NONE = 0
CAT_II = 2
CAT_IIIA = 3
CAT_IIIB = 4


def determine_cat_category(visibility_m):
    """Match the C++ EVS cat_category logic."""
    if visibility_m < 400.0:
        return CAT_IIIB
    elif visibility_m < 600.0:
        return CAT_IIIA
    elif visibility_m < 1200.0:
        return CAT_II
    return CAT_NONE


def determine_land_mode(cat_category):
    """LAND 3 when CAT IIIA/B, LAND 2 when CAT II."""
    if cat_category >= 3:
        return 3.0  # LAND 3
    elif cat_category >= 2:
        return 2.0  # LAND 2
    return 0.0


def determine_no_dh(visibility_m):
    """NO DH when visibility < 400m (CAT IIIB)."""
    return 1.0 if visibility_m < 400.0 else 0.0


# Expected annunciation labels
CAT_LABELS = {
    CAT_NONE: None,
    CAT_II: "CAT II",
    CAT_IIIA: "CAT IIIA",
    CAT_IIIB: "CAT IIIB",
}


class AnnunciationItem:
    def __init__(self, text, priority):
        self.text = text
        self.priority = priority


def build_annunciations(cat_category, land_mode, flare_active, rollout_active, no_dh):
    """Build and sort list of active annunciation items."""
    lines = []

    if cat_category >= 2:
        label = CAT_LABELS.get(cat_category)
        if label:
            lines.append(AnnunciationItem(label, 3))

    land_labels = {2: "LAND 2", 3: "LAND 3"}
    if land_mode >= 2 and cat_category >= 2:
        lines.append(AnnunciationItem(land_labels[land_mode], 4))

    if flare_active:
        lines.append(AnnunciationItem("FLARE", 2))

    if rollout_active:
        lines.append(AnnunciationItem("ROLLOUT", 2))

    if no_dh >= 0.5 and cat_category >= 2:
        lines.append(AnnunciationItem("NO DH", 1))

    # Sort by priority descending
    lines.sort(key=lambda x: -x.priority)
    return lines


# ======================================================================
#  Tests
# ======================================================================

class TestCATCategory:
    def test_clear_vis_no_cat(self):
        """Clear visibility > 1200m → no CAT."""
        assert determine_cat_category(5000.0) == CAT_NONE
        assert determine_cat_category(2000.0) == CAT_NONE

    def test_cat_ii_at_800m(self):
        """800m → CAT II."""
        assert determine_cat_category(800.0) == CAT_II

    def test_cat_ii_boundary(self):
        """Just below 1200m → CAT II."""
        assert determine_cat_category(1199.0) == CAT_II

    def test_cat_iiia_at_500m(self):
        """500m → CAT IIIA."""
        assert determine_cat_category(500.0) == CAT_IIIA

    def test_cat_iiia_boundary(self):
        """Just below 600m → CAT IIIA."""
        assert determine_cat_category(599.0) == CAT_IIIA

    def test_cat_iiib_at_300m(self):
        """300m → CAT IIIB."""
        assert determine_cat_category(300.0) == CAT_IIIB

    def test_cat_iiib_boundary(self):
        """Just below 400m → CAT IIIB."""
        assert determine_cat_category(399.0) == CAT_IIIB

    def test_extreme_fog(self):
        """Extreme fog → CAT IIIB."""
        assert determine_cat_category(50.0) == CAT_IIIB


class TestLANDMode:
    def test_no_land_when_no_cat(self):
        """No CAT → LAND 0."""
        assert determine_land_mode(CAT_NONE) == 0.0
        assert determine_land_mode(0) == 0.0

    def test_land_2_for_cat_ii(self):
        """CAT II → LAND 2."""
        assert determine_land_mode(CAT_II) == 2.0

    def test_land_3_for_cat_iiia(self):
        """CAT IIIA → LAND 3."""
        assert determine_land_mode(CAT_IIIA) == 3.0

    def test_land_3_for_cat_iiib(self):
        """CAT IIIB → LAND 3."""
        assert determine_land_mode(CAT_IIIB) == 3.0


class TestNoDH:
    def test_no_dh_in_iiib(self):
        """CAT IIIB vis → NO DH active."""
        assert determine_no_dh(300.0) == 1.0

    def test_no_dh_not_in_iiia(self):
        """CAT IIIA vis → NO DH NOT active."""
        assert determine_no_dh(500.0) == 0.0

    def test_no_dh_not_in_clear(self):
        """Clear vis → NO DH NOT active."""
        assert determine_no_dh(5000.0) == 0.0


class TestAnnunciationBuilding:
    def test_full_cat_iiib_set(self):
        """CAT IIIB with all phases → all annunciations."""
        result = build_annunciations(
            cat_category=CAT_IIIB, land_mode=3,
            flare_active=True, rollout_active=True, no_dh=True
        )
        texts = [item.text for item in result]
        assert "CAT IIIB" in texts
        assert "LAND 3" in texts
        assert "FLARE" in texts
        assert "ROLLOUT" in texts
        assert "NO DH" in texts

    def test_priority_ordering(self):
        """LAND 3 should appear before CAT (priority 4 > 3)."""
        result = build_annunciations(
            cat_category=CAT_IIIB, land_mode=3,
            flare_active=True, rollout_active=True, no_dh=True
        )
        # First item should be LAND 3 (highest priority)
        assert result[0].text == "LAND 3"
        # Last item should be NO DH (lowest priority)
        assert result[-1].text == "NO DH"

    def test_cat_ii_only(self):
        """CAT II without flare/rollout → CAT II + LAND 2."""
        result = build_annunciations(
            cat_category=CAT_II, land_mode=2,
            flare_active=False, rollout_active=False, no_dh=False
        )
        texts = [item.text for item in result]
        assert "CAT II" in texts
        assert "LAND 2" in texts
        assert "FLARE" not in texts
        assert "ROLLOUT" not in texts

    def test_no_annunciations_in_clear_weather(self):
        """Clear weather → no annunciations."""
        result = build_annunciations(
            cat_category=CAT_NONE, land_mode=0,
            flare_active=False, rollout_active=False, no_dh=False
        )
        assert len(result) == 0

    def test_flare_only(self):
        """Only flare active → FLARE shown."""
        result = build_annunciations(
            cat_category=CAT_NONE, land_mode=0,
            flare_active=True, rollout_active=False, no_dh=False
        )
        texts = [item.text for item in result]
        assert len(result) == 1
        assert "FLARE" in texts

    def test_rollout_only(self):
        """Only rollout active → ROLLOUT shown."""
        result = build_annunciations(
            cat_category=CAT_NONE, land_mode=0,
            flare_active=False, rollout_active=True, no_dh=False
        )
        texts = [item.text for item in result]
        assert "ROLLOUT" in texts

    def test_no_dh_only_without_cat(self):
        """NO DH only shown when CAT category >= 2."""
        result = build_annunciations(
            cat_category=CAT_NONE, land_mode=0,
            flare_active=False, rollout_active=False, no_dh=True
        )
        assert len(result) == 0

    def test_no_dh_with_cat(self):
        """NO DH shown with CAT II category."""
        result = build_annunciations(
            cat_category=CAT_II, land_mode=2,
            flare_active=False, rollout_active=False, no_dh=True
        )
        texts = [item.text for item in result]
        assert "NO DH" in texts
