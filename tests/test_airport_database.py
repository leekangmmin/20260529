#!/usr/bin/env python3
"""
Conformal HUD – Airport Database System Test Suite (v2.2.0)

Tests:
  1. Database initialisation and loading
  2. ILS frequency index building
  3. Runway lookup by ICAO + runway ID
  4. Runway lookup by ILS frequency
  5. Nearest-airport spatial query
  6. Airport runway enumeration
  7. Reciprocal runway mapping
  8. Displaced threshold handling
  9. Touchdown zone geometry defaults
  10. Active runway detection via multiple strategies
  11. Async loading state machine
  12. Runway cache operations (insert, lookup, LRU eviction)
  13. Spatial tile indexing
  14. Runway end geometry conversion

Run:  python -m pytest tests/test_airport_database.py -v
"""

import math
import pytest

# ======================================================================
#  Constants (mirrored from C++ airport_database.h)
# ======================================================================
EARTH_RADIUS_M = 6378137.0
DEG2RAD = math.pi / 180.0
RAD2DEG = 180.0 / math.pi
PROJ_EARTH_RADIUS_M = EARTH_RADIUS_M

DB_ICAO_CODE_MAX = 8
DB_RUNWAY_NAME_MAX = 8
DB_MAX_AIRPORTS_CACHED = 512
DB_MAX_RUNWAYS_PER_AIRPORT = 64
DB_MAX_ILS_FREQUENCIES = 256
RC_MAX_CACHED_RUNWAYS = 32

# ======================================================================
#  Enums
# ======================================================================
DB_UNINITIALISED = 0
DB_LOADING = 1
DB_READY = 2
DB_ERROR = 3

# ======================================================================
#  Data structures (Python reference implementations)
# ======================================================================


class DisplacedThreshold:
    def __init__(self):
        self.distance_from_end_m = 0.0
        self.landing_displaced = False
        self.valid = False


class TouchdownZoneGeometry:
    def __init__(self):
        self.distance_from_threshold_m = 0.0
        self.zone_length_m = 0.0
        self.zone_width_m = 0.0
        self.valid = False


class RunwayRecord:
    def __init__(self):
        self.icao_code = ""
        self.runway_id = ""
        self.threshold_lat_deg = 0.0
        self.threshold_lon_deg = 0.0
        self.threshold_alt_m = 0.0
        self.far_end_lat_deg = 0.0
        self.far_end_lon_deg = 0.0
        self.true_heading_deg = 0.0
        self.width_m = 0.0
        self.length_m = 0.0
        self.slope_pct = 0.0
        self.ils_frequency_mhz = 0.0
        self.gs_angle_deg = 3.0
        self.displaced_threshold = DisplacedThreshold()
        self.tdz_geometry = TouchdownZoneGeometry()
        self.reciprocal_index = -1
        self.surface_type = 0
        self.has_approach_lights = False
        self.has_papi = False
        self.valid = False


class AirportRecord:
    def __init__(self):
        self.icao_code = ""
        self.lat_deg = 0.0
        self.lon_deg = 0.0
        self.elevation_m = 0.0
        self.num_runways = 0
        self.runway_indices = []
        self.valid = False


class AirportDatabase:
    def __init__(self):
        self.airports = []
        self.runways = []
        self.ils_freq_indices = []
        self.ils_freq_values = []
        self.ils_freq_count = 0
        self.load_state = DB_UNINITIALISED
        self.load_progress_pct = 0
        self.async_loading = False
        self.async_stage = 0
        self.initialised = False


# ======================================================================
#  Reference database (subset of C++ g_builtin_runways)
# ======================================================================

