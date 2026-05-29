// ============================================================================
//  Conformal HUD – Runway Projection Engine Implementation
//  MSFS 2024  ·  C++17  ·  WASM
//
//  Implements the runway detection, corner computation, and conformal
//  HUD projection pipeline.
//
//  v2.2.0 additions:
//    · Database-integrated runway detection (runway_detect_active_db)
//    · Displaced threshold + reciprocal support (runway_compute_end_from_record)
// ============================================================================

#include "../../include/hud/runway_projection.h"
#include "../../include/projection.h"
#include "../../include/hud/airport_database.h"

// ============================================================================
//  1.  ILS frequency extraction
// ============================================================================

FLOAT64 runway_get_ils_frequency(void) {
    // Read NAV1 frequency from ModuleState (populated by
    // module_update_read_vars() via NAV ACTIVE FREQUENCY:1).
    // Returns the tuned frequency in MHz, or 0.0 if not available.
    if (g_state.initialised && g_state.nav1_freq_mhz > 0.0) {
        return g_state.nav1_freq_mhz;
    }
    return 0.0;
}

// ============================================================================
//  2.  Runway corner computation
// ============================================================================

void runway_compute_corners(const RunwayEnd* end, RunwayCorners* out_corners) {
    if (end == 0 || out_corners == 0 || !end->valid) {
        if (out_corners) {
            out_corners->valid = false;
            out_corners->vert_count = 0;
        }
        return;
    }

    const FLOAT64 hdg_rad = PROJ_DEG2RAD(end->true_heading);
    const FLOAT64 half_w = end->width_m * 0.5;

    // Runway direction vector (from threshold toward far end)
    // In NEU frame: east = sin(hdg), north = cos(hdg)
    const FLOAT64 dir_east = proj_sin(hdg_rad);
    const FLOAT64 dir_north = proj_cos(hdg_rad);

    // Perpendicular vector (left side of runway)
    const FLOAT64 perp_east = -dir_north;
    const FLOAT64 perp_north = dir_east;

    // Compute runway length from threshold to far end (metres)
    const FLOAT64 dlat = PROJ_DEG2RAD(end->far_end.z - end->threshold.z);
    const FLOAT64 dlon = PROJ_DEG2RAD(end->far_end.x - end->threshold.x);
    const FLOAT64 cos_lat = proj_cos(PROJ_DEG2RAD(end->threshold.z));
    const FLOAT64 length_m = proj_sqrt(
        (dlat * PROJ_EARTH_RADIUS_M) * (dlat * PROJ_EARTH_RADIUS_M) +
        (dlon * PROJ_EARTH_RADIUS_M * cos_lat) * (dlon * PROJ_EARTH_RADIUS_M * cos_lat)
    );

    // Safety: use default length if computation fails
    FLOAT64 use_length = length_m;
    if (use_length < 100.0 || use_length > 10000.0) {
        use_length = 3000.0;  // default 3 km
    }

    // The runway centerline in local NEU (relative to threshold)
    // Go 500 m beyond far end to ensure visibility
    const FLOAT64 extend = use_length + 500.0;

    // Convert threshold lat/lon to NEU (using threshold as reference)
    // For corners, we need delta in degrees
    const FLOAT64 dlat_per_m = 1.0 / PROJ_EARTH_RADIUS_M;         // radians per metre north
    const FLOAT64 dlon_per_m = 1.0 / (PROJ_EARTH_RADIUS_M * cos_lat); // radians per metre east

    // Near-left corner (threshold + half-width to left)
    const FLOAT64 nl_lat = end->threshold.z + PROJ_RAD2DEG(-half_w * perp_north * dlat_per_m);
    const FLOAT64 nl_lon = end->threshold.x + PROJ_RAD2DEG(-half_w * perp_east * dlon_per_m);
    const FLOAT64 nl_alt = end->threshold.y;

    // Near-right corner (threshold + half-width to right)
    const FLOAT64 nr_lat = end->threshold.z + PROJ_RAD2DEG(half_w * perp_north * dlat_per_m);
    const FLOAT64 nr_lon = end->threshold.x + PROJ_RAD2DEG(half_w * perp_east * dlon_per_m);
    const FLOAT64 nr_alt = end->threshold.y;

    // Far-left corner (far end + half-width to left)
    const FLOAT64 fl_lat = end->threshold.z + PROJ_RAD2DEG(extend * dir_north * dlat_per_m - half_w * perp_north * dlat_per_m);
    const FLOAT64 fl_lon = end->threshold.x + PROJ_RAD2DEG(extend * dir_east * dlon_per_m - half_w * perp_east * dlon_per_m);
    const FLOAT64 fl_alt = end->threshold.y;

    // Far-right corner
    const FLOAT64 fr_lat = end->threshold.z + PROJ_RAD2DEG(extend * dir_north * dlat_per_m + half_w * perp_north * dlat_per_m);
    const FLOAT64 fr_lon = end->threshold.x + PROJ_RAD2DEG(extend * dir_east * dlon_per_m + half_w * perp_east * dlon_per_m);
    const FLOAT64 fr_alt = end->threshold.y;

    // Store vertices in order: near-left, far-left, far-right, near-right
    out_corners->verts[0] = runway_make_position(nl_lon, nl_lat, nl_alt);  // near-left
    out_corners->verts[1] = runway_make_position(fl_lon, fl_lat, fl_alt);  // far-left
    out_corners->verts[2] = runway_make_position(fr_lon, fr_lat, fr_alt);  // far-right
    out_corners->verts[3] = runway_make_position(nr_lon, nr_lat, nr_alt);  // near-right

    // Extended: add extended centerline points (for centerline cue)
    // Far extended point (2x distance)
    const FLOAT64 ext2 = use_length * 2.5;
    const FLOAT64 ext_lat = end->threshold.z + PROJ_RAD2DEG(ext2 * dir_north * dlat_per_m);
    const FLOAT64 ext_lon = end->threshold.x + PROJ_RAD2DEG(ext2 * dir_east * dlon_per_m);
    out_corners->verts[4] = runway_make_position(
        (nl_lon + nr_lon) * 0.5, (nl_lat + nr_lat) * 0.5, nl_alt);  // near center
    out_corners->verts[5] = runway_make_position(
        (fl_lon + fr_lon) * 0.5, (fl_lat + fr_lat) * 0.5, fl_alt);  // far center
    out_corners->verts[6] = runway_make_position(ext_lon, ext_lat, nl_alt);   // extended center

    out_corners->vert_count = 7;
    out_corners->valid = true;
}

