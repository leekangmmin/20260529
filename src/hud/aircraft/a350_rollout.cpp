// ============================================================================
//  Conformal HUD – Airbus A350 Rollout Augmentation Implementation
//  MSFS 2024  ·  C++17  ·  WASM
//
//  v2.4.0 — Airbus-specific rollout behaviour.
//
//  Airbus rollout augmentation provides:
//    · Extremely stable centerline guidance with adaptive damping
//    · Predictive nosewheel alignment for smooth turn anticipation
//    · Gradual aerodynamic-to-nosewheel steering transition
//    · Crosswind compensation during rollout
//    · Wet runway stability enhancement
//    · Centerline and edge visual stabilisation
//
//  The system is designed to feel confident and stable, with smooth
//  transitions and no aggressive steering commands.
// ============================================================================

#include "../../../include/hud/aircraft/a350_rollout.h"
#include "../../../include/projection.h"

// ============================================================================
//  1.  Constants
// ============================================================================

#define A350_ROLLOUT_ACTIVE_SPEED_KT     80.0
#define A350_ROLLOUT_DECEL_TARGET_MS2    1.47   // ~0.15g
#define A350_ROLLOUT_DECEL_ALPHA         0.10   // Deceleration smoothing
#define A350_ROLLOUT_STEERING_ALPHA      0.15   // Steering command smoothing
#define A350_ROLLOUT_MAX_STEERING_DEG    8.0    // Max steering command
#define A350_ROLLOUT_CROSSWIND_LIMIT     15.0   // Crosswind limit (kt)

// ============================================================================
//  2.  Core computation
// ============================================================================

