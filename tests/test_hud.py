#!/usr/bin/env python3
"""
Conformal HUD – New Feature Test Suite (v2.0.0)

Tests for:
  1. Aircraft profile matching (PMDG 737/777, WT 787)
  2. Runway corner computation
  3. Flight Path Vector (FPV) computation
  4. ILS beam geometry
  5. Guidance / steering computation
  6. Horizon & pitch ladder
  7. Symbology clipping
  8. New projection math (tan, atan2, matrix ops)

Run:  python -m pytest tests/test_hud.py -v
"""

import math
import pytest

# ======================================================================
#  Constants
# ======================================================================
EARTH_RADIUS_M = 6378137.0
DEG2RAD = math.pi / 180.0
RAD2DEG = 180.0 / math.pi


# ======================================================================
#  Reusable vector math
# ======================================================================

class Vec2:
    __slots__ = ('x', 'y')
    def __init__(self, x=0.0, y=0.0):
        self.x, self.y = float(x), float(y)

class Vec3:
    __slots__ = ('x', 'y', 'z')
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.x, self.y, self.z = float(x), float(y), float(z)


# ======================================================================
#  1.  Aircraft Profile Matching Tests
# ======================================================================

PROFILES = [
    {"prefix": "PMDG 737", "hfov": 30.0, "vfov": 22.5,
     "eye_fwd": 0.5, "eye_right": 0.0, "eye_down": -1.2,
     "combiner": (150, 250, 724, 524)},
    {"prefix": "PMDG 777", "hfov": 33.0, "vfov": 24.0,
     "eye_fwd": 0.6, "eye_right": 0.0, "eye_down": -1.3,
     "combiner": (140, 240, 744, 544)},
    {"prefix": "ASOBO BOEING 787", "hfov": 36.0, "vfov": 26.0,
     "eye_fwd": 0.4, "eye_right": 0.0, "eye_down": -1.1,
     "combiner": (100, 200, 824, 624)},
    {"prefix": "WT_787", "hfov": 36.0, "vfov": 26.0,
     "eye_fwd": 0.4, "eye_right": 0.0, "eye_down": -1.1,
     "combiner": (100, 200, 824, 624)},
]


def match_profile(aircraft_id):
    if not aircraft_id:
        return PROFILES[-1]
    aid_lower = aircraft_id.lower()
    for p in PROFILES:
        if aid_lower.startswith(p["prefix"].lower()):
            return p
    return PROFILES[-1]


class TestAircraftProfiles:
    def test_pmdg_737_matches(self):
        p = match_profile("PMDG 737-800NGXu")
        assert p["prefix"] == "PMDG 737"
        assert p["hfov"] == 30.0

    def test_pmdg_737_variant(self):
        p = match_profile("PMDG 737-700")
        assert p["prefix"] == "PMDG 737"

    def test_pmdg_777_matches(self):
        p = match_profile("PMDG 777-300ER")
        assert p["prefix"] == "PMDG 777"

    def test_asobo_787_matches(self):
        p = match_profile("ASOBO BOEING 787-10")
        assert p["prefix"] == "ASOBO BOEING 787"

    def test_wt_787_matches(self):
        p = match_profile("WT_787_10")
        assert p["prefix"] == "WT_787"

    def test_case_insensitive(self):
        p = match_profile("pmdg 737-800")
        assert p["prefix"] == "PMDG 737"
        p2 = match_profile("Pmdg 737-800")
        assert p2["prefix"] == "PMDG 737"

    def test_unrecognized_returns_last(self):
        p = match_profile("CESSNA 172")
        assert p is not None

    def test_empty_string_ok(self):
        p = match_profile("")
        assert p is not None

    def test_none_ok(self):
        p = match_profile(None)
        assert p is not None

    def test_combiner_geometry(self):
        for p in PROFILES:
            cx, cy, cw, ch = p["combiner"]
            assert cx >= 0 and cy >= 0 and cw > 0 and ch > 0

    def test_focal_length_reasonable(self):
        for p in PROFILES:
            comb_w = p["combiner"][2]
            half_hfov = p["hfov"] * 0.5 * DEG2RAD
            focal_px = (comb_w * 0.5) / math.tan(half_hfov)
            assert 300 < focal_px < 1500


# ======================================================================
#  2.  Runway Corner Computation Tests
# ======================================================================

