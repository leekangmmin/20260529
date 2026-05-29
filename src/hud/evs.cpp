// ============================================================================
//  Conformal HUD – Enhanced Vision System (EVS) Effects Implementation
//  MSFS 2024  ·  C++17  ·  WASM
//
//  v2.3.0 — CAT II/III specific enhancement profiles.
//  Extends the visibility-adaptive pipeline with EVS-style enhancement
//  for low-visibility operations.  Now includes CAT category detection
//  for appropriate enhancement curves.
// ============================================================================

#include "../../include/hud/evs.h"
#include "../../include/projection.h"

// ============================================================================
//  1.  EVS computation  (v2.3.0: CAT II/III profiles)
// ============================================================================

void evs_compute(EVSState* evs, int phase) {
    if (evs == 0) {
        return;
    }

    // --- Clamp inputs ---
    FLOAT64 vis = evs->ambient_visibility_m;
    if (vis < 200.0) vis = 200.0;
    if (vis > 30000.0) vis = 30000.0;

    const FLOAT64 ra = proj_fmax(evs->radio_altitude_m, 0.0);

    // --- Determine visibility regime ---
    const FLOAT64 norm = (vis - 200.0) / (30000.0 - 200.0);
    evs->debug_visibility_norm = norm;

    evs->low_vis_mode  = (vis < 3000.0);
    evs->approach_mode = (phase >= 1 && ra < 600.0);

    // --- Determine CAT category (v2.3.0) ---
    // CAT II:  RVR 300m (visibility ~550m)
    // CAT IIIA: RVR 200m (visibility ~350m)
    // CAT IIIB: RVR 75m  (visibility ~200m)
    if (vis < 400.0) {
        evs->cat_category = 4;  // CAT IIIB
    } else if (vis < 600.0) {
        evs->cat_category = 3;  // CAT IIIA
    } else if (vis < 1200.0) {
        evs->cat_category = 2;  // CAT II
    } else {
        evs->cat_category = 0;
    }

    // --- EVS enabled when low visibility AND on approach ---
    evs->evs_enabled = evs->low_vis_mode ||
                       (evs->approach_mode && vis < 8000.0);

    if (!evs->evs_enabled) {
        evs->runway_contrast_boost = 1.0;
        evs->fog_penetration      = 0.0;
        evs->runway_glow_boost    = 1.0;
        evs->symbology_contrast   = 1.0;
        evs->terrain_enhancement  = 0.0;
        evs->active               = false;
        evs->debug_evs_intensity  = 0.0;
        return;
    }

    // --- Compute EVS intensity ---
    FLOAT64 intensity = 1.0 - norm;
    if (evs->approach_mode) {
        intensity = proj_fmin(1.0, intensity * 1.5);
    }

    // Boost intensity for CAT II/III conditions
    if (evs->cat_category >= 2) {
        intensity = proj_fmin(1.0, intensity * 1.3);
    }
    evs->debug_evs_intensity = intensity;

    // --- Runway contrast boost ---
    evs->runway_contrast_boost = 1.0 + intensity * 1.5;

    // --- Fog penetration ---
    evs->fog_penetration = intensity * 0.7;

    // --- Runway glow amplification ---
    evs->runway_glow_boost = 1.0 + intensity * 0.8;

    // --- Symbology contrast ---
    evs->symbology_contrast = 1.0 + intensity * 0.6;

    // --- Terrain silhouette enhancement ---
    if (evs->approach_mode && ra < 300.0) {
        evs->terrain_enhancement = intensity * 0.5 * (1.0 - ra / 300.0);
    } else {
        evs->terrain_enhancement = intensity * 0.2;
    }

    evs->active = (intensity > 0.01);
}

// ============================================================================
//  2.  Apply EVS enhancement to render params
// ============================================================================

void evs_apply(const EVSState* evs,
               const WeatherState* base,
               EVSRenderParams* out) {
    if (out == 0) return;

    if (base != 0 && base->valid) {
        out->line_width_px = base->line_width_px;
        out->opacity       = base->opacity;
    } else {
        out->line_width_px = 2.0;
        out->opacity       = 0.8;
    }

    out->contrast_boost    = 1.0;
    out->glow_amount       = 0.0;
    out->runway_edge_boost = 1.0;
    out->evs_active        = false;

    if (evs == 0 || !evs->active) {
        return;
    }

    out->line_width_px *= (1.0 + evs->fog_penetration * 0.5);
    if (out->line_width_px > 8.0) out->line_width_px = 8.0;

    out->opacity = proj_fmax(out->opacity,
                             0.7 + evs->fog_penetration * 0.3);

    out->contrast_boost = evs->symbology_contrast;
    out->glow_amount = evs->fog_penetration * 0.15;
    out->runway_edge_boost = evs->runway_contrast_boost;

    out->evs_active = true;
}

// ============================================================================
//  3.  Debug logging
// ============================================================================

void evs_debug_log(const EVSState* evs) {
    if (evs == 0) {
        MSFS_Log("[C_HUD_EVS] EVSState: NULL");
        return;
    }

    MSFS_Log("[C_HUD_EVS] VIS=%.0fm  RA=%.1fm  LV=%d  APPR=%d  "
             "CAT=%d  EN=%d  INT=%.3f  CTB=%.2f  FOG=%.3f  GLW=%.2f  "
             "CNT=%.2f  TRN=%.3f",
             evs->ambient_visibility_m, evs->radio_altitude_m,
             (int)evs->low_vis_mode, (int)evs->approach_mode,
             evs->cat_category,
             (int)evs->evs_enabled,
             evs->debug_evs_intensity,
             evs->runway_contrast_boost,
             evs->fog_penetration,
             evs->runway_glow_boost,
             evs->symbology_contrast,
             evs->terrain_enhancement);
}
