// ============================================================================
//  Conformal HUD – Rollout Guidance System Implementation
//  MSFS 2024  ·  C++17  ·  WASM
//
//  v2.4.0 — CAT III rollout guidance realism.
//  Provides stable, aircraft-like rollout behaviour with centerline
//  steering damping, nosewheel transition smoothing, deceleration
//  cues, and perspective compression during the landing roll.
// ============================================================================

#include "../../include/hud/rollout.h"
#include "../../include/projection.h"

// ============================================================================
//  1.  Constants
// ============================================================================

#define ROLLOUT_TRANSITION_TIME_S  2.0   // Flare→rollout handover time
#define ROLLOUT_NOSEWHEEL_TIME_S   2.5   // Nosewheel ramp-up time
#define ROLLOUT_ACTIVE_SPEED_KT    80.0  // Below this, rollout is active
#define ROLLOUT_COMPLETE_SPEED_KT  30.0  // Below this, rollout complete
#define ROLLOUT_STEERING_GAIN      3.0   // Heading error → steering command
#define ROLLOUT_STEERING_DAMP_BASE 0.6   // Base damping factor
#define ROLLOUT_MAX_STEERING_DEG  10.0   // Max steering command (deg)
#define ROLLOUT_CONFIDENCE_DECAY   0.98  // Confidence decay per frame
#define ROLLOUT_CONFIDENCE_RECOVER 0.01  // Confidence recovery per frame

// ============================================================================
//  2.  Rollout guidance computation
// ============================================================================

