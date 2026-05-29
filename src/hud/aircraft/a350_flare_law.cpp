// ============================================================================
//  Conformal HUD – Airbus A350 Flare Law Visualisation Implementation
//  MSFS 2024  ·  C++17  ·  WASM
//
//  v2.4.0 — Airbus-style flare transition logic.
//
//  The A350 flare law is designed to feel:
//    · Progressive: no abrupt pitch changes
//    · Soft: pitch transition begins subtly at 80 ft, builds at 50 ft
//    · Stable: sink rate is smoothly stabilised
//    · Confident: runway references are prioritised
//    · Suppressive: float is actively discouraged
//
//  Flare law model:
//    h_dot_command = -k * h^0.7  (softer than Boeing's sqrt law)
//    pitch_command = pitch_trim + flare_guidance * (1 - h/h_engage)
//
//  The key difference from Boeing is the exponent: 0.7 vs 0.5,
//  which produces a softer, more gradual flare onset. Since we don't
//  have a pow() function in the WASM environment, we approximate
//  h^0.7 using sqrt(h) with a softness factor that varies with altitude.
// ============================================================================

#include "../../../include/hud/aircraft/a350_flare_law.h"
#include "../../../include/projection.h"

// ============================================================================
//  1.  Constants
// ============================================================================

#define A350_FLARE_G            9.80665
#define A350_FLARE_K_BASE       1.8       // Base flare constant (softer than Boeing)
#define A350_FLARE_ALT_EPSILON  0.1       // Minimum altitude for computation
#define A350_FLARE_MIN_VS_MPS   0.3       // Minimum sink rate for activation
#define A350_FLARE_PITCH_RATE_LIMIT 2.0   // Max pitch rate (deg/s)
#define A350_FLARE_SINK_RATE_ALPHA 0.15   // Sink rate EMA alpha
#define A350_FLARE_PITCH_ALPHA     0.20   // Pitch command EMA alpha
#define A350_FLARE_TOUCHDOWN_ALT_M  0.5   // Touchdown altitude (m)

// ============================================================================
//  2.  Phase altitude thresholds (metres)
// ============================================================================

static FLOAT64 activate_alt_m(const A350FlareLaw* fl) {
    return fl->activation_alt_ft * 0.3048;
}

static FLOAT64 soft_transition_alt_m(const A350FlareLaw* fl) {
    return fl->soft_transition_alt_ft * 0.3048;
}

// ============================================================================
//  3.  Flare law computation
// ============================================================================

