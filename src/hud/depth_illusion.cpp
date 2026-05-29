// ============================================================================
//  Conformal HUD – Optical Depth Illusion Implementation
//  MSFS 2024  ·  C++17  ·  WASM
//
//  v2.4.0 — Subtle optical depth simulation for psychologically
//  believable HUD projection.
// ============================================================================

#include "../../include/hud/depth_illusion.h"
#include "../../include/projection.h"

// ============================================================================
//  1.  Constants
// ============================================================================

#define DI_WOBBLE_FREQ_BASE     8.0   // Base wobble frequency (Hz)
#define DI_WOBBLE_AMP_BASE      0.3   // Base wobble amplitude (pixels)
#define DI_HEAD_MOTION_GAIN     0.02  // Head motion → parallax gain
#define DI_INFINITY_STAB_GAIN   0.8   // Stabilisation gain for infinity layer

// Per-layer parallax scale factors (higher = more parallax for near layers)
static const FLOAT64 g_layer_parallax_scale[4] = {
    0.0,    // DEPTH_OPTICAL_INFINITY — no parallax (world-stabilised)
    0.8,    // DEPTH_COMBINER_NEAR  — most parallax
    0.4,    // DEPTH_COMBINER_MID   — moderate parallax
    0.2     // DEPTH_COMBINER_FAR   — slight parallax
};

// Per-layer focal blur (higher = more blurred)
static const FLOAT64 g_layer_focal_blur[4] = {
    0.0,    // DEPTH_OPTICAL_INFINITY — sharp (at infinity)
    0.15,   // DEPTH_COMBINER_NEAR  — slightly blurred (too close for focus)
    0.05,   // DEPTH_COMBINER_MID   — mostly sharp
    0.10    // DEPTH_COMBINER_FAR   — slight blur (distant focus)
};

// ============================================================================
//  2.  Depth illusion computation
// ============================================================================

void depth_illusion_compute(DepthIllusionState* di,
                             FLOAT64            dt_s,
                             const CollimationCorrection* cc,
                             FLOAT64            intensity) {
    if (di == 0) return;

    di->depth_intensity = proj_clamp(intensity, 0.0, 1.0);

    // ================================================================
    //  OPTICAL CENTRE WOBBLE
    //  Simulates micro-vibrations of the HUD optical system
    //  (combiner glass, mirrors) that create subtle movement.
    // ================================================================
    {
        const FLOAT64 time_sec = (FLOAT64)(int)(di->wobble_frequency * 100.0) / 100.0;
        di->wobble_frequency = DI_WOBBLE_FREQ_BASE;
        di->wobble_amplitude = DI_WOBBLE_AMP_BASE * di->depth_intensity;

        // Slow, sub-pixel wobble
        const FLOAT64 phase_x = di->wobble_frequency * 0.7 * 2.0 * 3.14159;
        const FLOAT64 phase_y = di->wobble_frequency * 0.5 * 2.0 * 3.14159;

        di->optical_wobble.x = di->wobble_amplitude *
            proj_sin((FLOAT64)(int)(phase_x * 100.0) / 100.0);
        di->optical_wobble.y = di->wobble_amplitude *
            proj_cos((FLOAT64)(int)(phase_y * 100.0) / 100.0);
    }

    // ================================================================
    //  HEAD-MOTION PARALLAX
    //  When the pilot moves their head, near-layer elements shift
    //  slightly more than far-layer elements, simulating the
    //  parallax effect of real collimated optics.
    // ================================================================
    {
        Vec2 head_delta = proj_vec3_make(0, 0, 0);
        if (cc != 0 && cc->active) {
            // Use collimation correction as a proxy for head movement
            head_delta.x = cc->debug_camera_delta_x * 100.0;  // convert to px
            head_delta.y = cc->debug_camera_delta_z * 100.0;
        }

        // Apply per-layer parallax
        for (int i = 0; i < 4; ++i) {
            const FLOAT64 scale = g_layer_parallax_scale[i] * di->depth_intensity;
            di->parallax_offset[i].x = head_delta.x * scale *
                                        DI_HEAD_MOTION_GAIN;
            di->parallax_offset[i].y = head_delta.y * scale *
                                        DI_HEAD_MOTION_GAIN;
        }

        di->head_motion_shift.x = head_delta.x * DI_HEAD_MOTION_GAIN *
                                   di->depth_intensity;
        di->head_motion_shift.y = head_delta.y * DI_HEAD_MOTION_GAIN *
                                   di->depth_intensity;
    }

    // ================================================================
    //  FOCAL BLUR & SHARPNESS
    //  Elements at different depths have subtly different sharpness,
    //  simulating the limited depth of field of the human eye when
    //  focused at optical infinity.
    // ================================================================
    {
        for (int i = 0; i < 4; ++i) {
            di->focal_blur[i] = g_layer_focal_blur[i] * di->depth_intensity;
            di->focal_sharpness[i] = 1.0 - di->focal_blur[i];
        }
    }

    // ================================================================
    //  INFINITY LAYER STABILISATION
    //  Elements at optical infinity (runway, FPV, horizon) should
    //  feel rock-steady. We add extra stabilisation from the
    //  collimation system.
    // ================================================================
    {
        di->infinity_layer_offset.x = -di->optical_wobble.x * DI_INFINITY_STAB_GAIN;
        di->infinity_layer_offset.y = -di->optical_wobble.y * DI_INFINITY_STAB_GAIN;
    }

    di->active = (di->depth_intensity > 0.01);
    di->valid = true;
}

// ============================================================================
//  3.  Debug logging
// ============================================================================

void depth_illusion_debug_log(const DepthIllusionState* di) {
    if (di == 0) {
        MSFS_Log("[C_HUD_DEPTH] DepthIllusionState: NULL");
        return;
    }

    MSFS_Log("[C_HUD_DEPTH] INTENS=%.2f  WOBBLE=(%.3f,%.3f)  "
             "HEAD=(%.3f,%.3f)  "
             "PARA_INF=(%.2f,%.2f) PARA_NEAR=(%.2f,%.2f)  "
             "ACT=%d",
             di->depth_intensity,
             di->optical_wobble.x, di->optical_wobble.y,
             di->head_motion_shift.x, di->head_motion_shift.y,
             di->parallax_offset[0].x, di->parallax_offset[0].y,
             di->parallax_offset[1].x, di->parallax_offset[1].y,
             (int)di->active);
}
