// ============================================================================
//  Conformal HUD – Confidence-Based Rendering System Implementation
//  MSFS 2024  ·  C++17  ·  WASM
//
//  v2.4.0 — Avionics confidence simulation.
//  Simulates sensor confidence and renders degraded guidance when
//  confidence is low, creating realistic avionics behaviour.
// ============================================================================

#include "../../include/hud/confidence.h"
#include "../../include/projection.h"

// ============================================================================
//  1.  Constants
// ============================================================================

#define CONF_LOC_DEV_THRESHOLD  0.8    // LOC deviation for confidence drop
#define CONF_GS_DEV_THRESHOLD   0.8    // GS deviation for confidence drop
#define CONF_CAPTURE_BOOST      0.2    // Confidence boost when captured
#define CONF_NOISE_FLOOR        0.05   // Minimum noise level
#define CONF_DASH_THRESHOLD     0.6    // Below this confidence → dashed
#define CONF_DIMMED_THRESHOLD   0.4    // Below this confidence → dimmed
#define CONF_HIDDEN_THRESHOLD   0.15   // Below this confidence → hidden
#define CONF_OSCILLATE_AMPL     0.03   // Oscillation amplitude for unstable

// ============================================================================
//  2.  Confidence computation
// ============================================================================

void confidence_compute(ConfidenceState* cs,
                         FLOAT64          dt_s,
                         FLOAT64          ils_loc_dots,
                         FLOAT64          ils_gs_dots,
                         bool             loc_captured,
                         bool             gs_captured,
                         bool             radio_alt_valid,
                         FLOAT64          groundspeed_ms,
                         bool             cat_iii_mode) {
    if (cs == 0) return;

    cs->time_s += dt_s;
    cs->oscillation_phase += dt_s * 3.0;  // slow oscillation

    // ================================================================
    //  ILS LOCALIZER CONFIDENCE
    // ================================================================
    {
        SensorConfidence* loc = &cs->sensors[SENSOR_ILS_LOC];
        loc->valid = true;

        // Signal quality based on deviation
        const FLOAT64 dev_quality = 1.0 - proj_fmin(proj_fabs(ils_loc_dots) /
                                                     2.0, 1.0);
        loc->signal_quality = dev_quality;

        // Capture status boosts confidence
        FLOAT64 capture_boost = loc_captured ? CONF_CAPTURE_BOOST : 0.0;

        // Noise level increases with deviation
        loc->noise_level = CONF_NOISE_FLOOR +
                           (1.0 - dev_quality) * 0.3;

        // Stability: good when captured and not oscillating
        loc->stability = loc_captured ? 0.95 : 0.7;

        // Oscillation when not captured
        if (!loc_captured) {
            loc->oscillation_freq = 0.5;
            loc->oscillation_amplitude = 0.02;
        } else {
            loc->oscillation_freq = 0.0;
            loc->oscillation_amplitude = 0.0;
        }

        // Overall confidence
        loc->confidence = (dev_quality * 0.5 + loc->stability * 0.3 +
                           capture_boost * 0.2);
        loc->confidence = proj_clamp(loc->confidence, 0.0, 1.0);
    }

    // ================================================================
    //  ILS GLIDESLOPE CONFIDENCE
    // ================================================================
    {
        SensorConfidence* gs = &cs->sensors[SENSOR_ILS_GS];
        gs->valid = true;

        const FLOAT64 dev_quality = 1.0 - proj_fmin(proj_fabs(ils_gs_dots) /
                                                     2.0, 1.0);
        gs->signal_quality = dev_quality;

        FLOAT64 capture_boost = gs_captured ? CONF_CAPTURE_BOOST : 0.0;

        gs->noise_level = CONF_NOISE_FLOOR +
                          (1.0 - dev_quality) * 0.3;

        gs->stability = gs_captured ? 0.95 : 0.7;

        if (!gs_captured) {
            gs->oscillation_freq = 0.4;
            gs->oscillation_amplitude = 0.015;
        } else {
            gs->oscillation_freq = 0.0;
            gs->oscillation_amplitude = 0.0;
        }

        gs->confidence = (dev_quality * 0.5 + gs->stability * 0.3 +
                          capture_boost * 0.2);
        gs->confidence = proj_clamp(gs->confidence, 0.0, 1.0);
    }

    // ================================================================
    //  GPS CONFIDENCE
    // ================================================================
    {
        SensorConfidence* gps = &cs->sensors[SENSOR_GPS];
        gps->valid = true;
        gps->signal_quality = 0.95;
        gps->stability = 0.9;
        gps->noise_level = 0.05;

        // Ground speed affects GPS confidence slightly
        if (groundspeed_ms < 0.5) {
            gps->confidence = 0.8;  // Reduced on ground
        } else {
            gps->confidence = 0.95;
        }
    }

    // ================================================================
    //  RADIO ALTIMETER CONFIDENCE
    // ================================================================
    {
        SensorConfidence* ra = &cs->sensors[SENSOR_RADIO_ALT];
        ra->valid = radio_alt_valid;
        if (radio_alt_valid) {
            ra->confidence = 0.98;
            ra->signal_quality = 0.98;
            ra->stability = 0.95;
            ra->noise_level = 0.02;
        } else {
            ra->confidence = 0.2;
            ra->signal_quality = 0.2;
            ra->stability = 0.2;
            ra->noise_level = 0.8;
        }
    }

    // ================================================================
    //  AIR DATA CONFIDENCE
    // ================================================================
    {
        SensorConfidence* ad = &cs->sensors[SENSOR_AIR_DATA];
        ad->valid = true;
        ad->confidence = 0.9;
        ad->signal_quality = 0.9;
        ad->stability = 0.85;
        ad->noise_level = 0.1;
    }

    // ================================================================
    //  ATTITUDE CONFIDENCE
    // ================================================================
    {
        SensorConfidence* att = &cs->sensors[SENSOR_ATTITUDE];
        att->valid = true;
        att->confidence = 0.95;
        att->signal_quality = 0.95;
        att->stability = 0.9;
        att->noise_level = 0.05;
    }

    // ================================================================
    //  COMPOSITE INTEGRITY
    // ================================================================
    {
        // ILS integrity is the minimum of LOC and GS confidence
        cs->ils_integrity = proj_fmin(
            cs->sensors[SENSOR_ILS_LOC].confidence,
            cs->sensors[SENSOR_ILS_GS].confidence);

        // Guidance integrity considers ILS + attitude
        cs->guidance_integrity = proj_fmin(cs->ils_integrity,
            cs->sensors[SENSOR_ATTITUDE].confidence);

        // Overall integrity includes all active sensors
        FLOAT64 sum = 0.0;
        int count = 0;
        for (int i = 0; i < SENSOR_COUNT; ++i) {
            if (cs->sensors[i].valid) {
                sum += cs->sensors[i].confidence;
                ++count;
            }
        }
        cs->overall_integrity = (count > 0) ? (sum / (FLOAT64)count) : 0.5;

        // CAT III qualification: requires very high integrity
        if (cat_iii_mode) {
            cs->cat_iii_qualification = cs->overall_integrity *
                                         proj_fmin(cs->guidance_integrity * 1.1, 1.0);
        } else {
            cs->cat_iii_qualification = cs->overall_integrity;
        }
    }

    // ================================================================
    //  RENDERING PARAMETERS
    // ================================================================
    {
        ConfidenceRenderParams* r = &cs->render;

        const FLOAT64 loc_conf = cs->sensors[SENSOR_ILS_LOC].confidence;
        const FLOAT64 gs_conf = cs->sensors[SENSOR_ILS_GS].confidence;

        // --- LOC rendering ---
        if (loc_conf < CONF_HIDDEN_THRESHOLD) {
            r->loc_mode = RENDER_HIDDEN;
            r->loc_alpha = 0.0;
            r->loc_dash_length = 0.0;
        } else if (loc_conf < CONF_DIMMED_THRESHOLD) {
            r->loc_mode = RENDER_DIMMED;
            r->loc_alpha = 0.3;
            r->loc_dash_length = 0.0;
        } else if (loc_conf < CONF_DASH_THRESHOLD) {
            r->loc_mode = RENDER_DASHED;
            r->loc_alpha = 0.5;
            r->loc_dash_length = 8.0 + (1.0 - loc_conf) * 12.0;
        } else {
            r->loc_mode = RENDER_SOLID;
            r->loc_alpha = 0.7 + loc_conf * 0.3;
            r->loc_dash_length = 0.0;
        }

        // --- GS rendering ---
        if (gs_conf < CONF_HIDDEN_THRESHOLD) {
            r->gs_mode = RENDER_HIDDEN;
            r->gs_alpha = 0.0;
            r->gs_dash_length = 0.0;
        } else if (gs_conf < CONF_DIMMED_THRESHOLD) {
            r->gs_mode = RENDER_DIMMED;
            r->gs_alpha = 0.3;
            r->gs_dash_length = 0.0;
        } else if (gs_conf < CONF_DASH_THRESHOLD) {
            r->gs_mode = RENDER_DASHED;
            r->gs_alpha = 0.5;
            r->gs_dash_length = 8.0 + (1.0 - gs_conf) * 12.0;
        } else {
            r->gs_mode = RENDER_SOLID;
            r->gs_alpha = 0.7 + gs_conf * 0.3;
            r->gs_dash_length = 0.0;
        }

        // --- FPV rendering ---
        const FLOAT64 gps_conf = cs->sensors[SENSOR_GPS].confidence;
        if (gps_conf < CONF_DIMMED_THRESHOLD) {
            r->fpv_mode = RENDER_DIMMED;
            r->fpv_alpha = gps_conf;
        } else {
            r->fpv_mode = RENDER_SOLID;
            r->fpv_alpha = 0.8 + gps_conf * 0.2;
        }

        // --- Flare cue rendering ---
        const FLOAT64 ra_conf = cs->sensors[SENSOR_RADIO_ALT].confidence;
        if (ra_conf < CONF_DIMMED_THRESHOLD) {
            r->flare_mode = RENDER_HIDDEN;
            r->flare_alpha = 0.0;
        } else {
            r->flare_mode = RENDER_SOLID;
            r->flare_alpha = ra_conf;
        }

        // --- Centerline rendering ---
        r->centerline_mode = RENDER_SOLID;
        r->centerline_alpha = cs->guidance_integrity;

        // --- Overall integrity for display ---
        r->integrity = cs->overall_integrity;
        r->valid = true;
    }

    cs->valid = true;
}

// ============================================================================
//  3.  Debug logging
// ============================================================================

void confidence_debug_log(const ConfidenceState* cs) {
    if (cs == 0) {
        MSFS_Log("[C_HUD_CONF] ConfidenceState: NULL");
        return;
    }

    MSFS_Log("[C_HUD_CONF] INTEG=%.2f  ILS=%.2f  "
             "LOC_CONF=%.2f GS_CONF=%.2f GPS=%.2f RA=%.2f "
             "CATIII=%.2f  "
             "LOC=%d(%d) GS=%d(%d)",
             cs->overall_integrity, cs->ils_integrity,
             cs->sensors[SENSOR_ILS_LOC].confidence,
             cs->sensors[SENSOR_ILS_GS].confidence,
             cs->sensors[SENSOR_GPS].confidence,
             cs->sensors[SENSOR_RADIO_ALT].confidence,
             cs->cat_iii_qualification,
             (int)cs->render.loc_mode, (int)(cs->render.loc_alpha * 100),
             (int)cs->render.gs_mode, (int)(cs->render.gs_alpha * 100));
}
