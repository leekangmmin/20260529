#ifndef C_HUD_A350_FPV_CONTROLLER_H
#define C_HUD_A350_FPV_CONTROLLER_H

// ============================================================================
//  Conformal HUD – Airbus A350 XWB Flight Path Vector Controller
//  MSFS 2024  ·  C++17  ·  WASM
//
//  v3.0.0 — A350 Certification Layer
//
//  Sits above the existing AirbusFPVFilter and provides the final
//  Airbus- certified FPV behaviour:
//
//    · Extremely stable, low-noise, low-pass filtered
//    · Turbulence resistant via intelligent rejection
//    · Inertially smoothed with predictive compensation
//    · Runway-referenced during flare (attaches to runway perspective)
//    · Visually calm — "attached to the runway" during landing
//    · Crosswind visual compensation for stable approach tracking
//
//  This is the TOP of the FPV filtering stack.  All other FPV
//  subsystems feed into this controller, which produces the final
//  screen position and stability metrics for the HUD.
// ============================================================================

#include "../../module.h"
#include "../../projection.h"
#include "../stabilization.h"
#include "airbus_fpv.h"

// ============================================================================
//  1.  Controller state
// ============================================================================

/// Adaptive filtering state for turbulence detection
typedef struct A350FPVTurbulenceState {
    FLOAT64 jitter_ema;                 // EMA of frame-to-frame jitter
    FLOAT64 turbulence_level;           // 0..1 estimated turbulence
    FLOAT64 turbulence_confidence;      // confidence in turbulence estimate
    FLOAT64 attack_alpha;               // fast attack time constant
    FLOAT64 decay_alpha;                // slow decay time constant
    FLOAT64 jitter_threshold_calm;      // threshold for calm (< this = calm)
    FLOAT64 jitter_threshold_severe;    // threshold for severe (> this = severe)
    bool    initialised;
} A350FPVTurbulenceState;

/// Flare stabilization state — runway-referenced FPV during flare
typedef struct A350FPVFlareStab {
    bool    flare_active;               // true during flare phase
    FLOAT64 flare_blend;                // 0..1 blending to runway reference
    Vec2    runway_reference_pos;       // FPV position locked to runway
    Vec2    runway_aim_point;           // runway aim point in screen coords
    FLOAT64 runway_reference_strength;  // how strongly FPV locks to runway
    FLOAT64 flare_height_m;             // height above runway (m)
    FLOAT64 flare_stabilization_gain;   // stabilization gain during flare
    Vec2    stabilized_pos;             // flare-stabilized position
    bool    initialised;
} A350FPVFlareStab;

/// Predictive runway alignment — anticipates flare and landing geometry
typedef struct A350FPVPredictiveAlign {
    FLOAT64 alignment_angle_deg;        // predicted alignment angle
    FLOAT64 alignment_quality;          // 0..1 quality of alignment estimate
    Vec2    predicted_touchdown_pos;    // predicted touchdown screen pos
    FLOAT64 crosswind_component_ms;     // crosswind component (m/s)
    Vec2    crosswind_compensation;     // visual compensation offset (px)
    FLOAT64 runway_slope_deg;           // runway slope estimate
    bool    valid;
} A350FPVPredictiveAlign;

/// Complete A350 FPV Controller state
typedef struct A350FlightPathVectorController {
    // -- Sub-components --
    AirbusFPVFilter         base_filter;            // underlying Airbus filter
    A350FPVTurbulenceState  turbulence;             // turbulence state
    A350FPVFlareStab        flare_stab;             // flare stabilization
    A350FPVPredictiveAlign  predictive_align;       // predictive alignment

    // -- Outputs --
    Vec2    final_screen_pos;           // final stabilized screen position
    Vec2    raw_screen_pos;             // raw (pre-filter) screen position
    Vec2    filtered_screen_pos;        // after base filtering
    Vec2    flare_adjusted_pos;         // after flare stabilization
    FLOAT64 stability_score;            // 0..1 overall FPV stability
    FLOAT64 fpv_quality;                // 0..1 FPV tracking quality
    bool    on_screen;                  // true if FPV is visible
    bool    valid;                      // true after successful compute

    // -- Configuration --
    FLOAT64 flare_activation_ft;        // flare activation altitude (ft)
    FLOAT64 flare_reference_gain;       // how strongly runway attracts FPV
    FLOAT64 crosswind_compensation_gain; // crosswind visual compensation
    FLOAT64 predictive_lead_time_s;     // prediction look-ahead (s)
    FLOAT64 stability_min_threshold;    // min stability for "smooth"
    FLOAT64 turbulence_rejection;       // 0..1 turbulence rejection strength
    bool    runway_referenced_flare;    // enable runway-referenced flare
    bool    crosswind_compensation;     // enable crosswind compensation
    bool    predictive_alignment;       // enable predictive alignment

    // -- Debug --
    FLOAT64 debug_jitter;
    FLOAT64 debug_turbulence;
    FLOAT64 debug_flare_blend;
    FLOAT64 debug_stability;
    FLOAT64 debug_crosswind_px;
} A350FlightPathVectorController;

// ============================================================================
//  2.  Initialisation
// ============================================================================