bool a350_rollout_compute(A350RolloutAugmentation* ra, FLOAT64 dt_s) {
    if (ra == 0) return false;

    ra->valid = false;

    const FLOAT64 speed_kt = ra->groundspeed_ms * 1.94384;  // m/s to kt
    const bool should_activate = a350_rollout_should_activate(
        ra->on_ground, 0.5, speed_kt);

    // --- Activation ---
    if (should_activate && !ra->active) {
        ra->active = true;
        ra->time_s = 0.0;
        ra->nosewheel_fraction = 0.0;
        ra->aerodynamic_fraction = 1.0;
    }

    if (!should_activate && ra->active) {
        if (ra->groundspeed_ms < 0.5) {
            ra->active = false;
        }
    }

    if (!ra->active) {
        ra->steering_command_deg = 0.0;
        ra->centerline_error_deg = 0.0;
        ra->centerline_stability = 1.0;
        ra->valid = true;
        return true;
    }

    ra->time_s += dt_s;

    // ================================================================
    //  Centerline error computation
    // ================================================================
    {
        FLOAT64 heading_error = ra->heading_deg - ra->runway_heading_deg;
        // Normalise to [-180, 180]
        while (heading_error > 180.0) heading_error -= 360.0;
        while (heading_error < -180.0) heading_error += 360.0;

        ra->centerline_error_deg = heading_error;

        // Lateral deviation contribution (scaled down for Airbus stability)
        FLOAT64 lateral_contrib = ra->lateral_deviation_m * 0.35;

        // Total raw error
        FLOAT64 total_error = heading_error + lateral_contrib;
        total_error = proj_clamp(total_error, -30.0, 30.0);

        ra->steering_raw_deg = total_error * ra->centerline_gain;
        ra->steering_raw_deg = proj_clamp(ra->steering_raw_deg,
                                           -A350_ROLLOUT_MAX_STEERING_DEG,
                                           A350_ROLLOUT_MAX_STEERING_DEG);
    }

    // ================================================================
    //  Predictive steering (anticipate turns)
    // ================================================================
    {
        // Compute track error rate of change as a predictor
        FLOAT64 track_error = ra->track_deg - ra->runway_heading_deg;
        while (track_error > 180.0) track_error -= 360.0;
        while (track_error < -180.0) track_error += 360.0;

        // Predictive component = track error * lead gain
        // This anticipates where the aircraft is heading
        ra->predictive_steering = track_error * ra->predictive_lead_gain * 0.5;

        // Blend predictive steering into raw command
        ra->steering_raw_deg += ra->predictive_steering;
        ra->steering_raw_deg = proj_clamp(ra->steering_raw_deg,
                                           -A350_ROLLOUT_MAX_STEERING_DEG,
                                           A350_ROLLOUT_MAX_STEERING_DEG);
    }

    // ================================================================
    //  Adaptive damping
    // ================================================================
    {
        // Base damping from profile
        FLOAT64 damping = ra->centerline_damping;

        // Reduce damping at low speed (more responsive)
        const FLOAT64 speed_factor = proj_fmin(speed_kt / A350_ROLLOUT_ACTIVE_SPEED_KT, 1.0);
        damping = damping * (0.5 + 0.5 * speed_factor);

        // Crosswind: increase damping with crosswind
        if (ra->crosswind_stab_gain > 0.0) {
            const FLOAT64 crosswind_kt = ra->crosswind_ms * 1.94384;
            const FLOAT64 cw_factor = proj_fmin(crosswind_kt / A350_ROLLOUT_CROSSWIND_LIMIT, 1.0);
            damping += cw_factor * 0.15;  // Additional damping in crosswind
        }

        // Wet runway: increase damping for stability
        if (ra->wet_runway && ra->wet_assist_enabled) {
            damping *= ra->wet_gain_multiplier;
        }

        ra->steering_damping = proj_clamp(damping, 0.3, 0.98);
    }

    // ================================================================
    //  Smooth steering command (EMA filter)
    // ================================================================
    {
        const FLOAT64 alpha = A350_ROLLOUT_STEERING_ALPHA * (1.0 - ra->steering_damping * 0.5);
        ra->steering_command_deg = ra->steering_command_deg * (1.0 - alpha) +
                                    ra->steering_raw_deg * alpha;
        ra->steering_command_deg = proj_clamp(ra->steering_command_deg,
                                               -A350_ROLLOUT_MAX_STEERING_DEG,
                                               A350_ROLLOUT_MAX_STEERING_DEG);
    }

    // ================================================================
    //  Nosewheel transition (gradual from aerodynamic)
    // ================================================================
    {
        // Nosewheel transitions from 0 to 1 as speed decreases
        // Aerodynamic steering is effective at high speed
        // Nosewheel steering is used at low speed
        const FLOAT64 speed_ratio = proj_fmin(speed_kt / A350_ROLLOUT_ACTIVE_SPEED_KT, 1.0);

        // Target: nosewheel takes over below ~40 kt
        if (speed_kt < 40.0) {
            ra->nosewheel_target = 1.0;
        } else if (speed_kt < 80.0) {
            ra->nosewheel_target = 1.0 - (speed_kt - 40.0) / 40.0;
        } else {
            ra->nosewheel_target = 0.0;
        }

        // Smooth transition
        const FLOAT64 transition_rate = dt_s / ra->nosewheel_transition_s;
        ra->nosewheel_fraction += (ra->nosewheel_target - ra->nosewheel_fraction) * transition_rate;
        ra->nosewheel_fraction = proj_clamp(ra->nosewheel_fraction, 0.0, 1.0);

        // Aerodynamic steering is complement of nosewheel
        ra->aerodynamic_fraction = 1.0 - ra->nosewheel_fraction;
    }

    // ================================================================
    //  Crosswind compensation
    // ================================================================
    {
        // Compute crosswind component relative to runway
        const FLOAT64 wind_angle = ra->track_deg - ra->runway_heading_deg;
        ra->crosswind_compensation = wind_angle * ra->crosswind_stab_gain * 0.3;
        ra->crosswind_compensation = proj_clamp(ra->crosswind_compensation, -3.0, 3.0);
    }

    // ================================================================
    //  Centerline stability assessment
    // ================================================================
    {
        // Stability is high when:
        //   - Centerline error is small
        //   - Speed is in appropriate range
        //   - Nosewheel transition is progressing smoothly

        const FLOAT64 error_quality = 1.0 - proj_fmin(proj_fabs(ra->centerline_error_deg) / 3.0, 1.0);
        const FLOAT64 speed_quality = (speed_kt > 20.0 && speed_kt < 100.0) ? 1.0 : 0.7;
        const FLOAT64 nosewheel_quality = 0.5 + ra->nosewheel_fraction * 0.5;
        const FLOAT64 time_quality = proj_fmin(ra->time_s / 3.0, 1.0);

        ra->centerline_stability = (error_quality * 0.4 +
                                     speed_quality * 0.2 +
                                     nosewheel_quality * 0.2 +
                                     time_quality * 0.2);
        ra->centerline_stability = proj_clamp(ra->centerline_stability, 0.0, 1.0);
    }

    // ================================================================
    //  Deceleration smoothing
    // ================================================================
    {
        ra->deceleration_smooth = ra->deceleration_smooth * (1.0 - A350_ROLLOUT_DECEL_ALPHA) +
                                  ra->deceleration_ms2 * A350_ROLLOUT_DECEL_ALPHA;
    }

    // ================================================================
    //  Visual stabilisation
    // ================================================================
    {
        // Edge stabilisation: smooth runway edge visuals
        ra->edge_stabilization = 0.5 + ra->centerline_stability * 0.5;
        ra->edge_stabilization *= ra->edge_stab_gain;

        // Centerline visual smoothing
        ra->centerline_visual_smooth = 0.7 + ra->centerline_stability * 0.3;
    }

    ra->valid = true;
    return true;
}

