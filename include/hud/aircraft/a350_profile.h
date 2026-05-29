#ifndef C_HUD_A350_PROFILE_H
#define C_HUD_A350_PROFILE_H

// ============================================================================
//  Conformal HUD – Airbus A350 HUD Behaviour Profile
//  MSFS 2024  ·  C++17  ·  WASM
//
//  v2.4.0 — Airbus-specific HUD personality.
//
//  The Airbus A350 HUD philosophy is fundamentally different from Boeing:
//    · Calm, filtered, highly augmented
//    · Low-workload, predictive, "smoothly computed" not raw
//    · Stable, quiet, confident symbology
//    · CAT III natural operations
//    · Reduced pilot workload during all phases
//
//  This profile implements the perceptual and tuning layer that makes
//  the HUD feel recognisably Airbus: expensive, refined, optically
//  stable, computationally assisted.
// ============================================================================

#include "../../module.h"
#include "../../projection.h"

// ============================================================================
//  1.  Smoothing constants
// ============================================================================

/// Response smoothing constants — Airbus HUD applies heavy filtering
/// to all symbology motion. These constants define the damping and
/// inertia characteristics.
typedef struct A350SmoothingConstants {
    // --- FPV smoothing ---
    FLOAT64 fpv_ema_alpha_min;          // Minimum EMA alpha (max smoothing)
    FLOAT64 fpv_ema_alpha_max;          // Maximum EMA alpha (min smoothing)
    FLOAT64 fpv_rate_threshold;         // Rate threshold for EMA adaptation
    FLOAT64 fpv_inertia_factor;         // Inertia factor (0..1, higher = more inertia)
    FLOAT64 fpv_predictive_gain;        // Predictive lead gain
    FLOAT64 fpv_intentional_latency_s;  // Intentional latency (seconds)

    // --- Flare law ---
    FLOAT64 flare_softness_gain;        // Flare transition softness (0..1)
    FLOAT64 flare_pitch_damping;        // Pitch rate damping during flare
    FLOAT64 flare_sink_rate_damping;    // Sink rate damping during flare

    // --- Flight director ---
    FLOAT64 fd_filter_cutoff_hz;        // Flight director low-pass cutoff
    FLOAT64 fd_damping_ratio;           // FD damping ratio (1.0 = critically damped)
    FLOAT64 fd_max_rate_dps;            // FD max rate of change (deg/s)

    // --- Rollout ---
    FLOAT64 rollout_damping_gain;       // Rollout damping multiplier
    FLOAT64 rollout_nosewheel_smooth_s; // Nosewheel transition smoothing time
    FLOAT64 rollout_wet_gain;           // Wet runway stability multiplier

    // --- Horizon stabilisation ---
    FLOAT64 horizon_damping_natural_freq; // Horizon damping natural frequency
    FLOAT64 horizon_damping_ratio;        // Horizon damping ratio

    // --- Brightness ---
    FLOAT64 brightness_ease_in;         // Brightness ease-in rate
    FLOAT64 brightness_ease_out;        // Brightness ease-out rate
    FLOAT64 brightness_minimum;         // Minimum brightness level
} A350SmoothingConstants;

// ============================================================================
//  2.  Declutter priorities for Airbus philosophy
// ============================================================================

/// Airbus-specific declutter priority modifiers.
/// Airbus HUD prioritises:
///   HIGH: FPV, runway references, flare guidance, LOC/GS, rollout centerline
///   LOW:  non-critical numeric data, secondary nav, excessive annunciations
typedef struct A350DeclutterPriorities {
    // Per-phase priority boost values (multipliers applied to base priority)
    FLOAT64 fpv_priority_boost;             // FPV priority multiplier
    FLOAT64 runway_priority_boost;          // Runway reference priority multiplier
    FLOAT64 flare_priority_boost;           // Flare cue priority multiplier
    FLOAT64 loc_gs_priority_boost;          // LOC/GS priority multiplier
    FLOAT64 rollout_priority_boost;         // Rollout centerline multiplier
    FLOAT64 numeric_data_reduction;         // Numeric data reduction factor
    FLOAT64 secondary_nav_reduction;        // Secondary nav reduction factor
    FLOAT64 annunciation_reduction;         // Annunciation reduction factor

    // Phase-specific aggressive declutter flags
    bool    aggressive_during_flare;        // Aggressively declutter during flare
    bool    aggressive_during_rollout;      // Aggressively declutter during rollout
    FLOAT64 flare_declutter_factor;         // How much to reduce non-critical during flare
    FLOAT64 rollout_declutter_factor;       // How much to reduce non-critical during rollout
} A350DeclutterPriorities;

// ============================================================================
//  3.  CAT III augmentation parameters
// ============================================================================

