#ifndef C_HUD_FPV_H
#define C_HUD_FPV_H

// ============================================================================
//  Conformal HUD – Flight Path Vector
//  MSFS 2024  ·  C++17  ·  WASM
//
//  v2.3.0 — FPV alignment with aircraft profile calibration offsets.
//  Computes the true inertial flight path vector (FPV) for display on
//  the HUD.  The FPV shows where the aircraft is ACTUALLY going through
//  the air, not where the nose is pointing.
//
//  The FPV accounts for:
//    · Ground speed vector (true motion over ground)
//    · Wind drift (difference between heading and track)
//    · Vertical speed (climb/descent rate)
//    · Aircraft attitude compensation
//
//  The FPV is projected into HUD space as a circle symbol that moves
//  with the aircraft's true flight path.
// ============================================================================

#include "../module.h"
#include "../projection.h"

// ============================================================================
//  1.  FPV state
// ============================================================================

typedef struct FPVState {
    // --- Inputs (raw SimVar, populated by update pipeline) ---
    FLOAT64 groundspeed_ms;      // ground speed (m/s)
    FLOAT64 true_airspeed_ms;    // true airspeed (m/s)
    FLOAT64 vertical_speed_ms;   // vertical speed (m/s, positive = up)
    FLOAT64 track_deg_true;      // ground track (degrees true)
    FLOAT64 heading_deg_true;    // true heading
    FLOAT64 pitch_deg;           // aircraft pitch
    FLOAT64 bank_deg;            // aircraft bank

    // --- Computed FPV angles ---
    FLOAT64 fpv_pitch;           // FPV pitch angle (degrees, positive = up)
    FLOAT64 fpv_heading;         // FPV heading (degrees true)
    FLOAT64 drift_angle;         // wind drift angle (heading - track)

    // --- Projected screen position ---
    Vec2    screen_pos;          // FPV position on HUD (pixels)
    bool    on_screen;           // true if FPV is visible
    bool    valid;               // true after successful computation

    // --- Debug ---
    FLOAT64 debug_airspeed;      // for debugging
    FLOAT64 debug_wind_correction;
} FPVState;

// ============================================================================
//  2.  FPV computation
// ============================================================================

/// Compute the flight path vector from aircraft state.
///
/// @param fpv   [in/out] FPV state with inputs populated, outputs written.
/// @return      true if computation was successful.
bool fpv_compute(FPVState* fpv);

/// Project the FPV into HUD screen coordinates.
///
/// v2.3.0: accepts alignment offsets from the active aircraft profile
/// for per-aircraft FPV position calibration.
///
/// @param fpv         [in/out] FPV state (needs fpv_heading, fpv_pitch)
/// @param ac_ref      Aircraft reference position (lon_deg, alt_m, lat_deg)
/// @param ac_hdg      Aircraft true heading (degrees)
/// @param ac_pitch    Aircraft pitch (degrees)
/// @param ac_bank     Aircraft bank (degrees)
/// @param b2w         Body-to-world rotation matrix
/// @param eye_offset  HUD eye offset in body frame
/// @param focal_px    Focal length in pixels
/// @param screen_w    Screen width
/// @param screen_h    Screen height
/// @param align_off_x Horizontal alignment offset (pixels, profile-specific)
/// @param align_off_y Vertical alignment offset (pixels, profile-specific)
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
                         FLOAT64           align_off_y);

/// Compute FPV position as a unit vector in the forward-up plane.
/// Returns a body-frame direction vector for the true flight path.
static inline Vec3 fpv_get_body_direction(FLOAT64 fpv_pitch_deg,
                                           FLOAT64 drift_angle_deg,
                                           FLOAT64 ac_pitch_deg,
                                           FLOAT64 ac_bank_deg) {
    const FLOAT64 pa = PROJ_DEG2RAD(fpv_pitch_deg);
    const FLOAT64 da = PROJ_DEG2RAD(drift_angle_deg);

    const FLOAT64 cp = proj_cos(pa);
    const FLOAT64 sp = proj_sin(pa);
    const FLOAT64 cd = proj_cos(da);
    const FLOAT64 sd = proj_sin(da);

    Vec3 dir;
    dir.x = cp * cd;
    dir.y = cp * sd;
    dir.z = -sp;

    return dir;
}

/// Debug logging for FPV computation.
void fpv_debug_log(const FPVState* fpv);

#endif // C_HUD_FPV_H
