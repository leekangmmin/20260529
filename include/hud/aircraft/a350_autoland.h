#ifndef C_HUD_A350_AUTOLAND_LAYER_H
#define C_HUD_A350_AUTOLAND_LAYER_H

// ============================================================================
//  Conformal HUD – Airbus A350 XWB Autoland HUD Layer
//  MSFS 2024  ·  C++17  ·  WASM
//
//  v3.0.0 — A350 Certification Layer
//
//  CAT III Autoland HUD layer that integrates with:
//    · Confidence system (SensorConfidence, ConfidenceState)
//    · Rollout system (RolloutState)
//    · Visual response system (VisualResponseState)
//
//  Features:
//    · CAT IIIA (DH 200 ft / RVR 550 m)
//    · CAT IIIB (DH 50 ft / RVR 300 m)  — A350 certified
//    · CAT IIIC (DH 0 ft / RVR 0 m)     — preparation
//    · Autoland confidence scoring
//    · Runway confidence tracking
//    · Flare confidence monitoring
//    · Rollout confidence assessment
//    · Graceful degradation — no abrupt failures
// ============================================================================

#include "../../module.h"
#include "../../projection.h"
#include "../confidence.h"
#include "../rollout.h"
#include "../visual_response.h"
#include "a350_cat3.h"

// ============================================================================
//  1.  CAT III operational state
// ============================================================================

typedef enum A350Cat3Level {
    CAT3_NONE     = 0,   // No CAT III operations
    CAT3_IIIA     = 1,   // CAT IIIA  (DH 200 ft)
    CAT3_IIIB     = 2,   // CAT IIIB  (DH 50 ft)  — A350 certified
    CAT3_IIIC     = 3,   // CAT IIIC  (DH 0 ft)   — preparation
} A350Cat3Level;

/// Autoland phase tracking
typedef enum A350AutolandPhase {
    AUTOLAND_INACTIVE    = 0,   // Not in autoland
    AUTOLAND_ARMED       = 1,   // Autoland armed, approaching glidepath
    AUTOLAND_ACTIVE      = 2,   // Autoland active, on glidepath
    AUTOLAND_FLARE       = 3,   // Flare phase
    AUTOLAND_ROLLOUT     = 4,   // Rollout phase
    AUTOLAND_COMPLETE    = 5,   // Autoland completed
} A350AutolandPhase;

// ============================================================================
//  2.  Confidence sub-scores
// ============================================================================

typedef struct A350AutolandConfidence {
    FLOAT64 overall;                // 0..1 overall autoland confidence
    FLOAT64 ils_signal;             // 0..1 ILS signal confidence
    FLOAT64 runway_alignment;       // 0..1 runway alignment confidence
    FLOAT64 vertical_profile;       // 0..1 vertical profile confidence
    FLOAT64 flare;                  // 0..1 flare confidence
    FLOAT64 rollout;                // 0..1 rollout confidence
    FLOAT64 system_integrity;       // 0..1 system integrity
    FLOAT64 cat3_qualification;     // 0..1 CAT III qualification score
    bool    valid;
} A350AutolandConfidence;

// ============================================================================
//  3.  Graceful degradation state
// ============================================================================

typedef struct A350DegradationState {
    bool    degrading;              // true when confidence is falling
    bool    failed;                 // true when degradation is critical
    FLOAT64 degradation_timer_s;    // time since degradation started
    FLOAT64 grace_period_s;         // grace period before degrading mode
    FLOAT64 degradation_rate;       // rate of confidence decay
    FLOAT64 failed_threshold;       // confidence threshold for failure
    FLOAT64 previous_confidence;    // previous frame confidence
    FLOAT64 smoothed_degradation;   // smoothed degradation indicator
} A350DegradationState;

// ============================================================================
//  4.  Complete autoland HUD layer state
// ============================================================================

typedef struct A350AutolandHudLayer {
    // --- Status ---
    A350Cat3Level       cat3_level;         // certified CAT III level
    A350AutolandPhase   autoland_phase;     // current autoland phase
    bool                autoland_active;    // true when autoland is engaged
    bool                cat3_available;     // true if CAT III is available

    // --- Confidence sub-scores ---
    A350AutolandConfidence confidence;

    // --- Degradation ---
    A350DegradationState degradation;

    // --- ILS deviation tracking ---
    FLOAT64 loc_deviation_dots;         // localizer deviation (dots)
    FLOAT64 gs_deviation_dots;          // glideslope deviation (dots)
    bool    loc_captured;               // localizer captured
    bool    gs_captured;                // glideslope captured
    FLOAT64 loc_deviation_rate;         // LOC deviation rate (dots/s)
    FLOAT64 gs_deviation_rate;          // GS deviation rate (dots/s)

    // --- Flight parameters ---
    FLOAT64 radio_altitude_m;           // radio altitude (m)
    FLOAT64 groundspeed_ms;             // ground speed (m/s)
    FLOAT64 vertical_speed_ms;          // vertical speed (m/s)
    FLOAT64 distance_to_runway_m;       // distance to runway threshold (m)
    bool    on_ground;                  // true if on ground

    // --- Configuration ---
    FLOAT64 cat3a_max_dh_m;             // CAT IIIA decision height (m)
    FLOAT64 cat3b_max_dh_m;             // CAT IIIB decision height (m)
    FLOAT64 confidence_smoothing;       // confidence EMA smoothing
    FLOAT64 degradation_grace_s;        // grace period before degraded mode (s)
    FLOAT64 min_confidence_cat3;         // min confidence for CAT III ops
    FLOAT64 flare_confidence_threshold;  // min confidence for flare phase
    FLOAT64 rollout_confidence_threshold; // min confidence for rollout phase

    // --- Visual state ---
    FLOAT64 visual_enhancement;         // 0..1 visual enhancement factor
    bool    low_visibility;             // true in low visibility

    // --- Debug ---
    bool    valid;
} A350AutolandHudLayer;