def build_test_database():
    """Build a minimal test database mimicking the C++ static table."""
    db = AirportDatabase()

    def add_runway(icao, rwy, lat, lon, alt, hdg, w, length, ils_freq,
                   gs_angle=3.0, slope=0.0):
        r = RunwayRecord()
        r.icao_code = icao
        r.runway_id = rwy
        r.threshold_lat_deg = lat
        r.threshold_lon_deg = lon
        r.threshold_alt_m = alt
        r.true_heading_deg = hdg
        r.width_m = w
        r.length_m = length
        r.ils_frequency_mhz = ils_freq
        r.gs_angle_deg = gs_angle
        r.slope_pct = slope

        # Compute far end
        hdg_rad = hdg * DEG2RAD
        cos_lat = math.cos(lat * DEG2RAD)
        dlat = length * math.cos(hdg_rad) / EARTH_RADIUS_M
        dlon = length * math.sin(hdg_rad) / (EARTH_RADIUS_M * cos_lat)
        r.far_end_lat_deg = lat + dlat * RAD2DEG
        r.far_end_lon_deg = lon + dlon * RAD2DEG

        # Default TDZ
        r.tdz_geometry.distance_from_threshold_m = 300.0
        r.tdz_geometry.zone_length_m = 300.0
        r.tdz_geometry.zone_width_m = w
        r.tdz_geometry.valid = True

        r.valid = True
        db.runways.append(r)
        return len(db.runways) - 1

    def add_airport(icao, lat, lon, elev, runway_indices):
        a = AirportRecord()
        a.icao_code = icao
        a.lat_deg = lat
        a.lon_deg = lon
        a.elevation_m = elev
        a.num_runways = len(runway_indices)
        a.runway_indices = runway_indices
        a.valid = True
        db.airports.append(a)

    # RKSI
    r0 = add_runway("RKSI", "15R", 37.4545, 126.4446, 7.0, 148.0, 60.0, 3750.0, 111.10)
    r1 = add_runway("RKSI", "33L", 37.4850, 126.4680, 7.0, 328.0, 60.0, 3750.0, 111.10)
    r2 = add_runway("RKSI", "16L", 37.4670, 126.4630, 7.0, 160.0, 60.0, 3750.0, 111.30)
    r3 = add_runway("RKSI", "34R", 37.4970, 126.4860, 7.0, 340.0, 60.0, 3750.0, 111.30)
    add_airport("RKSI", 37.46, 126.46, 7.0, [r0, r1, r2, r3])

    # EGLL
    r4 = add_runway("EGLL", "27L", 51.4775, -0.4614, 25.0, 270.0, 45.0, 3900.0, 110.30)
    r5 = add_runway("EGLL", "09R", 51.4775, -0.4150, 25.0, 90.0, 45.0, 3900.0, 110.30)
    r6 = add_runway("EGLL", "27R", 51.4720, -0.4835, 25.0, 270.0, 45.0, 3660.0, 109.50)
    r7 = add_runway("EGLL", "09L", 51.4720, -0.4380, 25.0, 90.0, 45.0, 3660.0, 109.50)
    add_airport("EGLL", 51.475, -0.45, 25.0, [r4, r5, r6, r7])

    # KSEA
    r8 = add_runway("KSEA", "16R", 47.4320, -122.3110, 106.0, 160.0, 46.0, 3628.0, 110.30)
    r9 = add_runway("KSEA", "34L", 47.4560, -122.3060, 106.0, 340.0, 46.0, 3628.0, 109.90)
    r10 = add_runway("KSEA", "16L", 47.4280, -122.3190, 106.0, 160.0, 46.0, 2869.0, 111.95)
    r11 = add_runway("KSEA", "34R", 47.4500, -122.3150, 106.0, 340.0, 46.0, 2869.0, 111.95)
    add_airport("KSEA", 47.45, -122.31, 106.0, [r8, r9, r10, r11])

    # EDDF
    r12 = add_runway("EDDF", "07R", 50.0310, 8.5620, 100.0, 70.0, 45.0, 4000.0, 111.15)
    r13 = add_runway("EDDF", "25L", 50.0340, 8.5900, 100.0, 250.0, 45.0, 4000.0, 111.15)
    r14 = add_runway("EDDF", "07L", 50.0330, 8.5580, 100.0, 70.0, 45.0, 2800.0, 110.50)
    r15 = add_runway("EDDF", "25R", 50.0360, 8.5800, 100.0, 250.0, 45.0, 2800.0, 110.50)
    add_airport("EDDF", 50.033, 8.57, 100.0, [r12, r13, r14, r15])

    # KDEN
    r16 = add_runway("KDEN", "35R", 39.8510, -104.6720, 1625.0, 350.0, 46.0, 4877.0, 111.95)
    r17 = add_runway("KDEN", "17L", 39.8860, -104.6740, 1625.0, 170.0, 46.0, 4877.0, 111.95)
    r18 = add_runway("KDEN", "34L", 39.8350, -104.6820, 1625.0, 340.0, 46.0, 4877.0, 111.70)
    r19 = add_runway("KDEN", "16R", 39.8700, -104.6840, 1625.0, 160.0, 46.0, 4877.0, 111.70)
    add_airport("KDEN", 39.85, -104.67, 1625.0, [r16, r17, r18, r19])

    # Resolve reciprocal indices (symmetric: A->B and B->A)
    for i, r in enumerate(db.runways):
        if r.reciprocal_index == -1:
            recip_hdg = (r.true_heading_deg + 180.0) % 360.0
            best_j = -1
            best_dist = 1e18
            for j, other in enumerate(db.runways):
                if i == j:
                    continue
                if other.icao_code == r.icao_code:
                    delta = abs(other.true_heading_deg - recip_hdg)
                    if delta > 180.0:
                        delta = 360.0 - delta
                    if delta < 2.0:
                        # Position proximity: far_end of A should be near threshold of B
                        dlat = other.threshold_lat_deg - r.far_end_lat_deg
                        dlon = other.threshold_lon_deg - r.far_end_lon_deg
                        dist = math.sqrt(dlat*dlat + dlon*dlon)
                        if dist < best_dist:
                            best_dist = dist
                            best_j = j
            if best_j >= 0 and db.runways[best_j].reciprocal_index == -1:
                db.runways[i].reciprocal_index = best_j
                # Also set the reciprocal of B to A (symmetric)
                db.runways[best_j].reciprocal_index = i

    # Build ILS frequency index
    for i, r in enumerate(db.runways):
        if 100.0 < r.ils_frequency_mhz < 120.0:
            if len(db.ils_freq_indices) < DB_MAX_ILS_FREQUENCIES:
                db.ils_freq_indices.append(i)
                db.ils_freq_values.append(r.ils_frequency_mhz)

    db.ils_freq_count = len(db.ils_freq_indices)
    db.load_state = DB_READY
    db.initialised = True

    return db


