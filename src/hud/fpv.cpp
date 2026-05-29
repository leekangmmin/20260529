// ============================================================================
//  Conformal HUD – Flight Path Vector Implementation
//  MSFS 2024  ·  C++17  ·  WASM
//
//  v2.3.0 — Added profile-aware FPV alignment offsets for per-aircraft
//  calibration.  The FPV position is now corrected by the aircraft
//  profile's fpv_align_offset_x/y to account for small differences
//  in HUD optical centre between aircraft types.
// ============================================================================

#include "../../include/hud/fpv.h"
#include "../../include/projection.h"

// ============================================================================
//  1.  FPV computation
// ============================================================================

bool fpv_compute(FPVState* fpv) {
    if (fpv == 0) {
        return false;
    }

    // Reset state
    fpv->valid = false;
    fpv->on_screen = false;
    fpv->screen_pos.x = -9999.0;
    fpv->screen_pos.y = -9999.0;

    // --- Clamp inputs to sensible ranges ---
    const FLOAT64 gs = proj_fmax(fpv->groundspeed_ms, 0.1);
    const FLOAT64 vs = proj_clamp(fpv->vertical_speed_ms, -100.0, 100.0);
    const FLOAT64 hdg = proj_fmod(fpv->heading_deg_true + 360.0, 360.0);
    const FLOAT64 track = proj_fmod(fpv->track_deg_true + 360.0, 360.0);

    // --- Compute drift angle ---
    FLOAT64 drift = track - hdg;
    if (drift > 180.0) drift -= 360.0;
    if (drift < -180.0) drift += 360.0;

    fpv->drift_angle = drift;

    // --- Compute FPV pitch angle ---
    const FLOAT64 fpa_rad = proj_atan2(vs, gs);
    fpv->fpv_pitch = PROJ_RAD2DEG(fpa_rad);

    // --- FPV heading = ground track ---
    fpv->fpv_heading = track;

    // --- Debug info ---
    fpv->debug_airspeed = gs;
    fpv->debug_wind_correction = drift;

    fpv->valid = true;
    return true;
}

// ============================================================================
//  2.  FPV projection to HUD  (v2.3.0: profile-aware alignment)
// ============================================================================

void fpv_project_to_hud(FPVState*         fpv,
                         Vec3              ac_ref,
                         FLOAT64           ac_hdg,
                         FLOAT64           ac_pitch,
                         FLOAT64           ac_bank,
                         const Mat4*       b2w,
                         Vec3              eye_offset,
                         FLOAT64           focal_px,
                         int               screen_w,
                         int               screen_h,
                         FLOAT64           align_off_x,
                         FLOAT64           align_off_y) {
    if (fpv == 0 || !fpv->valid || b2w == 0) {
        return;
    }

    // --- Project a point along the FPV direction ---
    const FLOAT64 fpa_rad = PROJ_DEG2RAD(fpv->fpv_pitch);
    const FLOAT64 drift_rad = PROJ_DEG2RAD(fpv->drift_angle);

    const FLOAT64 cp = proj_cos(fpa_rad);
    const FLOAT64 sp = proj_sin(fpa_rad);
    const FLOAT64 cd = proj_cos(drift_rad);
    const FLOAT64 sd = proj_sin(drift_rad);

    // FPV point 1000 m ahead in body frame
    const FLOAT64 dist = 1000.0;
    Vec3 fpv_body;
    fpv_body.x = dist * cp * cd;
    fpv_body.y = dist * cp * sd;
    fpv_body.z = -dist * sp;

    // Apply eye offset
    fpv_body = proj_vec3_sub(fpv_body, eye_offset);

    // Perspective projection
    bool behind = false;
    fpv->screen_pos = proj_perspective(fpv_body, focal_px,
                                        screen_w, screen_h,
                                        0.1, &behind);

    // Apply profile-specific alignment correction
    fpv->screen_pos.x += align_off_x;
    fpv->screen_pos.y += align_off_y;

    fpv->on_screen = !behind &&
                     fpv->screen_pos.x >= -100.0 &&
                     fpv->screen_pos.x < (FLOAT64)(screen_w + 100) &&
                     fpv->screen_pos.y >= -100.0 &&
                     fpv->screen_pos.y < (FLOAT64)(screen_h + 100);
}

// ============================================================================
//  3.  Debug logging
// ============================================================================

void fpv_debug_log(const FPVState* fpv) {
    if (fpv == 0) {
        MSFS_Log("[C_HUD_FPV] FPVState: NULL");
        return;
    }

    if (!fpv->valid) {
        MSFS_Log("[C_HUD_FPV] FPVState: INVALID");
        return;
    }

    MSFS_Log("[C_HUD_FPV] GS=%.1f m/s  VS=%.1f m/s  "
             "HDG=%.1f°  TRK=%.1f°  "
             "DRIFT=%.2f°  FPA=%.2f°  "
             "SCRN=(%.1f, %.1f)  ON=%d",
             fpv->groundspeed_ms, fpv->vertical_speed_ms,
             fpv->heading_deg_true, fpv->track_deg_true,
             fpv->drift_angle, fpv->fpv_pitch,
             fpv->screen_pos.x, fpv->screen_pos.y,
             (int)fpv->on_screen);
}