// ============================================================================
//  3.  Conformal projection pipeline
// ============================================================================

void runway_project_to_hud(const RunwayCorners* corners,
                            Vec3                  ac_ref,
                            const Mat4*           b2w,
                            Vec3                  eye_offset,
                            FLOAT64               focal_px,
                            int                   screen_w,
                            int                   screen_h,
                            ProjectedRunway*      out_proj) {
    if (out_proj == 0) { return; }
    out_proj->valid = false;
    out_proj->visible_count = 0;

    if (corners == 0 || !corners->valid || b2w == 0) {
        return;
    }

    const int n = corners->vert_count;
    if (n > 8) {  // safety check
        return;
    }

    for (int i = 0; i < n; ++i) {
        bool behind = false;
        Vec2 screen = { -9999.0, -9999.0 };

        proj_world_to_hud(corners->verts[i], ac_ref, b2w, eye_offset,
                           focal_px, screen_w, screen_h,
                           &screen, &behind);

        out_proj->screen_corners[i] = screen;
        out_proj->behind[i] = behind;

        if (!behind && screen.x >= -5000.0 && screen.x < (FLOAT64)(screen_w + 5000) &&
                       screen.y >= -5000.0 && screen.y < (FLOAT64)(screen_h + 5000)) {
            out_proj->visible_count++;
        }
    }

    out_proj->valid = (out_proj->visible_count >= 2);
}

// ============================================================================
//  4.  Active runway detection (well-known airport database)
// ============================================================================

/// Built-in small airport/runway database for ILS approaches.
/// Maps ILS frequency → runway data.
/// In production, this should be replaced by MSFS airport facilities API.
typedef struct ILSRunwayEntry {
    FLOAT64 ils_freq_mhz;      // ILS frequency
    const char* icao;          // airport ICAO code
    const char* rwy_id;        // runway identifier
    FLOAT64 threshold_lat;     // threshold latitude (degrees)
    FLOAT64 threshold_lon;     // threshold longitude (degrees)
    FLOAT64 threshold_alt_m;   // threshold altitude (metres)
    FLOAT64 true_heading;      // runway true heading (degrees)
    FLOAT64 width_m;           // runway width (metres)
    FLOAT64 length_m;          // runway length (metres)
    FLOAT64 far_end_lat;       // far end latitude
    FLOAT64 far_end_lon;       // far end longitude
} ILSRunwayEntry;