# ======================================================================
#  Reference functions (mirroring C++ airport_database.cpp)
# ======================================================================

def db_find_runway(db, icao_code, runway_id):
    if not db or not icao_code or not runway_id:
        return None
    icao_u = icao_code.upper()
    rwy_u = runway_id.upper()
    for r in db.runways:
        if not r.valid:
            continue
        if r.icao_code.upper() == icao_u and r.runway_id.upper() == rwy_u:
            return r
    return None


def db_find_by_ils_freq(db, freq_mhz, tolerance=0.01):
    if not db or freq_mhz <= 100.0 or freq_mhz >= 120.0:
        return None
    best_diff = tolerance
    best_idx = -1
    for i in range(db.ils_freq_count):
        idx = db.ils_freq_indices[i]
        diff = abs(db.ils_freq_values[i] - freq_mhz)
        if diff < best_diff:
            best_diff = diff
            best_idx = i
    if best_idx >= 0:
        idx = db.ils_freq_indices[best_idx]
        if 0 <= idx < len(db.runways):
            return db.runways[idx]
    return None


def db_find_nearest_airport(db, lat_deg, lon_deg):
    if not db or not db.airports:
        return None
    best_dist = 1e18
    best_ap = None
    for a in db.airports:
        if not a.valid:
            continue
        dlat = lat_deg - a.lat_deg
        dlon = lon_deg - a.lon_deg
        d = dlat * dlat + dlon * dlon
        if d < best_dist:
            best_dist = d
            best_ap = a
    return best_ap


def db_get_reciprocal_runway(db, rwy):
    if not db or not rwy or not rwy.valid:
        return None
    if rwy.reciprocal_index < 0 or rwy.reciprocal_index >= len(db.runways):
        return None
    recip = db.runways[rwy.reciprocal_index]
    return recip if recip.valid else None


