// ============================================================================
//  Conformal HUD – Symbol Stabilisation & Predictive Filtering Impl.
//  MSFS 2024  ·  C++17  ·  WASM
//
//  v2.3.0 — Turbulence-adaptive damping and motion confidence weighting.
//  Implements adaptive EMA filtering, temporal damping, and position
//  stabilisation for all HUD symbology elements.
// ============================================================================

#include "../../include/hud/stabilization.h"
#include "../../include/projection.h"

// ============================================================================
//  1.  Adaptive EMA filter
// ============================================================================

FLOAT64 adaptive_ema_feed(AdaptiveEMAFilter* f, FLOAT64 sample, FLOAT64 dt_s) {
    if (f == 0) return sample;

    if (dt_s > 0.0) {
        f->dt_s = dt_s;
    }

    if (!f->initialised) {
        f->value = sample;
        f->prev_raw = sample;
        f->initialised = true;
        return f->value;
    }

    const FLOAT64 rate = proj_fabs(sample - f->prev_raw);
    f->prev_raw = sample;

    if (rate > f->rate_threshold) {
        f->alpha = f->alpha + (f->alpha_max - f->alpha) * 0.2;
    } else {
        f->alpha = f->alpha_min + (f->alpha - f->alpha_min) * 0.9;
    }

    if (f->alpha < f->alpha_min) f->alpha = f->alpha_min;
    if (f->alpha > f->alpha_max) f->alpha = f->alpha_max;

    f->value = f->alpha * sample + (1.0 - f->alpha) * f->value;

    return f->value;
}

// ============================================================================
//  2.  2-D Position stabiliser
// ============================================================================

Vec2 pos_stab_feed(PosStabiliser* ps, Vec2 raw, FLOAT64 dt_s) {
    Vec2 result = { -9999.0, -9999.0 };
    if (ps == 0) return result;

    const Vec2 prev_smoothed = ps->smoothed;

    const FLOAT64 sx = adaptive_ema_feed(&ps->fx, raw.x, dt_s);
    const FLOAT64 sy = adaptive_ema_feed(&ps->fy, raw.y, dt_s);

    ps->smoothed.x = sx;
    ps->smoothed.y = sy;

    if (dt_s > 0.001 && ps->initialised) {
        ps->velocity.x = (sx - prev_smoothed.x) / dt_s;
        ps->velocity.y = (sy - prev_smoothed.y) / dt_s;
    }

    ps->initialised = true;

    result.x = sx;
    result.y = sy;
    return result;
}

// ============================================================================
//  3.  Temporal damper (second-order critically damped)
// ============================================================================

FLOAT64 damper_feed(TemporalDamper* d, FLOAT64 target, FLOAT64 dt_s) {
    if (d == 0) return target;

    if (dt_s > 0.0) {
        d->dt_s = dt_s;
    }

    if (!d->initialised) {
        d->value = target;
        d->velocity = 0.0;
        d->initialised = true;
        return d->value;
    }

    const FLOAT64 w = d->natural_freq;
    const FLOAT64 z = d->damping_ratio;
    const FLOAT64 dt = d->dt_s;

    const FLOAT64 error = target - d->value;
    const FLOAT64 accel = w * w * error - 2.0 * z * w * d->velocity;

    d->velocity += accel * dt;
    d->value     += d->velocity * dt;

    return d->value;
}

// ============================================================================
//  3b.  Turbulence detection helper
// ============================================================================

/// Estimates turbulence intensity from frame-to-frame jitter in the
/// FPV position.  Accumulates absolute rate of change and maps it to
/// a 0..1 turbulence intensity value.
static FLOAT64 detect_turbulence_intensity(HUDStabilisation* hs,
                                            FLOAT64 rate_x,
                                            FLOAT64 rate_y,
                                            FLOAT64 dt_s) {
    if (hs == 0) return 0.0;

    const FLOAT64 jitter = (proj_fabs(rate_x) + proj_fabs(rate_y)) * 0.5;

    // Accumulate with exponential decay
    const FLOAT64 decay = (dt_s > 0.0) ? proj_fmin(1.0, dt_s * 10.0) : 0.016;
    hs->jitter_accumulator = hs->jitter_accumulator * (1.0 - decay) +
                              jitter * decay;
    if (hs->jitter_sample_count < 100) ++hs->jitter_sample_count;

    // Map jitter to turbulence intensity (0..1)
    // jitter < 1 px = calm; 1-5 px = light; 5-15 px = moderate; >15 = severe
    FLOAT64 intensity = 0.0;
    const FLOAT64 j = hs->jitter_accumulator;
    if (j > 15.0) {
        intensity = 1.0;
    } else if (j > 5.0) {
        intensity = 0.5 + (j - 5.0) / 20.0;
    } else if (j > 1.0) {
        intensity = (j - 1.0) / 8.0;
    }

    return proj_clamp(intensity, 0.0, 1.0);
}