/// Initialise the A350 FPV controller with default Airbus tuning.
static inline void a350_fpv_controller_init(A350FlightPathVectorController* ctrl) {
    if (ctrl == 0) return;

    // Initialise base Airbus FPV filter
    airbus_fpv_init(&ctrl->base_filter);

    // Turbulence state
    ctrl->turbulence.jitter_ema             = 0.0;
    ctrl->turbulence.turbulence_level       = 0.0;
    ctrl->turbulence.turbulence_confidence  = 1.0;
    ctrl->turbulence.attack_alpha           = 0.25;
    ctrl->turbulence.decay_alpha            = 0.04;
    ctrl->turbulence.jitter_threshold_calm  = 0.3;
    ctrl->turbulence.jitter_threshold_severe = 6.0;
    ctrl->turbulence.initialised            = false;

    // Flare stabilization
    ctrl->flare_stab.flare_active              = false;
    ctrl->flare_stab.flare_blend               = 0.0;
    ctrl->flare_stab.runway_reference_pos      = proj_vec2_make(0, 0);
    ctrl->flare_stab.runway_aim_point          = proj_vec2_make(0, 0);
    ctrl->flare_stab.runway_reference_strength = 0.0;
    ctrl->flare_stab.flare_height_m            = 100.0;
    ctrl->flare_stab.flare_stabilization_gain  = 0.85;
    ctrl->flare_stab.stabilized_pos            = proj_vec2_make(0, 0);
    ctrl->flare_stab.initialised               = false;

    // Predictive alignment
    ctrl->predictive_align.alignment_angle_deg     = 0.0;
    ctrl->predictive_align.alignment_quality       = 0.0;
    ctrl->predictive_align.predicted_touchdown_pos = proj_vec2_make(0, 0);
    ctrl->predictive_align.crosswind_component_ms  = 0.0;
    ctrl->predictive_align.crosswind_compensation  = proj_vec2_make(0, 0);
    ctrl->predictive_align.runway_slope_deg        = 0.0;
    ctrl->predictive_align.valid                   = false;

    // Outputs
    ctrl->final_screen_pos       = proj_vec2_make(0, 0);
    ctrl->raw_screen_pos         = proj_vec2_make(0, 0);
    ctrl->filtered_screen_pos    = proj_vec2_make(0, 0);
    ctrl->flare_adjusted_pos     = proj_vec2_make(0, 0);
    ctrl->stability_score        = 1.0;
    ctrl->fpv_quality            = 1.0;
    ctrl->on_screen              = false;
    ctrl->valid                  = false;

    // Configuration — Airbus A350 certified values
    ctrl->flare_activation_ft        = 50.0;
    ctrl->flare_reference_gain       = 0.75;
    ctrl->crosswind_compensation_gain = 0.60;
    ctrl->predictive_lead_time_s     = 0.15;
    ctrl->stability_min_threshold    = 0.70;
    ctrl->turbulence_rejection       = 0.92;
    ctrl->runway_referenced_flare    = true;
    ctrl->crosswind_compensation     = true;
    ctrl->predictive_alignment       = true;

    // Debug
    ctrl->debug_jitter       = 0.0;
    ctrl->debug_turbulence   = 0.0;
    ctrl->debug_flare_blend  = 0.0;
    ctrl->debug_stability    = 1.0;
    ctrl->debug_crosswind_px = 0.0;
}

// ============================================================================
//  3.  Core computation
// ============================================================================

/// Compute the A350 FPV controller state for the current frame.
///
/// This is the TOP-LEVEL FPV computation for the A350 HUD.
/// It wraps/enhances the existing AirbusFPVFilter with additional
/// certification-layer behaviour.
///
/// @param ctrl          [in/out] Controller state
/// @param raw_pos       Raw FPV screen position (pixels)
/// @param runway_pos    Runway aim point on screen (pixels), or (0,0) if none
/// @param dt_s          Frame delta time (seconds)
/// @param phase         Flight phase (0=CRUISE, 1=APPROACH, 2=FLARE, 3=ROLLOUT)
/// @param crosswind_ms  Crosswind component (m/s, + = from right)
/// @param radio_alt_m   Radio altitude (metres)
/// @param groundspeed_ms Ground speed (m/s)
/// @param on_ground     True if aircraft is on ground
void a350_fpv_controller_compute(
    A350FlightPathVectorController* ctrl,
    Vec2            raw_pos,
    Vec2            runway_pos,
    FLOAT64         dt_s,
    int             phase,
    FLOAT64         crosswind_ms,
    FLOAT64         radio_alt_m,
    FLOAT64         groundspeed_ms,
    bool            on_ground);

/// Get the final stabilised FPV screen position.
static inline Vec2 a350_fpv_controller_get_pos(
    const A350FlightPathVectorController* ctrl) {
    if (ctrl == 0) return proj_vec2_make(0, 0);
    return ctrl->final_screen_pos;
}

/// Get the current FPV stability score (0..1).
static inline FLOAT64 a350_fpv_controller_get_stability(
    const A350FlightPathVectorController* ctrl) {
    if (ctrl == 0) return 0.0;
    return ctrl->stability_score;
}

/// Get the current FPV quality metric (0..1).
static inline FLOAT64 a350_fpv_controller_get_quality(
    const A350FlightPathVectorController* ctrl) {
    if (ctrl == 0) return 0.0;
    return ctrl->fpv_quality;
}

/// Get the current flare blend factor (0..1).
static inline FLOAT64 a350_fpv_controller_get_flare_blend(
    const A350FlightPathVectorController* ctrl) {
    if (ctrl == 0) return 0.0;
    return ctrl->flare_stab.flare_blend;
}

/// Get the current turbulence level (0..1).
static inline FLOAT64 a350_fpv_controller_get_turbulence(
    const A350FlightPathVectorController* ctrl) {
    if (ctrl == 0) return 0.0;
    return ctrl->turbulence.turbulence_level;
}

// ============================================================================
//  4.  Debug logging
// ============================================================================

void a350_fpv_controller_debug_log(const A350FlightPathVectorController* ctrl);

#endif // C_HUD_A350_FPV_CONTROLLER_H