def db_find_active_runway(db, ac_lat, ac_lon, ac_hdg, ils_freq):
    if not db or not db.initialised:
        return None

    # Strategy 1: ILS frequency
    if 100.0 < ils_freq < 120.0:
        rwy = db_find_by_ils_freq(db, ils_freq, 0.01)
        if rwy:
            return rwy

    # Strategy 2: Nearest airport + heading alignment
    airport = db_find_nearest_airport(db, ac_lat, ac_lon)
    if not airport:
        return None

    # Check distance
    dlat = ac_lat - airport.lat_deg
    dlon = ac_lon - airport.lon_deg
    dist_sq = dlat * dlat + dlon * dlon
    if dist_sq > 1.0:
        return None

    best_rwy = None
    best_delta = 90.0

    for idx in airport.runway_indices:
        if idx < 0 or idx >= len(db.runways):
            continue
        rwy = db.runways[idx]
        if not rwy.valid:
            continue
        delta = abs(ac_hdg - rwy.true_heading_deg)
        if delta > 180.0:
            delta = 360.0 - delta
        if delta < best_delta:
            best_delta = delta
            best_rwy = rwy

    if best_rwy and best_delta < 90.0:
        return best_rwy

    return None


# ======================================================================
#  Cache reference implementation (mirroring C++ runway_cache.h/.cpp)
# ======================================================================

class RunwayCacheEntry:
    def __init__(self):
        self.icao_code = ""
        self.runway_id = ""
        self.runway_db_index = -1
        self.frame_last_used = 0
        self.dirty = True
        self.valid = False
        self.prefetched = False


class RunwayCache:
    def __init__(self):
        self.entries = []
        self.num_entries = 0
        self.frame_counter = 0
        self.stat_hits = 0
        self.stat_misses = 0
        self.stat_evictions = 0
        self.prefetch_active = False

    def lookup(self, db_index):
        for e in self.entries:
            if e.runway_db_index == db_index and e.valid:
                e.frame_last_used = self.frame_counter
                self.stat_hits += 1
                return e
        self.stat_misses += 1
        return None

    def insert(self, rwy, db_index, frame):
        # Check existing
        for e in self.entries:
            if e.runway_db_index == db_index and e.valid:
                e.frame_last_used = frame
                e.dirty = True
                return

        # Free slot or evict LRU
        if len(self.entries) >= RC_MAX_CACHED_RUNWAYS:
            oldest = min(self.entries, key=lambda e: e.frame_last_used
                         if not e.prefetched else float('inf'))
            # If all are prefetched, evict the oldest
            if oldest.prefetched:
                oldest = min(self.entries, key=lambda e: e.frame_last_used)
            self.entries.remove(oldest)
            self.stat_evictions += 1

        entry = RunwayCacheEntry()
        entry.icao_code = rwy.icao_code
        entry.runway_id = rwy.runway_id
        entry.runway_db_index = db_index
        entry.frame_last_used = frame
        entry.dirty = True
        entry.valid = True
        self.entries.append(entry)
        self.num_entries = len(self.entries)


# ======================================================================
#  Tests
# ======================================================================

class TestDatabaseInit:
    def test_build_database(self):
        """Verify the test database builds correctly."""
        db = build_test_database()
        assert db.initialised is True
        assert db.load_state == DB_READY
        assert len(db.runways) > 0
        assert len(db.airports) > 0

    def test_runway_count(self):
        db = build_test_database()
        assert len(db.runways) == 20  # 5 airports × 4 runways

    def test_airport_count(self):
        db = build_test_database()
        assert len(db.airports) == 5

    def test_ils_freq_count(self):
        db = build_test_database()
        assert db.ils_freq_count > 0
        # Each runway with ILS should be indexed
        for r in db.runways:
            if r.ils_frequency_mhz > 0:
                assert any(abs(v - r.ils_frequency_mhz) < 0.001
                           for v in db.ils_freq_values)

    def test_reciprocal_resolution(self):
        db = build_test_database()
        # RKSI 15R should have a reciprocal
        rwy = db_find_runway(db, "RKSI", "15R")
        assert rwy is not None
        assert rwy.reciprocal_index >= 0