// ============================================================================
//  4.  HUD stabilisation initialisation  (v2.3.0: turbulence params)
// ============================================================================

void hud_stab_init(HUDStabilisation* hs) {
    if (hs == 0) return;

    pos_stab_init(&hs->fpv_pos, 0.15, 0.85, 10.0);
    damper_init(&hs->fpv_pitch_damper, 1.0, 3.0);
    damper_init(&hs->fpv_heading_damper, 1.0, 2.0);

    pos_stab_init(&hs->loc_bar_pos, 0.10, 0.70, 5.0);
    pos_stab_init(&hs->gs_bar_pos, 0.10, 0.70, 5.0);
    damper_init(&hs->steering_pitch, 1.0, 4.0);
    damper_init(&hs->steering_bank, 1.0, 4.0);

    for (int i = 0; i < 8; ++i) {
        hs->runway_ema_corners[i].x = 0.0;
        hs->runway_ema_corners[i].y = 0.0;
        hs->runway_ema_initialised[i] = false;
    }

    damper_init(&hs->horizon_y, 0.8, 5.0);
    damper_init(&hs->horizon_slope, 0.7, 4.0);

    for (int i = 0; i < 5; ++i) {
        damper_init(&hs->pitch_ladder_offsets[i], 0.9, 6.0);
    }

    damper_init(&hs->flare_cue, 0.8, 3.0);

    // v2.3.0: turbulence state
    hs->turbulence_intensity = 0.0;
    hs->motion_confidence = 1.0;
    hs->turbulence_damping_boost = 1.0;
    hs->jitter_accumulator = 0.0;
    hs->jitter_sample_count = 0;

    hs->initialised = true;
}

// ============================================================================
//  4b.  Turbulence-adaptive tuning  (v2.3.0)
// ============================================================================

void hud_stab_tune_for_turbulence(HUDStabilisation* hs,
                                   FLOAT64 dt_s,
                                   FLOAT64 turbulence_gain,
                                   FLOAT64 motion_weight) {
    if (hs == 0 || !hs->initialised) return;

    // Detect turbulence from FPV jitter if FPV has been initialised
    if (hs->fpv_pos.initialised) {
        const FLOAT64 rate_x = proj_fabs(hs->fpv_pos.fx.prev_raw -
                                          hs->fpv_pos.smoothed.x);
        const FLOAT64 rate_y = proj_fabs(hs->fpv_pos.fy.prev_raw -
                                          hs->fpv_pos.smoothed.y);
        hs->turbulence_intensity = detect_turbulence_intensity(
            hs, rate_x, rate_y, dt_s);
    }

    // Apply turbulence gain from profile
    hs->turbulence_intensity *= turbulence_gain;
    hs->turbulence_intensity = proj_clamp(hs->turbulence_intensity, 0.0, 1.0);

    // Motion confidence: when pilot is making deliberate inputs,
    // reduce turbulence smoothing
    hs->motion_confidence = motion_weight;

    // Compute damping boost: more turbulence = more smoothing
    hs->turbulence_damping_boost = 1.0 + hs->turbulence_intensity * 2.0;

    // Apply adaptive damping to FPV filter
    // In turbulence, increase alpha_min (more smoothing)
    const FLOAT64 base_alpha_min = 0.15;
    const FLOAT64 boosted_alpha_min = proj_fmin(
        0.50,
        base_alpha_min * hs->turbulence_damping_boost *
        (1.0 + (1.0 - hs->motion_confidence) * 0.5));

    hs->fpv_pos.fx.alpha_min = boosted_alpha_min;
    hs->fpv_pos.fy.alpha_min = boosted_alpha_min;

    // Adjust runway corner EMA alpha based on turbulence
    // (handled in hud_stab_runway_corner via adaptive alpha)
    // The runway corners use a fixed alpha that we now make adaptive
    // based on turbulence: higher turbulence → higher alpha (less smoothing
    // for fast movements, but more aggregate damping)
}

// ============================================================================
//  5.  Per-element stabilisation methods
// ============================================================================