// Well-known runways for testing & initial support
static const ILSRunwayEntry g_runway_db[] = {
    // Incheon (RKSI) 15R  ILS 111.10
    { 111.10, "RKSI", "15R", 37.4545, 126.4446, 7.0, 148.0, 60.0, 3750.0,
      37.4850, 126.4680 },
    // Incheon (RKSI) 16L  ILS 111.30
    { 111.30, "RKSI", "16L", 37.4670, 126.4630, 7.0, 160.0, 60.0, 3750.0,
      37.4970, 126.4860 },
    // London Heathrow (EGLL) 27L  ILS 110.30
    { 110.30, "EGLL", "27L", 51.4775, -0.4614, 25.0, 270.0, 45.0, 3900.0,
      51.4775, -0.4150 },
    // London Heathrow (EGLL) 27R  ILS 109.50
    { 109.50, "EGLL", "27R", 51.4720, -0.4835, 25.0, 270.0, 45.0, 3660.0,
      51.4720, -0.4380 },
    // Seattle KSEA 16R  ILS 110.30
    { 110.30, "KSEA", "16R", 47.4320, -122.3110, 106.0, 160.0, 46.0, 3628.0,
      47.4560, -122.3060 },
    // Seattle KSEA 34L  ILS 109.90
    { 109.90, "KSEA", "34L", 47.4560, -122.3060, 106.0, 340.0, 46.0, 3628.0,
      47.4320, -122.3110 },
    // Frankfurt EDDF 07R  ILS 111.15
    { 111.15, "EDDF", "07R", 50.0310, 8.5620, 100.0, 70.0, 45.0, 4000.0,
      50.0340, 8.5900 },
    // Frankfurt EDDF 25L  ILS 110.90
    { 110.90, "EDDF", "25L", 50.0340, 8.5900, 100.0, 250.0, 45.0, 4000.0,
      50.0310, 8.5620 },
    // Denver KDEN 35R  ILS 111.95
    { 111.95, "KDEN", "35R", 39.8510, -104.6720, 1625.0, 350.0, 46.0, 4877.0,
      39.8860, -104.6740 },
    // Denver KDEN 34L  ILS 111.70
    { 111.70, "KDEN", "34L", 39.8350, -104.6820, 1625.0, 340.0, 46.0, 4877.0,
      39.8700, -104.6840 },
    // Sentinels
    { 0.0, "", "", 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0 }
};

bool runway_detect_active(RunwayEnd* out_end) {
    if (out_end == 0) {
        return false;
    }

    // Read the ILS frequency (placeholder – in production this reads the
    // SimVar token).
    const FLOAT64 freq = runway_get_ils_frequency();

    if (freq <= 100.0 || freq >= 120.0) {
        // Invalid frequency – try using the hardcoded RKSI 15R as default
        // for testing.
        // In production, we'd return false and let the system indicate
        // "no runway detected".
        return false;
    }

    // Search the database for matching frequency
    for (int i = 0; g_runway_db[i].ils_freq_mhz > 0.0; ++i) {
        const ILSRunwayEntry* entry = &g_runway_db[i];
        const FLOAT64 diff = proj_fabs(freq - entry->ils_freq_mhz);
        if (diff < 0.01) {
            // Match found
            out_end->threshold = runway_make_position(
                entry->threshold_lon, entry->threshold_lat, entry->threshold_alt_m);
            out_end->far_end = runway_make_position(
                entry->far_end_lon, entry->far_end_lat, entry->threshold_alt_m);
            out_end->true_heading = entry->true_heading;
            out_end->width_m = entry->width_m;
            out_end->valid = true;
            return true;
        }
    }

    return false;
}

// ============================================================================
//  5.  Debug logging
// ============================================================================

void runway_debug_log(const ProjectedRunway* proj) {
    if (proj == 0 || !proj->valid) {
        MSFS_Log("[C_HUD_RWY] ProjectedRunway: INVALID");
        return;
    }

    MSFS_Log("[C_HUD_RWY] ProjectedRunway: %d verts, %d visible, valid=%d",
             proj->corners.vert_count, proj->visible_count, (int)proj->valid);

    for (int i = 0; i < proj->corners.vert_count && i < 8; ++i) {
        MSFS_Log("[C_HUD_RWY]   V[%d]: screen=(%.1f, %.1f) behind=%d",
                 i, proj->screen_corners[i].x, proj->screen_corners[i].y,
                 (int)proj->behind[i]);
    }
}

// ============================================================================
//  6.  Database-integrated runway detection
// ============================================================================

