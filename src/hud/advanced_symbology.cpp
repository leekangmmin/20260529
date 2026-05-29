// ============================================================================
//  Conformal HUD – Advanced Boeing HGS-Style Symbology Implementation
//  MSFS 2024  ·  C++17  ·  WASM
//
//  Implements acceleration caret, energy trend vector, flare anticipation
//  bracket, touchdown predictor, and velocity trend cue.
// ============================================================================

#include "../../include/hud/advanced_symbology.h"
#include "../../include/projection.h"

// ============================================================================
//  1.  Acceleration Caret
// ============================================================================

void accel_compute(AccelCaret* ac,
                   FLOAT64     focal_px,
                   int         screen_w,
                   int         screen_h,
                   FLOAT64     ref_x,
                   FLOAT64     ref_y) {
    if (ac == 0) {
        return;
    }

    ac->valid = false;
    ac->on_screen = false;

    const FLOAT64 tas = proj_fmax(ac->true_airspeed_ms, 1.0);
    const FLOAT64 accel = ac->acceleration_ms2;

    // Compute speed error (for display reference)
    ac->speed_error_ms = ac->indicated_airspeed_ms - ac->target_speed_ms;

    // Convert acceleration to "dots" for display
    // 1 dot ≈ 0.05 g ≈ 0.49 m/s²
    const FLOAT64 accel_dots = accel / 0.49;
    ac->accel_dots = proj_clamp(accel_dots, -3.0, 3.0);

    // Caret position: horizontal offset from the reference (speed tape)
    // Positive acceleration → caret moves up/right from reference
    const FLOAT64 scale = 20.0;  // pixels per dot
    const FLOAT64 offset_x = ac->accel_dots * scale;

    ac->screen_pos.x = ref_x + offset_x;
    ac->screen_pos.y = ref_y;

    // Check if on screen
    ac->on_screen = (ac->screen_pos.x >= -200.0 &&
                     ac->screen_pos.x <= (FLOAT64)(screen_w + 200) &&
                     ac->screen_pos.y >= -200.0 &&
                     ac->screen_pos.y <= (FLOAT64)(screen_h + 200));

    ac->valid = true;
}

// ============================================================================
//  2.  Energy Trend Vector
// ============================================================================

void energy_compute(EnergyTrend* et,
                    FLOAT64      focal_px,
                    int          screen_w,
                    int          screen_h,
                    FLOAT64      ref_x,
                    FLOAT64      ref_y) {
    if (et == 0) {
        return;
    }

    et->valid = false;
    et->on_screen = false;

    const FLOAT64 V = proj_fmax(et->true_airspeed_ms, 1.0);
    const FLOAT64 V_dot = et->acceleration_ms2;
    const FLOAT64 h_dot = et->vertical_speed_ms;
    const FLOAT64 g = 9.80665;

    // Specific energy rate: d(E/m)/dt = V * V_dot + g * h_dot
    // (kinetic + potential energy rate per unit mass)
    const FLOAT64 specific_energy_rate = V * V_dot + g * h_dot;
    et->specific_energy_rate = specific_energy_rate;

    // Normalise for display: 1 dot ≈ 50 (m²/s³) energy rate
    et->energy_rate_dots = specific_energy_rate / 50.0;
    et->energy_rate_dots = proj_clamp(et->energy_rate_dots, -3.0, 3.0);

    // Trend angle: direction of the energy vector
    // Positive = energy increasing (climbing or accelerating)
    const FLOAT64 vector_length = proj_fabs(et->energy_rate_dots);
    et->vector_length_px = vector_length * 15.0;  // 15 px per dot

    // Vertical component from energy rate
    // Upward trend (positive energy) → vector points up
    const FLOAT64 angle_rad = (et->energy_rate_dots >= 0)
        ? -PROJ_DEG2RAD(90.0)   // up
        : PROJ_DEG2RAD(90.0);   // down
    et->trend_angle_deg = PROJ_RAD2DEG(angle_rad);

    // Screen position: vertically above/below the reference
    et->screen_pos.x = ref_x;
    et->screen_pos.y = ref_y - et->energy_rate_dots * 12.0;

    et->on_screen = (et->screen_pos.y >= -200.0 &&
                     et->screen_pos.y <= (FLOAT64)(screen_h + 200));

    et->valid = true;
}

// ============================================================================
//  3.  Flare Anticipation Bracket
// ============================================================================

