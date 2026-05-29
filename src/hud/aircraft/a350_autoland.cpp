// ============================================================================
//  Conformal HUD – Airbus A350 XWB Autoland HUD Layer Implementation
//  MSFS 2024  ·  C++17  ·  WASM
//
//  v3.0.0 — A350 Certification Layer
//
//  Implements CAT III autoland HUD layer with:
//    · CAT IIIA/B/C state machine
//    · Confidence sub-scores for ILS, runway, flare, rollout
//    · Graceful degradation (no abrupt failures)
//    · Visual enhancement for low-visibility operations
// ============================================================================

#include "../../../include/hud/aircraft/a350_autoland.h"
#include "../../../include/projection.h"

// ============================================================================
//  Constants
// ============================================================================

#define AUTOLAND_CONF_ATTACK_ALPHA  0.15   // Fast attack for confidence
#define AUTOLAND_CONF_DECAY_ALPHA   0.04   // Slow decay for confidence
#define AUTOLAND_DEGRADATION_DECAY  0.02   // Slow degradation recovery

// ============================================================================
//  Internal: Update CAT III level based on conditions
// ============================================================================

static A350Cat3Level determine_cat3_level(
    FLOAT64 radio_alt_m,
    FLOAT64 confidence)
{
    // CAT IIIC requires highest confidence and is a preparation target
    if (confidence > 0.95 && radio_alt_m < 200.0) {
        return CAT3_IIIC;
    }
    // CAT IIIB — A350 certified, DH 50 ft
    if (confidence > 0.85 && radio_alt_m < 200.0) {
        return CAT3_IIIB;
    }
    // CAT IIIA — DH 200 ft
    if (confidence > 0.70 && radio_alt_m < 400.0) {
        return CAT3_IIIA;
    }
    return CAT3_NONE;
}

// ============================================================================
//  Internal: Compute confidence sub-scores
// ============================================================================

static void compute_confidence_scores(
    A350AutolandConfidence* conf,
    const ConfidenceState*  cs,
    const RolloutState*     rs,
    FLOAT64 ils_loc_dots,
    FLOAT64 ils_gs_dots,
    bool    loc_captured,
    bool    gs_captured,
    FLOAT64 radio_alt_m,
    bool    on_ground,
    FLOAT64 dt_s)
{
    if (conf == 0) return;

    // ================================================================
    //  ILS signal confidence
    // ================================================================
    FLOAT64 ils_signal = 0.5;
    if (cs != 0) {
        ils_signal = (cs->sensors[SENSOR_ILS_LOC].confidence +
                      cs->sensors[SENSOR_ILS_GS].confidence) * 0.5;
    }

    // Adjust based on deviation magnitudes
    const FLOAT64 loc_dev_factor = 1.0 - proj_fmin(proj_fabs(ils_loc_dots) * 0.2, 1.0);
    const FLOAT64 gs_dev_factor  = 1.0 - proj_fmin(proj_fabs(ils_gs_dots) * 0.2, 1.0);

    ils_signal = ils_signal * (0.6 + 0.2 * loc_dev_factor + 0.2 * gs_dev_factor);
    conf->ils_signal = proj_clamp(ils_signal, 0.0, 1.0);

    // ================================================================
    //  Runway alignment confidence
    // ================================================================
    FLOAT64 runway_align = 0.5;
    if (loc_captured) {
        runway_align = 0.7 + 0.3 * (1.0 - proj_fmin(proj_fabs(ils_loc_dots), 1.0));
    }
    if (gs_captured) {
        runway_align += 0.1 * (1.0 - proj_fmin(proj_fabs(ils_gs_dots), 1.0));
    }
    if (on_ground && rs != 0) {
        runway_align = rs->centerline_quality;
    }
    conf->runway_alignment = proj_clamp(runway_align, 0.0, 1.0);

    // ================================================================
    //  Vertical profile confidence
    // ================================================================
    FLOAT64 vert_profile = 0.5;
    if (gs_captured) {
        vert_profile = 0.7 + 0.3 * (1.0 - proj_fmin(proj_fabs(ils_gs_dots), 0.5));
    }
    // Adjust for altitude — closer to ground means higher scrutiny
    if (radio_alt_m < 100.0 && radio_alt_m > 0.0) {
        const FLOAT64 alt_factor = 1.0 - (radio_alt_m / 100.0);
        vert_profile -= alt_factor * 0.1;  // Slightly lower confidence near ground
    }
    conf->vertical_profile = proj_clamp(vert_profile, 0.0, 1.0);

    // ================================================================
    //  Flare confidence
    // ================================================================
    {
        // Flare confidence depends on approach stability and vertical profile
        FLOAT64 flare_conf = (conf->vertical_profile * 0.5 +
                              conf->ils_signal * 0.3 +
                              conf->runway_alignment * 0.2);

        // Boost when both LOC and GS are captured (stabilized approach)
        if (loc_captured && gs_captured) {
            flare_conf += 0.1;
        }

        conf->flare = proj_clamp(flare_conf, 0.0, 1.0);
    }

    // ================================================================
    //  Rollout confidence
    // ================================================================
    {
        FLOAT64 rollout_conf = 0.5;
        if (on_ground && rs != 0) {
            rollout_conf = rs->confidence * 0.6 +
                           rs->centerline_quality * 0.4;
        } else if (conf->runway_alignment > 0.7) {
            // Predict rollout confidence from alignment
            rollout_conf = conf->runway_alignment * 0.8;
        }
        conf->rollout = proj_clamp(rollout_conf, 0.0, 1.0);
    }

    // ================================================================
    //  Overall confidence
    // ================================================================
    {
        const FLOAT64 overall = (
            conf->ils_signal * 0.25 +
            conf->runway_alignment * 0.25 +
            conf->vertical_profile * 0.20 +
            conf->flare * 0.15 +
            conf->rollout * 0.15
        );
        conf->overall = proj_clamp(overall, 0.0, 1.0);
    }

    // ================================================================
    //  CAT III qualification
    // ================================================================
    {
        // CAT III qualification requires high ILS confidence + system integrity
        conf->cat3_qualification = (
            conf->ils_signal * 0.35 +
            conf->system_integrity * 0.35 +
            conf->runway_alignment * 0.20 +
            conf->vertical_profile * 0.10
        );
        conf->cat3_qualification = proj_clamp(conf->cat3_qualification, 0.0, 1.0);
    }

    conf->valid = true;
}