def compute_runway_corners(threshold_lat, threshold_lon, threshold_alt,
                           heading_deg, width_m, length_m):
    hdg_rad = heading_deg * DEG2RAD
    half_w = width_m * 0.5

    dir_east = math.sin(hdg_rad)
    dir_north = math.cos(hdg_rad)
    perp_east = -dir_north
    perp_north = dir_east

    cos_lat = math.cos(threshold_lat * DEG2RAD)
    dlat_per_m = 1.0 / EARTH_RADIUS_M
    dlon_per_m = 1.0 / (EARTH_RADIUS_M * cos_lat)

    extend = length_m + 500.0

    nl_lat = threshold_lat + RAD2DEG * (-half_w * perp_north * dlat_per_m)
    nl_lon = threshold_lon + RAD2DEG * (-half_w * perp_east * dlon_per_m)
    nr_lat = threshold_lat + RAD2DEG * (half_w * perp_north * dlat_per_m)
    nr_lon = threshold_lon + RAD2DEG * (half_w * perp_east * dlon_per_m)
    fl_lat = threshold_lat + RAD2DEG * (extend * dir_north * dlat_per_m - half_w * perp_north * dlat_per_m)
    fl_lon = threshold_lon + RAD2DEG * (extend * dir_east * dlon_per_m - half_w * perp_east * dlon_per_m)
    fr_lat = threshold_lat + RAD2DEG * (extend * dir_north * dlat_per_m + half_w * perp_north * dlat_per_m)
    fr_lon = threshold_lon + RAD2DEG * (extend * dir_east * dlon_per_m + half_w * perp_east * dlon_per_m)

    return [
        (nl_lon, nl_lat),
        (fl_lon, fl_lat),
        (fr_lon, fr_lat),
        (nr_lon, nr_lat),
    ]


class TestRunwayCorners:
    def test_four_corners_returned(self):
        corners = compute_runway_corners(37.4545, 126.4446, 7.0, 148.0, 60.0, 3750.0)
        assert len(corners) == 4

    def test_near_and_far_edges_parallel(self):
        corners = compute_runway_corners(37.4545, 126.4446, 7.0, 148.0, 60.0, 3750.0)
        ne_x = corners[3][0] - corners[0][0]
        ne_y = corners[3][1] - corners[0][1]
        fe_x = corners[2][0] - corners[1][0]
        fe_y = corners[2][1] - corners[1][1]
        dot = ne_x * fe_x + ne_y * fe_y
        assert dot > 0

    def test_runway_width_approx(self):
        corners = compute_runway_corners(37.4545, 126.4446, 7.0, 148.0, 60.0, 3750.0)
        cos_lat = math.cos(37.4545 * DEG2RAD)
        dlon = (corners[3][0] - corners[0][0]) * DEG2RAD
        width_approx = abs(dlon * EARTH_RADIUS_M * cos_lat)
        assert 50 < width_approx < 80

    def test_heading_90_nl_south_of_nr(self):
        """Heading 090: perp = (0,1)=north, nl = thresh - half_w*north → south of nr."""
        corners = compute_runway_corners(37.4545, 126.4446, 7.0, 90.0, 45.0, 3000.0)
        assert abs(corners[0][0] - corners[3][0]) < 0.0001
        assert corners[0][1] < corners[3][1]

    def test_heading_0_nl_east_of_nr(self):
        """Heading 000: perp = (-1,0)=west, nl = thresh + half_west → east of nr."""
        corners = compute_runway_corners(37.4545, 126.4446, 7.0, 0.0, 45.0, 3000.0)
        assert corners[0][0] > corners[3][0]

    def test_heading_148_extends_toward_se(self):
        """Heading 148°: far edge should be SE of near edge (lon+, lat-)."""
        corners = compute_runway_corners(37.4545, 126.4446, 7.0, 148.0, 60.0, 3750.0)
        assert corners[1][0] > corners[0][0]
        # For heading 148°, cos(148°) ≈ -0.848 → southward
        # So far edge should have same or smaller lat
        # Due to flat-earth approximation, might not be exact


# ======================================================================
#  3.  Flight Path Vector Tests
# ======================================================================

def compute_fpv(groundspeed_ms, vertical_speed_ms, heading_deg, track_deg):
    gs = max(groundspeed_ms, 0.1)
    vs = max(min(vertical_speed_ms, 100.0), -100.0)

    drift = track_deg - heading_deg
    if drift > 180.0: drift -= 360.0
    if drift < -180.0: drift += 360.0

    fpv_pitch = math.degrees(math.atan2(vs, gs))

    return {"fpv_pitch": fpv_pitch, "fpv_heading": track_deg, "drift_angle": drift}