void flare_bracket_compute(FlareBracket* fb,
                           FLOAT64       focal_px,
                           int           screen_w,
                           int           screen_h,
                           FLOAT64       ref_y) {
    if (fb == 0) {
        return;
    }

    fb->valid = false;
    fb->should_draw = false;

    const FLOAT64 ra = proj_fmax(fb->radio_altitude_m, 0.0);
    const FLOAT64 vs = fb->vertical_speed_ms;  // + = up
    const FLOAT64 gs = proj_fmax(fb->groundspeed_ms, 1.0);

    // Compute recommended flare initiation altitude
    // Boeing HGS uses: h_flare = (V_gs² / (2 * g)) * flare_constant
    // Simplified model based on sink rate and groundspeed
    const FLOAT64 sink_rate = proj_fmax(-vs, 0.1); // positive = descending
    const FLOAT64 flare_alt = 6.0 + sink_rate * 3.0 + gs * 0.05;
    fb->flare_initiate_alt_m = proj_clamp(flare_alt, 4.0, 25.0);

    // Compute error: how far from the flare initiation point
    fb->flare_altitude_error = ra - fb->flare_initiate_alt_m;

    // Bracket visibility: most visible when near the initiation altitude
    // Smooth ramp from ±5 ft around initiation
    const FLOAT64 error_ft = fb->flare_altitude_error / 0.3048;
    if (error_ft > 10.0) {
        fb->bracket_visibility = 0.0;  // too high
    } else if (error_ft < -5.0) {
        fb->bracket_visibility = 0.0;  // past initiation
    } else {
        // Peak at initiation altitude
        fb->bracket_visibility = 1.0 - proj_fabs(error_ft) / 10.0;
        fb->bracket_visibility = proj_clamp(fb->bracket_visibility, 0.0, 1.0);
        // Square for smoother fade
        fb->bracket_visibility = fb->bracket_visibility * fb->bracket_visibility;
    }

    // Position: centred horizontally, at the reference Y
    const FLOAT64 screen_cy = (FLOAT64)(screen_h / 2);
    fb->screen_pos.x = (FLOAT64)(screen_w / 2);
    fb->screen_pos.y = ref_y;

    // Bracket size scales with groundspeed (faster = larger bracket)
    fb->bracket_size_px = 20.0 + gs * 0.15;
    if (fb->bracket_size_px > 50.0) fb->bracket_size_px = 50.0;

    fb->should_draw = (fb->bracket_visibility > 0.01 &&
                       ra < 40.0 && ra > 1.0 && vs < 0.0);
    fb->valid = true;
}

// ============================================================================
//  4.  Touchdown Predictor
// ============================================================================

void td_predictor_compute(TDPredictor*    td,
                          Vec3            ac_ref,
                          const Mat4*     b2w,
                          Vec3            eye_offset,
                          FLOAT64         focal_px,
                          int             screen_w,
                          int             screen_h) {
    if (td == 0) {
        return;
    }

    td->valid = false;
    td->on_screen = false;

    const FLOAT64 gs = proj_fmax(td->groundspeed_ms, 0.1);
    const FLOAT64 vs = td->vertical_speed_ms;
    const FLOAT64 ra = proj_fmax(td->radio_altitude_m, 0.0);

    if (vs >= 0.0) {
        // Not descending, predictor not valid
        return;
    }

    // Compute predicted range to touchdown
    const FLOAT64 sink_rate = -vs;  // positive sink rate
    if (sink_rate < 0.1) {
        return;  // insignificant sink rate
    }

    const FLOAT64 time_to_td = ra / sink_rate;
    td->predicted_range_m = gs * time_to_td;
    td->time_to_touchdown_s = time_to_td;

    // Compute confidence: higher when closer to ground
    td->confidence = proj_clamp(1.0 - ra / 300.0, 0.1, 0.95);

    // Project predicted touchdown point into HUD space
    // Use the current flight path to estimate where the aircraft
    // will intersect the runway plane
    const FLOAT64 glidepath_rad = proj_atan2(vs, gs);
    const FLOAT64 forward_dist = td->predicted_range_m;

    // Compute a world-space point at the predicted touchdown location
    // along the current track
    const FLOAT64 hdg_rad = PROJ_DEG2RAD(td->runway_heading_deg);
    const FLOAT64 cos_lat = proj_cos(PROJ_DEG2RAD(ac_ref.z));

    const FLOAT64 dlat = PROJ_RAD2DEG(forward_dist * proj_cos(hdg_rad) /
                                       PROJ_EARTH_RADIUS_M);
    const FLOAT64 dlon = PROJ_RAD2DEG(forward_dist * proj_sin(hdg_rad) /
                                       (PROJ_EARTH_RADIUS_M * cos_lat));

    Vec3 td_world;
    td_world.x = ac_ref.x + dlon;
    td_world.y = 0.0;  // touchdown at ground level
    td_world.z = ac_ref.z + dlat;

    // Project to HUD
    bool behind = false;
    Vec2 screen = proj_vec3_zero();
    proj_world_to_hud(td_world, ac_ref, b2w, eye_offset,
                       focal_px, screen_w, screen_h,
                       &screen, &behind);

    if (!behind) {
        td->screen_pos = screen;
        td->on_screen = (screen.x >= -500.0 &&
                         screen.x <= (FLOAT64)(screen_w + 500) &&
                         screen.y >= -500.0 &&
                         screen.y <= (FLOAT64)(screen_h + 500));
    }

    td->predictor_size_px = 8.0 + td->confidence * 6.0;
    td->valid = true;
}