// ============================================================================
//  5.  Initialisation
// ============================================================================

/// Initialise the A350 autoland HUD layer.
static inline void a350_autoland_init(A350AutolandHudLayer* al) {
    if (al == 0) return;

    al->cat3_level         = CAT3_NONE;
    al->autoland_phase     = AUTOLAND_INACTIVE;
    al->autoland_active    = false;
    al->cat3_available     = false;

    al->confidence.overall             = 0.0;
    al->confidence.ils_signal          = 0.0;
    al->confidence.runway_alignment    = 0.0;
    al->confidence.vertical_profile    = 0.0;
    al->confidence.flare               = 0.0;
    al->confidence.rollout             = 0.0;
    al->confidence.system_integrity    = 1.0;
    al->confidence.cat3_qualification  = 0.0;
    al->confidence.valid               = false;

    al->degradation.degrading              = false;
    al->degradation.failed                 = false;
    al->degradation.degradation_timer_s    = 0.0;
    al->degradation.grace_period_s         = 2.0;
    al->degradation.degradation_rate       = 0.05;
    al->degradation.failed_threshold       = 0.30;
    al->degradation.previous_confidence    = 1.0;
    al->degradation.smoothed_degradation   = 0.0;

    al->loc_deviation_dots     = 0.0;
    al->gs_deviation_dots      = 0.0;
    al->loc_captured           = false;
    al->gs_captured            = false;
    al->loc_deviation_rate     = 0.0;
    al->gs_deviation_rate      = 0.0;

    al->radio_altitude_m       = 1000.0;
    al->groundspeed_ms         = 0.0;
    al->vertical_speed_ms      = 0.0;
    al->distance_to_runway_m   = 5000.0;
    al->on_ground              = false;

    // Airbus A350 certified values
    al->cat3a_max_dh_m              = 200.0 * 0.3048;    // 200 ft
    al->cat3b_max_dh_m              = 50.0 * 0.3048;     // 50 ft
    al->confidence_smoothing        = 0.10;
    al->degradation_grace_s         = 2.0;
    al->min_confidence_cat3         = 0.85;
    al->flare_confidence_threshold  = 0.75;
    al->rollout_confidence_threshold = 0.70;

    al->visual_enhancement  = 1.0;
    al->low_visibility      = false;

    al->valid               = false;
}

// ============================================================================
//  6.  Core computation
// ============================================================================

/// Compute the A350 autoland HUD layer state for the current frame.
///
/// @param al            [in/out] Autoland layer state
/// @param dt_s          Frame delta time (seconds)
/// @param cs            Confidence state from the confidence system
/// @param rs            Rollout state (may be null if not in rollout)
/// @param cat3          A350 CAT III state (may be null)
/// @param ils_loc_dots  ILS localizer deviation (dots)
/// @param ils_gs_dots   ILS glideslope deviation (dots)
/// @param loc_captured  True if localizer captured
/// @param gs_captured   True if glideslope captured
/// @param radio_alt_m   Radio altitude (metres)
/// @param groundspeed_ms Ground speed (m/s)
/// @param vs_ms         Vertical speed (m/s)
/// @param on_ground     True if on ground
/// @param low_vis       True if low visibility conditions
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
    bool                    low_vis);

/// Apply autoland layer effects to visual response parameters.
///
/// @param al   Autoland layer state
/// @param vr   [in/out] Visual render parameters to enhance
void a350_autoland_apply_visual(
    const A350AutolandHudLayer* al,
    VisualRenderParams*         vr);

/// Apply autoland layer effects to confidence render parameters.
///
/// @param al      Autoland layer state
/// @param render  [in/out] Confidence render parameters
void a350_autoland_apply_confidence(
    const A350AutolandHudLayer* al,
    ConfidenceRenderParams*     render);

// ============================================================================
//  7.  Accessors
// ============================================================================

/// Get the current CAT III level string.
static inline const char* a350_autoland_cat3_name(A350Cat3Level level) {
    switch (level) {
        case CAT3_NONE: return "NONE";
        case CAT3_IIIA: return "CAT IIIA";
        case CAT3_IIIB: return "CAT IIIB";
        case CAT3_IIIC: return "CAT IIIC";
        default:        return "UNKNOWN";
    }
}

/// Get the current autoland phase string.
static inline const char* a350_autoland_phase_name(A350AutolandPhase phase) {
    switch (phase) {
        case AUTOLAND_INACTIVE: return "INACTIVE";
        case AUTOLAND_ARMED:    return "ARMED";
        case AUTOLAND_ACTIVE:   return "ACTIVE";
        case AUTOLAND_FLARE:    return "FLARE";
        case AUTOLAND_ROLLOUT:  return "ROLLOUT";
        case AUTOLAND_COMPLETE: return "COMPLETE";
        default:                return "UNKNOWN";
    }
}

// ============================================================================
//  8.  Debug logging
// ============================================================================

void a350_autoland_debug_log(const A350AutolandHudLayer* al);

#endif // C_HUD_A350_AUTOLAND_LAYER_H