bool a350_flare_compute(A350FlareLaw* fl, FLOAT64 dt_s) {
    if (fl == 0) return false;

    fl->valid = false;

    const FLOAT64 ra     = proj_fmax(fl->radio_altitude_m, 0.0);
    const FLOAT64 vs     = fl->vertical_speed_ms;
    const FLOAT64 gs     = proj_fmax(fl->groundspeed_ms, 0.1);
    const FLOAT64 pitch  = fl->pitch_deg;
    const FLOAT64 gs_dev = fl->gs_deviation_deg;

    const FLOAT64 act_m  = activate_alt_m(fl);
    const FLOAT64 soft_m = soft_transition_alt_m(fl);

    // ================================================================
    //  Phase detection
    // ================================================================

    // Inactive -> Preflare transition
    if (fl->phase == A350_FLARE_INACTIVE && ra < soft_m && vs < -A350_FLARE_MIN_VS_MPS) {
        fl->phase = A350_FLARE_PREFLARE;
        fl->engagement_alt_m = ra;
        fl->time_in_phase_s = 0.0;
        fl->active = true;
    }

    // Preflare -> Active transition
    if (fl->phase == A350_FLARE_PREFLARE && ra < act_m) {
        fl->phase = A350_FLARE_ACTIVE;
        fl->time_in_phase_s = 0.0;
    }

    // Active -> Touchdown transition
    if (fl->phase == A350_FLARE_ACTIVE && ra <= A350_FLARE_TOUCHDOWN_ALT_M) {
        fl->phase = A350_FLARE_TOUCHDOWN;
        fl->time_in_phase_s = 0.0;
    }

    // Deactivate if climbing away
    if (fl->active && ra > soft_m + 15.0) {
        fl->phase = A350_FLARE_INACTIVE;
        fl->active = false;
        fl->time_in_phase_s = 0.0;
    }

    // Update phase timing
    if (fl->active) {
        fl->time_in_phase_s += dt_s;
    }

    // ================================================================
    //  Filter sink rate
    // ================================================================
    {
        fl->sink_rate_filtered = fl->sink_rate_filtered * (1.0 - A350_FLARE_SINK_RATE_ALPHA) +
                                 vs * A350_FLARE_SINK_RATE_ALPHA;
    }

    // ================================================================
    //  Sink rate command computation (Airbus-style soft flare)
    // ================================================================
    if (fl->active) {
        const FLOAT64 h_eff = proj_fmax(ra, A350_FLARE_ALT_EPSILON);

        // Airbus-style flare law: h_dot_cmd = -k * h^0.7
        // Uses exponent 0.7 (vs Boeing's 0.5) for softer onset.
        // Approximation: h^0.7 ≈ sqrt(h) * (1 - 0.3 * min(h/10, 1))
        // This gives a softer flare onset than pure sqrt by reducing
        // the command at higher altitudes where the Boeing flare
        // would already be aggressive.
        const FLOAT64 k = A350_FLARE_K_BASE * proj_sqrt(A350_FLARE_G);
        const FLOAT64 softness_factor = 1.0 - 0.3 * proj_fmin(h_eff / 10.0, 1.0);
        FLOAT64 raw_vs_cmd = -k * proj_sqrt(h_eff) * softness_factor;

        // Clamp to reasonable range
        raw_vs_cmd = proj_clamp(raw_vs_cmd, -5.0, 0.0);

        // Apply phase-based blending
        FLOAT64 phase_blend = 0.0;
        if (fl->phase == A350_FLARE_PREFLARE) {
            // Preflare: gradual onset based on altitude
            phase_blend = 1.0 - (ra / soft_m);
            phase_blend = proj_clamp(phase_blend, 0.0, 0.5);  // Max 50% in preflare
        } else if (fl->phase == A350_FLARE_ACTIVE) {
            // Active: full command with altitude-based softness
            phase_blend = 1.0 - (ra / act_m) * 0.3;
            phase_blend = proj_clamp(phase_blend, 0.7, 1.0);
        } else if (fl->phase == A350_FLARE_TOUCHDOWN) {
            // Touchdown: hold attitude
            phase_blend = 1.0;
            raw_vs_cmd = -0.5;  // Very gentle command at touchdown
        }

        fl->sink_rate_command_ms = raw_vs_cmd * phase_blend;

        // === Glideslope compensation ===
        // Small correction for glideslope deviation
        fl->sink_rate_command_ms -= gs_dev * 0.15;

        // === Sink rate error ===
        fl->sink_rate_error_ms = fl->sink_rate_command_ms - fl->sink_rate_filtered;

        // ================================================================
        //  Pitch command computation
        // ================================================================
        // Airbus flare raises pitch gradually to achieve the flare attitude
        // Pitch command = current pitch + flare pitch increment

        // Compute flare pitch increment based on altitude
        FLOAT64 flare_pitch_increment = 0.0;
        if (fl->phase == A350_FLARE_PREFLARE) {
            const FLOAT64 alt_progress = 1.0 - (ra / soft_m);
            flare_pitch_increment = alt_progress * 1.5;  // Up to 1.5 deg pitch up
        } else if (fl->phase == A350_FLARE_ACTIVE) {
            const FLOAT64 alt_progress = 1.0 - (ra / act_m);
            flare_pitch_increment = 1.5 + alt_progress * 2.0;  // 1.5 to 3.5 deg
        } else {
            flare_pitch_increment = 3.5;  // Hold at flare attitude
        }

        // Blend pitch command smoothly (attenuation factor)
        const FLOAT64 target_pitch = pitch + flare_pitch_increment;
        fl->pitch_filtered = fl->pitch_filtered * (1.0 - A350_FLARE_PITCH_ALPHA) +
                              target_pitch * A350_FLARE_PITCH_ALPHA;
        fl->pitch_command_deg = fl->pitch_filtered;

        // ================================================================
        //  Pitch attenuation (reduces unnecessary symbol motion)
        // ================================================================
        // During flare, the HUD pitch ladder movement is attenuated to
        // create the "calm" feeling.
        FLOAT64 attenuation = 0.0;
        if (fl->phase == A350_FLARE_PREFLARE) {
            attenuation = 0.3;  // 30% attenuation in preflare
        } else if (fl->phase == A350_FLARE_ACTIVE) {
            attenuation = 0.6;  // 60% attenuation during active flare
        } else {
            attenuation = 0.8;  // 80% attenuation at touchdown
        }
        fl->pitch_attenuation = attenuation;

        // ================================================================
        //  Runway stabilisation weighting
        // ================================================================
        {
            FLOAT64 stab_weight = fl->runway_stab_weight_setting;
            if (fl->phase == A350_FLARE_PREFLARE) {
                stab_weight *= 1.2;  // Boost runway stability in preflare
            } else if (fl->phase == A350_FLARE_ACTIVE) {
                stab_weight *= 1.5;  // Significantly boost in active flare
            } else {
                stab_weight *= 1.8;  // Maximum at touchdown
            }
            fl->runway_stab_weight = proj_clamp(stab_weight, 0.0, 1.0);
            fl->runway_visual_stab = fl->runway_stab_weight;
        }

        // ================================================================
        //  Sink rate stability assessment
        // ================================================================
        {
            // Stability is higher when sink rate error is small
            const FLOAT64 error_mag = proj_fabs(fl->sink_rate_error_ms);
            fl->sink_rate_stability = 1.0 - proj_fmin(error_mag / 2.0, 1.0);
            fl->sink_rate_stability = proj_clamp(fl->sink_rate_stability, 0.0, 1.0);
        }

        // ================================================================
        //  Float suppression cue
        // ================================================================
        {
            // Float suppression activates when sink rate is too low
            // (aircraft is floating above the runway)
            const FLOAT64 expected_sink = 0.5 + ra * 0.1;  // Expected sink at this altitude
            if (fl->sink_rate_filtered > -expected_sink && ra < 5.0) {
                // Floating detected — generate suppression cue
                fl->float_suppression_cue = proj_clamp(
                    (fl->sink_rate_filtered + expected_sink) / expected_sink,
                    0.0, 1.0);
            } else {
                fl->float_suppression_cue *= 0.9;  // Decay when not floating
            }
            fl->float_suppression_cue *= fl->float_suppression_gain;
        }

        // ================================================================
        //  Guidance confidence
        // ================================================================
        {
            // Blend profile confidence with real-time stability
            FLOAT64 confidence = fl->flare_guidance_confidence;
            confidence *= (0.5 + fl->sink_rate_stability * 0.5);
            fl->guidance_confidence = proj_clamp(confidence, 0.0, 1.0);
        }

        // ================================================================
        //  Flare completion
        // ================================================================
        {
            if (fl->phase == A350_FLARE_ACTIVE) {
                const FLOAT64 alt_progress = 1.0 - (ra / act_m);
                fl->flare_completion = proj_clamp(alt_progress, 0.0, 1.0);
            } else if (fl->phase == A350_FLARE_TOUCHDOWN) {
                fl->flare_completion = 1.0;
            } else {
                fl->flare_completion = 0.0;
            }
        }

    } else {
        // Not active — zero all outputs
        fl->pitch_command_deg       = 0.0;
        fl->pitch_rate_command_dps  = 0.0;
        fl->sink_rate_command_ms    = 0.0;
        fl->sink_rate_error_ms      = 0.0;
        fl->pitch_attenuation       = 0.0;
        fl->guidance_confidence     = 1.0;
        fl->sink_rate_stability     = 1.0;
        fl->runway_stab_weight      = 0.5;
        fl->runway_visual_stab      = 0.5;
        fl->float_suppression_cue    = 0.0;
        fl->flare_completion        = 0.0;
    }

    fl->prev_vertical_speed_ms = vs;
    fl->valid = true;
    return true;
}

