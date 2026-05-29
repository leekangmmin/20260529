#ifndef C_HUD_EVS_H
#define C_HUD_EVS_H

// ============================================================================
//  Conformal HUD – Enhanced Vision System (EVS) Effects
//  MSFS 2024  ·  C++17  ·  WASM
//
//  v2.3.0 — CAT II/III specific enhancement profiles.
//  Extends the existing visibility-adaptive rendering pipeline with
//  EVS-style low visibility enhancement:
//    · Runway edge enhancement (higher contrast on runway boundaries)
//    · Fog penetration effect (boost symbology in low visibility)
//    · Runway glow amplification (brightness boost for runway area)
//    · Contrast boosting in low visibility
//    · Terrain silhouette enhancement
//    · CAT II/III approach-specific intensity curves
//
//  EVS is typically associated with IR or mm-wave sensors that see
//  through fog. Here we simulate the effect by adjusting the rendering
//  parameters (opacity, line width, contrast boost) based on ambient
//  visibility and phase of flight.
// ============================================================================

#include "../module.h"

// ============================================================================
//  1.  EVS enhancement state
// ============================================================================

/// EVS enhancement levels and parameters.
typedef struct EVSState {
    // --- Raw inputs ---
    FLOAT64 ambient_visibility_m;  // ambient visibility (m)
    FLOAT64 radio_altitude_m;      // radio altitude (m) – for phase detection

    // --- Enhancement parameters (computed) ---
    FLOAT64 runway_contrast_boost; // multiplier on runway line contrast (1.0 = off)
    FLOAT64 fog_penetration;       // fog penetration factor (0..1, higher = more)
    FLOAT64 runway_glow_boost;     // brightness boost for runway area (1.0 = off)
    FLOAT64 symbology_contrast;    // global symbology contrast (1.0 = normal)
    FLOAT64 terrain_enhancement;   // terrain silhouette enhancement (0..1)

    // --- Mode ---
    bool    evs_enabled;           // true when EVS enhancement is active
    bool    low_vis_mode;          // true when visibility is degraded (< 3 km)
    bool    approach_mode;         // true when on approach (low altitude)
    bool    active;                // true when any enhancement is active

    // v2.3.0: CAT category (0 = none, 2 = CAT II, 3 = CAT IIIA, 4 = CAT IIIB)
    int     cat_category;

    // --- Debug ---
    FLOAT64 debug_visibility_norm;
    FLOAT64 debug_evs_intensity;
} EVSState;

// ============================================================================
//  2.  EVS rendering parameters output
// ============================================================================

/// Extended rendering parameters that incorporate EVS enhancement.
typedef struct EVSRenderParams {
    FLOAT64 line_width_px;         // final line width after EVS boost
    FLOAT64 opacity;               // final opacity after EVS boost
    FLOAT64 contrast_boost;        // contrast multiplier for rendering
    FLOAT64 glow_amount;           // glow/bloom amount
    FLOAT64 runway_edge_boost;     // additional runway edge emphasis
    bool    evs_active;            // true if EVS is currently enhancing
} EVSRenderParams;

// ============================================================================
//  3.  EVS state initialisation
// ============================================================================

static inline void evs_init(EVSState* evs) {
    if (evs == 0) return;
    evs->ambient_visibility_m = 20000.0;
    evs->radio_altitude_m     = 1000.0;
    evs->runway_contrast_boost = 1.0;
    evs->fog_penetration      = 0.0;
    evs->runway_glow_boost    = 1.0;
    evs->symbology_contrast   = 1.0;
    evs->terrain_enhancement  = 0.0;
    evs->evs_enabled          = false;
    evs->low_vis_mode         = false;
    evs->approach_mode        = false;
    evs->active               = false;
    evs->cat_category         = 0;
    evs->debug_visibility_norm = 1.0;
    evs->debug_evs_intensity   = 0.0;
}

// ============================================================================
//  4.  EVS computation
// ============================================================================

/// Compute EVS enhancement parameters from ambient conditions.
///
/// @param evs         [in/out] EVS state (inputs already populated)
/// @param phase       Flight phase (0 = cruise, 1 = approach, 2 = landing)
void evs_compute(EVSState* evs, int phase);

/// Apply EVS enhancement to existing weather/render parameters.
///
/// Takes the base weather-derived parameters and enhances them with
/// EVS effects where appropriate.
///
/// @param evs         Computed EVS state
/// @param base        Base render params (from weather_compute_params)
/// @param out         [out] Enhanced render params
void evs_apply(const EVSState* evs,
               const WeatherState* base,
               EVSRenderParams* out);

// ============================================================================
//  5.  Debug logging
// ============================================================================

void evs_debug_log(const EVSState* evs);

#endif // C_HUD_EVS_H