// ============================================================================
//  Internal: Graceful degradation handler
// ============================================================================

static void handle_degradation(
    A350DegradationState* deg,
    FLOAT64 current_confidence,
    FLOAT64 dt_s)
{
    if (deg == 0) return;

    // Detect degradation direction
    if (current_confidence < deg->previous_confidence - 0.02) {
        // Confidence is falling
        if (!deg->degrading) {
            deg->degrading = true;
            deg->degradation_timer_s = 0.0;
        }
        deg->degradation_timer_s += dt_s;

        // After grace period, start degrading output
        if (deg->degradation_timer_s > deg->grace_period_s) {
            deg->smoothed_degradation += deg->degradation_rate * dt_s;
            deg->smoothed_degradation = proj_fmin(deg->smoothed_degradation, 1.0);
        }

        // Check for critical failure
        if (current_confidence < deg->failed_threshold) {
            deg->failed = true;
        }
    } else {
        // Confidence stable or improving — recover gracefully
        if (deg->degrading) {
            // Only recover if confidence has been stable for a while
            deg->degradation_timer_s = proj_fmax(0.0, deg->degradation_timer_s - dt_s);
            if (deg->degradation_timer_s <= 0.0) {
                deg->degrading = false;
            }
        }

        // Slow decay of degradation indicator
        deg->smoothed_degradation *= (1.0 - AUTOLAND_DEGRADATION_DECAY);
        if (deg->smoothed_degradation < 0.01) {
            deg->smoothed_degradation = 0.0;
            deg->failed = false;
        }
    }

    deg->previous_confidence = current_confidence;
}

// ============================================================================
//  Core computation
// ============================================================================

