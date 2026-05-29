#ifndef C_HUD_DEPTH_ILLUSION_H
#define C_HUD_DEPTH_ILLUSION_H

// ============================================================================
//  Conformal HUD – Optical Depth Illusion Simulation
//  MSFS 2024  ·  C++17  ·  WASM
//
//  v2.4.0 — Subtle optical depth simulation.
//
//  Implements subtle visual cues that make the HUD symbology feel
//  optically projected into the outside world rather than drawn on
//  a flat glass surface:
//
//    · Slight parallax illusion: near symbols shift slightly relative
//      to far symbols during head movement
//    · Combiner focal-depth simulation: subtle blurring or sharpness
//      differences between near and far elements
//    · Symbol depth weighting: critical symbols feel "closer"
//    · Subtle optical offset during head motion: the entire HUD image
//      shifts microscopically as if projected through real optics
//    · Focal-plane stabilisation: elements at optical infinity remain
//      rock-steady while glass elements can have micro-wobble
//
//  The goal is psychological: the pilot should subconsciously perceive
//  the HUD as a real optical projection, not a video overlay.
// ============================================================================

#include "../module.h"
#include "../projection.h"
#include "collimation.h"

// ============================================================================
//  1.  Depth layer identifiers
// ============================================================================

typedef enum DepthLayer {
    DEPTH_OPTICAL_INFINITY  = 0,   // World-stabilised (runway, FPV, horizon)
    DEPTH_COMBINER_NEAR     = 1,   // Near the combiner glass (text, numbers)
    DEPTH_COMBINER_MID      = 2,   // Mid-depth (guidance bars)
    DEPTH_COMBINER_FAR      = 3,   // Far depth (background elements)
} DepthLayer;

// ============================================================================
//  2.  Depth illusion state
// ============================================================================

typedef struct DepthIllusionState {
    // --- Parallax offsets per depth layer (pixels) ---
    Vec2    parallax_offset[4];     // Per-layer parallax offset

    // --- Focal depth simulation ---
    FLOAT64 focal_blur[4];          // Per-layer blur amount (0..1)
    FLOAT64 focal_sharpness[4];     // Per-layer sharpness (0..1)

    // --- Head-motion induced shift ---
    Vec2    head_motion_shift;      // Subtle shift from head tracking
    FLOAT64 head_motion_gain;       // Gain for head-motion effect

    // --- Optical centre wobble ---
    Vec2    optical_wobble;         // Micro-wobble of optical centre
    FLOAT64 wobble_frequency;       // Wobble frequency
    FLOAT64 wobble_amplitude;       // Wobble amplitude (pixels)

    // --- Focal plane stabilisation ---
    Vec2    stabilisation_offset;   // Additional stabilisation for infinity layer

    // --- Overall depth effect ---
    FLOAT64 depth_intensity;        // 0..1 overall depth effect intensity
    Vec2    infinity_layer_offset;  // Cumulative offset for infinity layer

    // --- Debug ---
    bool    active;
    bool    valid;
} DepthIllusionState;

// ============================================================================
//  3.  Initialisation
// ============================================================================

/// Initialise depth illusion state.
static inline void depth_illusion_init(DepthIllusionState* di) {
    if (di == 0) return;
    for (int i = 0; i < 4; ++i) {
        di->parallax_offset[i] = proj_vec3_make(0, 0, 0);
        di->focal_blur[i] = 0.0;
        di->focal_sharpness[i] = 1.0;
    }
    di->head_motion_shift = proj_vec3_make(0, 0, 0);
    di->head_motion_gain = 0.02;
    di->optical_wobble = proj_vec3_make(0, 0, 0);
    di->wobble_frequency = 8.0;
    di->wobble_amplitude = 0.3;
    di->stabilisation_offset = proj_vec3_make(0, 0, 0);
    di->depth_intensity = 0.5;
    di->infinity_layer_offset = proj_vec3_make(0, 0, 0);
    di->active = false;
    di->valid = false;
}

// ============================================================================
//  4.  Depth illusion computation
// ============================================================================

/// Compute depth illusion offsets for the current frame.
///
/// @param di        [in/out] Depth illusion state
/// @param dt_s      Frame delta time (seconds)
/// @param cc        Collimation correction (for head-motion data)
/// @param intensity Depth intensity factor (0..1, from profile)
void depth_illusion_compute(DepthIllusionState* di,
                             FLOAT64            dt_s,
                             const CollimationCorrection* cc,
                             FLOAT64            intensity);

/// Apply depth offset to a screen position based on its depth layer.
///
/// @param di     Depth illusion state
/// @param pos    Original screen position
/// @param layer  Depth layer of the element
/// @return       Offset screen position
static inline Vec2 depth_illusion_apply(const DepthIllusionState* di,
                                         Vec2 pos,
                                         DepthLayer layer) {
    if (di == 0 || !di->active) return pos;
    Vec2 result = pos;
    // Apply per-layer parallax
    result.x += di->parallax_offset[layer].x;
    result.y += di->parallax_offset[layer].y;

    // Apply head-motion shift (more for near layers)
    const FLOAT64 depth_factor = 1.0 - (FLOAT64)layer * 0.25;
    result.x += di->head_motion_shift.x * depth_factor;
    result.y += di->head_motion_shift.y * depth_factor;

    // General optical wobble applies to all layers equally
    result.x += di->optical_wobble.x;
    result.y += di->optical_wobble.y;

    // Infinity layer gets extra stabilisation to counteract wobble
    // This makes infinity-layer symbols feel more solid
    if (layer == DEPTH_OPTICAL_INFINITY) {
        result.x += di->infinity_layer_offset.x;
        result.y += di->infinity_layer_offset.y;
    }

    return result;
}

// ============================================================================
//  5.  Debug logging
// ============================================================================

/// Log depth illusion state for debugging.
void depth_illusion_debug_log(const DepthIllusionState* di);

#endif // C_HUD_DEPTH_ILLUSION_H