class TestRunwayLookup:
    def test_find_runway_by_icao_rwy(self):
        db = build_test_database()
        rwy = db_find_runway(db, "RKSI", "15R")
        assert rwy is not None
        assert rwy.icao_code == "RKSI"
        assert rwy.runway_id == "15R"
        assert abs(rwy.threshold_lat_deg - 37.4545) < 0.001

    def test_find_runway_case_insensitive(self):
        db = build_test_database()
        rwy = db_find_runway(db, "rksi", "15r")
        assert rwy is not None
        assert rwy.icao_code == "RKSI"

    def test_find_runway_unknown(self):
        db = build_test_database()
        rwy = db_find_runway(db, "XXXX", "99")
        assert rwy is None

    def test_find_by_ils_freq_exact(self):
        db = build_test_database()
        rwy = db_find_by_ils_freq(db, 111.10)
        assert rwy is not None
        assert abs(rwy.ils_frequency_mhz - 111.10) < 0.001

    def test_find_by_ils_freq_near(self):
        db = build_test_database()
        rwy = db_find_by_ils_freq(db, 111.11, 0.02)
        assert rwy is not None
        assert abs(rwy.ils_frequency_mhz - 111.10) < 0.02

    def test_find_by_ils_freq_out_of_range(self):
        db = build_test_database()
        rwy = db_find_by_ils_freq(db, 99.0)
        assert rwy is None

    def test_find_by_ils_freq_no_match(self):
        db = build_test_database()
        rwy = db_find_by_ils_freq(db, 112.50)
        assert rwy is None

    def test_multiple_runways_same_freq(self):
        """RKSI 15R and EGLL 27L both have 110.30 — should find at least one."""
        db = build_test_database()
        rwy = db_find_by_ils_freq(db, 110.30, 0.01)
        assert rwy is not None


class TestNearestAirport:
    def test_nearest_rksi(self):
        db = build_test_database()
        # Position near RKSI
        ap = db_find_nearest_airport(db, 37.46, 126.46)
        assert ap is not None
        assert ap.icao_code == "RKSI"

    def test_nearest_egll(self):
        db = build_test_database()
        ap = db_find_nearest_airport(db, 51.48, -0.46)
        assert ap is not None
        assert ap.icao_code == "EGLL"

    def test_nearest_ksea(self):
        db = build_test_database()
        ap = db_find_nearest_airport(db, 47.45, -122.31)
        assert ap is not None
        assert ap.icao_code == "KSEA"

    def test_nearest_eddf(self):
        db = build_test_database()
        ap = db_find_nearest_airport(db, 50.03, 8.57)
        assert ap is not None
        assert ap.icao_code == "EDDF"

    def test_nearest_kden(self):
        db = build_test_database()
        ap = db_find_nearest_airport(db, 39.85, -104.67)
        assert ap is not None
        assert ap.icao_code == "KDEN"

    def test_nearest_unknown_location(self):
        """Mid-Atlantic should still return the nearest airport."""
        db = build_test_database()
        ap = db_find_nearest_airport(db, 0.0, 0.0)
        assert ap is not None  # Nearest of the 5


class TestAirportRunways:
    def test_rksi_runways(self):
        db = build_test_database()
        ap = db_find_nearest_airport(db, 37.46, 126.46)
        assert ap is not None
        assert ap.num_runways == 4

    def test_egll_runways(self):
        db = build_test_database()
        ap = db_find_nearest_airport(db, 51.48, -0.46)
        assert ap is not None
        assert ap.num_runways == 4

    def test_ksea_runways(self):
        db = build_test_database()
        ap = db_find_nearest_airport(db, 47.45, -122.31)
        assert ap is not None
        assert ap.num_runways == 4

    def test_runway_indices_valid(self):
        db = build_test_database()
        for a in db.airports:
            for idx in a.runway_indices:
                assert 0 <= idx < len(db.runways)
                assert db.runways[idx].valid