// ============================================================================
//  5.  Velocity Trend Cue
// ============================================================================

void velocity_trend_compute(VelocityTrend* vt,
                            FLOAT64        focal_px,
                            int            screen_w,
                            int            screen_h,
                            FLOAT64        ref_x,
                            FLOAT64        ref_y) {
    if (vt == 0) {
        return;
    }

    vt->valid = false;
    vt->on_screen = false;

    const FLOAT64 accel = vt->acceleration_ms2;

    // Determine direction and magnitude
    if (proj_fabs(accel) < 0.1) {
        vt->trend_direction = 0.0;       // steady
        vt->trend_magnitude_dots = 0.0;
    } else {
        vt->trend_direction = (accel > 0.0) ? 1.0 : -1.0;
        // Magnitude in dots: 1 dot ≈ 0.5 m/s²
        vt->trend_magnitude_dots = proj_fabs(accel) / 0.5;
        if (vt->trend_magnitude_dots > 3.0) vt->trend_magnitude_dots = 3.0;
    }

    // Position: to the right of the speed indicator
    vt->screen_pos.x = ref_x + 30.0;
    vt->screen_pos.y = ref_y;

    vt->on_screen = (vt->screen_pos.x >= -200.0 &&
                     vt->screen_pos.x <= (FLOAT64)(screen_w + 200) &&
                     vt->screen_pos.y >= -200.0 &&
                     vt->screen_pos.y <= (FLOAT64)(screen_h + 200));

    vt->valid = true;
}

// ============================================================================
//  6.  Debug logging
// ============================================================================

void accel_debug_log(const AccelCaret* ac) {
    if (ac == 0) {
        MSFS_Log("[C_HUD_ACCEL] AccelCaret: NULL");
        return;
    }
    MSFS_Log("[C_HUD_ACCEL] IAS=%.1f TGT=%.1f ERR=%.2f "
             "ACCEL=%.2f DOTS=%.1f SCRN=(%.0f,%.0f) VAL=%d",
             ac->indicated_airspeed_ms, ac->target_speed_ms,
             ac->speed_error_ms, ac->acceleration_ms2,
             ac->accel_dots, ac->screen_pos.x, ac->screen_pos.y,
             (int)ac->valid);
}

void energy_debug_log(const EnergyTrend* et) {
    if (et == 0) {
        MSFS_Log("[C_HUD_ENERGY] EnergyTrend: NULL");
        return;
    }
    MSFS_Log("[C_HUD_ENERGY] TAS=%.1f VS=%.2f ACC=%.2f "
             "E_DOT=%.1f DOTS=%.1f LEN=%.0f SCRN=(%.0f,%.0f) VAL=%d",
             et->true_airspeed_ms, et->vertical_speed_ms,
             et->acceleration_ms2,
             et->specific_energy_rate, et->energy_rate_dots,
             et->vector_length_px, et->screen_pos.x, et->screen_pos.y,
             (int)et->valid);
}

void flare_bracket_debug_log(const FlareBracket* fb) {
    if (fb == 0) {
        MSFS_Log("[C_HUD_FLARE_BR] FlareBracket: NULL");
        return;
    }
    MSFS_Log("[C_HUD_FLARE_BR] RA=%.1f VS=%.1f GS=%.1f "
             "FLARE_ALT=%.1f ERR=%.2f VIS=%.3f DRAW=%d",
             fb->radio_altitude_m, fb->vertical_speed_ms,
             fb->groundspeed_ms,
             fb->flare_initiate_alt_m, fb->flare_altitude_error,
             fb->bracket_visibility, (int)fb->should_draw);
}

void td_predictor_debug_log(const TDPredictor* td) {
    if (td == 0) {
        MSFS_Log("[C_HUD_TDPRED] TDPredictor: NULL");
        return;
    }
    MSFS_Log("[C_HUD_TDPRED] GS=%.1f VS=%.1f RA=%.1f "
             "RNG=%.0f TTD=%.1f CONF=%.2f SCRN=(%.0f,%.0f)",
             td->groundspeed_ms, td->vertical_speed_ms,
             td->radio_altitude_m,
             td->predicted_range_m, td->time_to_touchdown_s,
             td->confidence, td->screen_pos.x, td->screen_pos.y);
}

void velocity_trend_debug_log(const VelocityTrend* vt) {
    if (vt == 0) {
        MSFS_Log("[C_HUD_VTREND] VelocityTrend: NULL");
        return;
    }
    MSFS_Log("[C_HUD_VTREND] IAS=%.1f ACC=%.2f DIR=%.0f "
             "MAG=%.1f SCRN=(%.0f,%.0f) VAL=%d",
             vt->indicated_airspeed_ms, vt->acceleration_ms2,
             vt->trend_direction, vt->trend_magnitude_dots,
             vt->screen_pos.x, vt->screen_pos.y,
             (int)vt->valid);
}
