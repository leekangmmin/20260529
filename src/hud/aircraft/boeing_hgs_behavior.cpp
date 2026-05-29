// ============================================================================
//  Conformal HUD – Boeing HGS Behavior Implementation
//  MSFS 2024  ·  C++17  ·  WASM
//
//  PHASE 1 — UNIFIED AIRCRAFT BEHAVIOR ARCHITECTURE
//
//  Concrete IHudAircraftBehavior for Boeing-style HGS aircraft.
//  Encapsulates the legacy pipeline logic that was previously
//  inline in main.cpp.
// ============================================================================

#include "hud/aircraft/boeing_hgs_behavior.h"
#include "hud/runway_projection.h"
#include "hud/guidance.h"
#include "hud/collimation.h"
#include "hud/advanced_symbology.h"
#include "hud/aircraft_profiles.h"

// ============================================================================
//  Construction
// ============================================================================

BoeingHGSBehavior::BoeingHGSBehavior()
    : m_stab_init(false)
    , m_visual_init(false)
{
    // Stabilisation is initialised lazily on first compute
    // Visual response is initialised lazily on first compute
}

// ============================================================================
//  FPV
// ============================================================================

void BoeingHGSBehavior::compute_fpv(
    const HudBehaviorContext& ctx,
    const HUDProfile*         profile,
    const Mat4*               b2w,
    Vec3                      eye_offset,
    FLOAT64                   focal_px,
    FPVState*                 fpv)
{
    if (fpv == 0) return;

    __builtin_memset(fpv, 0, sizeof(*fpv));
    fpv->groundspeed_ms    = ctx.ac_groundspeed_ms;
    fpv->vertical_speed_ms = ctx.ac_vertical_speed_ms;
    fpv->heading_deg_true  = ctx.ac_hdg_true;
    fpv->track_deg_true    = ctx.ac_track_deg_true;

    fpv_compute(fpv);

    // Aircraft reference (lon, alt, lat)
    const Vec3 ac_ref = proj_vec3_make(ctx.ac_lon, ctx.ac_alt_m, ctx.ac_lat);

    fpv_project_to_hud(fpv, ac_ref,
                        ctx.ac_hdg_true, ctx.ac_pitch_deg,
                        ctx.ac_bank_deg, b2w, eye_offset,
                        focal_px, ctx.screen_w, ctx.screen_h,
                        profile->fpv_align_offset_x,
                        profile->fpv_align_offset_y);

    // Apply stabilisation to FPV position (Boeing-specific tuning)
    if (fpv->valid && fpv->on_screen) {
        if (!m_stab_init) {
            hud_stab_init(&m_stab);
            m_stab_init = true;
        }
        hud_stab_tune_for_turbulence(&m_stab, ctx.dt_s,
                                      profile->turbulence_stab_gain,
                                      profile->motion_confidence_weight);
        const Vec2 raw_fpv = fpv->screen_pos;
        fpv->screen_pos = hud_stab_fpv(&m_stab, raw_fpv, ctx.dt_s);
    }
}

// ============================================================================
//  Flare
// ============================================================================

void BoeingHGSBehavior::compute_flare(
    const HudBehaviorContext& ctx,
    const HUDProfile*         profile,
    Vec2                      td_ref,
    bool                      guidance_valid,
    FLOAT64                   gs_error_deg,
    FlareState*               flare,
    FlareCue*                 flare_cue,
    TouchdownZone*            td_zone)
{
    if (flare == 0 || flare_cue == 0 || td_zone == 0) return;

    __builtin_memset(flare, 0, sizeof(*flare));
    flare->radio_altitude_m  = ctx.ac_radio_alt_m;
    flare->vertical_speed_ms = ctx.ac_vertical_speed_ms;
    flare->groundspeed_ms    = ctx.ac_groundspeed_ms;
    flare->gs_deviation_deg  = gs_error_deg;

    // Per-aircraft flare constant override from profile
    // When set (> 0.0), flare_compute() uses this instead of the default 0.10
    flare->flare_constant_override = (profile->flare_constant > 0.0)
        ? profile->flare_constant : 0.0;

    flare_compute(flare, ctx.dt_s);

    // Use profile-tuned Boeing flare parameters
    const FLOAT64 focal_px = (profile->focal_length_px > 0)
                              ? profile->focal_length_px : 520.0;

    const FLOAT64 flare_constant = (profile->flare_constant > 0.0)
        ? profile->flare_constant : 0.10;
    const FLOAT64 max_rise_px = (profile->flare_max_rise_px > 0.0)
        ? profile->flare_max_rise_px : 80.0;
    const FLOAT64 min_cue_size = profile->flare_cue_min_size;
    const FLOAT64 max_cue_size = profile->flare_cue_max_size;

    flare_project_cue(flare, focal_px, ctx.screen_w, ctx.screen_h,
                       td_ref, flare_cue,
                       flare_constant, max_rise_px,
                       min_cue_size, max_cue_size);

    flare_project_touchdown(flare, focal_px, ctx.screen_w, ctx.screen_h,
                             td_ref, td_zone);
}