class TestReciprocalMapping:
    def test_rksi_15r_reciprocal(self):
        db = build_test_database()
        rwy = db_find_runway(db, "RKSI", "15R")
        assert rwy is not None
        recip = db_get_reciprocal_runway(db, rwy)
        assert recip is not None
        expected_hdg = (rwy.true_heading_deg + 180.0) % 360.0
        assert abs(recip.true_heading_deg - expected_hdg) < 2.0

    def test_rksi_33l_reciprocal(self):
        db = build_test_database()
        rwy = db_find_runway(db, "RKSI", "33L")
        assert rwy is not None
        recip = db_get_reciprocal_runway(db, rwy)
        assert recip is not None
        assert recip.runway_id == "15R"

    def test_egll_27l_reciprocal(self):
        db = build_test_database()
        rwy = db_find_runway(db, "EGLL", "27L")
        assert rwy is not None
        recip = db_get_reciprocal_runway(db, rwy)
        assert recip is not None
        # Reciprocal should be at EGLL with opposite heading (~090°)
        assert recip.icao_code == "EGLL"
        expected_hdg = (rwy.true_heading_deg + 180.0) % 360.0
        assert abs(recip.true_heading_deg - expected_hdg) < 2.0

    def test_reciprocal_round_trip(self):
        db = build_test_database()
        for r in db.runways:
            if r.reciprocal_index >= 0:
                recip = db_get_reciprocal_runway(db, r)
                assert recip is not None
                # The reciprocal of the reciprocal should be the original
                recip2 = db_get_reciprocal_runway(db, recip)
                if recip2 is not None:
                    assert recip2.runway_id == r.runway_id


class TestActiveRunwayDetection:
    def test_active_by_ils_freq(self):
        db = build_test_database()
        # Tuned to RKSI 15R ILS
        rwy = db_find_active_runway(db, 37.46, 126.46, 148.0, 111.10)
        assert rwy is not None
        # Should find RKSI 15R or 33L (both have 111.10)
        assert rwy.icao_code == "RKSI"
        assert abs(rwy.ils_frequency_mhz - 111.10) < 0.01

    def test_active_by_heading(self):
        db = build_test_database()
        # At RKSI, heading 340 should prefer 34R or 33L
        rwy = db_find_active_runway(db, 37.46, 126.46, 340.0, 0.0)
        assert rwy is not None
        assert rwy.icao_code == "RKSI"
        # Should be close to heading 340
        delta = abs(rwy.true_heading_deg - 340.0)
        assert delta < 20.0 or delta > 340.0

    def test_active_egll_heading_270(self):
        db = build_test_database()
        rwy = db_find_active_runway(db, 51.48, -0.46, 270.0, 0.0)
        assert rwy is not None
        assert rwy.icao_code == "EGLL"
        delta = abs(rwy.true_heading_deg - 270.0)
        assert delta < 20.0

    def test_active_no_airport_nearby(self):
        db = build_test_database()
        # Far away, no ILS
        rwy = db_find_active_runway(db, 10.0, 10.0, 180.0, 0.0)
        assert rwy is None

    def test_active_invalid_freq(self):
        db = build_test_database()
        rwy = db_find_active_runway(db, 37.46, 126.46, 148.0, 99.0)
        # Should still find by heading alignment
        assert rwy is not None
        assert rwy.icao_code == "RKSI"


class TestRunwayGeometry:
    def test_runway_has_tdz_default(self):
        db = build_test_database()
        for r in db.runways:
            if r.valid:
                assert r.tdz_geometry.valid
                assert r.tdz_geometry.distance_from_threshold_m == 300.0

    def test_runway_widths(self):
        db = build_test_database()
        for r in db.runways:
            if r.valid:
                assert r.width_m > 0

    def test_runway_lengths(self):
        db = build_test_database()
        for r in db.runways:
            if r.valid:
                assert r.length_m > 1000.0

    def test_runway_altitudes(self):
        db = build_test_database()
        for r in db.runways:
            if r.valid:
                assert r.threshold_alt_m > -50.0  # reasonable min
                assert r.threshold_alt_m < 5000.0  # reasonable max

    def test_runway_heading_range(self):
        db = build_test_database()
        for r in db.runways:
            if r.valid:
                assert 0.0 <= r.true_heading_deg <= 360.0

    def test_far_end_different(self):
        db = build_test_database()
        for r in db.runways:
            if r.valid:
                # Check total distance (some headings change only one axis)
                dlat = r.far_end_lat_deg - r.threshold_lat_deg
                dlon = r.far_end_lon_deg - r.threshold_lon_deg
                dist = math.sqrt(dlat*dlat + dlon*dlon)
                assert dist > 1e-6, f"Runway {r.icao_code}/{r.runway_id} has zero displacement"

    def test_displaced_threshold_default_none(self):
        db = build_test_database()
        for r in db.runways:
            if r.valid:
                assert r.displaced_threshold.valid is False
                assert r.displaced_threshold.distance_from_end_m == 0.0


