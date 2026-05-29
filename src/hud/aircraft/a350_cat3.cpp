// ============================================================================
//  Conformal HUD – Airbus A350 CAT III Capability Layer Implementation
//  MSFS 2024  ·  C++17  ·  WASM
//
//  v2.4.0 — Airbus CAT III enhanced augmentation.
//
//  Provides harmonised visual augmentation for CAT III operations:
//    · Enhanced runway stabilisation during low visibility
//    · Predictive localizer smoothing with confidence weighting
//    · Glideslope confidence stabilisation
//    · Flare cue stabilisation for CAT III autoland monitoring
//    · Rollout confidence amplification
//    · Degraded-mode graceful fallback
//    · Sensor fusion weighting for robust operations
// ============================================================================

#include "../../../include/hud/aircraft/a350_cat3.h"
#include "../../../include/projection.h"

// ============================================================================
//  1.  Constants
// ============================================================================

#define A350_CAT3_ALT_MAX_M        200.0   // Max altitude for CAT III mode
#define A350_CAT3_CONF_THRESHOLD   0.70    // Min confidence to engage
#define A350_CAT3_DECAY_ALPHA      0.05    // Slow decay for confidence
#define A350_CAT3_ATTACK_ALPHA     0.20    // Fast attack for confidence
#define A350_CAT3_ENHANCE_MAX      1.5     // Max visual enhancement factor
#define A350_CAT3_ENHANCE_MIN      0.5     // Min visual enhancement factor

// ============================================================================
//  2.  Core computation
// ============================================================================

void a350_cat3_compute(A350CatIIIState* c3,
                        FLOAT64 dt_s,
                        const ConfidenceState* cs) {
    if (c3 == 0) return;

    c3->valid = false;

    // ================================================================
    //  Status check
    // ================================================================
    const bool should_activate = a350_cat3_should_activate(
        c3->radio_altitude_m, c3->cat3_confidence);

    if (should_activate && !c3->cat3_active) {
        c3->cat3_active = true;
        c3->degraded_timer_s = 0.0;
    }

    if (!should_activate && c3->cat3_active) {
        if (c3->radio_altitude_m > A350_CAT3_ALT_MAX_M + 50.0) {
            c3->cat3_active = false;
        }
    }

    // ================================================================
    //  Sensor fusion confidence
    // ================================================================
    {
        FLOAT64 loc_conf = 0.5;
        FLOAT64 gs_conf = 0.5;
        FLOAT64 ra_conf = 0.5;
        FLOAT64 gps_conf = 0.5;
        FLOAT64 att_conf = 0.5;

        if (cs != 0) {
            loc_conf = cs->sensors[SENSOR_ILS_LOC].confidence;
            gs_conf  = cs->sensors[SENSOR_ILS_GS].confidence;
            ra_conf  = cs->sensors[SENSOR_RADIO_ALT].confidence;
            gps_conf = cs->sensors[SENSOR_GPS].confidence;
            att_conf = cs->sensors[SENSOR_ATTITUDE].confidence;
        }

        // Apply capture boosts
        if (c3->loc_captured) loc_conf += c3->gs_conf_boost_captured;
        if (c3->gs_captured)  gs_conf  += c3->gs_conf_boost_captured;
        loc_conf = proj_clamp(loc_conf, 0.0, 1.0);
        gs_conf  = proj_clamp(gs_conf, 0.0, 1.0);

        // Sensor fusion weighted average
        const FLOAT64 total_weight = c3->loc_weight + c3->gs_weight +
                                      c3->ra_weight + c3->gps_weight +
                                      c3->attitude_weight;

        c3->cat3_qualification = (loc_conf * c3->loc_weight +
                                   gs_conf  * c3->gs_weight +
                                   ra_conf  * c3->ra_weight +
                                   gps_conf * c3->gps_weight +
                                   att_conf * c3->attitude_weight) /
                                  total_weight;

        // Qualification check
        c3->cat3_qualified = (c3->cat3_qualification >= c3->confidence_min_cat3);

        // Smooth confidence with fast attack, slow decay
        if (c3->cat3_qualification > c3->confidence_smoothed) {
            c3->confidence_smoothed += (c3->cat3_qualification -
                                         c3->confidence_smoothed) *
                                        A350_CAT3_ATTACK_ALPHA;
        } else {
            c3->confidence_smoothed += (c3->cat3_qualification -
                                         c3->confidence_smoothed) *
                                        A350_CAT3_DECAY_ALPHA;
        }
        c3->confidence_smoothed = proj_clamp(c3->confidence_smoothed, 0.0, 1.0);

        c3->cat3_confidence = c3->confidence_smoothed;
    }

    // ================================================================
    //  Degraded mode handling
    // ================================================================
    {
        if (c3->cat3_active && !c3->cat3_qualified) {
            c3->degraded_timer_s += dt_s;
            if (c3->degraded_timer_s > c3->degraded_mode_grace_s) {
                // Enter degraded mode
                c3->rollout_confidence_amp = c3->rollout_degraded_fallback;
            }
        } else if (c3->cat3_active) {
            // Full confidence — reset timer and use amplification
            c3->degraded_timer_s = 0.0;
            c3->rollout_confidence_amp = c3->rollout_conf_amplifier;
        }
    }

    // ================================================================
    //  Runway stabilisation
    // ================================================================
    {
        c3->runway_stab_gain = c3->runway_stab_gain_setting;
        if (c3->cat3_active && c3->cat3_qualified) {
            // Boost runway stabilisation during active CAT III
            c3->runway_stab_gain *= 1.2;
        }
        c3->runway_stab_gain = proj_clamp(c3->runway_stab_gain, 0.0, 1.0);

        c3->loc_predictive_smooth = c3->loc_predictive_smooth_s;
    }

    // ================================================================
    //  Glideslope stabilisation
    // ================================================================
    {
        c3->gs_stabilisation = c3->gs_stab_gain_setting;
        if (c3->gs_captured) {
            c3->gs_stabilisation *= 1.1;  // Boost when captured
        }
        c3->gs_stabilisation = proj_clamp(c3->gs_stabilisation, 0.0, 1.0);

        c3->gs_confidence_boost = c3->gs_conf_boost_captured;
        if (c3->gs_captured) {
            c3->gs_confidence_boost *= 1.5;
        }
    }

    // ================================================================
    //  Flare cue stabilisation
    // ================================================================
    {
        c3->flare_cue_stab = c3->flare_cue_stab_gain;
        if (c3->cat3_active && c3->cat3_qualified) {
            c3->flare_cue_stab *= 1.2;  // More stable flare cues in CAT III
        }
        c3->flare_cue_stab = proj_clamp(c3->flare_cue_stab, 0.0, 1.0);

        c3->flare_cue_confidence = c3->flare_cue_min_conf;
        if (c3->cat3_active && c3->cat3_qualified) {
            c3->flare_cue_confidence *= 0.8;  // Lower threshold in CAT III
        }
    }

    // ================================================================
    //  Visual enhancements
    // ================================================================
    {
        if (c3->cat3_active && c3->cat3_qualified) {
            // Enhance visual elements during CAT III
            c3->runway_enhancement = 1.0 + c3->low_vis_enhancement * 0.3;
            c3->centerline_enhancement = 1.0 + c3->low_vis_enhancement * 0.4;
            c3->touchdown_enhancement = 1.0 + c3->low_vis_enhancement * 0.2;
        } else {
            c3->runway_enhancement = 1.0;
            c3->centerline_enhancement = 1.0;
            c3->touchdown_enhancement = 1.0;
        }

        c3->runway_enhancement = proj_clamp(c3->runway_enhancement,
                                             A350_CAT3_ENHANCE_MIN,
                                             A350_CAT3_ENHANCE_MAX);
        c3->centerline_enhancement = proj_clamp(c3->centerline_enhancement,
                                                 A350_CAT3_ENHANCE_MIN,
                                                 A350_CAT3_ENHANCE_MAX);
        c3->touchdown_enhancement = proj_clamp(c3->touchdown_enhancement,
                                                A350_CAT3_ENHANCE_MIN,
                                                A350_CAT3_ENHANCE_MAX);
    }

    c3->valid = true;
}