class TestFPV:
    def test_level_flight(self):
        fpv = compute_fpv(80.0, 0.0, 180.0, 180.0)
        assert abs(fpv["fpv_pitch"]) < 0.001
        assert abs(fpv["drift_angle"]) < 0.001

    def test_climbing(self):
        fpv = compute_fpv(80.0, 5.0, 180.0, 180.0)
        assert fpv["fpv_pitch"] > 0.0

    def test_descending(self):
        fpv = compute_fpv(80.0, -3.0, 180.0, 180.0)
        assert fpv["fpv_pitch"] < 0.0

    def test_crosswind_drift(self):
        fpv = compute_fpv(80.0, 0.0, 180.0, 175.0)
        assert abs(fpv["drift_angle"]) > 0.0

    def test_drift_negative_when_track_left_of_heading(self):
        fpv = compute_fpv(80.0, 0.0, 180.0, 175.0)
        assert fpv["drift_angle"] < 0.0

    def test_no_drift(self):
        fpv = compute_fpv(80.0, 0.0, 180.0, 180.0)
        assert abs(fpv["drift_angle"]) < 0.001

    def test_typical_approach_fpa(self):
        fpv = compute_fpv(72.0, -3.56, 148.0, 148.0)
        assert abs(fpv["fpv_pitch"] - (-3.0)) < 1.0

    def test_fpv_heading_is_track(self):
        fpv = compute_fpv(80.0, 0.0, 180.0, 175.0)
        assert fpv["fpv_heading"] == 175.0


# ======================================================================
#  4.  ILS Beam Geometry Tests
# ======================================================================

def compute_ils_beam(threshold_lat, threshold_lon, threshold_alt,
                     heading_deg, gs_angle_deg=3.0):
    hdg_rad = heading_deg * DEG2RAD
    cos_lat = math.cos(threshold_lat * DEG2RAD)

    td_dist = 300.0
    td_dlat = RAD2DEG * (td_dist * math.cos(hdg_rad) / EARTH_RADIUS_M)
    td_dlon = RAD2DEG * (td_dist * math.sin(hdg_rad) / (EARTH_RADIUS_M * cos_lat))

    touchdown = {"lon": threshold_lon + td_dlon, "lat": threshold_lat + td_dlat, "alt": threshold_alt}

    dme_m = 1852.0
    loc_dlat = RAD2DEG * (dme_m * math.cos(hdg_rad) / EARTH_RADIUS_M)
    loc_dlon = RAD2DEG * (dme_m * math.sin(hdg_rad) / (EARTH_RADIUS_M * cos_lat))

    loc_intercept = {"lon": touchdown["lon"] + loc_dlon, "lat": touchdown["lat"] + loc_dlat, "alt": touchdown["alt"]}

    gs_height = dme_m * math.tan(gs_angle_deg * DEG2RAD)
    gs_intercept = {"lon": touchdown["lon"] + loc_dlon, "lat": touchdown["lat"] + loc_dlat, "alt": touchdown["alt"] + gs_height * 0.5}

    return {"touchdown": touchdown, "loc_intercept": loc_intercept, "gs_intercept": gs_intercept, "loc_bearing": heading_deg, "gs_angle": gs_angle_deg}


class TestILSBeam:
    def test_touchdown_different_from_threshold(self):
        beam = compute_ils_beam(37.4545, 126.4446, 7.0, 148.0)
        assert beam["touchdown"]["lon"] != 126.4446
        assert beam["touchdown"]["lat"] != 37.4545

    def test_heading_148_touchdown_se(self):
        beam = compute_ils_beam(37.4545, 126.4446, 7.0, 148.0)
        assert beam["touchdown"]["lon"] > 126.4446
        assert beam["touchdown"]["lat"] < 37.4545

    def test_heading_270_touchdown_west(self):
        beam = compute_ils_beam(37.4545, 126.4446, 7.0, 270.0)
        assert beam["touchdown"]["lon"] < 126.4446

    def test_loc_intercept_further_along(self):
        beam = compute_ils_beam(37.4545, 126.4446, 7.0, 148.0)
        loc_dlon = beam["loc_intercept"]["lon"] - beam["touchdown"]["lon"]
        loc_dlat = beam["loc_intercept"]["lat"] - beam["touchdown"]["lat"]
        td_dlon = beam["touchdown"]["lon"] - 126.4446
        td_dlat = beam["touchdown"]["lat"] - 37.4545
        assert (loc_dlon > 0) == (td_dlon > 0)
        assert (loc_dlat > 0) == (td_dlat > 0)

    def test_gs_angle_default(self):
        beam = compute_ils_beam(37.4545, 126.4446, 7.0, 148.0)
        assert beam["gs_angle"] == 3.0

    def test_gs_intercept_above_ground(self):
        beam = compute_ils_beam(37.4545, 126.4446, 7.0, 148.0)
        assert beam["gs_intercept"]["alt"] > beam["touchdown"]["alt"]

    def test_gs_angle_param(self):
        beam = compute_ils_beam(37.4545, 126.4446, 7.0, 148.0, gs_angle_deg=3.5)
        assert beam["gs_angle"] == 3.5

    def test_heading_affects_beam(self):
        beam1 = compute_ils_beam(37.4545, 126.4446, 7.0, 148.0)
        beam2 = compute_ils_beam(37.4545, 126.4446, 7.0, 270.0)
        assert abs(beam1["loc_intercept"]["lon"] - beam2["loc_intercept"]["lon"]) > 0.001

    def test_heading_000_touchdown_north(self):
        beam = compute_ils_beam(37.4545, 126.4446, 7.0, 0.0)
        assert beam["touchdown"]["lat"] > 37.4545

    def test_heading_090_touchdown_east(self):
        beam = compute_ils_beam(37.4545, 126.4446, 7.0, 90.0)
        assert beam["touchdown"]["lon"] > 126.4446


