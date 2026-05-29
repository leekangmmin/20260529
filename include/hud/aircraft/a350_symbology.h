#ifndef C_HUD_A350_SYMBOLOGY_H
#define C_HUD_A350_SYMBOLOGY_H

// ============================================================================
//  Conformal HUD – Airbus A350 Symbology Styling
//  MSFS 2024  ·  C++17  ·  WASM
//
//  v2.4.0 — Airbus-specific HUD symbology presentation.
//
//  Airbus HUD symbology is designed to feel:
//    · Expensive — refined, clean lines, no visual noise
//    · Refined — subtle brightness transitions, less aggressive bloom
//    · Optically stable — stable horizon references, reduced oscillation
//    · Computationally assisted — smooth alpha fading, anti-flicker
//
//  This module defines the rendering parameters and filtering that
//  produce the characteristic Airbus HUD look.
// ============================================================================

#include "../../module.h"
#include "../../projection.h"

// ============================================================================
//  1.  Symbology styling state
// ============================================================================

/// Airbus HUD symbology styling state.
typedef struct A350SymbologyStyle {
    // --- Brightness ---
    FLOAT64 brightness_target;              // Target brightness level
    FLOAT64 brightness_current;             // Current (eased) brightness
    FLOAT64 brightness_easing_rate;         // Easing rate per frame
    FLOAT64 brightness_min;                 // Minimum brightness

    // --- Bloom ---
    FLOAT64 bloom_reduction;                // Bloom reduction factor (0..1)
    FLOAT64 bloom_current;                  // Current bloom level

    // --- Line quality ---
    FLOAT64 line_cleanliness;               // Line cleanliness factor (0..1)
    FLOAT64 line_intensity_stab;            // Line intensity stabilisation

    // --- Horizon ---
    FLOAT64 horizon_stability;              // Horizon stability multiplier
    FLOAT64 horizon_oscillation_damping;    // Oscillation damping factor

    // --- Alpha fading ---
    FLOAT64 alpha_fade_smoothness;          // Alpha fade smoothing (0..1)
    FLOAT64 alpha_transition_rate;          // Rate of alpha transitions

    // --- Anti-shimmer ---
    FLOAT64 anti_shimmer_gain;              // Anti-shimmer filter gain
    FLOAT64 shimmer_accumulator;            // Shimmer detection accumulator

    // --- Symbol persistence ---
    FLOAT64 symbol_persistence;             // Symbol persistence smoothing (0..1)
    FLOAT64 prev_alpha[32];                 // Previous alpha values for smoothing
    FLOAT64 prev_position[32];              // Previous positions for smoothing
    int     symbol_count;                   // Number of tracked symbols

    // --- Overall ---
    bool    active;                         // True when styling is active
    bool    valid;
} A350SymbologyStyle;

// ============================================================================
//  2.  Initialisation
// ============================================================================

/// Initialise the A350 symbology styling state.
static inline void a350_symbology_init(A350SymbologyStyle* ss) {
    if (ss == 0) return;

    ss->brightness_target      = 0.7;
    ss->brightness_current     = 0.7;
    ss->brightness_easing_rate = 0.20;
    ss->brightness_min         = 0.15;

    ss->bloom_reduction        = 0.60;
    ss->bloom_current          = 0.0;

    ss->line_cleanliness       = 0.85;
    ss->line_intensity_stab    = 0.90;

    ss->horizon_stability           = 0.90;
    ss->horizon_oscillation_damping = 0.80;

    ss->alpha_fade_smoothness   = 0.25;
    ss->alpha_transition_rate   = 0.15;

    ss->anti_shimmer_gain       = 0.70;
    ss->shimmer_accumulator     = 0.0;

    ss->symbol_persistence      = 0.30;
    for (int i = 0; i < 32; ++i) {
        ss->prev_alpha[i]    = 1.0;
        ss->prev_position[i] = 0.0;
    }
    ss->symbol_count = 0;

    ss->active = false;
    ss->valid  = false;
}

// ============================================================================
//  3.  Styling computation
// ============================================================================

/// Compute symbology styling parameters for the current frame.
///
/// @param ss              [in/out] Styling state
/// @param dt_s            Frame delta time (seconds)
/// @param target_bright   Target brightness (0..1)
/// @param turbulence      Current turbulence level (0..1)
void a350_symbology_compute(A350SymbologyStyle* ss,
                             FLOAT64 dt_s,
                             FLOAT64 target_bright,
                             FLOAT64 turbulence);

/// Apply brightness easing to a value.
///
/// @param ss       Styling state
/// @param raw      Raw brightness value
/// @param target   Target brightness
/// @return         Eased brightness value
static inline FLOAT64 a350_symbology_ease_brightness(A350SymbologyStyle* ss,
                                                       FLOAT64 raw,
                                                       FLOAT64 target) {
    if (ss == 0) return raw;
    const FLOAT64 rate = ss->brightness_easing_rate;
    FLOAT64 eased = raw + (target - raw) * rate;
    if (eased < ss->brightness_min) eased = ss->brightness_min;
    return eased;
}

/// Apply alpha fade smoothing.
///
/// @param ss       Styling state
/// @param raw_alpha   Raw alpha value
/// @param index    Symbol index for persistence tracking
/// @return         Smoothed alpha value
FLOAT64 a350_symbology_smooth_alpha(A350SymbologyStyle* ss,
                                     FLOAT64 raw_alpha,
                                     int index);

/// Apply anti-shimmer to a position value.
///
/// @param ss       Styling state
/// @param raw_pos  Raw position (pixels)
/// @param index    Symbol index
/// @return         Stabilised position
FLOAT64 a350_symbology_stabilise_pos(A350SymbologyStyle* ss,
                                      FLOAT64 raw_pos,
                                      int index);

// ============================================================================
//  4.  Debug logging
// ============================================================================

void a350_symbology_debug_log(const A350SymbologyStyle* ss);

#endif // C_HUD_A350_SYMBOLOGY_H
