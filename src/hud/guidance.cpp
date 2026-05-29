// ============================================================================
//  Conformal HUD – ILS Guidance / Steering Logic Implementation
//  MSFS 2024  ·  C++17  ·  WASM
//
//  Implements conformal ILS beam projection and Boeing HGS-style steering
//  guidance.
// ============================================================================

#include "../../include/hud/guidance.h"
#include "../../include/hud/runway_projection.h"
#include "../../include/projection.h"

// ============================================================================
//  1.  ILS beam geometry computation
// ============================================================================

void guidance_compute_beam(Vec3            ac_ref,
                           FLOAT64         ac_hdg,
                           const RunwayEnd* runway_end,
                           ILSBeam*        ils) {
    (void)ac_hdg;  // unused for beam geometry, but may be used for offset

    if (ils == 0 || runway_end == 0 || !runway_end->valid) {
        if (ils) ils->valid = false;
        return;
    }

    // --- Touchdown point: ~300 m past the threshold along the runway ---
    const FLOAT64 hdg_rad = PROJ_DEG2RAD(runway_end->true_heading);
    const FLOAT64 cos_lat = proj_cos(PROJ_DEG2RAD(runway_end->threshold.z));

    // Touchdown is 300 m past threshold
    const FLOAT64 td_distance = 300.0;
    const FLOAT64 dlat_td = PROJ_RAD2DEG(td_distance * proj_cos(hdg_rad) / PROJ_EARTH_RADIUS_M);
    const FLOAT64 dlon_td = PROJ_RAD2DEG(td_distance * proj_sin(hdg_rad) / (PROJ_EARTH_RADIUS_M * cos_lat));

    ils->touchdown.x = runway_end->threshold.x + dlon_td;
    ils->touchdown.y = runway_end->threshold.y;   // same elevation
    ils->touchdown.z = runway_end->threshold.z + dlat_td;

    ils->localizer_bearing = runway_end->true_heading;
    ils->gs_angle_deg = 3.0;  // standard 3° glideslope

    // Compute DME distance from aircraft to threshold
    Vec3 neu_offset = proj_vec3_zero();
    proj_world_to_neu(runway_end->threshold, ac_ref, &neu_offset);
    const FLOAT64 dist_m = proj_vec3_len(neu_offset);
    ils->ref_dme_nm = dist_m / 1852.0;  // metres to nautical miles

    // --- Compute intercept points ---
    // For localizer: project a point 1 NM ahead along the localizer course
    const FLOAT64 dme_dist_m = 1852.0;  // 1 NM
    const FLOAT64 loc_dlat = PROJ_RAD2DEG(dme_dist_m * proj_cos(hdg_rad) / PROJ_EARTH_RADIUS_M);
    const FLOAT64 loc_dlon = PROJ_RAD2DEG(dme_dist_m * proj_sin(hdg_rad) / (PROJ_EARTH_RADIUS_M * cos_lat));

    ils->loc_intercept.x = ils->touchdown.x + loc_dlon;
    ils->loc_intercept.y = ils->touchdown.y;
    ils->loc_intercept.z = ils->touchdown.z + loc_dlat;

    // For glideslope: compute a point along the 3° glideslope
    const FLOAT64 gs_height = dme_dist_m * proj_tan(PROJ_DEG2RAD(ils->gs_angle_deg));
    ils->gs_intercept.x = ils->touchdown.x + loc_dlon;
    ils->gs_intercept.y = ils->touchdown.y + gs_height * 0.5;  // half height for intercept
    ils->gs_intercept.z = ils->touchdown.z + loc_dlat;

    ils->valid = true;
}

// ============================================================================
//  2.  Guidance computation & projection
// ============================================================================