/// Airbus CAT III enhanced augmentation tuning.
/// The A350 is certified for CAT III autoland; the HUD provides
/// harmonised visual augmentation that feels integrated with the
/// autoland system.
typedef struct A350CatIIIParams {
    // --- Sensor fusion ---
    FLOAT64 loc_confidence_weight;          // Localizer confidence weight
    FLOAT64 gs_confidence_weight;           // Glideslope confidence weight
    FLOAT64 ra_confidence_weight;           // Radio altimeter confidence weight
    FLOAT64 gps_confidence_weight;          // GPS confidence weight

    // --- Confidence smoothing ---
    FLOAT64 confidence_smooth_alpha;        // Confidence EMA smoothing
    FLOAT64 confidence_min_cat3;            // Minimum confidence for CAT III ops

    // --- Runway stabilisation ---
    FLOAT64 runway_stab_gain;               // Runway stabilisation gain
    FLOAT64 loc_predictive_smooth_s;        // Localizer predictive smoothing (s)

    // --- Glideslope ---
    FLOAT64 gs_stabilisation_gain;          // Glideslope stabilisation
    FLOAT64 gs_confidence_boost_captured;   // Confidence boost when GS captured

    // --- Flare cue ---
    FLOAT64 flare_cue_stab_gain;            // Flare cue stabilisation
    FLOAT64 flare_cue_min_confidence;       // Min confidence for flare cue display

    // --- Rollout ---
    FLOAT64 rollout_confidence_amplifier;   // Rollout confidence amplification
    FLOAT64 rollout_degraded_fallback;      // Rollout degraded-mode fallback level

    // --- Low visibility ---
    FLOAT64 low_vis_enhancement_gain;       // Low visibility enhancement
    FLOAT64 degraded_mode_grace_seconds;    // Grace period before degraded mode (s)
} A350CatIIIParams;

// ============================================================================
//  4.  Complete A350 HUD profile
// ============================================================================

/// Complete A350 HUD behaviour profile.
/// Contains all tuning parameters that differentiate Airbus HUD
/// behaviour from generic or Boeing-style HUDs.
typedef struct A350HUDProfile {
    // --- Identification ---
    const char* profile_name;               // "A350_HUD_PROFILE"

    // --- Smoothing constants ---
    A350SmoothingConstants smoothing;

    // --- FPV tuning ---
    FLOAT64 fpv_adaptive_damping_min;       // Adaptive damping minimum
    FLOAT64 fpv_adaptive_damping_max;       // Adaptive damping maximum
    FLOAT64 fpv_acceleration_prediction;    // Acceleration prediction gain
    FLOAT64 fpv_turbulence_rejection;       // Turbulence rejection gain
    bool    fpv_phase_aware_smoothing;      // Phase-aware smoothing enabled

    // --- Flare law ---
    FLOAT64 flare_activation_alt_ft;        // Flare activation altitude (ft)
    FLOAT64 flare_soft_transition_alt_ft;   // Soft transition start (ft)
    FLOAT64 flare_guidance_confidence;      // Flare guidance confidence (0..1)
    FLOAT64 flare_runway_stab_weight;       // Runway stabilization weighting
    FLOAT64 flare_floating_suppression;     // Float suppression cue gain

    // --- Rollout ---
    FLOAT64 rollout_centerline_gain;        // Centerline tracking gain
    FLOAT64 rollout_centerline_damping;     // Centerline damping factor
    FLOAT64 rollout_predictive_lead;        // Predictive nosewheel alignment
    FLOAT64 rollout_crosswind_stab;         // Crosswind stabilization gain
    FLOAT64 rollout_edge_stabilization;     // Runway edge visual stabilization
    bool    rollout_wet_assist;             // Wet runway stability assistance

    // --- Symbology styling ---
    FLOAT64 brightness_easing;              // Brightness easing factor
    FLOAT64 bloom_reduction;                // Bloom intensity reduction
    FLOAT64 line_cleanliness;               // Line cleanliness factor
    FLOAT64 horizon_stability_gain;         // Horizon stability multiplier
    FLOAT64 oscillation_reduction;          // Oscillation damping
    FLOAT64 alpha_fade_smoothness;          // Alpha fade smoothing
    FLOAT64 anti_shimmer_gain;              // Anti-shimmer filter gain
    FLOAT64 symbol_persistence;             // Symbol persistence smoothing

    // --- Declutter ---
    A350DeclutterPriorities declutter;

    // --- CAT III ---
    A350CatIIIParams cat3;

    // --- General ---
    bool    airbus_style_fpv;               // Enable Airbus-style FPV filtering
    bool    airbus_style_flare;             // Enable Airbus-style flare law
    bool    airbus_style_rollout;           // Enable Airbus-style rollout
    bool    airbus_style_declutter;         // Enable Airbus-style declutter
    bool    airbus_style_symbology;         // Enable Airbus-style symbology
    bool    airbus_cat3_enhanced;           // Enable Airbus CAT III enhancements
} A350HUDProfile;

// ============================================================================
//  5.  Profile retrieval
// ============================================================================

/// Get the default A350 HUD profile with Airbus-calibrated tuning.
const A350HUDProfile* a350_get_default_profile(void);

/// Apply L:var overrides to an A350 HUD profile at runtime.
void a350_profile_apply_lvars(A350HUDProfile* profile);

/// Check if the active aircraft ID matches an A350 variant.
bool a350_is_active_aircraft(const char* aircraft_id);

#endif // C_HUD_A350_PROFILE_H
