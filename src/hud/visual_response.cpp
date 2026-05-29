// ============================================================================
//  Conformal HUD – Human Visual Response Simulation Implementation
//  MSFS 2024  ·  C++17  ·  WASM
//
//  v2.4.0 — Pilot visual perception simulation.
//  Simulates how the human visual system responds to changing light
//  conditions, bright lights, rain, and fatigue when viewing the HUD.
// ============================================================================

#include "../../include/hud/visual_response.h"
#include "../../include/projection.h"

// ============================================================================
//  1.  Constants
// ============================================================================

#define VR_DARK_ADAPT_RATE_UP      0.8   // Adaptation rate entering dark
#define VR_DARK_ADAPT_RATE_DOWN    0.3   // Adaptation rate leaving dark
#define VR_BLOOM_DECAY_RATE        2.0   // Bloom decay rate (per second)
#define VR_BLOOM_ATTACK_RATE       5.0   // Bloom onset rate
#define VR_PHOSPHOR_NIGHT_MAX_MS   80.0  // Max phosphor persistence at night
#define VR_PHOSPHOR_DAY_MIN_MS     20.0  // Min phosphor persistence in daylight
#define VR_BRIGHTNESS_ADAPT_RATE   0.4   // Brightness adaptation rate
#define VR_FATIGUE_ACCUM_RATE      0.02  // Fatigue accumulation per second
#define VR_ACCOMMODATION_RATE      0.5   // Accommodation change rate

// ============================================================================
//  2.  Visual response computation
// ============================================================================

void visual_response_compute(VisualResponseState* vs,
                              FLOAT64             dt_s,
                              FLOAT64             ambient_lux,
                              FLOAT64             rain_intensity,
                              bool                runway_light_boom) {
    if (vs == 0) return;

    // ================================================================
    //  DARK ADAPTATION
    // ================================================================
    {
        vs->ambient_luminance = proj_clamp(ambient_lux, 0.0, 1.0);
        vs->dark_adapt_time_s += dt_s;

        // Dark adaptation: target is ambient luminance
        // When ambient drops, dark adaptation increases (sensitivity up)
        const FLOAT64 target_adaptation = 1.0 - vs->ambient_luminance;

        if (target_adaptation > vs->dark_adaptation) {
            // Becoming dark-adapted (entering dark)
            vs->dark_adaptation += (target_adaptation - vs->dark_adaptation) *
                                   VR_DARK_ADAPT_RATE_UP * dt_s;
        } else {
            // Becoming light-adapted (leaving dark)
            vs->dark_adaptation += (target_adaptation - vs->dark_adaptation) *
                                   VR_DARK_ADAPT_RATE_DOWN * dt_s;
        }

        vs->dark_adaptation = proj_clamp(vs->dark_adaptation, 0.0, 1.0);
    }

    // ================================================================
    //  BLOOM / TEMPORARY BLINDNESS
    // ================================================================
    {
        // Simulate bright light exposure: runway lights, strobes, etc.
        if (runway_light_boom || vs->bloom_exposure > 0.01) {
            if (runway_light_boom) {
                // Exposure increases when looking at bright lights
                vs->bloom_exposure += (1.0 - vs->bloom_exposure) *
                                      VR_BLOOM_ATTACK_RATE * dt_s;
            } else {
                // Decay when lights are gone
                vs->bloom_exposure -= VR_BLOOM_DECAY_RATE * dt_s;
            }
            vs->bloom_exposure = proj_clamp(vs->bloom_exposure, 0.0, 1.0);
        }

        // Map bloom exposure to visual effect
        vs->bloom_amount = vs->bloom_exposure * 0.6;  // max 60% bloom effect
    }

    // ================================================================
    //  RAIN GLARE
    // ================================================================
    {
        vs->rain_intensity = proj_clamp(rain_intensity, 0.0, 1.0);
        vs->is_raining = (vs->rain_intensity > 0.05);

        // Rain glare: light scatter from rain on the combiner
        // Effect is stronger at night (dark adaptation amplifies glare)
        vs->rain_glare = vs->rain_intensity * 0.3 *
                         (1.0 + vs->dark_adaptation * 0.5);
        vs->rain_glare = proj_clamp(vs->rain_glare, 0.0, 1.0);
    }

    // ================================================================
    //  PHOSPHOR PERSISTENCE
    // ================================================================
    {
        // Night vision increases perceived phosphor persistence
        vs->persistence_boost = vs->dark_adaptation * 0.6;

        const FLOAT64 target_persistence = VR_PHOSPHOR_DAY_MIN_MS +
            (VR_PHOSPHOR_NIGHT_MAX_MS - VR_PHOSPHOR_DAY_MIN_MS) *
            vs->persistence_boost;

        vs->phosphor_current_ms += (target_persistence - vs->phosphor_current_ms) *
                                    VR_DARK_ADAPT_RATE_UP * dt_s;
    }

    // ================================================================
    //  BRIGHTNESS ADAPTATION LAG
    // ================================================================
    {
        // Target brightness is driven by ambient luminance
        vs->target_brightness = 0.3 + vs->ambient_luminance * 0.7;

        // Adaptation lag simulates pupillary response
        const FLOAT64 brightness_diff = vs->target_brightness - vs->current_brightness;
        const FLOAT64 adapt_speed = VR_BRIGHTNESS_ADAPT_RATE *
                                    (1.0 + vs->dark_adaptation * 0.5);

        vs->current_brightness += brightness_diff * adapt_speed * dt_s;
        vs->current_brightness = proj_clamp(vs->current_brightness, 0.05, 1.0);

        // Brightness lag: how far we are from target
        vs->brightness_lag = proj_fabs(vs->target_brightness - vs->current_brightness);
    }

    // ================================================================
    //  VISUAL CONTRAST FATIGUE
    // ================================================================
    {
        // Prolonged exposure to high-contrast HUD elements causes fatigue
        // Fatigue accumulates faster in bright conditions
        if (vs->ambient_luminance > 0.3) {
            vs->fatigue_accumulator += VR_FATIGUE_ACCUM_RATE * dt_s *
                                       vs->ambient_luminance;
        } else {
            // Recover in dark conditions
            vs->fatigue_accumulator -= vs->fatigue_recovery_rate * dt_s *
                                       (1.0 - vs->ambient_luminance);
        }

        vs->fatigue_accumulator = proj_clamp(vs->fatigue_accumulator, 0.0, 1.0);

        // Contrast reduction increases with fatigue
        if (vs->fatigue_accumulator > vs->fatigue_threshold) {
            vs->contrast_reduction = (vs->fatigue_accumulator - vs->fatigue_threshold) /
                                      (1.0 - vs->fatigue_threshold);
        } else {
            vs->contrast_reduction = 0.0;
        }

        vs->contrast_reduction = proj_clamp(vs->contrast_reduction, 0.0, 0.3);
    }

    // ================================================================
    //  EYE ACCOMMODATION
    // ================================================================
    {
        // Accommodation shifts between near (HUD glass) and far (outside)
        // Target is determined by what the pilot is likely focusing on:
        //   - In low vis or on approach: more near focus (HUD)
        //   - In clear vis or in rollout: more far focus (outside)
        FLOAT64 accommodation_target = 0.3;  // default: mostly far
        if (vs->ambient_luminance < 0.2) {
            accommodation_target = 0.7;  // night: more near focus
        }
        if (vs->rain_intensity > 0.3) {
            accommodation_target = 0.6;  // rain: more near focus
        }

        vs->accommodation_target = accommodation_target;
        vs->accommodation += (accommodation_target - vs->accommodation) *
                             VR_ACCOMMODATION_RATE * dt_s;
        vs->accommodation = proj_clamp(vs->accommodation, 0.0, 1.0);
    }

    // ================================================================
    //  OUTPUT GAINS
    // ================================================================
    {
        // Luminance gain: night adaptation increases gain
        vs->luminance_gain = 1.0 + vs->dark_adaptation * 0.3;

        // Contrast gain: fatigue reduces contrast
        vs->contrast_gain = 1.0 - vs->contrast_reduction;

        // Active if any effect is significant
        vs->active = (vs->dark_adaptation > 0.05 ||
                       vs->bloom_amount > 0.01 ||
                       vs->rain_glare > 0.01 ||
                       vs->contrast_reduction > 0.01 ||
                       vs->brightness_lag > 0.05);
    }

    // --- Debug ---
    vs->debug_adaptation_level = vs->dark_adaptation;
    vs->debug_bloom_level = vs->bloom_amount;
    vs->debug_phosphor_ms = vs->phosphor_current_ms;
    vs->debug_fatigue_level = vs->contrast_reduction;
}

