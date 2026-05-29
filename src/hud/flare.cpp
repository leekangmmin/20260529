// ============================================================================
//  Conformal HUD – Boeing-Style Flare Guidance System Implementation
//  MSFS 2024  ·  C++17  ·  WASM
//
//  v2.3.0 — Profile-aware flare cue tuning.  flare_project_cue() now
//  accepts aircraft-specific parameters (flare_constant, max_rise_px,
//  min/max cue sizes) from the active HUD profile.
//
//  v2.3.1 — profile-aware flare physics.  flare_compute() now reads
//  FlareState::flare_constant_override and uses the per-aircraft value
//  when it is set (> 0.0), falling back to the internal #define otherwise.
//
//  Implements the Boeing HGS-style flare director.
//  The flare cue rises from the touchdown aim point as the aircraft
//  descends through 80 ft RA, becoming fully active below 50 ft.
//
//  Flare command model:
//    h_dot_command = -k * sqrt(h - h_td)
//  where k = sqrt(2 * g * flare_constant)
//  This produces a flare path that exponentially decays the sink rate
//  as the aircraft approaches the runway.
// ============================================================================

#include "../../include/hud/flare.h"
#include "../../include/projection.h"

// ============================================================================
//  1.  Constants
// ============================================================================

#define FLARE_G 9.80665

#define FLARE_CONSTANT 0.10
#define FLARE_ACTIVATE_ALT_M  24.384
#define FLARE_FULLY_ACTIVE_M  15.24
#define FLARE_TD_HEIGHT_M  0.0
#define FLARE_MIN_VS_MPS  0.5

// ============================================================================
//  2.  Flare computation
// ============================================================================

bool flare_compute(FlareState* flare, FLOAT64 dt_s) {
    if (flare == 0) {
        return false;
    }

    const FLOAT64 ra     = proj_fmax(flare->radio_altitude_m, 0.0);
    const FLOAT64 vs     = flare->vertical_speed_ms;
    const FLOAT64 gs     = proj_fmax(flare->groundspeed_ms, 0.1);
    const FLOAT64 gs_dev = flare->gs_deviation_deg;

    const bool should_activate = flare_should_activate(ra);
    const bool should_full     = flare_fully_active_check(ra);

    if (!flare->flare_active && should_activate && vs < -FLARE_MIN_VS_MPS) {
        flare->flare_active = true;
        flare->flare_engagement_alt = ra;
        flare->flare_frame_count = 0;
        flare->flare_complete = false;
    }

    if (flare->flare_active && ra <= 0.5) {
        flare->flare_complete = true;
    }

    if (flare->flare_active && ra > 30.48) {
        flare->flare_active = false;
        flare->flare_frame_count = 0;
        flare->flare_complete = false;
    }

    flare->flare_fully_active = flare->flare_active && should_full;

    if (!flare->flare_active) {
        flare->flare_cue_vs = 0.0;
        flare->flare_cue_error = 0.0;
        flare->flare_cue_rise = 0.0;
        flare->flare_anticipation = 0.0;
        flare->touchdown_vs = 0.0;
        flare->touchdown_distance_m = 0.0;
        flare->time_to_touchdown_s = 0.0;
        flare->valid = true;
        return true;
    }

    ++flare->flare_frame_count;

    const FLOAT64 h_above_td = proj_fmax(ra - FLARE_TD_HEIGHT_M, 0.1);
    const FLOAT64 fc = (flare->flare_constant_override > 0.0)
        ? flare->flare_constant_override
        : FLARE_CONSTANT;
    const FLOAT64 k = proj_sqrt(2.0 * FLARE_G * fc);
    const FLOAT64 raw_command = -k * proj_sqrt(h_above_td);

    flare->debug_raw_command = raw_command;
    FLOAT64 commanded_vs = proj_clamp(raw_command, -10.0, 0.0);

    const FLOAT64 anticipation = proj_fmin(1.0,
        (FLOAT64)flare->flare_frame_count * dt_s / 1.5);
    flare->flare_anticipation = anticipation;
    commanded_vs *= anticipation;

    commanded_vs -= gs_dev * 0.2;

    flare->flare_cue_vs = commanded_vs;

    const FLOAT64 error = commanded_vs - vs;
    flare->flare_cue_error = error;

    const FLOAT64 alt_range = flare->flare_engagement_alt - FLARE_TD_HEIGHT_M;
    if (alt_range > 0.1) {
        const FLOAT64 alt_used = flare->flare_engagement_alt - ra;
        flare->flare_cue_rise = proj_clamp(alt_used / alt_range, 0.0, 1.0);
    } else {
        flare->flare_cue_rise = 1.0;
    }

    if (vs < 0.0) {
        flare->time_to_touchdown_s = ra / (-vs);
        flare->touchdown_distance_m = gs * flare->time_to_touchdown_s;
        const FLOAT64 flare_time = flare->time_to_touchdown_s;
        if (flare_time > 0.1) {
            flare->touchdown_vs = vs + (commanded_vs - vs) * 0.5;
        } else {
            flare->touchdown_vs = vs;
        }
    } else {
        flare->time_to_touchdown_s = 999.0;
        flare->touchdown_distance_m = 0.0;
        flare->touchdown_vs = vs;
    }

    flare->debug_flare_constant = fc;
    flare->debug_filtered_error = error;

    flare->valid = true;
    return true;
}

