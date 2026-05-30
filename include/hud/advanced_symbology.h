#ifndef C_HUD_ADVANCED_SYMBOLOGY_H
#define C_HUD_ADVANCED_SYMBOLOGY_H

// ============================================================================
//  Conformal HUD – Advanced Boeing HGS-Style Symbology
//  MSFS 2024  ·  C++17  ·  WASM
//
//  Adds the following advanced HUD symbology elements:
//    · Acceleration Caret – shows longitudinal acceleration trend
//    · Energy Trend Vector – indicates total energy state (speed + altitude)
//    · Flare Anticipation Bracket – visual cue for flare initiation
//    · Touchdown Predictor – predicted touchdown point on runway
//    · Velocity Trend Cue – trend vector for airspeed changes
//
//  All elements maintain Boeing HGS style and conformal accuracy.
// ============================================================================

#include "../module.h"
#include "../projection.h"

// ============================================================================
//  1.  Acceleration Caret
// ============================================================================

/// Acceleration caret shows longitudinal acceleration relative to
/// a reference speed (typically VREF or target speed).
typedef struct AccelCaret {
    // --- Inputs ---
    FLOAT64 indicated_airspeed_ms; // current IAS (m/s)
    FLOAT64 true_airspeed_ms;      // current TAS (m/s)
    FLOAT64 groundspeed_ms;        // ground speed (m/s)
    FLOAT64 acceleration_ms2;      // longitudinal acceleration (m/s²)
    FLOAT64 target_speed_ms;       // target/reference speed (m/s)

    // --- Computed ---
    FLOAT64 speed_error_ms;        // IAS - target speed (m/s)
    FLOAT64 accel_dots;            // acceleration in "dots" (normalised)
    Vec2    screen_pos;            // caret screen position
    FLOAT64 caret_offset_x;        // horizontal offset from speed tape (px)

    bool    valid;
    bool    on_screen;
} AccelCaret;

/// Compute the acceleration caret.
///
/// @param ac       [in/out] Accel caret state (inputs populated)
/// @param focal_px Focal length (pixels)
/// @param screen_w Screen width
/// @param screen_h Screen height
/// @param ref_x    Reference X position (e.g. speed tape position)
/// @param ref_y    Reference Y position
void accel_compute(AccelCaret* ac,
                   FLOAT64     focal_px,
                   int         screen_w,
                   int         screen_h,
                   FLOAT64     ref_x,
                   FLOAT64     ref_y);

// ============================================================================
//  2.  Energy Trend Vector
// ============================================================================

/// Energy trend indicates whether the aircraft's total energy
/// (kinetic + potential) is increasing or decreasing.
typedef struct EnergyTrend {
    // --- Inputs ---
    FLOAT64 true_airspeed_ms;      // TAS (m/s)
    FLOAT64 vertical_speed_ms;     // vertical speed (m/s, + = up)
    FLOAT64 acceleration_ms2;      // longitudinal accel (m/s²)

    // --- Computed ---
    FLOAT64 specific_energy_rate;  // d(E/m)/dt = V·V_dot + g·h_dot
    FLOAT64 energy_rate_dots;      // normalised display value
    FLOAT64 trend_angle_deg;       // direction of energy trend vector (deg)

    Vec2    screen_pos;            // screen position
    FLOAT64 vector_length_px;      // length of trend vector on HUD

    bool    valid;
    bool    on_screen;
} EnergyTrend;

/// Compute the energy trend vector.
///
/// @param et       [in/out] Energy trend state (inputs populated)
/// @param focal_px Focal length (pixels)
/// @param screen_w Screen width
/// @param screen_h Screen height
/// @param ref_x    Reference X on HUD
/// @param ref_y    Reference Y on HUD
void energy_compute(EnergyTrend* et,
                    FLOAT64      focal_px,
                    int          screen_w,
                    int          screen_h,
                    FLOAT64      ref_x,
                    FLOAT64      ref_y);

// ============================================================================
//  3.  Flare Anticipation Bracket
// ============================================================================