void guidance_compute(const ILSBeam*      ils,
                      Vec3                ac_ref,
                      const Mat4*         b2w,
                      Vec3                eye_offset,
                      FLOAT64             focal_px,
                      int                 screen_w,
                      int                 screen_h,
                      GuidanceState*      guidance) {
    if (guidance == 0) {
        return;
    }

    // Reset
    guidance->valid = false;
    guidance->loc_visible = false;
    guidance->gs_visible = false;

    if (ils == 0 || !ils->valid || b2w == 0) {
        return;
    }

    // --- Compute LOC beam intercept projection ---
    {
        bool behind = false;
        Vec2 screen = guidance_project_point(
            ils->loc_intercept, ac_ref, b2w, eye_offset,
            focal_px, screen_w, screen_h, &behind);

        if (!behind && screen.x >= -1000.0 && screen.x <= (FLOAT64)(screen_w + 1000) &&
                      screen.y >= -1000.0 && screen.y <= (FLOAT64)(screen_h + 1000)) {
            guidance->loc_target = screen;
            guidance->loc_visible = true;
        }
    }

    // --- Compute GS beam intercept projection ---
    {
        bool behind = false;
        Vec2 screen = guidance_project_point(
            ils->gs_intercept, ac_ref, b2w, eye_offset,
            focal_px, screen_w, screen_h, &behind);

        if (!behind && screen.x >= -1000.0 && screen.x <= (FLOAT64)(screen_w + 1000) &&
                      screen.y >= -1000.0 && screen.y <= (FLOAT64)(screen_h + 1000)) {
            guidance->gs_target = screen;
            guidance->gs_visible = true;
        }
    }

    // --- Capture logic ---
    // Localizer captured when deviation < 0.5 dots
    guidance->loc_captured = (proj_fabs(guidance->loc_error_dots) < 0.5);
    guidance->gs_captured  = (proj_fabs(guidance->gs_error_dots) < 0.5);

    guidance->valid = true;
}

// ============================================================================
//  3.  Flight Director
// ============================================================================

void guidance_flight_director(GuidanceState* guidance,
                              FLOAT64        ac_pitch,
                              FLOAT64        ac_bank,
                              const ILSBeam* ils) {
    (void)ac_bank;

    if (guidance == 0 || ils == 0 || !ils->valid) {
        return;
    }

    // --- Pitch steering ---
    // Command pitch to capture and hold the glideslope
    // GS error in degrees: positive = above glideslope
    // We want to pitch down if above, pitch up if below
    FLOAT64 gs_deg = guidance->gs_error_deg;
    FLOAT64 desired_pitch = ils->gs_angle_deg - gs_deg;  // e.g., 3.0° - (+1.0°) = 2.0° pitch down
    if (desired_pitch < -5.0) desired_pitch = -5.0;
    if (desired_pitch > 15.0) desired_pitch = 15.0;
    guidance->steering_pitch = desired_pitch - ac_pitch;  // error in degrees

    // --- Bank steering ---
    // Command bank to capture and hold the localizer
    FLOAT64 loc_deg = guidance->loc_error_deg;
    // Simple proportional guidance
    FLOAT64 desired_bank = -loc_deg * 3.0;  // scale factor
    if (desired_bank > 25.0) desired_bank = 25.0;
    if (desired_bank < -25.0) desired_bank = -25.0;
    guidance->steering_bank = desired_bank;
}

// ============================================================================
//  4.  Debug logging
// ============================================================================

void guidance_debug_log(const GuidanceState* guidance) {
    if (guidance == 0) {
        MSFS_Log("[C_HUD_GUIDE] GuidanceState: NULL");
        return;
    }

    if (!guidance->valid) {
        MSFS_Log("[C_HUD_GUIDE] GuidanceState: INVALID");
        return;
    }

    MSFS_Log("[C_HUD_GUIDE] LOC_err=%.3f°(%.2f dots)  GS_err=%.3f°(%.2f dots)  "
             "CAPTURED(LOC=%d GS=%d)  "
             "VIS(LOC=%d GS=%d)  "
             "STEER(pitch=%.1f° bank=%.1f°)",
             guidance->loc_error_deg, guidance->loc_error_dots,
             guidance->gs_error_deg, guidance->gs_error_dots,
             (int)guidance->loc_captured, (int)guidance->gs_captured,
             (int)guidance->loc_visible, (int)guidance->gs_visible,
             guidance->steering_pitch, guidance->steering_bank);
}

void guidance_debug_beam(const ILSBeam* ils) {
    if (ils == 0 || !ils->valid) {
        MSFS_Log("[C_HUD_GUIDE] ILSBeam: INVALID");
        return;
    }

    MSFS_Log("[C_HUD_GUIDE] ILSBeam: TD=(%.4f, %.4f, %.1f)  CRS=%.1f°  "
             "GS_ANGLE=%.1f°  DME=%.1f NM",
             ils->touchdown.x, ils->touchdown.z, ils->touchdown.y,
             ils->localizer_bearing, ils->gs_angle_deg, ils->ref_dme_nm);
}
