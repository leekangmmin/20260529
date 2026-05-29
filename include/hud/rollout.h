#ifndef C_HUD_ROLLOUT_H
#define C_HUD_ROLLOUT_H

// ============================================================================
//  Conformal HUD – Rollout Guidance System
//  MSFS 2024  ·  C++17  ·  WASM
//
//  v2.4.0 — Rollout guidance realism for CAT III operations.
//
//  Implements the final phase of an automatic landing: rollout guidance
//  after touchdown.  Provides:
//    · Runway centerline steering with adaptive damping
//    · Rollout anticipation logic (predictive centerline tracking)
//    · Nosewheel transition smoothing (progressive nosewheel steering)
//    · Touchdown transition smoothing (flare → rollout handover)
//    · Runway perspective compression effect during rollout
//    · Deceleration cue symbology (braking advisory)
//    · Rollout centerline confidence weighting
//
//  The rollout system activates when the aircraft touches down (radio
//  altitude < 0.5 m or on-ground flag true) and provides lateral
//  steering guidance to track the runway centerline during the landing
//  roll, similar to real Boeing HGS CAT III rollout guidance.
// ============================================================================

#include "../module.h"
#include "../projection.h"

// ============================================================================
//  1.  Rollout State
// ============================================================================

/// Rollout guidance phase.
typedef enum RolloutPhase {
    ROLLOUT_PHASE_INACTIVE   = 0,   // Not in rollout (airborne)
    ROLLOUT_PHASE_TRANSITION = 1,   // Touchdown transition (first ~2 s)
    ROLLOUT_PHASE_ACTIVE     = 2,   // Active rollout guidance
    ROLLOUT_PHASE_COMPLETE   = 3,   // Slow speed (< 30 kt), guidance ends
} RolloutPhase;

/// Rollout guidance state.
typedef struct RolloutState {
    // --- Inputs (populated by main pipeline) ---
    bool    on_ground;              // true when aircraft is on ground
    FLOAT64 groundspeed_ms;         // ground speed (m/s)
    FLOAT64 radio_altitude_m;       // radio altitude (m)
    FLOAT64 heading_deg;            // aircraft true heading
    FLOAT64 track_deg;              // ground track
    FLOAT64 runway_heading_deg;     // runway true heading
    FLOAT64 lateral_deviation_m;    // lateral deviation from centerline (m, + = right)

    // --- Computed rollout guidance ---
    RolloutPhase phase;             // current rollout phase
    FLOAT64 centerline_error_deg;   // heading error relative to centerline (deg)
    FLOAT64 centerline_error_dots;  // normalised error (dots)
    FLOAT64 steering_command_deg;   // steering command (deg, positive = right)
    FLOAT64 steering_damping;       // adaptive damping factor (0..1)

    // --- Nosewheel transition ---
    FLOAT64 nosewheel_fraction;     // nosewheel steering fraction (0..1)
    FLOAT64 nosewheel_transition_s; // nosewheel transition time constant

    // --- Touchdown transition ---
    FLOAT64 transition_s;           // time since touchdown (s)
    FLOAT64 transition_complete;    // 0..1 transition completeness

    // --- Deceleration cue ---
    FLOAT64 decel_rate_ms2;         // actual deceleration (m/s²)
    FLOAT64 target_decel_ms2;       // target deceleration (m/s²)
    FLOAT64 decel_error;            // deceleration error (normalised)
    FLOAT64 brake_advisory;         // braking advisory cue (0..1)

    // --- Centerline confidence ---
    FLOAT64 confidence;             // overall rollout confidence (0..1)
    FLOAT64 centerline_quality;     // centerline tracking quality (0..1)
    FLOAT64 centerline_offset_px;   // lateral offset on HUD (pixels)

    // --- Perspective compression ---
    FLOAT64 perspective_compression; // runway compression factor during roll

    // --- Timing ---
    FLOAT64 rollout_time_s;         // total time in rollout (s)
    int     rollout_frame_count;    // frames since touchdown

    // --- Debug ---
    bool    valid;
} RolloutState;

