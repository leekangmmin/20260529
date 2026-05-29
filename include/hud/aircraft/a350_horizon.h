#ifndef C_HUD_A350_HORIZON_CONTROLLER_H
#define C_HUD_A350_HORIZON_CONTROLLER_H

// ============================================================================
//  Conformal HUD – Airbus A350 XWB Horizon Stabilization Controller
//  MSFS 2024  ·  C++17  ·  WASM
//
//  v3.0.0 — A350 Certification Layer
//
//  Airbus-specific horizon stabilization that provides:
//
//    · Reduced micro-movement — horizon feels rock-solid
//    · Stabilized during turbulence — no visible jitter
//    · Predictive smoothing — anticipates pitch/bank changes
//    · No visible jitter — even in severe turbulence
//    · Flare stabilization — horizon stabilizes further during flare
//    · Low visibility enhancement — horizon more prominent in IMC
//
//  Sits on top of the existing HUDStabilisation temporal damper
//  for horizon pitch and slope.
// ============================================================================

#include "../../module.h"
#include "../../projection.h"
#include "../stabilization.h"

// ============================================================================
//  1.  Horizon controller state
// ============================================================================

typedef struct A350HorizonController {
    // --- Filtered outputs ---
    FLOAT64 stabilized_pitch_deg;       // final stabilized pitch (deg)
    FLOAT64 stabilized_bank_deg;        // final stabilized bank (deg)
    FLOAT64 horizon_y_px;              // horizon Y position on screen (px)
    FLOAT64 horizon_slope;             // horizon slope (tan of bank angle)
    FLOAT64 pitch_stability;           // 0..1 pitch stability estimate
    FLOAT64 bank_stability;            // 0..1 bank stability estimate

    // --- Internal filtering ---
    FLOAT64 pitch_raw;                  // raw pitch input
    FLOAT64 bank_raw;                   // raw bank input
    FLOAT64 pitch_filtered;             // EMA-filtered pitch
    FLOAT64 bank_filtered;              // EMA-filtered bank
    FLOAT64 pitch_rate_dps;             // pitch rate (deg/s)
    FLOAT64 bank_rate_dps;              // bank rate (deg/s)
    FLOAT64 pitch_ema_alpha;            // current pitch EMA alpha
    FLOAT64 bank_ema_alpha;             // current bank EMA alpha

    // --- Turbulence rejection ---
    FLOAT64 turbulence_damping;         // 0..1 extra damping from turbulence
    FLOAT64 jitter_accumulator;         // jitter tracking for horizon
    FLOAT64 turbulence_level;           // 0..1 estimated turbulence

    // --- Flare stabilization ---
    bool    flare_active;               // true during flare
    FLOAT64 flare_damping_boost;        // extra damping during flare
    FLOAT64 flare_pitch_hold_gain;      // pitch holding near touchdown

    // --- Low visibility enhancement ---
    bool    low_visibility;             // true in IMC / low vis
    FLOAT64 low_vis_stability_boost;    // extra stability in low vis

    // --- Configuration ---
    FLOAT64 pitch_alpha_min;            // min pitch EMA alpha (max smoothing)
    FLOAT64 pitch_alpha_max;            // max pitch EMA alpha
    FLOAT64 bank_alpha_min;             // min bank EMA alpha
    FLOAT64 bank_alpha_max;             // max bank EMA alpha
    FLOAT64 jitter_threshold;           // jitter threshold for damping
    FLOAT64 flare_damping_multiplier;   // damping multiplier during flare
    FLOAT64 low_vis_multiplier;         // stability multiplier in low vis

    // --- Debug ---
    bool    initialised;
    bool    valid;
} A350HorizonController;

// ============================================================================
//  2.  Initialisation
// ============================================================================

/// Initialise the A350 horizon controller with Airbus-default tuning.
static inline void a350_horizon_init(A350HorizonController* hc) {
    if (hc == 0) return;

    hc->stabilized_pitch_deg  = 0.0;
    hc->stabilized_bank_deg   = 0.0;
    hc->horizon_y_px          = 0.0;
    hc->horizon_slope         = 0.0;
    hc->pitch_stability       = 1.0;
    hc->bank_stability        = 1.0;

    hc->pitch_raw             = 0.0;
    hc->bank_raw              = 0.0;
    hc->pitch_filtered        = 0.0;
    hc->bank_filtered         = 0.0;
    hc->pitch_rate_dps        = 0.0;
    hc->bank_rate_dps         = 0.0;
    hc->pitch_ema_alpha       = 0.15;
    hc->bank_ema_alpha        = 0.12;

    hc->turbulence_damping    = 0.0;
    hc->jitter_accumulator    = 0.0;
    hc->turbulence_level      = 0.0;

    hc->flare_active          = false;
    hc->flare_damping_boost   = 0.0;
    hc->flare_pitch_hold_gain = 0.0;

    hc->low_visibility        = false;
    hc->low_vis_stability_boost = 0.0;

    // Airbus A350 certified tuning
    hc->pitch_alpha_min       = 0.08;   // very smooth pitch (max damping)
    hc->pitch_alpha_max       = 0.35;   // moderate responsiveness
    hc->bank_alpha_min        = 0.06;   // even smoother bank (max damping)
    hc->bank_alpha_max        = 0.30;
    hc->jitter_threshold      = 0.15;   // very sensitive jitter detection
    hc->flare_damping_multiplier = 2.0; // 2x damping during flare
    hc->low_vis_multiplier    = 1.5;    // 1.5x stability in low vis

    hc->initialised           = false;
    hc->valid                 = false;
}

// ============================================================================
//  3.  Core computation
// ============================================================================

/// Compute the A350 horizon stabilization for the current frame.
///
/// @param hc               [in/out] Horizon controller state
/// @param raw_pitch_deg    Raw aircraft pitch (degrees)
/// @param raw_bank_deg     Raw aircraft bank (degrees)
/// @param dt_s             Frame delta time (seconds)
/// @param flight_phase     Flight phase (0=CRUISE, 1=APPROACH, 2=FLARE, 3=ROLLOUT)
/// @param turbulence_level External turbulence estimate (0..1), or -1 for auto
/// @param low_visibility   True if low visibility conditions
void a350_horizon_compute(
    A350HorizonController* hc,
    FLOAT64 raw_pitch_deg,
    FLOAT64 raw_bank_deg,
    FLOAT64 dt_s,
    int     flight_phase,
    FLOAT64 turbulence_level,
    bool    low_visibility);

/// Get the stabilised pitch for horizon rendering.
static inline FLOAT64 a350_horizon_get_pitch(const A350HorizonController* hc) {
    if (hc == 0) return 0.0;
    return hc->stabilized_pitch_deg;
}

/// Get the stabilised bank for horizon rendering.
static inline FLOAT64 a350_horizon_get_bank(const A350HorizonController* hc) {
    if (hc == 0) return 0.0;
    return hc->stabilized_bank_deg;
}

/// Get the horizon stability score (0..1).
static inline FLOAT64 a350_horizon_get_stability(const A350HorizonController* hc) {
    if (hc == 0) return 0.0;
    return (hc->pitch_stability + hc->bank_stability) * 0.5;
}

// ============================================================================
//  4.  Debug logging
// ============================================================================

void a350_horizon_debug_log(const A350HorizonController* hc);

#endif // C_HUD_A350_HORIZON_CONTROLLER_H