bool rollout_compute(RolloutState* rs, FLOAT64 dt_s) {
    if (rs == 0) return false;

    rs->valid = false;

    const bool should_activate = rollout_should_activate(
        rs->on_ground, rs->radio_altitude_m, -1.0);  // assumed descending

    // --- Phase management ---
    if (!should_activate && rs->phase == ROLLOUT_PHASE_INACTIVE) {
        // Remain inactive
        rs->steering_command_deg = 0.0;
        rs->centerline_error_dots = 0.0;
        rs->transition_complete = 0.0;
        rs->nosewheel_fraction = 0.0;
        rs->brake_advisory = 0.0;
        rs->valid = true;
        return true;
    }

    if (should_activate && rs->phase == ROLLOUT_PHASE_INACTIVE) {
        // Transition from inactive → transition
        rs->phase = ROLLOUT_PHASE_TRANSITION;
        rs->transition_s = 0.0;
        rs->rollout_time_s = 0.0;
        rs->rollout_frame_count = 0;
        rs->nosewheel_fraction = 0.0;
        rs->confidence = 0.3;  // Low confidence at touchdown
    }

    // --- Speed check for phase transitions ---
    const FLOAT64 speed_kt = rs->groundspeed_ms * 1.94384;  // m/s → kt

    if (rs->phase != ROLLOUT_PHASE_INACTIVE) {
        rs->rollout_time_s += dt_s;
        ++rs->rollout_frame_count;
    }

    if (rs->phase == ROLLOUT_PHASE_ACTIVE && speed_kt < ROLLOUT_COMPLETE_SPEED_KT) {
        rs->phase = ROLLOUT_PHASE_COMPLETE;
    }

    // ================================================================
    //  TOUCHDOWN TRANSITION SMOOTHING
    // ================================================================
    if (rs->phase == ROLLOUT_PHASE_TRANSITION) {
        rs->transition_s += dt_s;
        rs->transition_complete = proj_fmin(1.0,
            rs->transition_s / ROLLOUT_TRANSITION_TIME_S);

        if (rs->transition_complete >= 1.0) {
            rs->phase = ROLLOUT_PHASE_ACTIVE;
            rs->transition_complete = 1.0;
        }
    } else {
        rs->transition_complete = 1.0;
    }

    // ================================================================
    //  NOSEWHEEL TRANSITION SMOOTHING
    // ================================================================
    if (rs->phase == ROLLOUT_PHASE_TRANSITION || rs->phase == ROLLOUT_PHASE_ACTIVE) {
        // Nosewheel fraction ramps up over time
        const FLOAT64 nosewheel_target = (rs->phase == ROLLOUT_PHASE_ACTIVE) ? 1.0 : 0.3;
        const FLOAT64 ramp_time = (rs->phase == ROLLOUT_PHASE_ACTIVE)
            ? ROLLOUT_NOSEWHEEL_TIME_S : ROLLOUT_NOSEWHEEL_TIME_S * 0.5;

        rs->nosewheel_fraction += (nosewheel_target - rs->nosewheel_fraction) *
                                   (dt_s / ramp_time);
        rs->nosewheel_fraction = proj_clamp(rs->nosewheel_fraction, 0.0, 1.0);
    }

    // ================================================================
    //  CENTERLINE STEERING
    // ================================================================
    {
        // Compute heading error relative to runway centerline
        FLOAT64 heading_error = rs->heading_deg - rs->runway_heading_deg;
        // Normalize to [-180, 180]
        while (heading_error > 180.0) heading_error -= 360.0;
        while (heading_error < -180.0) heading_error += 360.0;

        rs->centerline_error_deg = heading_error;

        // Lateral deviation contribution (scaled)
        FLOAT64 lateral_contrib = rs->lateral_deviation_m * 0.5;

        // Total error for steering
        FLOAT64 total_error = heading_error + lateral_contrib;
        if (total_error > 30.0) total_error = 30.0;
        if (total_error < -30.0) total_error = -30.0;

        // Adaptive damping: more damping at higher speed, less at low speed
        const FLOAT64 speed_norm = proj_fmin(speed_kt / ROLLOUT_ACTIVE_SPEED_KT, 1.0);
        rs->steering_damping = ROLLOUT_STEERING_DAMP_BASE +
                               speed_norm * 0.3;  // 0.6 → 0.9

        // Apply steering with damping
        const FLOAT64 damping_factor = 1.0 - rs->steering_damping * 0.5;
        rs->steering_command_deg = rs->steering_command_deg * damping_factor +
                                    total_error * ROLLOUT_STEERING_GAIN * (1.0 - damping_factor);

        // Clamp steering command
        if (rs->steering_command_deg > ROLLOUT_MAX_STEERING_DEG)
            rs->steering_command_deg = ROLLOUT_MAX_STEERING_DEG;
        if (rs->steering_command_deg < -ROLLOUT_MAX_STEERING_DEG)
            rs->steering_command_deg = -ROLLOUT_MAX_STEERING_DEG;

        // Convert to dots for display
        rs->centerline_error_dots = total_error * 0.1;
        if (rs->centerline_error_dots > 1.0) rs->centerline_error_dots = 1.0;
        if (rs->centerline_error_dots < -1.0) rs->centerline_error_dots = -1.0;
    }

    // ================================================================
    //  CONFIDENCE WEIGHTING
    // ================================================================
    {
        // Confidence is high when:
        //   - Centerline error is small
        //   - Speed is in the right range
        //   - Nosewheel is fully engaged
        //   - Rollout has been active for a few seconds

        const FLOAT64 error_quality = 1.0 - proj_fmin(proj_fabs(rs->centerline_error_deg) / 5.0, 1.0);
        const FLOAT64 speed_quality = (speed_kt > 30.0 && speed_kt < 120.0) ? 1.0 : 0.5;
        const FLOAT64 nosewheel_quality = rs->nosewheel_fraction;
        const FLOAT64 time_quality = proj_fmin(rs->rollout_time_s / 5.0, 1.0);

        FLOAT64 raw_confidence = (error_quality * 0.4 +
                                   speed_quality * 0.2 +
                                   nosewheel_quality * 0.25 +
                                   time_quality * 0.15);

        // Smooth confidence changes
        if (raw_confidence > rs->confidence) {
            rs->confidence += (raw_confidence - rs->confidence) * 0.05;
        } else {
            rs->confidence += (raw_confidence - rs->confidence) * 0.1;
        }
        rs->confidence = proj_clamp(rs->confidence, 0.0, 1.0);

        rs->centerline_quality = error_quality;
    }

    // ================================================================
    //  DECELERATION CUE
    // ================================================================
    {
        // Target deceleration: ~0.15 g (1.47 m/s²) for normal braking
        rs->target_decel_ms2 = 1.47;
        rs->decel_rate_ms2 = (speed_kt > 30.0) ?
            proj_fmin(proj_fabs(rs->decel_rate_ms2), 4.0) : 0.0;

        // Compute deceleration error
        FLOAT64 decel_diff = rs->decel_rate_ms2 - rs->target_decel_ms2;
        rs->decel_error = decel_diff / 1.47;  // normalised to g

        // Brake advisory: show when deceleration is below target
        if (rs->phase == ROLLOUT_PHASE_ACTIVE && speed_kt > 40.0) {
            rs->brake_advisory = proj_clamp(
                (rs->target_decel_ms2 - rs->decel_rate_ms2) / 1.0,
                0.0, 1.0);

            // Reduce advisory close to target
            if (rs->decel_error < 0.3) {
                rs->brake_advisory *= 0.3;
            }
        } else {
            rs->brake_advisory = 0.0;
        }
    }

    // ================================================================
    //  PERSPECTIVE COMPRESSION
    // ================================================================
    {
        // During rollout, the runway perspective compresses as speed
        // decreases. This creates a visual "slowing down" effect.
        // Compression factor: 1.0 at touchdown, approaches 0.3 at low speed.
        if (rs->phase == ROLLOUT_PHASE_ACTIVE || rs->phase == ROLLOUT_PHASE_TRANSITION) {
            const FLOAT64 speed_factor = proj_fmin(speed_kt / ROLLOUT_ACTIVE_SPEED_KT, 1.0);
            rs->perspective_compression = 0.3 + 0.7 * speed_factor;
        } else {
            rs->perspective_compression = 1.0;
        }
    }

    rs->valid = true;
    return true;
}

