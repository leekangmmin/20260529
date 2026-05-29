// ============================================================================
//  Conformal HUD – Airbus A350 XWB Landing Energy Management Model
//  MSFS 2024  ·  C++17  ·  WASM
//
//  v3.0.0 — A350 Certification Layer
//
//  Implements the landing energy model that computes energy scores,
//  flare aggressiveness recommendations, and rollout predictions.
// ============================================================================

#include "../../../include/hud/aircraft/a350_landing_energy.h"
#include "../../../include/projection.h"

// ============================================================================
//  Constants
// ============================================================================

#define ENERGY_EMA_ALPHA        0.10
#define STOP_DIST_ALPHA         0.15
#define BRAKE_EFFECTIVENESS_ALPHA 0.05

// ============================================================================
//  Core computation
// ============================================================================

void a350_landing_energy_compute(A350LandingEnergyModel* em, FLOAT64 dt_s) {
    if (em == 0) return;

    em->valid = false;

    const FLOAT64 weight_kg = proj_fmax(em->aircraft_weight_kg, 10000.0);
    const FLOAT64 gs_ms     = proj_fmax(em->groundspeed_ms, 0.1);
    const FLOAT64 vs_ms     = em->sink_rate_ms;  // negative = descent
    const FLOAT64 rwy_len   = proj_fmax(em->runway_length_m, 100.0);
    const FLOAT64 rwy_rem   = proj_fmax(em->runway_remaining_m, 0.0);
    const FLOAT64 decel     = proj_fmax(em->braking_decel_ms2, 0.0);

    // ================================================================
    //  Energy computation
    // ================================================================

    // Kinetic energy: 0.5 * m * v^2  (in joules, then MJ)
    em->kinetic_energy_mj = 0.5 * weight_kg * gs_ms * gs_ms * 1e-6;

    // Vertical energy: m * g * h where h is from sink rate
    // Using sink rate as a proxy for excess vertical energy
    const FLOAT64 sink_positive = proj_fmax(-vs_ms, 0.0);  // positive sink rate
    em->vertical_energy_mj = weight_kg * 9.80665 * sink_positive * 0.1 * 1e-6;

    // Total energy
    em->total_energy_mj = em->kinetic_energy_mj + em->vertical_energy_mj;

    // Reference energy (at reference approach speed and nominal sink)
    const FLOAT64 ref_ke = 0.5 * em->reference_landing_weight_kg *
                           em->reference_approach_speed_ms *
                           em->reference_approach_speed_ms * 1e-6;
    const FLOAT64 ref_ve = em->reference_landing_weight_kg * 9.80665 *
                           1.5 * 0.1 * 1e-6;  // 1.5 m/s nominal sink
    const FLOAT64 ref_total = ref_ke + ref_ve;

    // Energy above reference
    em->energy_above_reference = em->total_energy_mj - ref_total;

    // Specific energy (J/kg)
    em->specific_energy_j_kg = (em->kinetic_energy_mj * 1e6) / weight_kg;

    // ================================================================
    //  Landing energy score (0..1, lower = safer)
    // ================================================================

    {
        // Factor 1: Speed deviation from reference
        const FLOAT64 speed_ratio = gs_ms / proj_fmax(em->reference_approach_speed_ms, 1.0);
        FLOAT64 speed_score = 0.0;
        if (speed_ratio > 1.3) {
            speed_score = 1.0;  // 30% above ref = maximum score
        } else if (speed_ratio > 1.0) {
            speed_score = (speed_ratio - 1.0) / 0.3;
        }
        speed_score = proj_clamp(speed_score, 0.0, 1.0);

        // Factor 2: Sink rate
        const FLOAT64 sink_ratio = sink_positive / proj_fmax(em->max_sink_rate_ms, 0.1);
        FLOAT64 sink_score = proj_clamp(sink_ratio, 0.0, 1.0);

        // Factor 3: Runway remaining vs predicted
        FLOAT64 runway_score = 0.0;
        if (em->on_ground) {
            const FLOAT64 stop_dist = (gs_ms * gs_ms) /
                (2.0 * proj_fmax(decel, 0.5));
            const FLOAT64 stop_margin = rwy_rem - stop_dist;
            if (stop_margin < 0.0) {
                runway_score = 1.0;  // Overrun risk
            } else if (stop_margin < 500.0) {
                runway_score = 1.0 - (stop_margin / 500.0);
            }
        }

        // Weighted score (lower = better)
        const FLOAT64 raw_score = speed_score * 0.40 +
                                  sink_score * 0.35 +
                                  runway_score * 0.25;
        em->landing_energy_score = proj_clamp(raw_score, 0.0, 1.0);
    }

    // ================================================================
    //  Flare aggressiveness recommendation
    // ================================================================

    {
        // Higher energy = more aggressive flare (to dissipate energy)
        // Lower energy = gentler flare (to avoid stall)
        FLOAT64 aggressiveness = 0.5;  // nominal

        if (em->on_ground) {
            // On ground, no flare needed
            aggressiveness = 0.0;
        } else if (gs_ms > em->reference_approach_speed_ms * 1.1) {
            // Fast approach: more aggressive flare
            aggressiveness = 0.5 + 0.5 * ((gs_ms / em->reference_approach_speed_ms) - 1.1) / 0.2;
        } else if (sink_positive > 2.5) {
            // High sink rate: more aggressive flare
            aggressiveness = 0.5 + 0.5 * (sink_positive - 2.5) / 1.0;
        } else if (gs_ms < em->reference_approach_speed_ms * 0.9) {
            // Slow approach: gentler flare
            aggressiveness = 0.5 * (gs_ms / (em->reference_approach_speed_ms * 0.9));
        }

        em->flare_aggressiveness = proj_clamp(aggressiveness, 0.0, 1.0);

        // Sink rate advisory
        if (em->flare_aggressiveness > 0.7) {
            em->sink_rate_advisory_ms = -1.0 - (em->flare_aggressiveness - 0.7) * 1.5;
        } else {
            em->sink_rate_advisory_ms = -1.5 - (1.0 - em->flare_aggressiveness) * 0.5;
        }
        em->sink_rate_advisory_ms = proj_clamp(em->sink_rate_advisory_ms, -4.0, -0.5);

        // Flare onset advisory
        if (em->landing_energy_score > em->energy_warning_threshold) {
            em->flare_onset_advisory_ft = 60.0;  // Higher energy = flare earlier
        } else if (em->landing_energy_score > em->energy_caution_threshold) {
            em->flare_onset_advisory_ft = 55.0;
        } else {
            em->flare_onset_advisory_ft = 50.0;  // Normal 50 ft
        }
    }

    // ================================================================
    //  Rollout prediction
    // ================================================================

    {
        if (em->on_ground && gs_ms > 1.0) {
            // Current deceleration with braking effectiveness
            FLOAT64 effective_decel = decel;
            if (em->spoilers_deployed) effective_decel += 1.0;   // ~0.1g from spoilers
            if (em->reversers_deployed) effective_decel += 0.5;  // ~0.05g from reversers
            effective_decel = proj_fmax(effective_decel, 0.3);
            effective_decel = proj_fmin(effective_decel, em->max_braking_ms2);

            // Predicted stop distance from current speed
            const FLOAT64 stop_dist = (gs_ms * gs_ms) / (2.0 * effective_decel);
            em->predicted_stop_distance_m = stop_dist;

            // Stop margin
            em->predicted_stop_margin_m = rwy_rem - stop_dist;

            // Predicted exit speed (at runway end)
            if (stop_dist > rwy_rem) {
                const FLOAT64 excess_dist = stop_dist - rwy_rem;
                const FLOAT64 excess_energy = excess_dist * effective_decel;
                em->predicted_exit_speed_ms = proj_sqrt(2.0 * excess_energy);
            } else {
                em->predicted_exit_speed_ms = 0.0;
            }

            // Rollout energy remaining (fraction of initial energy)
            const FLOAT64 initial_ke = 0.5 * weight_kg *
                (proj_fmax(em->groundspeed_ms, gs_ms)) *
                (proj_fmax(em->groundspeed_ms, gs_ms));
            const FLOAT64 current_ke = 0.5 * weight_kg * gs_ms * gs_ms;
            if (initial_ke > 0.0) {
                em->rollout_energy_remaining = current_ke / initial_ke;
            }
        } else {
            // Not in rollout — predict based on approach energy
            const FLOAT64 predicted_stop = (gs_ms * gs_ms) / (2.0 * 1.47);
            em->predicted_stop_distance_m = predicted_stop;
            em->predicted_stop_margin_m = rwy_len - predicted_stop;
            em->predicted_exit_speed_ms = 0.0;
            em->rollout_energy_remaining = 1.0;
        }
    }

    // ================================================================
    //  Braking assessment
    // ================================================================

    {
        // Braking effectiveness based on deceleration vs max
        if (em->max_braking_ms2 > 0.1) {
            em->braking_effectiveness = decel / em->max_braking_ms2;
        }
        em->braking_effectiveness = proj_clamp(em->braking_effectiveness, 0.0, 1.0);

        // Braking advisory
        if (em->on_ground && em->predicted_stop_margin_m < 200.0) {
            // Need more braking
            em->braking_advisory = 1.0 - (em->predicted_stop_margin_m / 200.0);
            em->braking_advisory = proj_clamp(em->braking_advisory, 0.0, 1.0);
        } else {
            em->braking_advisory = 0.0;
        }

        // Recommended deceleration for safe stop
        if (em->on_ground && rwy_rem > 50.0 && gs_ms > 1.0) {
            em->recommended_decel_ms2 = (gs_ms * gs_ms) / (2.0 * rwy_rem * 0.8);
            em->recommended_decel_ms2 = proj_clamp(em->recommended_decel_ms2, 0.5, 4.5);
        } else {
            em->recommended_decel_ms2 = 1.47;
        }

        em->braking_effectiveness = proj_clamp(em->braking_effectiveness, 0.0, 1.0);
    }

    em->valid = true;
}

// ============================================================================
//  Debug logging
// ============================================================================

void a350_landing_energy_debug_log(const A350LandingEnergyModel* em) {
    if (em == 0) {
        MSFS_Log("[C_HUD_A350_ENERGY] A350LandingEnergyModel: NULL");
        return;
    }

    MSFS_Log("[C_HUD_A350_ENERGY] SCORE=%.2f KE=%.1fMJ VE=%.1fMJ "
             "FLARE_AGG=%.2f SINK_ADV=%.1f FLARE_ALT=%.0fft "
             "STOP_DIST=%.0fm MARGIN=%.0fm BRAKE=%.2f",
             em->landing_energy_score,
             em->kinetic_energy_mj, em->vertical_energy_mj,
             em->flare_aggressiveness,
             em->sink_rate_advisory_ms,
             em->flare_onset_advisory_ft,
             em->predicted_stop_distance_m,
             em->predicted_stop_margin_m,
             em->braking_effectiveness);
}
