#ifndef C_HUD_FLARE_H
#define C_HUD_FLARE_H

// ============================================================================
//  Conformal HUD – Boeing-Style Flare Guidance System
//  MSFS 2024  ·  C++17  ·  WASM
//
//  v2.3.0 — Profile-aware flare cue calibration.
//  Implements a Boeing HGS-style flare director that provides:
//    · Flare cue activation below 80 ft RA (fully active below 50 ft)
//    · Flare command computation from radio altitude, sink rate,
//      runway aim point geometry, and glideslope deviation
//    · Flare cue rise behaviour (the flare command symbol rises
//      from the touchdown point to guide the flare manoeuvre)
//    · Touchdown point anticipation and smoothing
//
//  The flare director computes a commanded flare path based on:
//    h_dot_command = -sqrt(2 * g * (h - h_touchdown) * flare_constant)
//  where h is radio altitude, h_touchdown is the touchdown height
//  (typically 0), and flare_constant modulates the flare aggressiveness.
//
//  Required SimVars:
//    · RADIO HEIGHT (radio_altitude_m)
//    · VERTICAL SPEED (vertical_speed_ms, positive = up)
//    · GROUND SPEED (groundspeed_ms)
//    · AGL altitude (available as radio altitude)
// ============================================================================

#include "../module.h"
#include "../projection.h"

// ============================================================================
//  1.  Flare guidance state
// ============================================================================

/// Flare director processing state.
typedef struct FlareState {
    // --- Inputs (populated by update pipeline) ---
    FLOAT64 radio_altitude_m;    // radio altitude above ground (m)
    FLOAT64 vertical_speed_ms;   // vertical speed (m/s, positive = up)
    FLOAT64 groundspeed_ms;      // true ground speed (m/s)
    FLOAT64 gs_deviation_deg;    // glideslope deviation (deg, positive = above)

    // --- Flare command ---
    FLOAT64 flare_cue_vs;        // commanded vertical speed (m/s)
    FLOAT64 flare_cue_error;     // error between commanded and actual VS (m/s)
    FLOAT64 flare_cue_rise;      // cue rise fraction 0..1 (how far cue has risen)
    FLOAT64 flare_anticipation;  // anticipation factor (smooth transition)

    // --- Phase tracking ---
    bool    flare_active;         // true when flare mode is active
    bool    flare_fully_active;   // true below 50 ft RA
    FLOAT64 flare_engagement_alt; // altitude where flare first activated (m)
    int     flare_frame_count;    // frames since flare activation
    bool    flare_complete;       // true when touchdown is imminent

    // --- Touchdown prediction ---
    FLOAT64 touchdown_vs;         // predicted vertical speed at touchdown (m/s)
    FLOAT64 touchdown_distance_m; // predicted distance to touchdown (m)
    FLOAT64 time_to_touchdown_s;  // estimated time to touchdown (s)

    // --- Debug ---
    FLOAT64 debug_flare_constant;
    FLOAT64 debug_raw_command;
    FLOAT64 debug_filtered_error;

    bool    valid;
} FlareState;

// ============================================================================
//  2.  Flare cue rendered position
// ============================================================================

/// The flare director cue position in HUD screen coordinates.
typedef struct FlareCue {
    Vec2    screen_pos;          // centre of flare cue (pixels)
    FLOAT64 vertical_offset_px;  // offset from reference (rise behaviour)
    FLOAT64 size_px;             // cue size (changes during flare)
    FLOAT64 alpha;               // cue opacity
    bool    on_screen;           // true if cue should be drawn
    bool    visible;             // true if flare mode is active and cue valid
} FlareCue;

// ============================================================================
//  3.  Touchdown zone markers
// ============================================================================

/// Touchdown zone markers on the HUD.
typedef struct TouchdownZone {
    Vec2    aim_point;           // touchdown aim point on HUD (pixels)
    FLOAT64 aim_point_size_px;   // size of aim point marker
    FLOAT64 aiming_point_alpha;  // opacity
    bool    visible;
} TouchdownZone;

// ============================================================================
//  4.  Flare guidance computation
// ============================================================================

/// Compute flare guidance state.
///
/// @param flare    [in/out] Flare state with inputs populated
/// @param dt_s     Frame delta time (seconds)
/// @return         true if flare computation succeeded
bool flare_compute(FlareState* flare, FLOAT64 dt_s);

/// Project flare cue to HUD screen coordinates.
///
/// v2.3.0: accepts profile-tuned parameters for aircraft-specific
/// flare cue behaviour.
///
/// @param flare         Flare state (needs flare_cue_error, flare_active, etc.)
/// @param focal_px      Focal length (pixels)
/// @param screen_w      Screen width
/// @param screen_h      Screen height
/// @param ref_point     Reference point on HUD (e.g. touchdown aim point)
/// @param cue           [out] Flare cue position and rendering params
/// @param flare_constant   Profile-specific flare aggressiveness (0.08–0.15)
/// @param max_rise_px      Profile-specific max cue rise from TD point (px)
/// @param min_cue_size     Profile-specific minimum cue size (px)
/// @param max_cue_size     Profile-specific maximum cue size (px)
void flare_project_cue(const FlareState* flare,
                        FLOAT64           focal_px,
                        int               screen_w,
                        int               screen_h,
                        Vec2              ref_point,
                        FlareCue*         cue,
                        FLOAT64           flare_constant,
                        FLOAT64           max_rise_px,
                        FLOAT64           min_cue_size,
                        FLOAT64           max_cue_size);

/// Project the touchdown aim point marker.
///
/// @param flare         Flare state
/// @param focal_px      Focal length (pixels)
/// @param screen_w      Screen width
/// @param screen_h      Screen height
/// @param ref_point     Touchdown point on HUD
/// @param zone          [out] Touchdown zone rendering params
void flare_project_touchdown(const FlareState* flare,
                              FLOAT64           focal_px,
                              int               screen_w,
                              int               screen_h,
                              Vec2              ref_point,
                              TouchdownZone*    zone);

/// Check if the flare should be active.
///
/// @param radio_alt_m  Radio altitude (m)
/// @return             true if flare should activate
static inline bool flare_should_activate(FLOAT64 radio_alt_m) {
    return radio_alt_m < 24.384;  // 80 ft in metres
}

/// Check if the flare is fully active.
///
/// @param radio_alt_m  Radio altitude (m)
/// @return             true if flare is fully active
static inline bool flare_fully_active_check(FLOAT64 radio_alt_m) {
    return radio_alt_m < 15.24;  // 50 ft in metres
}

// ============================================================================
//  5.  Debug logging
// ============================================================================

void flare_debug_log(const FlareState* flare);

#endif // C_HUD_FLARE_H