// ============================================================================
//  Rollout
// ============================================================================

void BoeingHGSBehavior::compute_rollout(
    const HudBehaviorContext& ctx,
    FLOAT64                   runway_heading_deg,
    FLOAT64                   lateral_deviation_m,
    RolloutState*             rs,
    RolloutCue*               cue)
{
    if (rs == 0 || cue == 0) return;

    rollout_init(rs);

    rs->on_ground           = ctx.ac_on_ground;
    rs->groundspeed_ms      = ctx.ac_groundspeed_ms;
    rs->radio_altitude_m    = ctx.ac_radio_alt_m;
    rs->heading_deg         = ctx.ac_hdg_true;
    rs->track_deg           = ctx.ac_track_deg_true;
    rs->runway_heading_deg  = runway_heading_deg;
    rs->lateral_deviation_m = lateral_deviation_m;

    rollout_compute(rs, ctx.dt_s);

    // Project cue (use centre of screen as fallback)
    const FLOAT64 cx = (FLOAT64)(ctx.screen_w / 2);
    const FLOAT64 cy = (FLOAT64)(ctx.screen_h / 2);
    rollout_project_cue(rs, 520.0, ctx.screen_w, ctx.screen_h,
                         cx, cy, cue);
}

// ============================================================================
//  CAT III  (Boeing — standard confidence-based rendering)
// ============================================================================

void BoeingHGSBehavior::compute_cat3(
    const HudBehaviorContext& ctx,
    ConfidenceState*          cs,
    ConfidenceRenderParams*   render)
{
    if (cs == 0 || render == 0) return;

    confidence_init(cs);

    const bool loc_captured = (ctx.ils_loc_dots < 0.5);
    const bool gs_captured  = (ctx.ils_gs_dots  < 0.5);
    const bool cat3_mode    = (ctx.ac_radio_alt_m < 200.0);

    confidence_compute(cs, ctx.dt_s,
                        ctx.ils_loc_dots, ctx.ils_gs_dots,
                        loc_captured, gs_captured,
                        (ctx.ac_radio_alt_m > 0.0),
                        ctx.ac_groundspeed_ms,
                        cat3_mode);

    // Copy render params from confidence state
    *render = cs->render;
}

// ============================================================================
//  Declutter  (Boeing HGS standard priority scheme)
// ============================================================================

void BoeingHGSBehavior::compute_declutter(
    const HudBehaviorContext& ctx,
    HudFlightPhase            phase,
    DeclutterState*           ds)
{
    if (ds == 0) return;

    declutter_init(ds);

    // Map unified phase to declutter FlightPhase
    FlightPhase declutter_phase = PHASE_CRUISE;
    switch (phase) {
        case HudFlightPhase::CRUISE:   declutter_phase = PHASE_CRUISE;   break;
        case HudFlightPhase::APPROACH: declutter_phase = PHASE_APPROACH; break;
        case HudFlightPhase::FLARE:    declutter_phase = PHASE_FLARE;    break;
        case HudFlightPhase::ROLLOUT:  declutter_phase = PHASE_ROLLOUT;  break;
        case HudFlightPhase::TAXI:     declutter_phase = PHASE_TAXI;     break;
    }

    const bool low_vis = (ctx.visibility_m < 3000.0);
    declutter_compute(ds, declutter_phase, low_vis, ctx.visibility_m);
}

// ============================================================================
//  Optics  (Boeing HGS optical realism)
// ============================================================================

void BoeingHGSBehavior::compute_optics(
    const HudBehaviorContext& ctx,
    const HUDProfile*         profile,
    VisualResponseState*      vs,
    VisualRenderParams*       render)
{
    if (vs == 0 || render == 0) return;

    if (!m_visual_init) {
        visual_response_init(vs);
        m_visual_init = true;
    }

    const FLOAT64 ambient_lux = ctx.ambient_luminance;
    const bool runway_light_boom = (ctx.ac_radio_alt_m < 60.0);

    visual_response_compute(vs, ctx.dt_s,
                             ambient_lux,
                             0.0,  // rain_intensity (would come from weather)
                             runway_light_boom);

    // Fill output render params
    render->brightness             = vs->current_brightness;
    render->contrast               = vs->contrast_gain;
    render->phosphor_persistence_ms = vs->phosphor_current_ms;
    render->bloom_intensity        = vs->bloom_amount;
    render->glare_amount           = vs->rain_glare;
    render->edge_fade_night_boost  = 1.0 - vs->dark_adaptation;
    render->active                 = vs->active;
}
