#ifndef C_HUD_A350_RUNWAY_AUGMENTATION_H
#define C_HUD_A350_RUNWAY_AUGMENTATION_H

// ============================================================================
//  Conformal HUD – Airbus A350 XWB Runway Visual Augmentation
//  MSFS 2024  ·  C++17  ·  WASM
//
//  v3.0.0 — A350 Certification Layer
//
//  Provides optical stabilization for runway symbology:
//
//    · Runway threshold stabilization — smooths threshold position
//    · Centerline stabilization — reduces jitter on centerline
//    · Edge-light stabilization — smooths runway edge lights
//    · Flare reference enhancement — enhances runway cues during flare
//
//  The runway should appear optically stable even in turbulence,
//  using existing collimation, depth illusion, and confidence systems.
// ============================================================================

#include "../../module.h"
#include "../../projection.h"
#include "../stabilization.h"

// ============================================================================
//  1.  Runway augmentation state
// ============================================================================

typedef struct A350RunwayAugmentation {
    // --- Threshold stabilization ---
    Vec2    threshold_smoothed;         // EMA-smoothed threshold position
    Vec2    threshold_raw;              // raw threshold position
    FLOAT64 threshold_stability;        // 0..1 threshold stability
    FLOAT64 threshold_alpha;            // EMA alpha for threshold

    // --- Centerline stabilization ---
    Vec2    centerline_smoothed;        // smoothed centerline reference
    Vec2    centerline_raw;             // raw centerline position
    FLOAT64 centerline_stability;       // 0..1 centerline stability
    FLOAT64 centerline_alpha;           // EMA alpha for centerline

    // --- Edge light stabilization ---
    FLOAT64 edge_light_stability;       // 0..1 edge light stability
    FLOAT64 left_edge_offset_px;        // left edge screen offset (pixels)
    FLOAT64 right_edge_offset_px;       // right edge screen offset (pixels)

    // --- Flare reference ---
    bool    flare_active;               // true during flare
    FLOAT64 flare_enhancement;          // 0..1 runway enhancement during flare
    FLOAT64 flare_reference_blend;      // blend factor during flare

    // --- Configuration ---
    FLOAT64 threshold_smooth_alpha;     // threshold smoothing factor
    FLOAT64 centerline_smooth_alpha;    // centerline smoothing factor
    FLOAT64 edge_light_smooth_alpha;    // edge light smoothing factor
    FLOAT64 flare_enhancement_gain;     // flare enhancement multiplier
    FLOAT64 turbulence_adaptation;      // 0..1 adapt to turbulence

    // --- Debug ---
    bool    active;
    bool    valid;
} A350RunwayAugmentation;

// ============================================================================
//  2.  Initialisation
// ============================================================================

static inline void a350_runway_augmentation_init(A350RunwayAugmentation* ra) {
    if (ra == 0) return;

    ra->threshold_smoothed       = proj_vec2_make(0, 0);
    ra->threshold_raw            = proj_vec2_make(0, 0);
    ra->threshold_stability      = 1.0;
    ra->threshold_alpha          = 0.20;

    ra->centerline_smoothed       = proj_vec2_make(0, 0);
    ra->centerline_raw            = proj_vec2_make(0, 0);
    ra->centerline_stability      = 1.0;
    ra->centerline_alpha          = 0.15;

    ra->edge_light_stability      = 1.0;
    ra->left_edge_offset_px       = 0.0;
    ra->right_edge_offset_px      = 0.0;

    ra->flare_active              = false;
    ra->flare_enhancement         = 1.0;
    ra->flare_reference_blend     = 0.0;

    // Airbus A350 tuning
    ra->threshold_smooth_alpha    = 0.20;
    ra->centerline_smooth_alpha   = 0.15;
    ra->edge_light_smooth_alpha   = 0.25;
    ra->flare_enhancement_gain    = 0.40;
    ra->turbulence_adaptation     = 0.70;

    ra->active                    = false;
    ra->valid                     = false;
}

// ============================================================================
//  3.  Core computation
// ============================================================================

/// Compute runway augmentation for the current frame.
///
/// @param ra           [in/out] Runway augmentation state
/// @param dt_s         Frame delta time (seconds)
/// @param runway_valid True if runway is currently visible/valid
/// @param threshold    Raw threshold screen position (pixels)
/// @param centerline   Raw centerline screen position (pixels)
/// @param flare_active True if in flare phase
/// @param turbulence   Current turbulence level (0..1)
void a350_runway_augmentation_compute(
    A350RunwayAugmentation* ra,
    FLOAT64 dt_s,
    bool    runway_valid,
    Vec2    threshold,
    Vec2    centerline,
    bool    flare_active,
    FLOAT64 turbulence);

/// Apply runway augmentation stabilisation offsets.
///
/// @param ra        Runway augmentation state
/// @param pos       [in/out] Screen position to stabilise
/// @param is_threshold  True if this is a threshold element
/// @param is_centerline True if this is a centerline element
void a350_runway_augmentation_apply(
    const A350RunwayAugmentation* ra,
    Vec2*   pos,
    bool    is_threshold,
    bool    is_centerline);

/// Get the current runway stability score (0..1).
static inline FLOAT64 a350_runway_augmentation_stability(
    const A350RunwayAugmentation* ra) {
    if (ra == 0) return 0.0;
    return (ra->threshold_stability + ra->centerline_stability +
            ra->edge_light_stability) * 0.333;
}

// ============================================================================
//  4.  Debug logging
// ============================================================================

void a350_runway_augmentation_debug_log(const A350RunwayAugmentation* ra);

#endif // C_HUD_A350_RUNWAY_AUGMENTATION_H