void a350_autoland_compute(
    A350AutolandHudLayer*   al,
    FLOAT64                 dt_s,
    const ConfidenceState*  cs,
    const RolloutState*     rs,
    const A350CatIIIState*  cat3,
    FLOAT64                 ils_loc_dots,
    FLOAT64                 ils_gs_dots,
    bool                    loc_captured,
    bool                    gs_captured,
    FLOAT64                 radio_alt_m,
    FLOAT64                 groundspeed_ms,
    FLOAT64                 vs_ms,
    bool                    on_ground,
    bool                    low_vis)
{
    if (al == 0) return;

    al->valid = false;

    // Store inputs
    al->loc_deviation_dots    = ils_loc_dots;
    al->gs_deviation_dots     = ils_gs_dots;
    al->loc_captured          = loc_captured;
    al->gs_captured           = gs_captured;
    al->radio_altitude_m      = radio_alt_m;
    al->groundspeed_ms        = groundspeed_ms;
    al->vertical_speed_ms     = vs_ms;
    al->on_ground             = on_ground;
    al->low_visibility        = low_vis;

    // ================================================================
    //  Compute deviation rates (for trend monitoring)
    // ================================================================
    {
        static FLOAT64 prev_loc = 0.0;
        static FLOAT64 prev_gs  = 0.0;
        static bool    rate_init = false;

        if (!rate_init) {
            prev_loc = ils_loc_dots;
            prev_gs  = ils_gs_dots;
            rate_init = true;
        }

        al->loc_deviation_rate = (ils_loc_dots - prev_loc) / proj_fmax(dt_s, 0.001);
        al->gs_deviation_rate  = (ils_gs_dots - prev_gs) / proj_fmax(dt_s, 0.001);

        prev_loc = ils_loc_dots;
        prev_gs  = ils_gs_dots;
    }

    // ================================================================
    //  Determine autoland phase
    // ================================================================
    {
        if (on_ground && groundspeed_ms < 1.0) {
            al->autoland_phase = AUTOLAND_COMPLETE;
        } else if (on_ground) {
            al->autoland_phase = AUTOLAND_ROLLOUT;
        } else if (radio_alt_m < 50.0 * 0.3048 && radio_alt_m > 0.1) {
            al->autoland_phase = AUTOLAND_FLARE;
        } else if (loc_captured && gs_captured && radio_alt_m < 600.0) {
            al->autoland_phase = AUTOLAND_ACTIVE;
        } else if (loc_captured || gs_captured) {
            al->autoland_phase = AUTOLAND_ARMED;
        } else {
            al->autoland_phase = AUTOLAND_INACTIVE;
        }

        al->autoland_active = (al->autoland_phase >= AUTOLAND_ARMED &&
                               al->autoland_phase <= AUTOLAND_ROLLOUT);
    }

    // ================================================================
    //  Compute confidence sub-scores
    // ================================================================
    {
        A350AutolandConfidence prev_conf = al->confidence;

        compute_confidence_scores(
            &al->confidence,
            cs, rs,
            ils_loc_dots, ils_gs_dots,
            loc_captured, gs_captured,
            radio_alt_m, on_ground, dt_s);

        // System integrity from CAT III state or confidence system
        if (cat3 != 0 && cat3->valid) {
            al->confidence.system_integrity = cat3->cat3_confidence;
        } else if (cs != 0) {
            al->confidence.system_integrity = cs->overall_integrity;
        }

        // Smooth overall confidence with EMA
        al->confidence.overall = prev_conf.overall *
            (1.0 - al->confidence_smoothing) +
            al->confidence.overall * al->confidence_smoothing;

        // Update CAT III qualification
        al->confidence.cat3_qualification = (
            al->confidence.ils_signal * 0.35 +
            al->confidence.system_integrity * 0.35 +
            al->confidence.runway_alignment * 0.20 +
            al->confidence.vertical_profile * 0.10
        );
        al->confidence.cat3_qualification = proj_clamp(
            al->confidence.cat3_qualification, 0.0, 1.0);
    }

    // ================================================================
    //  Determine CAT III level
    // ================================================================
    {
        al->cat3_level = determine_cat3_level(
            radio_alt_m,
            al->confidence.cat3_qualification);

        al->cat3_available = (al->cat3_level >= CAT3_IIIA);
    }

    // ================================================================
    //  Graceful degradation handling
    // ================================================================
    {
        handle_degradation(
            &al->degradation,
            al->confidence.overall,
            dt_s);
    }

    // ================================================================
    //  Visual enhancement
    // ================================================================
    {
        al->visual_enhancement = 1.0;
        if (al->autoland_active && al->low_visibility) {
            // Enhance visual elements in low vis during autoland
            al->visual_enhancement = 1.0 + (1.0 - al->degradation.smoothed_degradation) * 0.3;
        }
        al->visual_enhancement = proj_clamp(al->visual_enhancement, 0.7, 1.5);
    }

    al->valid = true;
}

