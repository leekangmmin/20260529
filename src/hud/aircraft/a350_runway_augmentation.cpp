// ============================================================================
//  Conformal HUD – Airbus A350 XWB Runway Visual Augmentation
//  MSFS 2024  ·  C++17  ·  WASM
//
//  v3.0.0 — A350 Certification Layer
//
//  Implements optical stabilization for runway symbology elements:
//    · Threshold, centerline, and edge-light stabilization
//    · Flare reference enhancement
//    · Turbulence-adaptive smoothing
// ============================================================================

#include "../../../include/hud/aircraft/a350_runway_augmentation.h"
#include "../../../include/projection.h"

// ============================================================================
//  Core computation
// ============================================================================

void a350_runway_augmentation_compute(
    A350RunwayAugmentation* ra,
    FLOAT64 dt_s,
    bool    runway_valid,
    Vec2    threshold,
    Vec2    centerline,
    bool    flare_active,
    FLOAT64 turbulence)
{
    if (ra == 0) return;

    ra->valid = false;

    // Store raw positions
    ra->threshold_raw  = threshold;
    ra->centerline_raw = centerline;
    ra->flare_active   = flare_active;

    // ================================================================
    //  Adapt smoothing based on turbulence
    // ================================================================
    FLOAT64 turb_factor = 1.0;
    if (turbulence > 0.05) {
        turb_factor = 1.0 + turbulence * ra->turbulence_adaptation;
    }

    FLOAT64 threshold_alpha = ra->threshold_smooth_alpha / turb_factor;
    FLOAT64 centerline_alpha = ra->centerline_smooth_alpha / turb_factor;
    FLOAT64 edge_alpha = ra->edge_light_smooth_alpha / turb_factor;

    threshold_alpha  = proj_clamp(threshold_alpha, 0.05, 0.40);
    centerline_alpha = proj_clamp(centerline_alpha, 0.05, 0.35);
    edge_alpha       = proj_clamp(edge_alpha, 0.08, 0.45);

    ra->threshold_alpha  = threshold_alpha;
    ra->centerline_alpha = centerline_alpha;
    ra->edge_light_smooth_alpha = edge_alpha;

    // ================================================================
    //  Threshold stabilization (EMA)
    // ================================================================
    if (runway_valid) {
        if (!ra->active) {
            // First valid frame: initialise
            ra->threshold_smoothed  = threshold;
            ra->centerline_smoothed = centerline;
            ra->left_edge_offset_px = 0.0;
            ra->right_edge_offset_px = 0.0;
            ra->active = true;
        } else {
            // EMA smoothing
            ra->threshold_smoothed.x = ra->threshold_smoothed.x * (1.0 - threshold_alpha) +
                                       threshold.x * threshold_alpha;
            ra->threshold_smoothed.y = ra->threshold_smoothed.y * (1.0 - threshold_alpha) +
                                       threshold.y * threshold_alpha;

            ra->centerline_smoothed.x = ra->centerline_smoothed.x * (1.0 - centerline_alpha) +
                                        centerline.x * centerline_alpha;
            ra->centerline_smoothed.y = ra->centerline_smoothed.y * (1.0 - centerline_alpha) +
                                        centerline.y * centerline_alpha;
        }

        // Stability assessment
        {
            const FLOAT64 threshold_delta = proj_vec2_dist(ra->threshold_smoothed, threshold);
            const FLOAT64 centerline_delta = proj_vec2_dist(ra->centerline_smoothed, centerline);

            ra->threshold_stability = 1.0 - proj_fmin(threshold_delta / 10.0, 1.0);
            ra->centerline_stability = 1.0 - proj_fmin(centerline_delta / 10.0, 1.0);
            ra->edge_light_stability = (ra->threshold_stability + ra->centerline_stability) * 0.5;

            ra->threshold_stability  = proj_clamp(ra->threshold_stability, 0.0, 1.0);
            ra->centerline_stability = proj_clamp(ra->centerline_stability, 0.0, 1.0);
            ra->edge_light_stability = proj_clamp(ra->edge_light_stability, 0.0, 1.0);
        }
    } else {
        // Runway not valid — decay state
        if (ra->active) {
            // Slowly decay to prevent abrupt disappearance
            ra->threshold_stability  *= 0.95;
            ra->centerline_stability *= 0.95;
            ra->edge_light_stability *= 0.95;

            if (ra->threshold_stability < 0.01) {
                ra->active = false;
            }
        }
    }

    // ================================================================
    //  Flare reference enhancement
    // ================================================================
    {
        if (flare_active && ra->active) {
            // Increase runway visual prominence during flare
            ra->flare_reference_blend += (1.0 - ra->flare_reference_blend) * 0.05;
            ra->flare_enhancement = 1.0 + ra->flare_reference_blend * ra->flare_enhancement_gain;
        } else {
            // Decay flare enhancement
            ra->flare_reference_blend *= 0.95;
            ra->flare_enhancement = 1.0;
        }

        ra->flare_reference_blend = proj_clamp(ra->flare_reference_blend, 0.0, 1.0);
        ra->flare_enhancement = proj_clamp(ra->flare_enhancement, 1.0, 2.0);
    }

    ra->valid = true;
}

// ============================================================================
//  Apply stabilisation offsets
// ============================================================================

void a350_runway_augmentation_apply(
    const A350RunwayAugmentation* ra,
    Vec2*   pos,
    bool    is_threshold,
    bool    is_centerline)
{
    if (ra == 0 || pos == 0 || !ra->active) return;

    if (is_threshold) {
        // Use smoothed threshold position
        *pos = ra->threshold_smoothed;
    } else if (is_centerline) {
        // Use smoothed centerline
        *pos = ra->centerline_smoothed;
    }
    // Edge lights and other elements use the general stability
    // which is applied through the depth_illusion and collimation systems
}

// ============================================================================
//  Debug logging
// ============================================================================

void a350_runway_augmentation_debug_log(const A350RunwayAugmentation* ra) {
    if (ra == 0) {
        MSFS_Log("[C_HUD_A350_RWY_AUG] A350RunwayAugmentation: NULL");
        return;
    }

    MSFS_Log("[C_HUD_A350_RWY_AUG] ACT=%d THR_STAB=%.2f CL_STAB=%.2f "
             "EDGE_STAB=%.2f FLARE_ENH=%.2f FLARE_BLEND=%.2f",
             (int)ra->active,
             ra->threshold_stability,
             ra->centerline_stability,
             ra->edge_light_stability,
             ra->flare_enhancement,
             ra->flare_reference_blend);
}