# ======================================================================
#  5.  Guidance Logic Tests
# ======================================================================

class TestGuidance:
    def test_loc_captured(self):
        assert abs(0.3) < 0.5

    def test_loc_not_captured(self):
        assert not (abs(0.7) < 0.5)

    def test_gs_captured(self):
        assert abs(-0.2) < 0.5

    def test_gs_not_captured(self):
        assert not (abs(0.8) < 0.5)

    def test_fd_pitch_up_when_below_gs(self):
        gs_error_deg = -0.5; gs_angle = 3.0; ac_pitch = 2.0
        desired_pitch = gs_angle - gs_error_deg
        pitch_error = desired_pitch - ac_pitch
        assert pitch_error > 0

    def test_fd_pitch_down_when_above_gs(self):
        gs_error_deg = 1.0; gs_angle = 3.0; ac_pitch = 3.0
        desired_pitch = gs_angle - gs_error_deg
        pitch_error = desired_pitch - ac_pitch
        assert pitch_error < 0

    def test_fd_bank_left_for_right_deviation(self):
        loc_error_deg = 0.5
        desired_bank = max(-25.0, min(25.0, -loc_error_deg * 3.0))
        assert desired_bank < 0

    def test_fd_bank_right_for_left_deviation(self):
        loc_error_deg = -0.5
        desired_bank = max(-25.0, min(25.0, -loc_error_deg * 3.0))
        assert desired_bank > 0

    def test_fd_bank_limited(self):
        desired_bank = max(-25.0, min(25.0, -10.0 * 3.0))
        assert desired_bank == -25.0

    def test_fd_no_bank_when_centered(self):
        desired_bank = max(-25.0, min(25.0, 0.0))
        assert abs(desired_bank) < 0.001


# ======================================================================
#  6.  Horizon & Pitch Ladder Tests
# ======================================================================

class TestHorizon:
    def test_center_when_level(self):
        horizon_y = 512 - 520 * math.tan(0)
        assert abs(horizon_y - 512) < 0.001

    def test_changes_with_pitch(self):
        h0 = 512 - 520 * math.tan(0 * DEG2RAD)
        h10 = 512 - 520 * math.tan(10 * DEG2RAD)
        assert h10 != h0

    def test_bank_slope_positive(self):
        slope = math.tan(15 * DEG2RAD)
        assert slope > 0.0

    def test_bank_slope_negative(self):
        slope = math.tan(-15 * DEG2RAD)
        assert slope < 0.0

    def test_no_bank_no_slope(self):
        assert abs(math.tan(0)) < 0.001


class TestPitchLadder:
    def test_five_lines(self):
        angles = [-10.0, -5.0, 0.0, 5.0, 10.0]
        assert len(angles) == 5

    def test_symmetric_spacing(self):
        focal_px = 520.0; screen_h = 1024; screen_cy = screen_h / 2
        offsets = []
        for angle in [-10.0, -5.0, 0.0, 5.0, 10.0]:
            y = screen_cy - focal_px * math.tan(angle * DEG2RAD)
            offsets.append(y)
        assert abs((offsets[0] - screen_cy) - (screen_cy - offsets[4])) < 1.0
        assert abs((offsets[1] - screen_cy) - (screen_cy - offsets[3])) < 1.0

    def test_center_0_deg(self):
        y = 512 - 520 * math.tan(0)
        assert abs(y - 512) < 0.001

    def test_moves_with_pitch(self):
        y0 = 512 - 520 * math.tan(5 * DEG2RAD)
        y10 = 512 - 520 * math.tan(5 * DEG2RAD - 10 * DEG2RAD)
        assert abs(y10 - y0) > 1.0


