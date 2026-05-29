#ifndef C_HUD_VISUAL_RESPONSE_H
#define C_HUD_VISUAL_RESPONSE_H

// ============================================================================
//  Conformal HUD – Human Visual Response Simulation
//  MSFS 2024  ·  C++17  ·  WASM
//
//  v2.4.0 — Pilot visual perception effects.
//
//  Simulates the human pilot's visual system response to the outside
//  environment as seen through the HUD combiner:
//
//    · Dark adaptation: gradual sensitivity increase in low light
//    · Temporary bloom blindness: bright lights cause temporary
//      desensitisation (e.g. runway strobes, approach lights)
//    · Rain glare: diffracted light from rain on the combiner
//    · Low-light phosphor persistence increase: at night, the HUD
//      phosphor appears to persist longer (temporal blending)
//    · Brightness adaptation lag: rapid brightness changes adapt
//      gradually (like human pupillary response)
//    · Visual contrast fatigue: prolonged exposure reduces contrast
//      sensitivity
//    · Eye accommodation simulation: subtle focus shifts between
//      near (HUD glass) and far (outside world) targets
//
//  Effects are subtle and physiologically motivated. They operate
//  on the rendering parameters to create the illusion of a real
//  optical/visual system rather than a perfect digital overlay.
// ============================================================================

#include "../module.h"

// ============================================================================
//  1.  Visual response state
// ============================================================================

/// Visual response state tracking all human visual effects.
typedef struct VisualResponseState {
    // --- Dark adaptation ---
    FLOAT64 dark_adaptation;        // 0..1, 0 = fully dark-adapted
    FLOAT64 ambient_luminance;      // estimated ambient luminance (normalised)
    FLOAT64 dark_adapt_time_s;      // time spent in current light level

    // --- Bloom/temporary blindness ---
    FLOAT64 bloom_exposure;         // 0..1, accumulated bloom exposure
    FLOAT64 bloom_decay;            // bloom decay time constant
    FLOAT64 bloom_threshold;        // luminance threshold for bloom trigger
    FLOAT64 bloom_amount;           // current bloom effect (0..1)

    // --- Rain glare ---
    FLOAT64 rain_intensity;         // 0..1, estimated rain intensity
    FLOAT64 rain_glare;             // 0..1, rain-induced glare effect
    bool    is_raining;             // true when precipitation is detected

    // --- Phosphor persistence ---
    FLOAT64 phosphor_base_ms;       // base phosphor persistence (ms)
    FLOAT64 phosphor_current_ms;    // current effective persistence (ms)
    FLOAT64 persistence_boost;      // 0..1, night-vision persistence boost

    // --- Brightness adaptation ---
    FLOAT64 current_brightness;     // current perceived brightness (0..1)
    FLOAT64 target_brightness;      // target brightness level
    FLOAT64 adaptation_rate;        // adaptation rate (1/time constant)
    FLOAT64 brightness_lag;         // 0..1, adaptation lag

    // --- Visual contrast fatigue ---
    FLOAT64 fatigue_accumulator;    // accumulated fatigue
    FLOAT64 fatigue_threshold;      // threshold for fatigue effect
    FLOAT64 contrast_reduction;     // 0..1, contrast reduction from fatigue
    FLOAT64 fatigue_recovery_rate;  // recovery rate per second

    // --- Eye accommodation ---
    FLOAT64 accommodation;          // 0..1 (0 = far focus, 1 = near focus)
    FLOAT64 accommodation_lag;      // accommodation lag time constant
    FLOAT64 accommodation_target;   // target accommodation state

    // --- Overall ---
    FLOAT64 luminance_gain;         // overall luminance gain (0..2)
    FLOAT64 contrast_gain;          // overall contrast gain (0..1.5)
    bool    active;                 // true when any effect is active

    // --- Debug ---
    FLOAT64 debug_adaptation_level;
    FLOAT64 debug_bloom_level;
    FLOAT64 debug_phosphor_ms;
    FLOAT64 debug_fatigue_level;
} VisualResponseState;

// ============================================================================
//  2.  Rendering parameters output
// ============================================================================

/// Visual-response-adjusted rendering parameters.
typedef struct VisualRenderParams {
    FLOAT64 brightness;             // final perceived brightness
    FLOAT64 contrast;               // final contrast
    FLOAT64 phosphor_persistence_ms; // effective phosphor persistence
    FLOAT64 bloom_intensity;        // bloom/blindness effect
    FLOAT64 glare_amount;           // rain/glare effect
    FLOAT64 edge_fade_night_boost;  // night-time edge fade boost
    bool    active;                 // true if any visual effect is active
} VisualRenderParams;

// ============================================================================
//  3.  Initialisation
// ============================================================================

/// Initialise visual response state.
static inline void visual_response_init(VisualResponseState* vs) {
    if (vs == 0) return;
    vs->dark_adaptation        = 0.0;
    vs->ambient_luminance      = 0.5;  // default daylight
    vs->dark_adapt_time_s      = 0.0;

    vs->bloom_exposure         = 0.0;
    vs->bloom_decay            = 1.0;
    vs->bloom_threshold        = 0.7;
    vs->bloom_amount           = 0.0;

    vs->rain_intensity         = 0.0;
    vs->rain_glare             = 0.0;
    vs->is_raining             = false;

    vs->phosphor_base_ms       = 30.0;
    vs->phosphor_current_ms    = 30.0;
    vs->persistence_boost      = 0.0;

    vs->current_brightness     = 0.7;
    vs->target_brightness      = 0.7;
    vs->adaptation_rate        = 0.5;
    vs->brightness_lag         = 0.0;

    vs->fatigue_accumulator    = 0.0;
    vs->fatigue_threshold      = 0.5;
    vs->contrast_reduction     = 0.0;
    vs->fatigue_recovery_rate  = 0.1;

    vs->accommodation          = 0.0;
    vs->accommodation_lag      = 0.3;
    vs->accommodation_target   = 0.0;

    vs->luminance_gain         = 1.0;
    vs->contrast_gain          = 1.0;
    vs->active                 = false;
    vs->debug_adaptation_level = 0.0;
    vs->debug_bloom_level      = 0.0;
    vs->debug_phosphor_ms      = 30.0;
    vs->debug_fatigue_level    = 0.0;
}

// ============================================================================
//  4.  Visual response computation
// ============================================================================

/// Compute visual response effects for the current frame.
///
/// @param vs     [in/out] Visual response state
/// @param dt_s   Frame delta time (seconds)
/// @param ambient_lux  Ambient light level (0 = night, 1 = full daylight)
/// @param rain_intensity  0..1, rain/precipitation intensity
/// @param runway_light_boom  True if bright runway/approach lights ahead
void visual_response_compute(VisualResponseState* vs,
                              FLOAT64             dt_s,
                              FLOAT64             ambient_lux,
                              FLOAT64             rain_intensity,
                              bool                runway_light_boom);

/// Apply visual response effects to rendering parameters.
///
/// @param vs      Computed visual response state
/// @param base    Base render parameters (from profile + weather)
/// @param out     [out] Adjusted render parameters
void visual_response_apply(const VisualResponseState* vs,
                            const VisualRenderParams*  base,
                            VisualRenderParams*        out);

// ============================================================================
//  5.  Debug logging
// ============================================================================

/// Log visual response state for debugging.
void visual_response_debug_log(const VisualResponseState* vs);

#endif // C_HUD_VISUAL_RESPONSE_H
