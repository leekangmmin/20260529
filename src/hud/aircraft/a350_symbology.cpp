// ============================================================================
//  Conformal HUD – Airbus A350 Symbology Styling Implementation
//  MSFS 2024  ·  C++17  ·  WASM
//
//  v2.4.0 — Airbus-specific HUD symbology presentation.
//
//  Provides the visually refined, optically stable presentation that
//  characterises the Airbus A350 HUD:
//    · Softer brightness transitions (eased, not abrupt)
//    · Less aggressive bloom (reduced intensity)
//    · Cleaner lines (intensity stabilisation)
//    · Stable horizon references (oscillation damped)
//    · Smooth alpha fading (no sudden appearance/disappearance)
//    · Anti-shimmer filtering for fine lines
//    · Symbol persistence smoothing for reduced flicker
// ============================================================================

#include "../../../include/hud/aircraft/a350_symbology.h"
#include "../../../include/projection.h"

// ============================================================================
//  1.  Constants
// ============================================================================

#define A350_SYM_ALPHA_SMOOTH_ALPHA    0.15  // Alpha EMA factor
#define A350_SYM_POS_SMOOTH_ALPHA      0.20  // Position EMA factor
#define A350_SYM_SHMMER_THRESHOLD      2.0   // Shimmer detection threshold (px)
#define A350_SYM_MAX_TRACKED_SYMBOLS   32    // Max symbols to track

// ============================================================================
//  2.  Styling computation
// ============================================================================

void a350_symbology_compute(A350SymbologyStyle* ss,
                             FLOAT64 dt_s,
                             FLOAT64 target_bright,
                             FLOAT64 turbulence) {
    if (ss == 0) return;

    // ================================================================
    //  Brightness easing
    // ================================================================
    {
        ss->brightness_target = proj_clamp(target_bright, 0.0, 1.0);

        const FLOAT64 diff = ss->brightness_target - ss->brightness_current;
        const FLOAT64 rate = (diff > 0.0) ? ss->brightness_easing_rate :
                                             ss->brightness_easing_rate * 0.7;
        ss->brightness_current += diff * rate * dt_s * 10.0;
        ss->brightness_current = proj_clamp(ss->brightness_current,
                                             ss->brightness_min, 1.0);
    }

    // ================================================================
    //  Bloom reduction
    // ================================================================
    {
        // In turbulence, reduce bloom further (avoids visual noise)
        FLOAT64 reduction = ss->bloom_reduction;
        if (turbulence > 0.2) {
            reduction += (1.0 - reduction) * turbulence * 0.3;
        }
        ss->bloom_current = 1.0 - reduction;
        ss->bloom_current = proj_clamp(ss->bloom_current, 0.0, 1.0);
    }

    // ================================================================
    //  Horizon oscillation damping
    // ================================================================
    {
        if (turbulence > 0.1) {
            // Increase oscillation damping during turbulence
            ss->horizon_oscillation_damping = proj_fmin(
                0.80 + turbulence * 0.15, 0.98);
        } else {
            ss->horizon_oscillation_damping = 0.80;
        }
    }

    // ================================================================
    //  Anti-shimmer adaptation
    // ================================================================
    {
        if (turbulence > 0.3) {
            // Increase anti-shimmer gain during turbulence
            ss->anti_shimmer_gain = proj_fmin(
                0.70 + turbulence * 0.20, 0.95);
        } else {
            ss->anti_shimmer_gain = 0.70;
        }
    }

    // ================================================================
    //  Alpha transition rate adaptation
    // ================================================================
    {
        // Slower alpha transitions during turbulence (less flicker)
        if (turbulence > 0.2) {
            ss->alpha_transition_rate = 0.10;
        } else {
            ss->alpha_transition_rate = 0.15;
        }
    }

    ss->active = true;
    ss->valid  = true;
}

// ============================================================================
//  3.  Alpha smoothing
// ============================================================================

FLOAT64 a350_symbology_smooth_alpha(A350SymbologyStyle* ss,
                                     FLOAT64 raw_alpha,
                                     int index) {
    if (ss == 0) return raw_alpha;
    if (index < 0 || index >= A350_SYM_MAX_TRACKED_SYMBOLS) return raw_alpha;

    // Apply EMA smoothing to alpha
    const FLOAT64 alpha = A350_SYM_ALPHA_SMOOTH_ALPHA *
                          (1.0 + ss->symbol_persistence);
    FLOAT64 smoothed = ss->prev_alpha[index] * (1.0 - alpha) +
                        raw_alpha * alpha;

    // During turbulence, add extra smoothing
    if (ss->anti_shimmer_gain > 0.7) {
        const FLOAT64 extra_smooth = (ss->anti_shimmer_gain - 0.7) / 0.3;
        smoothed = ss->prev_alpha[index] * extra_smooth +
                   smoothed * (1.0 - extra_smooth);
    }

    ss->prev_alpha[index] = smoothed;
    return proj_clamp(smoothed, 0.0, 1.0);
}

// ============================================================================
//  4.  Position stabilisation (anti-shimmer)
// ============================================================================

FLOAT64 a350_symbology_stabilise_pos(A350SymbologyStyle* ss,
                                      FLOAT64 raw_pos,
                                      int index) {
    if (ss == 0) return raw_pos;
    if (index < 0 || index >= A350_SYM_MAX_TRACKED_SYMBOLS) return raw_pos;

    // Detect shimmer: large frame-to-frame change that reverses quickly
    const FLOAT64 prev = ss->prev_position[index];
    const FLOAT64 delta = raw_pos - prev;

    // If the delta is large but the previous delta was opposite,
    // this is likely shimmer
    if (ss->shimmer_accumulator > A350_SYM_SHMMER_THRESHOLD) {
        // Shimmer detected — apply strong smoothing
        const FLOAT64 alpha = A350_SYM_POS_SMOOTH_ALPHA *
                              (1.0 - ss->anti_shimmer_gain * 0.5);
        ss->prev_position[index] = prev * (1.0 - alpha) + raw_pos * alpha;
    } else {
        // Normal movement — apply standard EMA
        const FLOAT64 alpha = A350_SYM_POS_SMOOTH_ALPHA *
                              (1.0 - ss->anti_shimmer_gain * 0.2);
        ss->prev_position[index] = prev * (1.0 - alpha) + raw_pos * alpha;
    }

    // Update shimmer accumulator
    if (proj_fabs(delta) > 1.0) {
        ss->shimmer_accumulator += proj_fabs(delta) * 0.1;
        ss->shimmer_accumulator = proj_fmin(ss->shimmer_accumulator, 10.0);
    } else {
        ss->shimmer_accumulator -= 0.05;
        ss->shimmer_accumulator = proj_fmax(ss->shimmer_accumulator, 0.0);
    }

    return ss->prev_position[index];
}

// ============================================================================
//  5.  Debug logging
// ============================================================================

void a350_symbology_debug_log(const A350SymbologyStyle* ss) {
    if (ss == 0) {
        MSFS_Log("[C_HUD_A350_SYM] A350SymbologyStyle: NULL");
        return;
    }

    MSFS_Log("[C_HUD_A350_SYM] BRI=%.2f/%.2f BLOOM=%.2f "
             "HOR_STAB=%.2f OSC_DAMP=%.2f "
             "ANTI_SHIM=%.2f PERSIST=%.2f ACT=%d",
             ss->brightness_current, ss->brightness_target,
             ss->bloom_current,
             ss->horizon_stability, ss->horizon_oscillation_damping,
             ss->anti_shimmer_gain, ss->symbol_persistence,
             (int)ss->active);
}