bool runway_detect_active_db(AirportDatabase* db,
                              FLOAT64 ac_lat_deg,
                              FLOAT64 ac_lon_deg,
                              FLOAT64 ac_hdg_true,
                              FLOAT64 ils_freq_mhz,
                              RunwayEnd* out_end) {
    if (out_end == 0) return false;

    // Clear output
    out_end->valid = false;

    if (db == 0 || !db->initialised || db->load_state != DB_READY) {
        // Fallback to legacy
        return runway_detect_active(out_end);
    }

    // Strategy 1: Try ILS frequency lookup
    if (ils_freq_mhz > 100.0 && ils_freq_mhz < 120.0) {
        const RunwayRecord* rwy = db_find_by_ils_freq(db, ils_freq_mhz, 0.01);
        if (rwy != 0) {
            return runway_compute_end_from_record(rwy, false, out_end);
        }
    }

    // Strategy 2: Nearest airport → heading alignment
    const RunwayRecord* best_rwy = 0;
    FLOAT64 best_delta = 90.0;  // only accept < 90 deg alignment

    const AirportRecord* airport = db_find_nearest_airport(db, ac_lat_deg, ac_lon_deg);
    if (airport != 0) {
        for (int i = 0; i < airport->num_runways; ++i) {
            const int idx = airport->runway_indices[i];
            if (idx < 0 || idx >= db->num_runways) continue;
            const RunwayRecord* rwy = &db->runways[idx];
            if (!rwy->valid) continue;

            // Compute heading difference
            FLOAT64 d = ac_hdg_true - rwy->true_heading_deg;
            while (d > 180.0) d -= 360.0;
            while (d < -180.0) d += 360.0;
            const FLOAT64 delta = (d < 0.0) ? -d : d;

            if (delta < best_delta) {
                best_delta = delta;
                best_rwy = rwy;
            }
        }
    }

    if (best_rwy != 0) {
        return runway_compute_end_from_record(best_rwy, false, out_end);
    }

    // Strategy 3: Fallback to legacy detection
    return runway_detect_active(out_end);
}

// ============================================================================
//  7.  Runway geometry from database record
// ============================================================================

bool runway_compute_end_from_record(const RunwayRecord* rwy,
                                     bool use_reciprocal,
                                     RunwayEnd* out_end) {
    if (rwy == 0 || out_end == 0 || !rwy->valid) return false;

    const RunwayRecord* active_rwy = rwy;
    FLOAT64 threshold_lat = rwy->threshold_lat_deg;
    FLOAT64 threshold_lon = rwy->threshold_lon_deg;
    FLOAT64 threshold_alt = rwy->threshold_alt_m;
    FLOAT64 heading = rwy->true_heading_deg;
    FLOAT64 width = rwy->width_m;
    FLOAT64 far_lat = rwy->far_end_lat_deg;
    FLOAT64 far_lon = rwy->far_end_lon_deg;

    if (use_reciprocal) {
        // Swap: the far end becomes the threshold
        // Heading is reciprocal (opposite direction)
        threshold_lat = rwy->far_end_lat_deg;
        threshold_lon = rwy->far_end_lon_deg;
        far_lat = rwy->threshold_lat_deg;
        far_lon = rwy->threshold_lon_deg;
        heading = rwy->true_heading_deg + 180.0;
        if (heading >= 360.0) heading -= 360.0;
    }

    // Apply displaced threshold offset if applicable
    if (rwy->displaced_threshold.valid && rwy->displaced_threshold.landing_displaced) {
        const FLOAT64 disp_m = rwy->displaced_threshold.distance_from_end_m;
        const FLOAT64 hdg_rad = PROJ_DEG2RAD(heading);
        const FLOAT64 cos_lat = proj_cos(PROJ_DEG2RAD(threshold_lat));
        const FLOAT64 dlat = -disp_m * proj_cos(hdg_rad) / PROJ_EARTH_RADIUS_M;
        const FLOAT64 dlon = -disp_m * proj_sin(hdg_rad) / (PROJ_EARTH_RADIUS_M * cos_lat);
        threshold_lat += PROJ_RAD2DEG(dlat);
        threshold_lon += PROJ_RAD2DEG(dlon);
        // Reduce effective runway length
        const FLOAT64 far_dlat = -disp_m * proj_cos(hdg_rad) / PROJ_EARTH_RADIUS_M;
        const FLOAT64 far_dlon = -disp_m * proj_sin(hdg_rad) / (PROJ_EARTH_RADIUS_M * cos_lat);
        far_lat += PROJ_RAD2DEG(far_dlat);
        far_lon += PROJ_RAD2DEG(far_dlon);
    }

    // Populate RunwayEnd (note: positions use lon, alt, lat Vec3 order)
    out_end->threshold = runway_make_position(threshold_lon, threshold_lat, threshold_alt);
    out_end->far_end = runway_make_position(far_lon, far_lat, threshold_alt);
    out_end->true_heading = heading;
    out_end->width_m = width;
    out_end->valid = true;

    return true;
}
