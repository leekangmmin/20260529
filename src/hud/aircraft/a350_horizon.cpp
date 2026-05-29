// ============================================================================
//  Conformal HUD – Airbus A350 XWB Horizon Stabilization Controller
//  MSFS 2024  ·  C++17  ·  WASM
//
//  v3.0.0 — A350 Certification Layer
//
//  Implements Airbus-specific horizon stabilization with:
//    · Aggressive jitter rejection (no visible micro-movement)
//    · Predictive rate-based smoothing
//    · Phase-aware damping (extra stable during flare)
//    · Low visibility stability enhancement
// ============================================================================

#include "../../../include/hud/aircraft/a350_horizon.h"
#include "../../../include/projection.h"

// ============================================================================
//  Internal: Adaptive rate-based smoothing
// ============================================================================

/// Apply adaptive EMA smoothing with rate-based alpha adjustment.
/// Fast sustained rates = higher alpha (more responsive).
/// Small jitter = lower alpha (more smoothing).
static FLOAT64 adaptive_smooth_pitch(
    FLOAT64 raw,
    FLOAT64 prev_filtered,
    FLOAT64* rate_dps,
    FLOAT64* alpha_out,
    FLOAT64 alpha_min,
    FLOAT64 alpha_max,
    FLOAT64 damping_boost,
    FLOAT64 dt_s)
{
    // Compute rate of change
    FLOAT64 rate = (raw - prev_filtered) / proj_fmax(dt_s, 0.001);

    // Smooth rate estimate with EMA
    if (rate_dps != 0) {
        *rate_dps = *rate_dps * 0.8 + rate * 0.2;
        rate = *rate_dps;
    }

    // Determine alpha based on rate magnitude
    // Small rates (< 0.5 deg/s) = jitter, use min alpha (max smoothing)
    // Large rates (> 3 deg/s) = deliberate input, use max alpha
    const FLOAT64 abs_rate = proj_fabs(rate);
    FLOAT64 alpha;

    if (abs_rate < 0.5) {
        alpha = alpha_min * (1.0 + damping_boost);
    } else if (abs_rate > 3.0) {
        alpha = alpha_max;
    } else {
        // Linear interpolation between min and max
        const FLOAT64 t = (abs_rate - 0.5) / 2.5;
        alpha = (alpha_min * (1.0 + damping_boost)) * (1.0 - t) + alpha_max * t;
    }

    alpha = proj_clamp(alpha, alpha_min * 0.5, alpha_max);

    if (alpha_out != 0) {
        *alpha_out = alpha;
    }

    // Apply EMA
    return prev_filtered * (1.0 - alpha) + raw * alpha;
}

// ============================================================================
//  Core computation
// ============================================================================

