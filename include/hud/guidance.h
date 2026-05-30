#ifndef C_HUD_GUIDANCE_H
#define C_HUD_GUIDANCE_H

// ============================================================================
//  Conformal HUD – ILS Guidance / Steering Logic
//  MSFS 2024  ·  C++17  ·  WASM
//
//  Implements Boeing HGS-style conformal ILS guidance symbology:
//    · Localizer deviation bar (conformal, fixed to runway position)
//    · Glideslope deviation bar (conformal, fixed to touchdown point)
//    · Steering cues (flight director bars for pitch and roll)
//    · Centerline extension cue
//
//  The guidance bars are WORLD-REFERENCED: they represent the actual
//  ILS beam position in space, projected conformally onto the HUD.
// ============================================================================

#include "../module.h"
#include "../projection.h"
#include "runway_projection.h"   // RunwayEnd

// ============================================================================
//  1.  ILS beam geometry
// ============================================================================

/// ILS beam geometry for the current approach.
typedef struct ILSBeam {
    // --- Beam origin (touchdown point on runway) ---
    Vec3  touchdown;        // (lon_deg, alt_m, lat_deg) – ILS reference point
    
    // --- Beam direction ---
    FLOAT64 localizer_bearing;  // runway heading (degrees true)
    
    // --- Deviations (from SimVars or computed) ---
    FLOAT64 loc_error_deg;  // localizer deviation (degrees, left = negative)
    FLOAT64 gs_error_deg;   // glideslope deviation (degrees, below = negative)
    
    // --- Beam geometry ---
    FLOAT64 gs_angle_deg;   // glideslope angle (typically 3.0°)
    FLOAT64 ref_dme_nm;     // DME distance to threshold (nautical miles)
    
    // --- Computed intercept points ---
    Vec3    loc_intercept;  // point where LOC beam is intercepted (world coords)
    Vec3    gs_intercept;   // point where GS beam is intercepted (world coords)
    
    bool    valid;          // true after successful beam computation
} ILSBeam;

/// Guidance state combining raw deviations with conformal beam projection.
typedef struct GuidanceState {
    // --- Raw ILS deviations (from SimVars, EMA-filtered) ---
    FLOAT64 loc_error_dots;     // localizer error (dots, ±1 full scale)
    FLOAT64 gs_error_dots;      // glideslope error (dots, ±1 full scale)
    FLOAT64 loc_error_deg;      // localizer error (degrees)
    FLOAT64 gs_error_deg;       // glideslope error (degrees)
    
    // --- Conformal steering target positions (HUD screen coords) ---
    Vec2    loc_target;         // localizer bar target position (pixels)
    Vec2    gs_target;          // glideslope bar target position (pixels)
    Vec2    flight_director;    // flight director crosshair (pixels)
    
    // --- Steering commands ---
    FLOAT64 steering_pitch;     // pitch steering command (degrees)
    FLOAT64 steering_bank;      // bank steering command (degrees)
    
    // --- Guidance flags ---
    bool    loc_captured;       // localizer captured
    bool    gs_captured;        // glideslope captured
    bool    approach_armed;     // approach mode armed
    
    // --- Visibility ---
    bool    loc_visible;        // localizer bar visible on screen
    bool    gs_visible;         // glideslope bar visible on screen
    bool    valid;              // true after successful computation
} GuidanceState;

// ============================================================================
//  2.  Guidance computation
// ============================================================================

/// Compute ILS beam geometry from current aircraft position.
///
/// @param ac_ref      Aircraft position (lon_deg, alt_m, lat_deg)
/// @param ac_hdg      Aircraft true heading
/// @param runway_end  Runway threshold data
/// @param ils         [out] Computed ILS beam geometry
void guidance_compute_beam(Vec3            ac_ref,
                           FLOAT64         ac_hdg,
                           const RunwayEnd* runway_end,
                           ILSBeam*        ils);

/// Compute steering guidance from ILS deviations.
///
/// @param ils         ILS beam geometry
/// @param ac_ref      Aircraft position
/// @param b2w         Body-to-world rotation matrix
/// @param eye_offset  HUD eye offset
/// @param focal_px    Focal length in pixels
/// @param screen_w    Screen width
/// @param screen_h    Screen height
/// @param guidance    [out] Computed guidance state
void guidance_compute(const ILSBeam*      ils,
                      Vec3                ac_ref,
                      const Mat4*         b2w,
                      Vec3                eye_offset,
                      FLOAT64             focal_px,
                      int                 screen_w,
                      int                 screen_h,
                      GuidanceState*      guidance);

/// Project a world-space ILS beam point to HUD screen.
static inline Vec2 guidance_project_point(Vec3    world_pt,
                                          Vec3    ac_ref,
                                          const Mat4* b2w,
                                          Vec3    eye_offset,
                                          FLOAT64 focal_px,
                                          int     screen_w,
                                          int     screen_h,
                                          bool*   out_behind) {
    Vec2 result = { -9999.0, -9999.0 };
    proj_world_to_hud(world_pt, ac_ref, b2w, eye_offset,
                       focal_px, screen_w, screen_h,
                       &result, out_behind);
    return result;
}

// ============================================================================
//  3.  Flight Director logic
// ============================================================================

/// Compute flight director steering commands.
///
/// @param guidance    [in/out] Guidance state (fills steering commands)
/// @param ac_pitch    Aircraft pitch (degrees)
/// @param ac_bank     Aircraft bank (degrees)
/// @param ils         ILS beam geometry
void guidance_flight_director(GuidanceState* guidance,
                              FLOAT64        ac_pitch,
                              FLOAT64        ac_bank,
                              const ILSBeam* ils);

// ============================================================================
//  4.  Debug logging
// ============================================================================

void guidance_debug_log(const GuidanceState* guidance);
void guidance_debug_beam(const ILSBeam* ils);

#endif // C_HUD_GUIDANCE_H
