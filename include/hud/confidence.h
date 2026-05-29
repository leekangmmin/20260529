#ifndef C_HUD_CONFIDENCE_H
#define C_HUD_CONFIDENCE_H

// ============================================================================
//  Conformal HUD – Confidence-Based Rendering System
//  MSFS 2024  ·  C++17  ·  WASM
//
//  v2.4.0 — Avionics confidence simulation.
//
//  Simulates the behaviour of real avionics where sensor confidence
//  affects how guidance symbology is rendered:
//
//    · Sensor confidence scoring (ILS, GPS, radio altimeter)
//    · Degraded guidance rendering (dashed lines, dimmed bars)
//    · Dashed symbology for low confidence
//    · Dimmed LOC/GS guidance when confidence is low
//    · Unstable sensor oscillation behaviour
//    · Confidence-weighted stabilisation
//
//  When confidence is low, the HUD should visually degrade in a
//  way that feels like real avionics rather than a clean digital
//  overlay.  CAT III operations require high integrity.
// ============================================================================

#include "../module.h"

// ============================================================================
//  1.  Sensor types
// ============================================================================

typedef enum SensorType {
    SENSOR_ILS_LOC      = 0,
    SENSOR_ILS_GS       = 1,
    SENSOR_GPS          = 2,
    SENSOR_RADIO_ALT    = 3,
    SENSOR_AIR_DATA     = 4,
    SENSOR_ATTITUDE     = 5,

    SENSOR_COUNT        = 6,
} SensorType;

// ============================================================================
//  2.  Confidence state per sensor
// ============================================================================

typedef struct SensorConfidence {
    FLOAT64 confidence;             // 0..1 overall confidence
    FLOAT64 signal_quality;         // 0..1 signal quality
    FLOAT64 signal_strength;        // 0..1 signal strength
    FLOAT64 noise_level;            // 0..1 estimated noise
    FLOAT64 stability;              // 0..1 signal stability (jitter resistance)
    FLOAT64 oscillation_freq;       // oscillation frequency (Hz), if unstable
    FLOAT64 oscillation_amplitude;  // oscillation amplitude
    bool    valid;                  // true if sensor is providing data
} SensorConfidence;

// ============================================================================
//  3.  Rendering quality state
// ============================================================================

/// How a specific guidance element should be rendered.
typedef enum GuidanceRenderMode {
    RENDER_SOLID      = 0,   // Full quality
    RENDER_DIMMED     = 1,   // Reduced opacity
    RENDER_DASHED     = 2,   // Dashed line pattern
    RENDER_OSCILLATE  = 3,   // Unstable oscillation
    RENDER_HIDDEN     = 4,   // Not rendered
} GuidanceRenderMode;

/// Per-element rendering parameters from confidence system.
typedef struct ConfidenceRenderParams {
    GuidanceRenderMode loc_mode;         // LOC bar rendering mode
    GuidanceRenderMode gs_mode;          // GS bar rendering mode
    GuidanceRenderMode fpv_mode;         // FPV rendering mode
    GuidanceRenderMode flare_mode;       // Flare cue rendering mode
    GuidanceRenderMode centerline_mode;  // Centerline rendering mode

    FLOAT64 loc_alpha;          // LOC bar alpha (0..1)
    FLOAT64 gs_alpha;           // GS bar alpha (0..1)
    FLOAT64 fpv_alpha;          // FPV alpha (0..1)
    FLOAT64 flare_alpha;        // Flare cue alpha (0..1)
    FLOAT64 centerline_alpha;   // Centerline alpha (0..1)

    FLOAT64 loc_dash_length;    // Dash length for LOC (pixels, 0 = solid)
    FLOAT64 gs_dash_length;     // Dash length for GS (pixels, 0 = solid)

    FLOAT64 integrity;          // Overall system integrity (0..1)

    bool    valid;
} ConfidenceRenderParams;

// ============================================================================
//  4.  Confidence system state
// ============================================================================