// ============================================================================
//  3.  Apply to render parameters
// ============================================================================

void a350_cat3_apply_to_render(const A350CatIIIState* c3,
                                ConfidenceRenderParams* render) {
    if (c3 == 0 || render == 0) return;

    if (!c3->cat3_active || !c3->cat3_qualified) {
        return;  // No enhancement when not in CAT III
    }

    // Boost LOC/GS alpha for better visibility in low vis
    render->loc_alpha = proj_fmin(1.0, render->loc_alpha * 1.2);
    render->gs_alpha = proj_fmin(1.0, render->gs_alpha * 1.2);

    // Boost centerline visibility
    render->centerline_alpha = proj_fmin(1.0, render->centerline_alpha * 1.3);

    // Ensure flare cue is visible during CAT III
    if (render->flare_alpha < 0.5 && c3->flare_cue_confidence > 0.5) {
        render->flare_alpha = 0.6;
        render->flare_mode = RENDER_SOLID;
    }

    // Ensure solid rendering mode during CAT III (no dashed/dimmed)
    if (c3->cat3_qualified) {
        if (render->loc_mode == RENDER_DASHED || render->loc_mode == RENDER_DIMMED) {
            render->loc_mode = RENDER_SOLID;
            render->loc_alpha = proj_fmax(render->loc_alpha, 0.5);
        }
        if (render->gs_mode == RENDER_DASHED || render->gs_mode == RENDER_DIMMED) {
            render->gs_mode = RENDER_SOLID;
            render->gs_alpha = proj_fmax(render->gs_alpha, 0.5);
        }
        render->centerline_mode = RENDER_SOLID;
    }

    // Boost overall integrity display
    render->integrity = proj_fmax(render->integrity, c3->cat3_confidence);
}

// ============================================================================
//  4.  Debug logging
// ============================================================================

void a350_cat3_debug_log(const A350CatIIIState* c3) {
    if (c3 == 0) {
        MSFS_Log("[C_HUD_A350_CAT3] A350CatIIIState: NULL");
        return;
    }

    MSFS_Log("[C_HUD_A350_CAT3] ACT=%d QUAL=%d CONF=%.2f QUALIF=%.2f "
             "RWY_STAB=%.2f LOC_SMOOTH=%.2f GS_STAB=%.2f "
             "FLARE_STAB=%.2f ROLL_AMP=%.2f "
             "RWY_ENH=%.2f CL_ENH=%.2f TD_ENH=%.2f",
             (int)c3->cat3_active, (int)c3->cat3_qualified,
             c3->cat3_confidence, c3->cat3_qualification,
             c3->runway_stab_gain, c3->loc_predictive_smooth,
             c3->gs_stabilisation,
             c3->flare_cue_stab, c3->rollout_confidence_amp,
             c3->runway_enhancement, c3->centerline_enhancement,
             c3->touchdown_enhancement);
}