// ============================================================================
//  Apply to visual response parameters
// ============================================================================

void a350_autoland_apply_visual(
    const A350AutolandHudLayer* al,
    VisualRenderParams*         vr)
{
    if (al == 0 || vr == 0) return;
    if (!al->autoland_active) return;

    // During autoland, slightly boost brightness and contrast
    // for better visibility in low conditions
    vr->brightness *= (0.9 + al->visual_enhancement * 0.1);
    vr->contrast   *= (0.9 + al->visual_enhancement * 0.1);

    // Increase phosphor persistence during autoland for stability perception
    if (al->low_visibility) {
        vr->phosphor_persistence_ms *= 1.2;
    }

    // Reduce bloom intensity during autoland (avoid distractions)
    vr->bloom_intensity *= 0.8;

    // Slightly increase edge fade for reduced peripheral distraction
    vr->edge_fade_night_boost *= 1.1;

    vr->active = true;
}

// ============================================================================
//  Apply to confidence render parameters
// ============================================================================

void a350_autoland_apply_confidence(
    const A350AutolandHudLayer* al,
    ConfidenceRenderParams*     render)
{
    if (al == 0 || render == 0) return;
    if (!al->autoland_active) return;

    // During active autoland, ensure critical guidance is solid
    if (al->confidence.overall > 0.7) {
        if (al->autoland_phase >= AUTOLAND_ACTIVE) {
            render->loc_mode = RENDER_SOLID;
            render->gs_mode  = RENDER_SOLID;
            render->loc_alpha = proj_fmax(render->loc_alpha, 0.7);
            render->gs_alpha  = proj_fmax(render->gs_alpha, 0.7);
        }

        // Flare cue confidence
        if (al->confidence.flare > al->flare_confidence_threshold) {
            render->flare_mode  = RENDER_SOLID;
            render->flare_alpha = proj_fmax(render->flare_alpha, 0.6);
        }

        // Rollout guidance
        if (al->autoland_phase >= AUTOLAND_ROLLOUT &&
            al->confidence.rollout > al->rollout_confidence_threshold) {
            render->centerline_mode  = RENDER_SOLID;
            render->centerline_alpha = proj_fmax(render->centerline_alpha, 0.7);
        }
    }

    // Degraded mode — reduce rendering quality gracefully
    if (al->degradation.smoothed_degradation > 0.3) {
        const FLOAT64 deg = al->degradation.smoothed_degradation;

        if (deg > 0.7) {
            // Severe degradation: dash the LOC/GS
            if (render->loc_mode == RENDER_SOLID) {
                render->loc_mode = RENDER_DIMMED;
                render->loc_alpha *= 0.7;
            }
            if (render->gs_mode == RENDER_SOLID) {
                render->gs_mode = RENDER_DIMMED;
                render->gs_alpha *= 0.7;
            }
        }

        // Reduce overall integrity
        render->integrity *= (1.0 - deg * 0.3);
    }

    // No abrupt failures — never hide critical guidance suddenly
    // Even in degraded mode, keep LOC/GS visible (just dimmed)
}

// ============================================================================
//  Debug logging
// ============================================================================

void a350_autoland_debug_log(const A350AutolandHudLayer* al) {
    if (al == 0) {
        MSFS_Log("[C_HUD_A350_AUTOLAND] A350AutolandHudLayer: NULL");
        return;
    }

    MSFS_Log("[C_HUD_A350_AUTOLAND] PHASE=%s CAT3=%s ACT=%d "
             "CONF=%.2f ILS=%.2f RWY=%.2f FLARE=%.2f ROLL=%.2f "
             "DEGRAD=%.2f FAIL=%d VIS=%.2f",
             a350_autoland_phase_name(al->autoland_phase),
             a350_autoland_cat3_name(al->cat3_level),
             (int)al->autoland_active,
             al->confidence.overall,
             al->confidence.ils_signal,
             al->confidence.runway_alignment,
             al->confidence.flare,
             al->confidence.rollout,
             al->degradation.smoothed_degradation,
             (int)al->degradation.failed,
             al->visual_enhancement);
}
