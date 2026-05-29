#ifndef C_HUD_AIRBUS_FPV_H
#define C_HUD_AIRBUS_FPV_H

// ============================================================================
//  Conformal HUD – Airbus-Style Flight Path Vector Filter
//  MSFS 2024  ·  C++17  ·  WASM
//
//  v2.4.0 — Airbus FPV characteristics.
//
//  The Airbus HUD flight path vector is designed to feel:
//    · Heavily damped — no jitter, smooth inertia
//    · Predictively led — anticipates flight path changes
//    · Low-pass filtered — intentional latency for stability
//    · Stabilised during turbulence — no annoying FPV dancing
//
//  Key differences from Boeing FPV:
//    · More aggressive filtering (higher damping ratios)
//    · Intentional phase delay for perceived stability
//    · Acceleration prediction to maintain responsiveness
//    · Turbulence rejection that doesn't wash out during gusts
//    · Runway alignment stabilisation during flare
// ============================================================================

#include "../../module.h"
#include "../../projection.h"
#include "../stabilization.h"

// ============================================================================
//  1.  Airbus FPV filter state
// ============================================================================

/// Airbus-specific FPV filter with adaptive damping, acceleration
/// prediction, turbulence rejection, and phase-aware smoothing.
typedef struct AirbusFPVFilter {
    // --- Adaptive damping ---
    FLOAT64 damping_min;                    // Minimum damping (least smooth)
    FLOAT64 damping_max;                    // Maximum damping (most smooth)
    FLOAT64 current_damping;                // Current adaptive damping factor
    FLOAT64 damping_adaptation_rate;        // How fast damping adapts

    // --- Acceleration prediction ---
    FLOAT64 acceleration;                   // Estimated acceleration
    FLOAT64 velocity;                       // Estimated velocity
    FLOAT64 prediction_gain;                // Prediction gain (0..1)
    FLOAT64 prev_filtered;                  // Previous filtered value

    // --- Turbulence rejection ---
    FLOAT64 turbulence_level;               // 0..1 estimated turbulence
    FLOAT64 turbulence_rejection_gain;      // How aggressively to reject
    FLOAT64 jitter_accumulator;             // Jitter tracking

    // --- Phase-aware smoothing ---
    bool    phase_aware_enabled;            // Enable phase-aware behaviour
    FLOAT64 phase_damping_multiplier;       // Damping multiplier per phase
    int     current_phase;                  // Current flight phase

    // --- Low-pass filter ---
    FLOAT64 lpf_cutoff_hz;                  // Low-pass cutoff frequency
    FLOAT64 lpf_state;                      // LPF internal state
    FLOAT64 intentional_latency_s;          // Intentional delay

    // --- Internal state ---
    AdaptiveEMAFilter ema_x;                // X-axis EMA filter
    AdaptiveEMAFilter ema_y;                // Y-axis EMA filter
    Vec2    raw_input;                      // Last raw input
    Vec2    filtered_output;                // Filtered output
    Vec2    predicted_output;               // With prediction applied
    bool    initialised;
} AirbusFPVFilter;

// ============================================================================
//  2.  Initialisation
// ============================================================================

/// Initialise the Airbus FPV filter with default tuning.
static inline void airbus_fpv_init(AirbusFPVFilter* f) {
    if (f == 0) return;

    f->damping_min              = 0.08;
    f->damping_max              = 0.55;
    f->current_damping          = 0.30;
    f->damping_adaptation_rate  = 0.05;

    f->acceleration             = 0.0;
    f->velocity                 = 0.0;
    f->prediction_gain          = 0.30;
    f->prev_filtered            = 0.0;

    f->turbulence_level         = 0.0;
    f->turbulence_rejection_gain = 0.90;
    f->jitter_accumulator       = 0.0;

    f->phase_aware_enabled      = true;
    f->phase_damping_multiplier = 1.0;
    f->current_phase            = 0;

    f->lpf_cutoff_hz            = 4.0;
    f->lpf_state                = 0.0;
    f->intentional_latency_s    = 0.050;

    adaptive_ema_init(&f->ema_x, f->damping_min, f->damping_max, 8.0);
    adaptive_ema_init(&f->ema_y, f->damping_min, f->damping_max, 8.0);

    f->raw_input        = proj_vec3_make(0, 0, 0);
    f->filtered_output  = proj_vec3_make(0, 0, 0);
    f->predicted_output = proj_vec3_make(0, 0, 0);
    f->initialised      = true;
}

// ============================================================================
//  3.  Core filtering
// ============================================================================

/// Configure the Airbus FPV filter with profile parameters.
///
/// @param f               Filter state
/// @param damping_min     Minimum adaptive damping (0.02..0.30)
/// @param damping_max     Maximum adaptive damping (0.20..0.80)
/// @param prediction_gain Prediction gain (0..1)
/// @param turbulence_rej  Turbulence rejection gain (0..1)
/// @param latency_s       Intentional latency (seconds)
void airbus_fpv_configure(AirbusFPVFilter* f,
                           FLOAT64 damping_min,
                           FLOAT64 damping_max,
                           FLOAT64 prediction_gain,
                           FLOAT64 turbulence_rej,
                           FLOAT64 latency_s);

/// Update the flight phase for phase-aware smoothing.
///
/// @param f       Filter state
/// @param phase   Flight phase identifier (0=CRUISE, 1=APPROACH, 2=FLARE, etc.)
void airbus_fpv_set_phase(AirbusFPVFilter* f, int phase);

/// Feed a raw FPV screen position into the filter.
///
/// The filter applies:
///   1. Adaptive EMA damping (turbulence-aware)
///   2. Low-pass filtering for intentional latency
///   3. Acceleration prediction for responsive feel
///   4. Phase-aware damping modulation
///
/// @param f        Filter state
/// @param raw      Raw FPV position (pixels)
/// @param dt_s     Frame delta time (seconds)
/// @return         Filtered FPV position with prediction
Vec2 airbus_fpv_feed(AirbusFPVFilter* f, Vec2 raw, FLOAT64 dt_s);

/// Get the current filtered (non-predicted) FPV position.
static inline Vec2 airbus_fpv_get_filtered(const AirbusFPVFilter* f) {
    if (f == 0) return proj_vec3_make(-9999, -9999, 0);
    return f->filtered_output;
}

/// Get the predicted FPV position (filtered + prediction).
static inline Vec2 airbus_fpv_get_predicted(const AirbusFPVFilter* f) {
    if (f == 0) return proj_vec3_make(-9999, -9999, 0);
    return f->predicted_output;
}

/// Get the current turbulence level estimate.
static inline FLOAT64 airbus_fpv_get_turbulence(const AirbusFPVFilter* f) {
    if (f == 0) return 0.0;
    return f->turbulence_level;
}

/// Reset the filter to an initial state.
void airbus_fpv_reset(AirbusFPVFilter* f);

#endif // C_HUD_AIRBUS_FPV_H