Vec2 hud_stab_runway_corner(HUDStabilisation* hs,
                             int index,
                             Vec2 raw,
                             FLOAT64 dt_s,
                             bool valid) {
    Vec2 result = raw;
    if (hs == 0 || index < 0 || index >= 8) return result;

    if (!valid) {
        if (hs->runway_ema_initialised[index]) {
            result = hs->runway_ema_corners[index];
        }
        return result;
    }

    // v2.3.0: turbulence-adaptive runway smoothing.
    // Base alpha is 0.30; in turbulence, increase to prevent jitter.
    FLOAT64 alpha = 0.30;
    if (hs->turbulence_intensity > 0.1) {
        // In turbulence, increase EMA alpha (more weight on current sample)
        // to avoid excessive lag, but clamp to prevent jitter.
        alpha = 0.30 + hs->turbulence_intensity * 0.25;
        alpha = proj_fmin(alpha, 0.60);
    }

    if (!hs->runway_ema_initialised[index]) {
        hs->runway_ema_corners[index] = raw;
        hs->runway_ema_initialised[index] = true;
        result = raw;
    } else {
        hs->runway_ema_corners[index].x =
            alpha * raw.x + (1.0 - alpha) * hs->runway_ema_corners[index].x;
        hs->runway_ema_corners[index].y =
            alpha * raw.y + (1.0 - alpha) * hs->runway_ema_corners[index].y;
        result = hs->runway_ema_corners[index];
    }

    return result;
}

Vec2 hud_stab_fpv(HUDStabilisation* hs, Vec2 raw, FLOAT64 dt_s) {
    if (hs == 0) return raw;
    return pos_stab_feed(&hs->fpv_pos, raw, dt_s);
}

void hud_stab_guidance(HUDStabilisation* hs,
                        Vec2  raw_loc,
                        Vec2  raw_gs,
                        FLOAT64 loc_error_dots,
                        FLOAT64 gs_error_dots,
                        FLOAT64 dt_s) {
    if (hs == 0) return;

    if (proj_fabs(loc_error_dots) < 5.0) {
        hs->loc_bar_pos.smoothed = pos_stab_feed(&hs->loc_bar_pos, raw_loc, dt_s);
    }
    if (proj_fabs(gs_error_dots) < 5.0) {
        hs->gs_bar_pos.smoothed = pos_stab_feed(&hs->gs_bar_pos, raw_gs, dt_s);
    }
}

FLOAT64 hud_stab_horizon_y(HUDStabilisation* hs, FLOAT64 raw_y, FLOAT64 dt_s) {
    if (hs == 0) return raw_y;

    // v2.3.0: turbulence-adaptive horizon damping
    if (hs->turbulence_intensity > 0.1) {
        // Increase natural frequency in turbulence for faster response
        hs->horizon_y.natural_freq = 5.0 + hs->turbulence_intensity * 3.0;
    }

    return damper_feed(&hs->horizon_y, raw_y, dt_s);
}

FLOAT64 hud_stab_horizon_slope(HUDStabilisation* hs,
                                FLOAT64 raw_slope,
                                FLOAT64 dt_s) {
    if (hs == 0) return raw_slope;

    if (hs->turbulence_intensity > 0.1) {
        hs->horizon_slope.natural_freq = 4.0 + hs->turbulence_intensity * 2.0;
    }

    return damper_feed(&hs->horizon_slope, raw_slope, dt_s);
}

FLOAT64 hud_stab_pitch_line(HUDStabilisation* hs,
                             int index,
                             FLOAT64 raw,
                             FLOAT64 dt_s) {
    if (hs == 0 || index < 0 || index >= 5) return raw;

    if (hs->turbulence_intensity > 0.1) {
        hs->pitch_ladder_offsets[index].natural_freq =
            6.0 + hs->turbulence_intensity * 4.0;
    }

    return damper_feed(&hs->pitch_ladder_offsets[index], raw, dt_s);
}

// ============================================================================
//  6.  Debug logging
// ============================================================================

void hud_stab_debug_log(const HUDStabilisation* hs) {
    if (hs == 0) {
        MSFS_Log("[C_HUD_STAB] HUDStabilisation: NULL");
        return;
    }

    MSFS_Log("[C_HUD_STAB] FPV: sm=(%.1f, %.1f) vel=(%.1f, %.1f)  "
             "LOC: sm=(%.1f, %.1f)  GS: sm=(%.1f, %.1f)  "
             "HORIZ: y=%.1f slope=%.4f  "
             "TURB=%.3f MC=%.3f DAMP_BOOST=%.3f  INIT=%d",
             hs->fpv_pos.smoothed.x, hs->fpv_pos.smoothed.y,
             hs->fpv_pos.velocity.x, hs->fpv_pos.velocity.y,
             hs->loc_bar_pos.smoothed.x, hs->loc_bar_pos.smoothed.y,
             hs->gs_bar_pos.smoothed.x, hs->gs_bar_pos.smoothed.y,
             hs->horizon_y.value, hs->horizon_slope.value,
             hs->turbulence_intensity, hs->motion_confidence,
             hs->turbulence_damping_boost,
             (int)hs->initialised);
}
