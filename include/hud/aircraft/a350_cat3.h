#ifndef C_HUD_A350_CAT3_H
#define C_HUD_A350_CAT3_H

// ============================================================================
//  Conformal HUD – Airbus A350 CAT III Capability Layer
//  MSFS 2024  ·  C++17  ·  WASM
//
//  v2.4.0 — Airbus CAT III enhanced augmentation.
//
//  The A350 is certified for CAT IIIa/b autoland operations. The HUD
//  provides harmonised visual augmentation that feels integrated with
//  the autoland system.
//
//  Features:
//    · Enhanced runway stabilisation during low visibility
//    · Predictive localizer smoothing with confidence weighting
//    · Glideslope confidence stabilisation
//    · Flare cue stabilisation for CAT III autoland monitoring
//    · Rollout confidence amplification
//    · Degraded-mode graceful fallback
//    · Sensor fusion weighting
// ============================================================================

#include "../../module.h"
#include "../../projection.h"
#include "../confidence.h"

// ============================================================================
//  1.  Airbus CAT III state
// ============================================================================

/// Airbus CAT III enhanced augmentation state.
/// Tracks all parameters needed for CAT III HUD behaviour.
typedef struct A350CatIIIState {
    // --- Status ---
    bool    cat3_active;                    // True when CAT III mode is active
    bool    cat3_qualified;                 // True when CAT III qualifications met
    FLOAT64 cat3_confidence;                // Overall CAT III confidence (0..1)
    FLOAT64 cat3_qualification;             // CAT III qualification score (0..1)

    // --- Sensor fusion weights ---
    FLOAT64 loc_weight;                     // Localizer weight in fusion
    FLOAT64 gs_weight;                      // Glideslope weight in fusion
    FLOAT64 ra_weight;                      // Radio altimeter weight
    FLOAT64 gps_weight;                     // GPS weight
    FLOAT64 attitude_weight;                // Attitude reference weight

    // --- Confidence smoothing ---
    FLOAT64 confidence_smoothed;            // EMA-smoothed confidence
    FLOAT64 confidence_alpha;               // Smoothing factor

    // --- Runway stabilisation ---
    FLOAT64 runway_stab_gain;               // Current runway stabilisation gain
    FLOAT64 loc_predictive_smooth;          // Localizer predictive smoothing

    // --- Glideslope ---
    FLOAT64 gs_stabilisation;               // GS stabilisation factor
    FLOAT64 gs_confidence_boost;            // GS confidence boost

    // --- Flare cue ---
    FLOAT64 flare_cue_stab;                 // Flare cue stabilisation
    FLOAT64 flare_cue_confidence;           // Flare cue confidence threshold

    // --- Rollout ---
    FLOAT64 rollout_confidence_amp;         // Rollout confidence amplification
    FLOAT64 rollout_degraded_fallback;      // Degraded-mode fallback level

    // --- Low visibility ---
    FLOAT64 low_vis_enhancement;            // Low visibility enhancement gain
    FLOAT64 degraded_mode_grace_s;          // Grace period before degraded mode
    FLOAT64 degraded_timer_s;               // Current degraded timer

    // --- Sensor data ---
    FLOAT64 ils_loc_dots;                   // Localizer deviation (dots)
    FLOAT64 ils_gs_dots;                    // Glideslope deviation (dots)
    bool    loc_captured;                   // Localizer captured
    bool    gs_captured;                    // Glideslope captured
    bool    radio_alt_valid;                // Radio altimeter valid
    FLOAT64 groundspeed_ms;                // Ground speed
    FLOAT64 radio_altitude_m;               // Radio altitude

    // --- Visual enhancement ---
    FLOAT64 runway_enhancement;             // Runway visual enhancement
    FLOAT64 centerline_enhancement;         // Centerline visual enhancement
    FLOAT64 touchdown_enhancement;          // Touchdown zone enhancement

    // --- Profile tuning ---
    FLOAT64 loc_weight_setting;
    FLOAT64 gs_weight_setting;
    FLOAT64 ra_weight_setting;
    FLOAT64 gps_weight_setting;
    FLOAT64 confidence_smooth_alpha;
    FLOAT64 confidence_min_cat3;
    FLOAT64 runway_stab_gain_setting;
    FLOAT64 loc_predictive_smooth_s;
    FLOAT64 gs_stab_gain_setting;
    FLOAT64 gs_conf_boost_captured;
    FLOAT64 flare_cue_stab_gain;
    FLOAT64 flare_cue_min_conf;
    FLOAT64 rollout_conf_amplifier;
    FLOAT64 rollout_degraded_fallback_setting;
    FLOAT64 low_vis_enhancement_gain;
    FLOAT64 degraded_grace_seconds;

    // --- Debug ---
    bool    valid;
} A350CatIIIState;