// ============================================================================
//  3.  Rollout cue projection
// ============================================================================

void rollout_project_cue(const RolloutState* rs,
                          FLOAT64             focal_px,
                          int                 screen_w,
                          int                 screen_h,
                          FLOAT64             runway_cx,
                          FLOAT64             runway_cy,
                          RolloutCue*         cue) {
    (void)focal_px;

    if (cue == 0) {
        return;
    }

    cue->visible = false;
    cue->centerline_pos.x = -9999.0;
    cue->centerline_pos.y = -9999.0;
    cue->centerline_width_px = 0.0;
    cue->centerline_alpha = 0.0;

    if (rs == 0 || !rs->valid) {
        return;
    }

    if (rs->phase == ROLLOUT_PHASE_INACTIVE || rs->phase == ROLLOUT_PHASE_COMPLETE) {
        return;
    }

    // --- Centerline cue position ---
    // The centerline cue is positioned at the runway center, with
    // lateral offset proportional to the steering command.
    const FLOAT64 lateral_offset = rs->steering_command_deg * 2.0;
    cue->centerline_pos.x = runway_cx + lateral_offset;
    cue->centerline_pos.y = runway_cy;

    // Clamp to screen
    if (cue->centerline_pos.x < 0.0) cue->centerline_pos.x = 0.0;
    if (cue->centerline_pos.x > (FLOAT64)screen_w) cue->centerline_pos.x = (FLOAT64)screen_w;

    // --- Centerline width ---
    // Width decreases as confidence increases (tighter tracking)
    cue->centerline_width_px = 4.0 + (1.0 - rs->confidence) * 4.0;

    // --- Centerline alpha ---
    // Fade in during transition, modulated by confidence
    FLOAT64 alpha = rs->transition_complete * 0.7 +
                    rs->confidence * 0.3;
    if (rs->phase == ROLLOUT_PHASE_TRANSITION) {
        alpha *= rs->transition_complete;
    }
    cue->centerline_alpha = proj_clamp(alpha, 0.0, 1.0);

    // --- Deceleration cue ---
    // Show a deceleration cue indicator on the right side
    if (rs->brake_advisory > 0.01) {
        cue->decel_cue_pos_x = (FLOAT64)screen_w - 100.0;
        cue->decel_cue_alpha = rs->brake_advisory * 0.8;
    } else {
        cue->decel_cue_pos_x = -9999.0;
        cue->decel_cue_alpha = 0.0;
    }

    cue->visible = (cue->centerline_alpha > 0.01);
}

// ============================================================================
//  4.  Debug logging
// ============================================================================

void rollout_debug_log(const RolloutState* rs) {
    if (rs == 0) {
        MSFS_Log("[C_HUD_ROLL] RolloutState: NULL");
        return;
    }
    if (!rs->valid) {
        MSFS_Log("[C_HUD_ROLL] RolloutState: INVALID");
        return;
    }

    const char* phase_str = "?";
    switch (rs->phase) {
        case ROLLOUT_PHASE_INACTIVE:   phase_str = "INACTIVE";   break;
        case ROLLOUT_PHASE_TRANSITION: phase_str = "TRANSITION"; break;
        case ROLLOUT_PHASE_ACTIVE:     phase_str = "ACTIVE";     break;
        case ROLLOUT_PHASE_COMPLETE:   phase_str = "COMPLETE";   break;
    }

    MSFS_Log("[C_HUD_ROLL] PHASE=%s  GS=%.1fkt  HDG_ERR=%.1f°  "
             "STEER=%.1f°  DAMP=%.2f  NW=%.2f  "
             "TRANS=%.2f  BRAKE=%.3f  CONF=%.2f  COMPR=%.2f",
             phase_str, rs->groundspeed_ms * 1.94384,
             rs->centerline_error_deg,
             rs->steering_command_deg, rs->steering_damping,
             rs->nosewheel_fraction,
             rs->transition_complete, rs->brake_advisory,
             rs->confidence, rs->perspective_compression);
}