// ============================================================================
//  3.  Flare cue projection  (v2.3.0: profile-aware parameters)
// ============================================================================

void flare_project_cue(const FlareState* flare,
                        FLOAT64           focal_px,
                        int               screen_w,
                        int               screen_h,
                        Vec2              ref_point,
                        FlareCue*         cue,
                        FLOAT64           flare_constant,
                        FLOAT64           max_rise_px,
                        FLOAT64           min_cue_size,
                        FLOAT64           max_cue_size) {
    (void)focal_px;
    /* flare_constant parameter reserved for future cue-size scaling;
       actual flare law uses FlareState.flare_constant_override */

    if (cue == 0) {
        return;
    }

    cue->visible = false;
    cue->on_screen = false;
    cue->screen_pos.x = -9999.0;
    cue->screen_pos.y = -9999.0;
    cue->vertical_offset_px = 0.0;
    cue->size_px = 0.0;
    cue->alpha = 0.0;

    if (flare == 0 || !flare->valid || !flare->flare_active) {
        return;
    }

    const FLOAT64 rise_fraction = flare->flare_cue_rise;

    const FLOAT64 rise_px = rise_fraction * max_rise_px;

    Vec2 pos;
    pos.x = ref_point.x;
    pos.y = ref_point.y - rise_px;

    pos.x = proj_clamp(pos.x, -500.0, (FLOAT64)(screen_w + 500));
    pos.y = proj_clamp(pos.y, -500.0, (FLOAT64)(screen_h + 500));

    cue->screen_pos = pos;
    cue->vertical_offset_px = rise_px;
    cue->on_screen = (pos.x >= 0 && pos.x <= (FLOAT64)screen_w &&
                      pos.y >= 0 && pos.y <= (FLOAT64)screen_h);

    const FLOAT64 max_size = max_cue_size > 0.0 ? max_cue_size : 28.0;
    const FLOAT64 min_size = min_cue_size > 0.0 ? min_cue_size : 12.0;
    cue->size_px = max_size - (max_size - min_size) * rise_fraction;

    const FLOAT64 fade_fraction = proj_fmin(1.0,
        (FLOAT64)flare->flare_frame_count / 30.0);
    cue->alpha = 0.3 + 0.7 * fade_fraction;
    cue->alpha *= (flare->flare_fully_active ? 1.0 : 0.6);

    const FLOAT64 error_boost = proj_fmin(1.0,
        proj_fabs(flare->flare_cue_error) * 0.15);
    cue->alpha = proj_fmin(1.0, cue->alpha + error_boost * 0.3);

    cue->visible = true;
}

// ============================================================================
//  4.  Touchdown zone projection
// ============================================================================

void flare_project_touchdown(const FlareState* flare,
                              FLOAT64           focal_px,
                              int               screen_w,
                              int               screen_h,
                              Vec2              ref_point,
                              TouchdownZone*    zone) {
    (void)focal_px;
    (void)screen_w;
    (void)screen_h;

    if (zone == 0) {
        return;
    }

    zone->visible = false;
    zone->aim_point = ref_point;
    zone->aim_point_size_px = 0.0;
    zone->aiming_point_alpha = 0.0;

    if (flare == 0 || !flare->valid) {
        return;
    }

    zone->aim_point = ref_point;

    if (flare->flare_active) {
        zone->aim_point_size_px = 10.0 + 8.0 * flare->flare_cue_rise;
        zone->aiming_point_alpha = 0.6 + 0.4 * flare->flare_cue_rise;
    } else {
        zone->aim_point_size_px = 8.0;
        zone->aiming_point_alpha = 0.4;
    }

    zone->visible = true;
}

// ============================================================================
//  5.  Debug logging
// ============================================================================

void flare_debug_log(const FlareState* flare) {
    if (flare == 0) {
        MSFS_Log("[C_HUD_FLARE] FlareState: NULL");
        return;
    }

    if (!flare->valid) {
        MSFS_Log("[C_HUD_FLARE] FlareState: INVALID");
        return;
    }

    MSFS_Log("[C_HUD_FLARE] RA=%.2fm  VS=%.2fm/s  GS=%.1fm/s  "
             "ACTIVE=%d FULL=%d CMD_VS=%.2f ERR=%.2f RISE=%.2f "
             "ANT=%.2f TTD=%.1fs TD_VS=%.1f FC=%d",
             flare->radio_altitude_m, flare->vertical_speed_ms,
             flare->groundspeed_ms,
             (int)flare->flare_active, (int)flare->flare_fully_active,
             flare->flare_cue_vs, flare->flare_cue_error,
             flare->flare_cue_rise,
             flare->flare_anticipation,
             flare->time_to_touchdown_s,
             flare->touchdown_vs,
             flare->flare_frame_count);
}