/// A bracket symbol that appears to indicate the optimal flare initiation
/// point (typically 20-30 ft RA depending on sink rate).
typedef struct FlareBracket {
    // --- Inputs ---
    FLOAT64 radio_altitude_m;      // radio altitude (m)
    FLOAT64 vertical_speed_ms;     // vertical speed (m/s, + = up)
    FLOAT64 groundspeed_ms;        // ground speed (m/s)

    // --- Computed ---
    FLOAT64 flare_initiate_alt_m;  // recommended flare initiation altitude (m)
    FLOAT64 flare_altitude_error;  // current altitude - initiate altitude (m)
    FLOAT64 bracket_visibility;    // 0..1, fade in/out
    Vec2    screen_pos;            // bracket screen position
    FLOAT64 bracket_size_px;       // size of bracket

    bool    should_draw;           // true when bracket should be visible
    bool    valid;
} FlareBracket;

/// Compute the flare anticipation bracket.
///
/// @param fb       [in/out] Flare bracket state
/// @param focal_px Focal length (pixels)
/// @param screen_w Screen width
/// @param screen_h Screen height
/// @param ref_y    Reference Y position (e.g. horizon Y or TD point Y)
void flare_bracket_compute(FlareBracket* fb,
                           FLOAT64       focal_px,
                           int           screen_w,
                           int           screen_h,
                           FLOAT64       ref_y);

// ============================================================================
//  4.  Touchdown Predictor
// ============================================================================

/// Predicts where the aircraft will touch down based on current
/// flight path and energy state.
typedef struct TDPredictor {
    // --- Inputs ---
    FLOAT64 groundspeed_ms;        // ground speed (m/s)
    FLOAT64 vertical_speed_ms;     // vertical speed (m/s)
    FLOAT64 radio_altitude_m;      // radio altitude (m)
    FLOAT64 glidepath_deg;         // current glidepath angle (deg)
    FLOAT64 runway_heading_deg;    // runway heading (deg)
    FLOAT64 lat;                   // current latitude (deg)
    FLOAT64 lon;                   // current longitude (deg)

    // --- Computed ---
    FLOAT64 predicted_range_m;     // predicted distance to touchdown (m)
    FLOAT64 time_to_touchdown_s;   // predicted time to touchdown (s)
    Vec2    screen_pos;            // predicted TD point on HUD
    FLOAT64 predictor_size_px;     // size of predictor symbol
    FLOAT64 confidence;            // prediction confidence (0..1)

    bool    valid;
    bool    on_screen;
} TDPredictor;

/// Compute the touchdown predictor.
///
/// @param td       [in/out] Touchdown predictor state
/// @param ac_ref   Aircraft reference position (lon, alt, lat)
/// @param b2w      Body-to-world rotation matrix
/// @param eye_offset HUD eye offset
/// @param focal_px Focal length (pixels)
/// @param screen_w Screen width
/// @param screen_h Screen height
void td_predictor_compute(TDPredictor*    td,
                          Vec3            ac_ref,
                          const Mat4*     b2w,
                          Vec3            eye_offset,
                          FLOAT64         focal_px,
                          int             screen_w,
                          int             screen_h);

// ============================================================================
//  5.  Velocity Trend Cue
// ============================================================================

/// Shows the trend of airspeed changes as a small chevron or arrow.
typedef struct VelocityTrend {
    // --- Inputs ---
    FLOAT64 indicated_airspeed_ms; // current IAS (m/s)
    FLOAT64 acceleration_ms2;      // longitudinal acceleration (m/s²)
    FLOAT64 target_speed_ms;       // reference/target speed (m/s)

    // --- Computed ---
    FLOAT64 trend_direction;       // +1 = accelerating, -1 = decelerating, 0 = steady
    FLOAT64 trend_magnitude_dots;  // trend magnitude in "dots"
    Vec2    screen_pos;            // screen position

    bool    valid;
    bool    on_screen;
} VelocityTrend;

/// Compute the velocity trend cue.
///
/// @param vt       [in/out] Velocity trend state (inputs populated)
/// @param focal_px Focal length (pixels)
/// @param screen_w Screen width
/// @param screen_h Screen height
/// @param ref_x    Reference X on HUD
/// @param ref_y    Reference Y on HUD
void velocity_trend_compute(VelocityTrend* vt,
                            FLOAT64        focal_px,
                            int            screen_w,
                            int            screen_h,
                            FLOAT64        ref_x,
                            FLOAT64        ref_y);

// ============================================================================
//  6.  Debug logging
// ============================================================================

void accel_debug_log(const AccelCaret* ac);
void energy_debug_log(const EnergyTrend* et);
void flare_bracket_debug_log(const FlareBracket* fb);
void td_predictor_debug_log(const TDPredictor* td);
void velocity_trend_debug_log(const VelocityTrend* vt);

#endif // C_HUD_ADVANCED_SYMBOLOGY_H