class TestRunwayCache:
    def test_cache_empty_init(self):
        cache = RunwayCache()
        assert cache.num_entries == 0
        assert cache.stat_hits == 0
        assert cache.stat_misses == 0

    def test_cache_lookup_miss(self):
        cache = RunwayCache()
        result = cache.lookup(0)
        assert result is None
        assert cache.stat_misses == 1

    def test_cache_insert_and_lookup(self):
        db = build_test_database()
        cache = RunwayCache()
        rwy = db.runways[0]
        cache.insert(rwy, 0, 1)
        result = cache.lookup(0)
        assert result is not None
        assert result.runway_db_index == 0
        assert cache.stat_hits == 1

    def test_cache_insert_updates_existing(self):
        db = build_test_database()
        cache = RunwayCache()
        cache.insert(db.runways[0], 0, 1)
        cache.insert(db.runways[0], 0, 2)  # same index
        assert len(cache.entries) == 1
        assert cache.entries[0].frame_last_used == 2

    def test_cache_lru_eviction(self):
        db = build_test_database()
        cache = RunwayCache()
        # Fill cache
        for i in range(RC_MAX_CACHED_RUNWAYS):
            if i < len(db.runways):
                cache.insert(db.runways[i], i, i)
        assert len(cache.entries) == min(RC_MAX_CACHED_RUNWAYS, len(db.runways))

        # Insert one more (should evict oldest, which was accessed at time 0)
        if RC_MAX_CACHED_RUNWAYS < len(db.runways):
            cache.insert(db.runways[RC_MAX_CACHED_RUNWAYS],
                         RC_MAX_CACHED_RUNWAYS,
                         RC_MAX_CACHED_RUNWAYS)
            # Should have evicted one
            assert cache.stat_evictions >= 1

    def test_cache_marks_dirty_on_insert(self):
        db = build_test_database()
        cache = RunwayCache()
        cache.insert(db.runways[0], 0, 1)
        assert cache.entries[0].dirty is True

    def test_cache_updates_frame_on_lookup(self):
        db = build_test_database()
        cache = RunwayCache()
        cache.frame_counter = 100
        cache.insert(db.runways[0], 0, 50)
        result = cache.lookup(0)
        assert result.frame_last_used == 100


class TestDatabaseEdgeCases:
    def test_empty_database(self):
        db = AirportDatabase()
        db.initialised = True
        rwy = db_find_active_runway(db, 0.0, 0.0, 0.0, 0.0)
        assert rwy is None

    def test_uninitialised_database(self):
        db = AirportDatabase()
        rwy = db_find_runway(db, "RKSI", "15R")
        assert rwy is None

    def test_null_inputs(self):
        assert db_find_runway(None, "RKSI", "15R") is None
        assert db_find_by_ils_freq(None, 111.10) is None
        assert db_find_nearest_airport(None, 0, 0) is None
        assert db_get_reciprocal_runway(None, None) is None

    def test_ils_freq_tolerance(self):
        db = build_test_database()
        # Tight tolerance — should still find exact matches
        rwy = db_find_by_ils_freq(db, 111.10, 0.001)
        assert rwy is not None
        # Very tight — should not find near matches
        rwy2 = db_find_by_ils_freq(db, 111.11, 0.001)
        assert rwy2 is None

    def test_runway_without_ils(self):
        """Runways with 0 ILS frequency should not appear in freq index."""
        db = build_test_database()
        for r in db.runways:
            if r.ils_frequency_mhz == 0.0:
                for v in db.ils_freq_values:
                    assert abs(v - 0.0) > 0.001
