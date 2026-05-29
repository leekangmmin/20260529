#ifndef C_HUD_A350_LANDING_ENERGY_H
#define C_HUD_A350_LANDING_ENERGY_H

// ============================================================================
//  Conformal HUD – Airbus A350 XWB Landing Energy Management Model
//  MSFS 2024  ·  C++17  ·  WASM
//
//  v3.0.0 — A350 Certification Layer
//
//  Models the landing energy state for the A350 HUD, providing:
//
//    · Landing energy score based on weight, sink rate, groundspeed
//    · Flare aggressiveness recommendations
//    · Rollout prediction (stop point, remaining runway)
//    · Braking performance estimation
//    · Dedicated L:Var publishing for external use
//
//  This module allows the HUD to display energy-aware symbology
//  that helps the pilot manage the landing profile.
// ============================================================================

#include "../../module.h"
#include "../../projection.h"

// ============================================================================
//  1.  Landing energy state
// ============================================================================

typedef struct A350LandingEnergyModel {
    // --- Inputs ---
    FLOAT64 aircraft_weight_kg;         // aircraft weight (kg)
    FLOAT64 sink_rate_ms;               // vertical speed (m/s, positive = up)
    FLOAT64 groundspeed_ms;             // ground speed (m/s)
    FLOAT64 runway_length_m;            // runway length (m)
    FLOAT64 runway_remaining_m;         // remaining runway (m)
    FLOAT64 braking_decel_ms2;          // current braking deceleration (m/s²)
    FLOAT64 max_braking_ms2;            // maximum possible braking (m/s²)
    FLOAT64 headwind_component_ms;      // headwind component (m/s)
    bool    reversers_deployed;         // thrust reversers deployed
    bool    spoilers_deployed;          // ground spoilers deployed
    bool    on_ground;                  // true if on ground
    bool    autobrake_active;           // true if autobrake is active

    // --- Computed values ---
    FLOAT64 landing_energy_score;       // 0..1 normalized energy score
    FLOAT64 kinetic_energy_mj;         // kinetic energy (megajoules)
    FLOAT64 vertical_energy_mj;        // vertical energy component (MJ)
    FLOAT64 total_energy_mj;           // total landing energy (MJ)
    FLOAT64 energy_above_reference;    // energy above reference (MJ)
    FLOAT64 specific_energy_j_kg;      // specific energy (J/kg)

    // --- Flare aggressiveness ---
    FLOAT64 flare_aggressiveness;       // 0..1 recommended flare aggressiveness
    FLOAT64 sink_rate_advisory_ms;      // recommended sink rate (m/s)
    FLOAT64 flare_onset_advisory_ft;    // recommended flare onset altitude (ft)

    // --- Rollout prediction ---
    FLOAT64 predicted_stop_distance_m;  // predicted stop distance (m)
    FLOAT64 predicted_stop_margin_m;    // stop margin = remaining - predicted (m)
    FLOAT64 predicted_exit_speed_ms;    // predicted exit speed (m/s)
    FLOAT64 rollout_energy_remaining;   // 0..1 energy remaining in rollout

    // --- Braking assessment ---
    FLOAT64 braking_effectiveness;      // 0..1 braking effectiveness
    FLOAT64 braking_advisory;           // braking advisory level (0..1)
    FLOAT64 recommended_decel_ms2;      // recommended deceleration (m/s²)

    // --- Configuration ---
    FLOAT64 reference_landing_weight_kg;  // reference landing weight (kg)
    FLOAT64 reference_approach_speed_ms;  // reference Vapp (m/s)
    FLOAT64 max_sink_rate_ms;           // max acceptable sink rate (m/s)
    FLOAT64 energy_warning_threshold;    // warning threshold (0..1)
    FLOAT64 energy_caution_threshold;    // caution threshold (0..1)

    // --- Debug ---
    bool    valid;
} A350LandingEnergyModel;

// ============================================================================
//  2.  Initialisation
// ============================================================================

/// Initialise the landing energy model with Airbus-default tuning.
static inline void a350_landing_energy_init(A350LandingEnergyModel* em) {
    if (em == 0) return;

    em->aircraft_weight_kg     = 180000.0;   // ~180t typical landing weight
    em->sink_rate_ms           = -2.0;        // typical 2 m/s sink rate
    em->groundspeed_ms         = 70.0;        // ~136 kt approach speed
    em->runway_length_m        = 3000.0;      // 3000m typical
    em->runway_remaining_m     = 3000.0;
    em->braking_decel_ms2      = 0.0;
    em->max_braking_ms2        = 4.5;         // ~0.46g max braking
    em->headwind_component_ms  = 0.0;
    em->reversers_deployed     = false;
    em->spoilers_deployed      = false;
    em->on_ground              = false;
    em->autobrake_active       = false;

    em->landing_energy_score     = 0.0;
    em->kinetic_energy_mj       = 0.0;
    em->vertical_energy_mj      = 0.0;
    em->total_energy_mj         = 0.0;
    em->energy_above_reference  = 0.0;
    em->specific_energy_j_kg    = 0.0;

    em->flare_aggressiveness    = 0.5;
    em->sink_rate_advisory_ms   = -1.5;
    em->flare_onset_advisory_ft = 50.0;

    em->predicted_stop_distance_m = 0.0;
    em->predicted_stop_margin_m   = 0.0;
    em->predicted_exit_speed_ms   = 0.0;
    em->rollout_energy_remaining   = 0.0;

    em->braking_effectiveness   = 1.0;
    em->braking_advisory        = 0.0;
    em->recommended_decel_ms2   = 1.47;   // ~0.15g

    // Airbus A350 reference values
    em->reference_landing_weight_kg = 180000.0;
    em->reference_approach_speed_ms = 70.0;    // ~136 kt
    em->max_sink_rate_ms           = 3.5;       // max 3.5 m/s
    em->energy_warning_threshold   = 0.80;
    em->energy_caution_threshold   = 0.60;

    em->valid = false;
}

// ============================================================================
//  3.  Core computation
// ============================================================================

/// Compute the landing energy model state for the current frame.
///
/// @param em    [in/out] Energy model state (inputs must be populated)
/// @param dt_s  Frame delta time (seconds)
void a350_landing_energy_compute(A350LandingEnergyModel* em, FLOAT64 dt_s);

/// Get the landing energy score as a normalised value (0..1).
static inline FLOAT64 a350_landing_energy_score(const A350LandingEnergyModel* em) {
    if (em == 0) return 0.0;
    return em->landing_energy_score;
}

/// Get the recommended flare aggressiveness (0 = gentle, 1 = aggressive).
static inline FLOAT64 a350_landing_flare_aggressiveness(const A350LandingEnergyModel* em) {
    if (em == 0) return 0.5;
    return em->flare_aggressiveness;
}

/// Get the predicted stop margin (positive = enough runway, negative = overrun risk).
static inline FLOAT64 a350_landing_stop_margin_m(const A350LandingEnergyModel* em) {
    if (em == 0) return 0.0;
    return em->predicted_stop_margin_m;
}

// ============================================================================
//  4.  Debug logging
// ============================================================================

void a350_landing_energy_debug_log(const A350LandingEnergyModel* em);

#endif // C_HUD_A350_LANDING_ENERGY_H