/// Rollout cue rendering parameters.
typedef struct RolloutCue {
    Vec2    centerline_pos;         // centerline cue position on HUD
    FLOAT64 centerline_width_px;    // width of centerline cue
    FLOAT64 centerline_alpha;       // opacity of centerline
    FLOAT64 decel_cue_pos_x;        // deceleration cue position
    FLOAT64 decel_cue_alpha;        // deceleration cue opacity
    bool    visible;                // true if rollout cues should be drawn
} RolloutCue;

// ============================================================================
//  2.  Rollout state initialisation
// ============================================================================

/// Initialise rollout state.
static inline void rollout_init(RolloutState* rs) {
    if (rs == 0) return;
    rs->on_ground              = false;
    rs->groundspeed_ms         = 0.0;
    rs->radio_altitude_m       = 100.0;
    rs->heading_deg            = 0.0;
    rs->track_deg              = 0.0;
    rs->runway_heading_deg     = 0.0;
    rs->lateral_deviation_m    = 0.0;

    rs->phase                  = ROLLOUT_PHASE_INACTIVE;
    rs->centerline_error_deg   = 0.0;
    rs->centerline_error_dots  = 0.0;
    rs->steering_command_deg   = 0.0;
    rs->steering_damping       = 0.0;

    rs->nosewheel_fraction     = 0.0;
    rs->nosewheel_transition_s = 2.0;

    rs->transition_s           = 0.0;
    rs->transition_complete    = 0.0;

    rs->decel_rate_ms2         = 0.0;
    rs->target_decel_ms2       = 0.0;
    rs->decel_error            = 0.0;
    rs->brake_advisory         = 0.0;

    rs->confidence             = 0.5;
    rs->centerline_quality     = 1.0;
    rs->centerline_offset_px   = 0.0;

    rs->perspective_compression = 1.0;

    rs->rollout_time_s         = 0.0;
    rs->rollout_frame_count    = 0;

    rs->valid                  = false;
}

// ============================================================================
//  3.  Rollout guidance computation
// ============================================================================

/// Compute rollout guidance state.
///
/// Should be called each frame after touchdown detection.
///
/// @param rs    [in/out] Rollout state (inputs populated, outputs computed)
/// @param dt_s  Frame delta time (seconds)
/// @return      true if computation succeeded
bool rollout_compute(RolloutState* rs, FLOAT64 dt_s);

/// Detect if the rollout phase should be initiated.
///
/// @param on_ground    True if aircraft is on ground
/// @param ra_m         Radio altitude (metres)
/// @param vs_ms        Vertical speed (m/s, positive = up)
/// @return             true if rollout should activate
static inline bool rollout_should_activate(bool on_ground,
                                            FLOAT64 ra_m,
                                            FLOAT64 vs_ms) {
    // Activate when on ground or very close to ground with sink rate
    return (on_ground) || (ra_m < 0.5 && vs_ms < -0.1);
}

// ============================================================================
//  4.  Rollout cue projection
// ============================================================================

/// Project rollout cues to HUD screen coordinates.
///
/// @param rs          Rollout state
/// @param focal_px    Focal length (pixels)
/// @param screen_w    Screen width
/// @param screen_h    Screen height
/// @param runway_cx   Runway center X on HUD (pixels)
/// @param runway_cy   Runway center Y on HUD (pixels)
/// @param cue         [out] Rollout cue rendering parameters
void rollout_project_cue(const RolloutState* rs,
                          FLOAT64             focal_px,
                          int                 screen_w,
                          int                 screen_h,
                          FLOAT64             runway_cx,
                          FLOAT64             runway_cy,
                          RolloutCue*         cue);

// ============================================================================
//  5.  Debug logging
// ============================================================================

/// Log rollout state for debugging.
void rollout_debug_log(const RolloutState* rs);

#endif // C_HUD_ROLLOUT_H
