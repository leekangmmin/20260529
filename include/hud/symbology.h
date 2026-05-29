#ifndef C_HUD_SYMBOLOGY_H
#define C_HUD_SYMBOLOGY_H

// ============================================================================
//  Conformal HUD – Symbology Management
//  MSFS 2024  ·  C++17  ·  WASM
//
//  Manages the complete set of HUD symbology elements and handles the
//  conversion between world-referenced geometry and HUD display coordinates.
//
//  This is the central coordination point that:
//    1. Aggregates all symbology sources (runway, FPV, guidance, horizon)
//    2. Applies aircraft profile parameters
//    3. Applies clipping to HUD combiner region
//    4. Publishes results to L:vars for the HTML overlay
//    5. Provides debugging data
//
//  Extended in v2.1.0:
//    · Flare guidance (flare cue, touchdown zone)
//    · EVS-enhanced rendering parameters
//    · Semi-collimated projection correction
//    · Advanced symbology (accel caret, energy trend, etc.)
// ============================================================================

#include "../module.h"
#include "../projection.h"
#include "aircraft_profiles.h"
#include "runway_projection.h"
#include "fpv.h"
#include "guidance.h"
#include "collimation.h"
#include "flare.h"
#include "evs.h"
#include "stabilization.h"
#include "advanced_symbology.h"

// ============================================================================
//  1.  Extended symbology bitmask flags
// ============================================================================

typedef enum HUDAdvSymbologyBits {
    HUD_SYM_FLARE_CUE          = 1 << 16,  // Flare director cue
    HUD_SYM_TOUCHDOWN_ZONE     = 1 << 17,  // Touchdown aim point
    HUD_SYM_ACCEL_CARET        = 1 << 18,  // Acceleration caret
    HUD_SYM_ENERGY_TREND       = 1 << 19,  // Energy trend vector
    HUD_SYM_FLARE_BRACKET      = 1 << 20,  // Flare anticipation bracket
    HUD_SYM_TD_PREDICTOR       = 1 << 21,  // Touchdown predictor
    HUD_SYM_VELOCITY_TREND     = 1 << 22,  // Velocity trend cue
} HUDAdvSymbologyBits;

#define C_HUD_SYM_FULL_ADVANCED \
    (HUD_SYM_FLARE_CUE | HUD_SYM_TOUCHDOWN_ZONE | HUD_SYM_ACCEL_CARET | \
     HUD_SYM_ENERGY_TREND | HUD_SYM_FLARE_BRACKET | HUD_SYM_TD_PREDICTOR | \
     HUD_SYM_VELOCITY_TREND)

// ============================================================================
//  2.  Complete HUD symbology state
// ============================================================================

/// Maximum number of polyline vertices for any symbology element.
#define C_HUD_SYM_MAX_VERTS  64

/// A 2-D polyline (for horizon, pitch ladder, etc.)
typedef struct SymPolyline {
    Vec2  verts[C_HUD_SYM_MAX_VERTS];
    int   count;
    bool  valid;
} SymPolyline;

/// Complete output state for the HUD renderer.
typedef struct HUDOutput {
    // --- HUD configuration ---
    const HUDProfile* profile;     // active aircraft profile
    bool    hud_active;            // true if HUD should be rendered
    Vec2    hud_origin;            // HUD origin in panel coordinates (pixels)
    FLOAT64 focal_px;             // focal length in pixels

    // --- Runway ---
    ProjectedRunway runway;
    bool    runway_visible;

    // --- Horizon ---
    FLOAT64 horizon_y;             // horizon line Y position (pixels)
    FLOAT64 horizon_slope;         // horizon line slope (bank-induced tilt)
    bool    horizon_valid;

    // --- Pitch ladder ---
    SymPolyline pitch_lines[5];    // pitch ladder lines (±5°, ±10°, ±15°)
    int         pitch_line_count;
    bool        pitch_ladder_valid;

    // --- FPV ---
    FPVState    fpv;
    bool        fpv_visible;

    // --- Guidance ---
    GuidanceState guidance;
    bool        guidance_visible;

    // --- ILS crosshair (traditional) ---
    Vec2    ils_crosshair;         // ILS crosshair position
    bool    ils_crosshair_visible;

    // ================================================================
    //  v2.1.0 – Flare guidance
    // ================================================================
    FlareState      flare;         // flare guidance state
    FlareCue        flare_cue;     // flare director cue rendering
    TouchdownZone   touchdown_zone; // touchdown aim point marker
    bool            flare_visible;

    // ================================================================
    //  v2.1.0 – Semi-collimated rendering
    // ================================================================
    CollimationCorrection collimation;  // collimation correction state
    Vec3            corrected_eye_offset; // eye offset after collimation
    bool            collimation_active;

    // ================================================================
    //  v2.1.0 – EVS enhancement
    // ================================================================
    EVSState        evs;           // EVS state
    EVSRenderParams evs_render;    // EVS-enhanced render params
    bool            evs_active;

    // ================================================================
    //  v2.1.0 – Advanced symbology
    // ================================================================
    AccelCaret      accel_caret;   // acceleration caret
    EnergyTrend     energy_trend;  // energy trend vector
    FlareBracket    flare_bracket; // flare anticipation bracket
    TDPredictor     td_predictor;  // touchdown predictor
    VelocityTrend   velocity_trend; // velocity trend cue

    // ================================================================
    //  v2.1.0 – Stabilisation filter states (persistent)
    // ================================================================
    HUDStabilisation stab;         // all stabilisation filter states

    // --- Weather ---
    FLOAT64 line_width_px;
    FLOAT64 opacity;

    // --- Frame ---
    int     frame_count;
    bool    valid;
} HUDOutput;