// ============================================================================
//  3.  Apply to generic rollout state
// ============================================================================

void a350_rollout_apply_to_state(RolloutState* rs,
                                  const A350RolloutAugmentation* ra) {
    if (rs == 0 || ra == 0) return;

    if (!ra->active || !ra->valid) return;

    // Override generic steering command with Airbus-filtered version
    rs->steering_command_deg = ra->steering_command_deg;

    // Apply crosswind compensation
    rs->centerline_error_deg = ra->centerline_error_deg + ra->crosswind_compensation;

    // Apply adaptive damping
    rs->steering_damping = ra->steering_damping;

    // Apply nosewheel transition
    rs->nosewheel_fraction = ra->nosewheel_fraction;

    // Centerline quality from Airbus stability assessment
    rs->centerline_quality = ra->centerline_stability;

    // Confidence amplification from stability
    rs->confidence = (rs->confidence + ra->centerline_stability) * 0.5;

    // Perspective compression adjusted for Airbus smoothness
    if (rs->phase == ROLLOUT_PHASE_ACTIVE) {
        const FLOAT64 speed_kt = ra->groundspeed_ms * 1.94384;
        const FLOAT64 speed_factor = proj_fmin(speed_kt / A350_ROLLOUT_ACTIVE_SPEED_KT, 1.0);
        rs->perspective_compression = 0.3 + 0.7 * speed_factor;
    }
}

// ============================================================================
//  4.  Debug logging
// ============================================================================

void a350_rollout_debug_log(const A350RolloutAugmentation* ra) {
    if (ra == 0) {
        MSFS_Log("[C_HUD_A350_ROLL] A350RolloutAugmentation: NULL");
        return;
    }

    MSFS_Log("[C_HUD_A350_ROLL] ACT=%d SPEED=%.1fkt ERR=%.1fdeg "
             "STEER=%.1fdeg DAMP=%.2f NW=%.2f AERO=%.2f "
             "CROSS=%.2f STAB=%.2f EDGE=%.2f",
             (int)ra->active, ra->groundspeed_ms * 1.94384,
             ra->centerline_error_deg,
             ra->steering_command_deg, ra->steering_damping,
             ra->nosewheel_fraction, ra->aerodynamic_fraction,
             ra->crosswind_compensation,
             ra->centerline_stability, ra->edge_stabilization);
}