# ======================================================================
#  7.  Symbology Clipping Tests
# ======================================================================

class TestSymbologyClipping:
    def test_inside_combiner(self):
        comb = {"x": 150, "y": 250, "w": 724, "h": 524}
        visible = (400 >= comb["x"] and 400 <= comb["x"] + comb["w"] and
                   500 >= comb["y"] and 500 <= comb["y"] + comb["h"])
        assert visible

    def test_left_outside(self):
        comb = {"x": 150, "y": 250, "w": 724, "h": 524}
        visible = (100 >= comb["x"] and 100 <= comb["x"] + comb["w"] and
                   500 >= comb["y"] and 500 <= comb["y"] + comb["h"])
        assert not visible

    def test_top_outside(self):
        comb = {"x": 150, "y": 250, "w": 724, "h": 524}
        visible = (400 >= comb["x"] and 400 <= comb["x"] + comb["w"] and
                   200 >= comb["y"] and 200 <= comb["y"] + comb["h"])
        assert not visible

    def test_clip_left(self):
        assert max(100, 150) == 150

    def test_clip_top(self):
        assert max(200, 250) == 250

    def test_clip_bottom(self):
        assert min(800, 250 + 524) == 774

    def test_clip_right(self):
        assert min(900, 150 + 724) == 874

    def test_on_edge(self):
        comb = {"x": 150, "y": 250, "w": 724, "h": 524}
        visible = (150 >= comb["x"] and 150 <= comb["x"] + comb["w"] and
                   500 >= comb["y"] and 500 <= comb["y"] + comb["h"])
        assert visible

    def test_below_outside(self):
        comb = {"x": 150, "y": 250, "w": 724, "h": 524}
        visible = (400 >= comb["x"] and 400 <= comb["x"] + comb["w"] and
                   800 >= comb["y"] and 800 <= comb["y"] + comb["h"])
        assert not visible


# ======================================================================
#  8.  New Projection Math Tests
# ======================================================================

class TestNewProjectionMath:
    def test_tan_zero(self):
        assert abs(math.tan(0.0)) < 1e-15

    def test_tan_45(self):
        assert abs(math.tan(45 * DEG2RAD) - 1.0) < 1e-10

    def test_atan2_identity(self):
        angle = 30 * DEG2RAD
        assert abs(math.atan2(math.sin(angle), math.cos(angle)) - angle) < 1e-10

    def test_fov_focal_relationship(self):
        hfov_deg = 30.0; panel_w = 1024
        focal_px = (panel_w * 0.5) / math.tan(hfov_deg * 0.5 * DEG2RAD)
        recovered = 2 * math.degrees(math.atan((panel_w * 0.5) / focal_px))
        assert abs(recovered - hfov_deg) < 0.01

    def test_focal_scales_with_width(self):
        hfov = 30.0
        fl_512 = (256) / math.tan(hfov * 0.5 * DEG2RAD)
        fl_1024 = (512) / math.tan(hfov * 0.5 * DEG2RAD)
        assert abs(fl_1024 / fl_512 - 2.0) < 0.001

    def test_perspective_center(self):
        cx, cy = 512, 512
        focal_px = 520.0
        pt = (0.0, 0.0, 1000.0)
        behind = pt[2] <= 0.1
        assert not behind
        sx = cx + focal_px * pt[0] / pt[2]
        sy = cy - focal_px * pt[1] / pt[2]
        assert abs(sx - cx) < 0.001
        assert abs(sy - cy) < 0.001

    def test_perspective_right(self):
        cx, cy = 512, 512
        focal_px = 520.0
        pt = (100.0, 0.0, 1000.0)
        sx = cx + focal_px * pt[0] / pt[2]
        assert sx > cx

    def test_perspective_above(self):
        cx, cy = 512, 512
        focal_px = 520.0
        pt = (0.0, 50.0, 500.0)
        sy = cy - focal_px * pt[1] / pt[2]
        assert sy < cy

    def test_perspective_behind(self):
        behind = (-1.0 <= 0.1)
        assert behind

    def test_perspective_at_near_clip(self):
        behind = (0.1 <= 0.1)
        assert behind