// ============================================================================
//  3.  Symbology computation
// ============================================================================

/// [TEST SUPPORT - DEPRECATED in v2.7.0] Compute all HUD symbology elements.
/// No longer called from production pipeline (main.cpp uses direct HUDState fields).
///
/// @param state      Module state (aircraft data, etc.)
/// @param dd         Gauge draw data (screen dimensions)
/// @param output     [out] Complete HUD output
/// @return           true if any symbology is visible
bool sym_compute_all(const ModuleState* state,
                     const sGaugeDrawData* dd,
                     HUDOutput* output);

/// Compute the horizon line position and slope.
void sym_compute_horizon(const ModuleState* state,
                         const HUDProfile* profile,
                         FLOAT64 focal_px,
                         int screen_w,
                         int screen_h,
                         HUDOutput* output);

/// Compute the pitch ladder.
void sym_compute_pitch_ladder(const ModuleState* state,
                              const HUDProfile* profile,
                              FLOAT64 focal_px,
                              int screen_w,
                              int screen_h,
                              HUDOutput* output);

// ============================================================================
//  4.  v2.1.0 computation helpers
// ============================================================================

/// Compute semi-collimated correction for the current frame.
///
/// @param cd                 [in/out] Camera delta tracker (persistent across frames)
/// @param output             [out] HUD output (collimation fields filled)
/// @param current_eye_offset Current eye offset (body frame, m)
/// @param ac_ref             Aircraft reference position (lon, alt, lat)
/// @param heading_deg        Current heading (deg)
/// @param pitch_deg          Current pitch (deg)
/// @param bank_deg           Current bank (deg)
/// @param dt_s               Frame delta time (seconds)
void sym_compute_collimation(CameraDelta* cd,
                              HUDOutput* output,
                              Vec3 current_eye_offset,
                              Vec3 ac_ref,
                              FLOAT64 heading_deg,
                              FLOAT64 pitch_deg,
                              FLOAT64 bank_deg,
                              FLOAT64 dt_s);

/// Compute flare guidance for the current frame.
void sym_compute_flare(HUDOutput* output,
                        FLOAT64 focal_px,
                        int screen_w,
                        int screen_h,
                        Vec2 td_reference,
                        FLOAT64 dt_s);

/// Compute EVS enhancement for the current frame.
void sym_compute_evs(HUDOutput* output,
                      int phase);

/// Compute advanced symbology (acceleration, energy, trend, etc.)
void sym_compute_advanced(HUDOutput* output,
                           Vec3 ac_ref,
                           const Mat4* b2w,
                           Vec3 eye_offset,
                           FLOAT64 focal_px,
                           int screen_w,
                           int screen_h);

// ============================================================================
//  5.  Clipping
// ============================================================================

/// Clip a screen position to the HUD combiner region.
/// Returns the clipped position and a visibility flag.
static inline Vec2 sym_clip_to_combiner(Vec2 pos,
                                         const HUDCombinerRect* comb) {
    Vec2 clipped = pos;
    if (clipped.x < (FLOAT64)comb->x)
        clipped.x = (FLOAT64)comb->x;
    if (clipped.x > (FLOAT64)(comb->x + comb->width))
        clipped.x = (FLOAT64)(comb->x + comb->width);
    if (clipped.y < (FLOAT64)comb->y)
        clipped.y = (FLOAT64)comb->y;
    if (clipped.y > (FLOAT64)(comb->y + comb->height))
        clipped.y = (FLOAT64)(comb->y + comb->height);
    return clipped;
}

/// Test if a screen position is within the combiner region.
static inline bool sym_in_combiner(Vec2 pos, const HUDCombinerRect* comb) {
    return (pos.x >= (FLOAT64)comb->x &&
            pos.x <= (FLOAT64)(comb->x + comb->width) &&
            pos.y >= (FLOAT64)comb->y &&
            pos.y <= (FLOAT64)(comb->y + comb->height));
}

// ============================================================================
//  6.  Publishing
// ============================================================================

/// [DEPRECATED in v2.7.0] Publish all HUD output to L:vars.
/// Publishing now handled directly in module_update_publish() in main.cpp.
void sym_publish_all(HUDOutput* output);

/// [DEPRECATED in v2.7.0 - stub, never called]
void sym_publish_runway(const ProjectedRunway* runway);

/// [DEPRECATED in v2.7.0 - stub, never called]
void sym_publish_fpv(const FPVState* fpv);

/// [DEPRECATED in v2.7.0 - stub, never called]
void sym_publish_guidance(const GuidanceState* guidance);

/// [DEPRECATED in v2.7.0 - stub, never called]
void sym_publish_horizon(const HUDOutput* output);

/// [DEPRECATED in v2.7.0 - stub, never called from production]
void sym_publish_flare(const HUDOutput* output);

/// [DEPRECATED in v2.7.0 - stub, never called]
void sym_publish_collimation_debug(const HUDOutput* output);

/// [DEPRECATED in v2.7.0 - stub, never called]
void sym_publish_evs(const HUDOutput* output);

#endif // C_HUD_SYMBOLOGY_H