// ============================================================================
//  4.  Phase name helper
// ============================================================================

const char* a350_flare_phase_name(A350FlarePhase phase) {
    switch (phase) {
        case A350_FLARE_INACTIVE:  return "INACTIVE";
        case A350_FLARE_PREFLARE:  return "PREFLARE";
        case A350_FLARE_ACTIVE:    return "ACTIVE";
        case A350_FLARE_TOUCHDOWN: return "TOUCHDOWN";
        default:                   return "UNKNOWN";
    }
}

// ============================================================================
//  5.  Debug logging
// ============================================================================

void a350_flare_debug_log(const A350FlareLaw* fl) {
    if (fl == 0) {
        MSFS_Log("[C_HUD_A350_FLARE] A350FlareLaw: NULL");
        return;
    }

    if (!fl->valid) {
        MSFS_Log("[C_HUD_A350_FLARE] A350FlareLaw: INVALID");
        return;
    }

    MSFS_Log("[C_HUD_A350_FLARE] PHASE=%s RA=%.2fm VS=%.2fm/s "
             "PITCH_CMD=%.1fdeg SINK_CMD=%.2f ERR=%.2f "
             "ATTEN=%.2f RWY_STAB=%.2f FLOAT=%.2f CONF=%.2f",
             a350_flare_phase_name(fl->phase),
             fl->radio_altitude_m, fl->vertical_speed_ms,
             fl->pitch_command_deg, fl->sink_rate_command_ms,
             fl->sink_rate_error_ms,
             fl->pitch_attenuation, fl->runway_stab_weight,
             fl->float_suppression_cue,
             fl->guidance_confidence);
}