// ============================================================================
//  2.  Initialisation
// ============================================================================

/// Initialise the A350 CAT III state.
static inline void a350_cat3_init(A350CatIIIState* c3) {
    if (c3 == 0) return;
    c3->cat3_active         = false;
    c3->cat3_qualified      = false;
    c3->cat3_confidence     = 0.0;
    c3->cat3_qualification  = 0.0;

    c3->loc_weight           = 0.40;
    c3->gs_weight            = 0.30;
    c3->ra_weight            = 0.20;
    c3->gps_weight           = 0.10;
    c3->attitude_weight      = 0.15;

    c3->confidence_smoothed  = 0.0;
    c3->confidence_alpha     = 0.10;

    c3->runway_stab_gain        = 0.0;
    c3->loc_predictive_smooth   = 0.0;

    c3->gs_stabilisation        = 0.0;
    c3->gs_confidence_boost     = 0.0;

    c3->flare_cue_stab        = 0.0;
    c3->flare_cue_confidence   = 0.0;

    c3->rollout_confidence_amp  = 1.0;
    c3->rollout_degraded_fallback = 0.60;

    c3->low_vis_enhancement     = 1.0;
    c3->degraded_mode_grace_s   = 2.0;
    c3->degraded_timer_s        = 0.0;

    c3->ils_loc_dots        = 0.0;
    c3->ils_gs_dots         = 0.0;
    c3->loc_captured        = false;
    c3->gs_captured         = false;
    c3->radio_alt_valid     = false;
    c3->groundspeed_ms      = 0.0;
    c3->radio_altitude_m    = 100.0;

    c3->runway_enhancement     = 1.0;
    c3->centerline_enhancement = 1.0;
    c3->touchdown_enhancement  = 1.0;

    // Default tuning
    c3->loc_weight_setting            = 0.40;
    c3->gs_weight_setting             = 0.30;
    c3->ra_weight_setting             = 0.20;
    c3->gps_weight_setting            = 0.10;
    c3->confidence_smooth_alpha       = 0.10;
    c3->confidence_min_cat3           = 0.85;
    c3->runway_stab_gain_setting      = 0.85;
    c3->loc_predictive_smooth_s       = 0.30;
    c3->gs_stab_gain_setting          = 0.80;
    c3->gs_conf_boost_captured        = 0.15;
    c3->flare_cue_stab_gain           = 0.85;
    c3->flare_cue_min_conf            = 0.70;
    c3->rollout_conf_amplifier        = 1.30;
    c3->rollout_degraded_fallback_setting = 0.60;
    c3->low_vis_enhancement_gain      = 1.20;
    c3->degraded_grace_seconds        = 2.00;

    c3->valid = false;
}

// ============================================================================
//  3.  Core computation
// ============================================================================

/// Compute the A350 CAT III augmentation state.
///
/// @param c3    [in/out] CAT III state
/// @param dt_s  Frame delta time (seconds)
/// @param cs    Confidence state from the confidence system
void a350_cat3_compute(A350CatIIIState* c3,
                        FLOAT64 dt_s,
                        const ConfidenceState* cs);

/// Apply CAT III enhancements to confidence render parameters.
///
/// @param c3      CAT III state
/// @param render  [in/out] Render parameters to enhance
void a350_cat3_apply_to_render(const A350CatIIIState* c3,
                                ConfidenceRenderParams* render);

// ============================================================================
//  4.  Helpers
// ============================================================================

/// Check if CAT III operations should be active.
static inline bool a350_cat3_should_activate(FLOAT64 radio_alt_m,
                                               FLOAT64 confidence) {
    return radio_alt_m < 200.0 && confidence > 0.7;
}

/// Debug logging.
void a350_cat3_debug_log(const A350CatIIIState* c3);

#endif // C_HUD_A350_CAT3_H
