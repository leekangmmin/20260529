#ifndef C_HUD_A350_FLARE_LAW_H
#define C_HUD_A350_FLARE_LAW_H

// ============================================================================
//  Conformal HUD – Airbus A350 Flare Law Visualisation
//  MSFS 2024  ·  C++17  ·  WASM
//
//  v2.4.0 — Airbus-style flare transition logic.
//
//  The Airbus flare philosophy is fundamentally different from Boeing:
//    · Soft pitch transition below ~50 ft RA (progressive, not abrupt)
//    · Smooth sink-rate stabilisation (no aggressive flare command)
//    · Landing attitude assistance (steady pitch attitude hold)
//    · Floating suppression cues (subtle guidance to avoid float)
//    · Runway reference prioritisation during flare
//
//  The HUD becomes calmer during flare:
//    · Reduced unnecessary symbol motion
//    · Increased runway stabilisation
//    · Subtly prioritised runway references
//
//  Implementation is a three-phase system:
//    1. Pre-flare (80-50 ft): subtle pitch guidance cues begin
//    2. Flare (50-0 ft): primary flare law active, smooth transition
//    3. Touchdown: sink rate controlled, attitude held
// ============================================================================

#include "../../module.h"
#include "../../projection.h"

// ============================================================================
//  1.  Flare phase identifiers
// ============================================================================

typedef enum A350FlarePhase {
    A350_FLARE_INACTIVE    = 0,   // Above soft transition altitude
    A350_FLARE_PREFLARE    = 1,   // 80-50 ft: subtle cues begin
    A350_FLARE_ACTIVE      = 2,   // 50-0 ft: primary flare law
    A350_FLARE_TOUCHDOWN   = 3,   // At touchdown: attitude hold
} A350FlarePhase;

// ============================================================================
//  2.  Flare law state
// ============================================================================

typedef struct A350FlareLaw {
    // --- Phase tracking ---
    A350FlarePhase phase;                   // Current phase
    FLOAT64 engagement_alt_m;               // Altitude where flare engaged (m)
    FLOAT64 time_in_phase_s;                // Time spent in current phase (s)

    // --- Flare guidance ---
    FLOAT64 pitch_command_deg;              // Commanded pitch (deg)
    FLOAT64 pitch_rate_command_dps;         // Commanded pitch rate (deg/s)
    FLOAT64 sink_rate_command_ms;           // Commanded sink rate (m/s)
    FLOAT64 sink_rate_error_ms;             // Error between actual and commanded (m/s)

    // --- Smooth pitch attenuation ---
    FLOAT64 pitch_attenuation;              // 0..1 pitch attenuation factor
    FLOAT64 pitch_rate_limit_dps;           // Pitch rate limit (deg/s)

    // --- Flare guidance confidence ---
    FLOAT64 guidance_confidence;            // 0..1 flare guidance quality
    FLOAT64 sink_rate_stability;            // 0..1 sink rate stability

    // --- Runway stabilisation weighting ---
    FLOAT64 runway_stab_weight;             // 0..1 runway stabilisation weight
    FLOAT64 runway_visual_stab;             // 0..1 visual stability enhancement

    // --- Float suppression ---
    FLOAT64 float_suppression_cue;          // 0..1 float suppression
    FLOAT64 flare_completion;               // 0..1 flare completeness

    // --- Internal ---
    FLOAT64 prev_vertical_speed_ms;         // Previous vertical speed for rate calc
    FLOAT64 sink_rate_filtered;             // Filtered sink rate
    FLOAT64 pitch_filtered;                 // Filtered pitch command

    // --- Inputs ---
    FLOAT64 radio_altitude_m;               // Radio altitude (m)
    FLOAT64 vertical_speed_ms;              // Vertical speed (m/s)
    FLOAT64 groundspeed_ms;                 // Ground speed (m/s)
    FLOAT64 pitch_deg;                      // Aircraft pitch (deg)
    FLOAT64 gs_deviation_deg;               // Glideslope deviation (deg)

    // --- Profile tuning ---
    FLOAT64 activation_alt_ft;              // Activation altitude (ft)
    FLOAT64 soft_transition_alt_ft;         // Soft transition start (ft)
    FLOAT64 flare_guidance_confidence;      // Guidance confidence setting
    FLOAT64 runway_stab_weight_setting;     // Runway stabilization setting
    FLOAT64 float_suppression_gain;         // Float suppression gain setting

    // --- Debug ---
    bool    valid;
    bool    active;
} A350FlareLaw;

// ============================================================================
//  3.  Initialisation
// ============================================================================

/// Initialise the A350 flare law.
static inline void a350_flare_init(A350FlareLaw* fl) {
    if (fl == 0) return;

    fl->phase                     = A350_FLARE_INACTIVE;
    fl->engagement_alt_m          = 0.0;
    fl->time_in_phase_s           = 0.0;

    fl->pitch_command_deg         = 0.0;
    fl->pitch_rate_command_dps    = 0.0;
    fl->sink_rate_command_ms      = 0.0;
    fl->sink_rate_error_ms        = 0.0;

    fl->pitch_attenuation         = 0.0;
    fl->pitch_rate_limit_dps      = 2.0;

    fl->guidance_confidence       = 1.0;
    fl->sink_rate_stability       = 1.0;

    fl->runway_stab_weight        = 0.5;
    fl->runway_visual_stab        = 0.5;

    fl->float_suppression_cue      = 0.0;
    fl->flare_completion          = 0.0;

    fl->prev_vertical_speed_ms    = 0.0;
    fl->sink_rate_filtered        = 0.0;
    fl->pitch_filtered            = 0.0;

    fl->radio_altitude_m          = 100.0;
    fl->vertical_speed_ms         = 0.0;
    fl->groundspeed_ms            = 70.0;
    fl->pitch_deg                 = 2.0;
    fl->gs_deviation_deg          = 0.0;

    // Default tuning — Airbus style
    fl->activation_alt_ft           = 50.0;
    fl->soft_transition_alt_ft      = 80.0;
    fl->flare_guidance_confidence   = 0.95;
    fl->runway_stab_weight_setting  = 0.80;
    fl->float_suppression_gain      = 0.70;

    fl->valid  = false;
    fl->active = false;
}

// ============================================================================
//  4.  Flare law computation
// ============================================================================

/// Compute the A350 flare law state for the current frame.
///
/// Should be called every frame during approach and flare.
///
/// @param fl    [in/out] Flare law state (inputs populated, outputs computed)
/// @param dt_s  Frame delta time (seconds)
/// @return      true if computation succeeded
bool a350_flare_compute(A350FlareLaw* fl, FLOAT64 dt_s);

/// Get the runway stabilization multiplier for this frame.
/// Higher values = more stable runway symbology during flare.
///
/// @param fl    Flare law state
/// @return      Runway stabilization weight (0..1)
static inline FLOAT64 a350_flare_runway_stab(const A350FlareLaw* fl) {
    if (fl == 0) return 0.5;
    return fl->runway_stab_weight;
}

/// Get the flare phase as a human-readable string (for debugging).
const char* a350_flare_phase_name(A350FlarePhase phase);

/// Debug logging.
void a350_flare_debug_log(const A350FlareLaw* fl);

#endif // C_HUD_A350_FLARE_LAW_H