// ============================================================================
//  3.  Apply visual response to rendering parameters
// ============================================================================

void visual_response_apply(const VisualResponseState* vs,
                            const VisualRenderParams*  base,
                            VisualRenderParams*        out) {
    if (out == 0) return;

    // Copy base values
    if (base != 0) {
        *out = *base;
    } else {
        out->brightness = 0.7;
        out->contrast = 1.0;
        out->phosphor_persistence_ms = 30.0;
        out->bloom_intensity = 0.0;
        out->glare_amount = 0.0;
        out->edge_fade_night_boost = 0.0;
        out->active = false;
    }

    if (vs == 0 || !vs->active) {
        return;
    }

    // Apply dark adaptation → brightness gain
    out->brightness *= vs->luminance_gain;

    // Apply contrast fatigue
    out->contrast *= vs->contrast_gain;

    // Apply phosphor persistence
    out->phosphor_persistence_ms = vs->phosphor_current_ms;

    // Apply bloom effect
    out->bloom_intensity = vs->bloom_amount;

    // Apply rain glare
    out->glare_amount = vs->rain_glare;

    // Night edge fade boost (more prominent at night)
    out->edge_fade_night_boost = vs->dark_adaptation * 0.3;

    out->active = true;
}

// ============================================================================
//  4.  Debug logging
// ============================================================================

void visual_response_debug_log(const VisualResponseState* vs) {
    if (vs == 0) {
        MSFS_Log("[C_HUD_VIS] VisualResponseState: NULL");
        return;
    }

    MSFS_Log("[C_HUD_VIS] LUM=%.2f  DARK_ADAPT=%.2f  BLOOM=%.2f  "
             "RAIN=%.2f(%d)  PHOS=%.1fms  BRI=%.2f/%.2f  "
             "FATIGUE=%.2f  ACCOM=%.2f  ACT=%d",
             vs->ambient_luminance, vs->dark_adaptation, vs->bloom_amount,
             vs->rain_glare, (int)vs->is_raining,
             vs->phosphor_current_ms,
             vs->current_brightness, vs->target_brightness,
             vs->contrast_reduction, vs->accommodation,
             (int)vs->active);
}