void a350_horizon_compute(
    A350HorizonController* hc,
    FLOAT64 raw_pitch_deg,
    FLOAT64 raw_bank_deg,
    FLOAT64 dt_s,
    int     flight_phase,
    FLOAT64 turbulence_level,
    bool    low_visibility)
{
    if (hc == 0) return;

    hc->valid = false;

    // Store raw inputs
    hc->pitch_raw = raw_pitch_deg;
    hc->bank_raw  = raw_bank_deg;

    // ================================================================
    //  Context determination
    // ================================================================

    // Flare detection
    hc->flare_active = (flight_phase == 2);

    // Low visibility
    hc->low_visibility = low_visibility;

    // Turbulence level (use external if provided, otherwise auto-detect)
    if (turbulence_level >= 0.0) {
        hc->turbulence_level = turbulence_level;
    }
    // If turbulence_level is negative, we just keep previous estimate

    // ================================================================
    //  Compute damping boosts
    // ================================================================

    // Turbulence damping boost
    hc->turbulence_damping = hc->turbulence_level * 0.5;

    // Flare damping boost
    hc->flare_damping_boost = hc->flare_active ? hc->flare_damping_multiplier : 0.0;

    // Low visibility stability boost
    hc->low_vis_stability_boost = hc->low_visibility ? (hc->low_vis_multiplier - 1.0) : 0.0;

    // Total damping boost (compounded)
    FLOAT64 total_damping = 1.0 + hc->turbulence_damping +
                            hc->flare_damping_boost * 0.3 +
                            hc->low_vis_stability_boost * 0.2;

    // ================================================================
    //  Smooth pitch
    // ================================================================
    if (!hc->initialised) {
        hc->pitch_filtered = raw_pitch_deg;
        hc->bank_filtered  = raw_bank_deg;
        hc->initialised    = true;
    }

    FLOAT64 pitch_alpha_min = hc->pitch_alpha_min;
    FLOAT64 pitch_alpha_max = hc->pitch_alpha_max;

    // Apply total damping (reduces alpha for more smoothing)
    pitch_alpha_min /= total_damping;
    pitch_alpha_max /= total_damping;

    pitch_alpha_min = proj_clamp(pitch_alpha_min, 0.02, 0.30);
    pitch_alpha_max = proj_clamp(pitch_alpha_max, 0.10, 0.50);

    hc->pitch_filtered = adaptive_smooth_pitch(
        raw_pitch_deg,
        hc->pitch_filtered,
        &hc->pitch_rate_dps,
        &hc->pitch_ema_alpha,
        pitch_alpha_min,
        pitch_alpha_max,
        0.0,  // already included in alpha_min
        dt_s);

    // ================================================================
    //  Smooth bank
    // ================================================================
    FLOAT64 bank_alpha_min = hc->bank_alpha_min;
    FLOAT64 bank_alpha_max = hc->bank_alpha_max;

    bank_alpha_min /= total_damping;
    bank_alpha_max /= total_damping;

    bank_alpha_min = proj_clamp(bank_alpha_min, 0.02, 0.30);
    bank_alpha_max = proj_clamp(bank_alpha_max, 0.08, 0.45);

    hc->bank_filtered = adaptive_smooth_pitch(
        raw_bank_deg,
        hc->bank_filtered,
        &hc->bank_rate_dps,
        &hc->bank_ema_alpha,
        bank_alpha_min,
        bank_alpha_max,
        0.0,
        dt_s);

    // ================================================================
    //  Apply flare pitch hold (near touchdown)
    // ================================================================
    if (hc->flare_active) {
        // As we approach touchdown, increasingly hold pitch attitude
        // to prevent unnecessary horizon movement
        const FLOAT64 hold_strength = 0.3;
        hc->pitch_filtered = hc->pitch_filtered * (1.0 - hold_strength) +
                             hc->pitch_filtered * hold_strength * 0.5 +
                             raw_pitch_deg * hold_strength * 0.5;
    }

    // ================================================================
    //  Set outputs
    // ================================================================
    hc->stabilized_pitch_deg = hc->pitch_filtered;
    hc->stabilized_bank_deg  = hc->bank_filtered;

    // Compute stability scores
    {
        // Pitch stability: high when rate is low and filtering is stable
        const FLOAT64 pitch_rate_quality = 1.0 - proj_fmin(proj_fabs(hc->pitch_rate_dps) / 10.0, 1.0);
        hc->pitch_stability = 0.5 + pitch_rate_quality * 0.5;

        // Bank stability
        const FLOAT64 bank_rate_quality = 1.0 - proj_fmin(proj_fabs(hc->bank_rate_dps) / 8.0, 1.0);
        hc->bank_stability = 0.5 + bank_rate_quality * 0.5;

        hc->pitch_stability = proj_clamp(hc->pitch_stability, 0.0, 1.0);
        hc->bank_stability  = proj_clamp(hc->bank_stability, 0.0, 1.0);
    }

    hc->valid = true;
}

// ============================================================================
//  Debug logging
// ============================================================================

void a350_horizon_debug_log(const A350HorizonController* hc) {
    if (hc == 0) {
        MSFS_Log("[C_HUD_A350_HORIZON] A350HorizonController: NULL");
        return;
    }

    MSFS_Log("[C_HUD_A350_HORIZON] PITCH=%.1f->%.1f BANK=%.1f->%.1f "
             "P_STAB=%.2f B_STAB=%.2f TURB=%.2f FLARE=%d LOWVIS=%d",
             hc->pitch_raw, hc->stabilized_pitch_deg,
             hc->bank_raw, hc->stabilized_bank_deg,
             hc->pitch_stability, hc->bank_stability,
             hc->turbulence_level,
             (int)hc->flare_active, (int)hc->low_visibility);
}
