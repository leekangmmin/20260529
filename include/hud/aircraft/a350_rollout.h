#ifndef C_HUD_A350_ROLLOUT_H
#define C_HUD_A350_ROLLOUT_H

// ============================================================================
//  Conformal HUD – Airbus A350 Rollout Augmentation
//  MSFS 2024  ·  C++17  ·  WASM
//
//  v2.4.0 — Airbus-specific rollout behaviour.
//
//  Airbus rollout philosophy:
//    · Extremely stable centerline guidance
//    · Predictive nosewheel alignment (anticipates turns)
//    · Smooth deceleration symbology (no aggressive cues)
//    · Low-jitter rollout steering
//    · Gradual transition from aerodynamic to nosewheel steering
//    · Wet runway stability assistance
//    · Crosswind rollout stabilisation
//    · Runway edge visual stabilisation
// ============================================================================

#include "../../module.h"
#include "../../projection.h"
#include "../rollout.h"

// ============================================================================
//  1.  Airbus rollout augmentation state
// ============================================================================

typedef struct A350RolloutAugmentation {
    // --- Inputs ---
    bool    on_ground;
    FLOAT64 groundspeed_ms;
    FLOAT64 heading_deg;
    FLOAT64 track_deg;
    FLOAT64 runway_heading_deg;
    FLOAT64 lateral_deviation_m;
    FLOAT64 crosswind_ms;
    bool    wet_runway;

    // --- Steering ---
    FLOAT64 steering_command_deg;           // Filtered steering command (deg)
    FLOAT64 steering_raw_deg;               // Raw steering command (deg)
    FLOAT64 steering_damping;               // Adaptive damping factor
    FLOAT64 centerline_error_deg;           // Heading error (deg)
    FLOAT64 predictive_steering;            // Predictive component (deg)

    // --- Nosewheel ---
    FLOAT64 nosewheel_fraction;             // Nosewheel engagement 0..1
    FLOAT64 nosewheel_target;               // Target engagement
    FLOAT64 nosewheel_transition_s;         // Transition time constant (s)
    FLOAT64 aerodynamic_fraction;           // Aerodynamic steering 0..1

    // --- Deceleration ---
    FLOAT64 deceleration_ms2;               // Current deceleration
    FLOAT64 target_decel_ms2;               // Target deceleration
    FLOAT64 deceleration_smooth;            // Smoothed deceleration

    // --- Stability ---
    FLOAT64 centerline_stability;           // 0..1 tracking quality
    FLOAT64 crosswind_compensation;         // Crosswind correction
    FLOAT64 wet_gain_multiplier;            // Wet runway gain multiplier

    // --- Visual stabilisation ---
    FLOAT64 edge_stabilization;             // Runway edge visual stabilisation
    FLOAT64 centerline_visual_smooth;       // Centerline visual smoothing

    // --- Phase ---
    bool    active;
    FLOAT64 time_s;                         // Time since activation

    // --- Profile tuning ---
    FLOAT64 centerline_gain;                // Centerline tracking gain
    FLOAT64 centerline_damping;             // Centerline damping factor
    FLOAT64 predictive_lead_gain;           // Predictive lead gain
    FLOAT64 crosswind_stab_gain;            // Crosswind stabilisation gain
    FLOAT64 edge_stab_gain;                 // Edge visual stabilisation gain
    bool    wet_assist_enabled;             // Wet runway assistance

    // --- Debug ---
    bool    valid;
} A350RolloutAugmentation;

// ============================================================================
//  2.  Initialisation
// ============================================================================

/// Initialise the A350 rollout augmentation.
static inline void a350_rollout_init(A350RolloutAugmentation* ra) {
    if (ra == 0) return;

    ra->on_ground               = false;
    ra->groundspeed_ms          = 0.0;
    ra->heading_deg             = 0.0;
    ra->track_deg               = 0.0;
    ra->runway_heading_deg      = 0.0;
    ra->lateral_deviation_m     = 0.0;
    ra->crosswind_ms            = 0.0;
    ra->wet_runway              = false;

    ra->steering_command_deg    = 0.0;
    ra->steering_raw_deg        = 0.0;
    ra->steering_damping        = 0.80;
    ra->centerline_error_deg    = 0.0;
    ra->predictive_steering     = 0.0;

    ra->nosewheel_fraction      = 0.0;
    ra->nosewheel_target        = 0.0;
    ra->nosewheel_transition_s  = 3.0;
    ra->aerodynamic_fraction    = 1.0;

    ra->deceleration_ms2        = 0.0;
    ra->target_decel_ms2        = 1.47;
    ra->deceleration_smooth     = 0.0;

    ra->centerline_stability    = 1.0;
    ra->crosswind_compensation  = 0.0;
    ra->wet_gain_multiplier     = 1.0;

    ra->edge_stabilization      = 1.0;
    ra->centerline_visual_smooth = 1.0;

    ra->active                  = false;
    ra->time_s                  = 0.0;

    // Default Airbus tuning
    ra->centerline_gain         = 2.5;
    ra->centerline_damping      = 0.80;
    ra->predictive_lead_gain    = 0.40;
    ra->crosswind_stab_gain     = 0.75;
    ra->edge_stab_gain          = 0.70;
    ra->wet_assist_enabled      = true;

    ra->valid                   = false;
}

// ============================================================================
//  3.  Core computation
// ============================================================================

/// Compute Airbus rollout augmentation for the current frame.
///
/// @param ra    [in/out] Rollout augmentation state
/// @param dt_s  Frame delta time (seconds)
/// @return      true if computation succeeded
bool a350_rollout_compute(A350RolloutAugmentation* ra, FLOAT64 dt_s);

/// Apply Airbus-specific damping to a generic rollout state.
///
/// This function takes the existing RolloutState and applies Airbus
/// augmentation on top, modifying the steering commands and cues.
///
/// @param rs    [in/out] Generic rollout state (will be modified)
/// @param ra    Airbus rollout augmentation state
void a350_rollout_apply_to_state(RolloutState* rs,
                                  const A350RolloutAugmentation* ra);

// ============================================================================
//  4.  Helper
// ============================================================================

/// Check if rollout augmentation should activate.
static inline bool a350_rollout_should_activate(bool on_ground,
                                                  FLOAT64 ra_m,
                                                  FLOAT64 groundspeed_kt) {
    return on_ground && groundspeed_kt > 10.0 && ra_m < 1.0;
}

/// Debug logging.
void a350_rollout_debug_log(const A350RolloutAugmentation* ra);

#endif // C_HUD_A350_ROLLOUT_H