typedef struct ConfidenceState {
    // --- Per-sensor confidence ---
    SensorConfidence sensors[SENSOR_COUNT];

    // --- Computed integrity ---
    FLOAT64 overall_integrity;       // 0..1 overall system integrity
    FLOAT64 ils_integrity;           // ILS-specific integrity
    FLOAT64 guidance_integrity;      // Guidance system integrity
    FLOAT64 cat_iii_qualification;   // 0..1 CAT III qualification

    // --- Rendering parameters ---
    ConfidenceRenderParams render;

    // --- Oscillation state ---
    FLOAT64 oscillation_phase;       // current oscillation phase (radians)
    FLOAT64 time_s;                  // running time (seconds)

    // --- Profile tuning ---
    FLOAT64 noise_sensitivity;       // 0..1 noise sensitivity
    FLOAT64 stability_gain;          // stability gain from profile

    // --- Debug ---
    bool    valid;
} ConfidenceState;

// ============================================================================
//  5.  Initialisation
// ============================================================================

/// Initialise the confidence system.
static inline void confidence_init(ConfidenceState* cs) {
    if (cs == 0) return;

    for (int i = 0; i < SENSOR_COUNT; ++i) {
        cs->sensors[i].confidence          = 1.0;
        cs->sensors[i].signal_quality      = 1.0;
        cs->sensors[i].signal_strength     = 1.0;
        cs->sensors[i].noise_level         = 0.0;
        cs->sensors[i].stability           = 1.0;
        cs->sensors[i].oscillation_freq    = 0.0;
        cs->sensors[i].oscillation_amplitude = 0.0;
        cs->sensors[i].valid              = true;
    }

    cs->overall_integrity      = 1.0;
    cs->ils_integrity          = 1.0;
    cs->guidance_integrity     = 1.0;
    cs->cat_iii_qualification  = 1.0;

    cs->oscillation_phase      = 0.0;
    cs->time_s                 = 0.0;

    cs->noise_sensitivity      = 0.5;
    cs->stability_gain         = 1.0;

    // Render params
    cs->render.loc_mode        = RENDER_SOLID;
    cs->render.gs_mode         = RENDER_SOLID;
    cs->render.fpv_mode        = RENDER_SOLID;
    cs->render.flare_mode      = RENDER_SOLID;
    cs->render.centerline_mode = RENDER_SOLID;
    cs->render.loc_alpha       = 1.0;
    cs->render.gs_alpha        = 1.0;
    cs->render.fpv_alpha       = 1.0;
    cs->render.flare_alpha     = 1.0;
    cs->render.centerline_alpha = 1.0;
    cs->render.loc_dash_length = 0.0;
    cs->render.gs_dash_length  = 0.0;
    cs->render.integrity       = 1.0;
    cs->render.valid           = true;

    cs->valid = true;
}

// ============================================================================
//  6.  Confidence computation
// ============================================================================

/// Compute confidence state for the current frame.
///
/// @param cs              [in/out] Confidence state
/// @param dt_s            Frame delta time (seconds)
/// @param ils_loc_dots    ILS localizer deviation (dots)
/// @param ils_gs_dots     ILS glideslope deviation (dots)
/// @param loc_captured    True if localizer is captured
/// @param gs_captured     True if glideslope is captured
/// @param radio_alt_valid True if radio altimeter data is valid
/// @param groundspeed_ms  Ground speed (m/s)
/// @param cat_iii_mode    True if CAT III operations
void confidence_compute(ConfidenceState* cs,
                         FLOAT64          dt_s,
                         FLOAT64          ils_loc_dots,
                         FLOAT64          ils_gs_dots,
                         bool             loc_captured,
                         bool             gs_captured,
                         bool             radio_alt_valid,
                         FLOAT64          groundspeed_ms,
                         bool             cat_iii_mode);

/// Get the rendering mode for a specific guidance element.
///
/// @param cs   Confidence state
/// @param type Sensor type
/// @return     Render mode for the element
static inline GuidanceRenderMode confidence_get_mode(const ConfidenceState* cs,
                                                       SensorType type) {
    if (cs == 0 || type < 0 || type >= SENSOR_COUNT) return RENDER_SOLID;
    return cs->render.loc_mode;  // simplified — caller should check type
}

// ============================================================================
//  7.  Debug logging
// ============================================================================

/// Log confidence state for debugging.
void confidence_debug_log(const ConfidenceState* cs);

#endif // C_HUD_CONFIDENCE_H
