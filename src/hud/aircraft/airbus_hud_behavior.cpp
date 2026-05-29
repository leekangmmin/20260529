// ============================================================================
//  Conformal HUD – Airbus HUD Behavior Implementation
//  MSFS 2024  ·  C++17  ·  WASM
//
//  PHASE 1 — UNIFIED AIRCRAFT BEHAVIOR ARCHITECTURE
//
//  Concrete IHudAircraftBehavior for Airbus-style HUD aircraft.
//  Wraps the A350-specific modules (AirbusFPVFilter, A350FlareLaw,
//  A350RolloutAugmentation, A350CatIIIState, A350SymbologyStyle)
//  into a clean virtual-method interface.
// ============================================================================

#include "hud/aircraft/airbus_hud_behavior.h"
#include "hud/runway_projection.h"
#include "hud/guidance.h"
#include "hud/collimation.h"
#include "hud/advanced_symbology.h"
#include "hud/aircraft_profiles.h"

// ============================================================================
//  Construction
// ============================================================================

AirbusHUDBehavior::AirbusHUDBehavior()
    : m_fpv_init(false)
    , m_flare_init(false)
    , m_rollout_init(false)
    , m_cat3_init(false)
    , m_symbology_init(false)
{
    // Retrieve the default A350 profile
    const A350HUDProfile* def = a350_get_default_profile();
    if (def != 0) {
        m_a350_profile = *def;
    }
}

// ============================================================================
//  FPV  —  Airbus-style: heavily damped, predictive, turbulence-rejected
// ============================================================================

void AirbusHUDBehavior::compute_fpv(
    const HudBehaviorContext& ctx,
    const HUDProfile*         profile,
    const Mat4*               b2w,
    Vec3                      eye_offset,
    FLOAT64                   focal_px,
    FPVState*                 fpv)
{
    if (fpv == 0) return;

    // 1. Initialise Airbus FPV filter on first frame
    if (!m_fpv_init) {
        airbus_fpv_init(&m_airbus_fpv);
        // Apply A350 profile tuning
        airbus_fpv_configure(&m_airbus_fpv,
                              m_a350_profile.smoothing.fpv_ema_alpha_min,
                              m_a350_profile.smoothing.fpv_ema_alpha_max,
                              m_a350_profile.fpv_acceleration_prediction,
                              m_a350_profile.fpv_turbulence_rejection,
                              m_a350_profile.smoothing.fpv_intentional_latency_s);
        m_fpv_init = true;
    }

    // 2. Compute raw FPV using standard computation
    __builtin_memset(fpv, 0, sizeof(*fpv));
    fpv->groundspeed_ms    = ctx.ac_groundspeed_ms;
    fpv->vertical_speed_ms = ctx.ac_vertical_speed_ms;
    fpv->heading_deg_true  = ctx.ac_hdg_true;
    fpv->track_deg_true    = ctx.ac_track_deg_true;

    fpv_compute(fpv);

    // 3. Project raw FPV to screen
    const Vec3 ac_ref = proj_vec3_make(ctx.ac_lon, ctx.ac_alt_m, ctx.ac_lat);

    fpv_project_to_hud(fpv, ac_ref,
                        ctx.ac_hdg_true, ctx.ac_pitch_deg,
                        ctx.ac_bank_deg, b2w, eye_offset,
                        focal_px, ctx.screen_w, ctx.screen_h,
                        profile->fpv_align_offset_x,
                        profile->fpv_align_offset_y);

    // 4. Apply Airbus-specific filtering on screen position
    if (fpv->valid && fpv->on_screen) {
        // Set phase for phase-aware smoothing
        HudFlightPhase phase = HudFlightPhase::APPROACH;
        if (ctx.ac_radio_alt_m < 24.384) {
            phase = HudFlightPhase::FLARE;
        } else if (ctx.ac_on_ground) {
            phase = HudFlightPhase::ROLLOUT;
        } else if (ctx.ac_radio_alt_m < 600.0) {
            phase = HudFlightPhase::APPROACH;
        }
        airbus_fpv_set_phase(&m_airbus_fpv, static_cast<int>(phase));

        // Filter through Airbus FPV pipeline
        const Vec2 raw_pos = fpv->screen_pos;
        const Vec2 filtered = airbus_fpv_feed(&m_airbus_fpv, raw_pos, ctx.dt_s);

        // Use the predicted (filtered + prediction lead) output
        fpv->screen_pos = airbus_fpv_get_predicted(&m_airbus_fpv);
        fpv->on_screen  = true;
    }
}

// ============================================================================
//  Flare  —  Airbus-style: soft pitch transition, smooth sink-rate
// ============================================================================

void AirbusHUDBehavior::compute_flare(
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

    // 1. Initialise Airbus flare law on first frame
    if (!m_flare_init) {
        a350_flare_init(&m_a350_flare);
        m_a350_flare.activation_alt_ft      = m_a350_profile.flare_activation_alt_ft;
        m_a350_flare.soft_transition_alt_ft = m_a350_profile.flare_soft_transition_alt_ft;
        m_a350_flare.flare_guidance_confidence = m_a350_profile.flare_guidance_confidence;
        m_a350_flare.runway_stab_weight_setting = m_a350_profile.flare_runway_stab_weight;
        m_a350_flare.float_suppression_gain = m_a350_profile.flare_floating_suppression;
        m_flare_init = true;
    }

    // 2. Populate inputs
    m_a350_flare.radio_altitude_m  = ctx.ac_radio_alt_m;
    m_a350_flare.vertical_speed_ms = ctx.ac_vertical_speed_ms;
    m_a350_flare.groundspeed_ms    = ctx.ac_groundspeed_ms;
    m_a350_flare.pitch_deg         = ctx.ac_pitch_deg;
    m_a350_flare.gs_deviation_deg  = gs_error_deg;

    // 3. Compute Airbus flare law
    a350_flare_compute(&m_a350_flare, ctx.dt_s);

    // 4. Populate standard FlareState from A350 flare law for compatibility
    __builtin_memset(flare, 0, sizeof(*flare));
    flare->radio_altitude_m       = ctx.ac_radio_alt_m;
    flare->vertical_speed_ms      = ctx.ac_vertical_speed_ms;
    flare->groundspeed_ms         = ctx.ac_groundspeed_ms;
    flare->gs_deviation_deg       = gs_error_deg;

    // Map A350 phase to standard flare state
    if (m_a350_flare.phase == A350_FLARE_INACTIVE) {
        flare->flare_active       = false;
        flare->flare_fully_active = false;
    } else if (m_a350_flare.phase == A350_FLARE_PREFLARE) {
        flare->flare_active       = true;
        flare->flare_fully_active = false;
    } else {
        flare->flare_active       = true;
        flare->flare_fully_active = true;
    }

    flare->flare_cue_vs      = m_a350_flare.sink_rate_command_ms;
    flare->flare_cue_error   = m_a350_flare.sink_rate_error_ms;
    flare->flare_cue_rise    = m_a350_flare.flare_completion;
    flare->flare_engagement_alt = m_a350_flare.engagement_alt_m;
    flare->flare_frame_count = (int)(m_a350_flare.time_in_phase_s / 0.016);
    flare->flare_complete    = (m_a350_flare.phase == A350_FLARE_TOUCHDOWN);
    flare->valid             = true;

    // 5. Project flare cue (use standard projection with Airbus-derived params)
    const FLOAT64 focal_px = (profile->focal_length_px > 0)
                              ? profile->focal_length_px : 520.0;

    // Airbus uses softer flare cues — read from profile when available
    const FLOAT64 flare_constant = (profile->flare_constant > 0.0)
        ? profile->flare_constant : 0.08;
    const FLOAT64 max_rise_px = (profile->flare_max_rise_px > 0.0)
        ? profile->flare_max_rise_px : 60.0;
    const FLOAT64 min_cue_size = (profile->flare_cue_min_size > 0.0)
        ? profile->flare_cue_min_size : 8.0;
    const FLOAT64 max_cue_size = (profile->flare_cue_max_size > 0.0)
        ? profile->flare_cue_max_size : 40.0;

    flare_project_cue(flare, focal_px, ctx.screen_w, ctx.screen_h,
                       td_ref, flare_cue,
                       flare_constant, max_rise_px,
                       min_cue_size, max_cue_size);

    flare_project_touchdown(flare, focal_px, ctx.screen_w, ctx.screen_h,
                             td_ref, td_zone);
}

// ============================================================================
//  Rollout  —  Airbus-style: stable centerline, predictive nosewheel
// ============================================================================

void AirbusHUDBehavior::compute_rollout(
    const HudBehaviorContext& ctx,
    FLOAT64                   runway_heading_deg,
    FLOAT64                   lateral_deviation_m,
    RolloutState*             rs,
    RolloutCue*               cue)
{
    if (rs == 0 || cue == 0) return;

    // 1. Initialise Airbus rollout augmentation on first frame
    if (!m_rollout_init) {
        a350_rollout_init(&m_a350_rollout);
        m_a350_rollout.centerline_gain      = m_a350_profile.rollout_centerline_gain;
        m_a350_rollout.centerline_damping   = m_a350_profile.rollout_centerline_damping;
        m_a350_rollout.predictive_lead_gain = m_a350_profile.rollout_predictive_lead;
        m_a350_rollout.crosswind_stab_gain  = m_a350_profile.rollout_crosswind_stab;
        m_a350_rollout.edge_stab_gain       = m_a350_profile.rollout_edge_stabilization;
        m_a350_rollout.wet_assist_enabled   = m_a350_profile.rollout_wet_assist;
        m_rollout_init = true;
    }

    // 2. Populate standard rollout state
    rollout_init(rs);

    rs->on_ground           = ctx.ac_on_ground;
    rs->groundspeed_ms      = ctx.ac_groundspeed_ms;
    rs->radio_altitude_m    = ctx.ac_radio_alt_m;
    rs->heading_deg         = ctx.ac_hdg_true;
    rs->track_deg           = ctx.ac_track_deg_true;
    rs->runway_heading_deg  = runway_heading_deg;
    rs->lateral_deviation_m = lateral_deviation_m;

    rollout_compute(rs, ctx.dt_s);

    // 3. Compute Airbus-specific rollout augmentation
    m_a350_rollout.on_ground           = ctx.ac_on_ground;
    m_a350_rollout.groundspeed_ms      = ctx.ac_groundspeed_ms;
    m_a350_rollout.heading_deg         = ctx.ac_hdg_true;
    m_a350_rollout.track_deg           = ctx.ac_track_deg_true;
    m_a350_rollout.runway_heading_deg  = runway_heading_deg;
    m_a350_rollout.lateral_deviation_m = lateral_deviation_m;

    a350_rollout_compute(&m_a350_rollout, ctx.dt_s);

    // 4. Apply Airbus augmentation to rollout state
    a350_rollout_apply_to_state(rs, &m_a350_rollout);

    // 5. Project rollout cues
    const FLOAT64 cx = (FLOAT64)(ctx.screen_w / 2);
    const FLOAT64 cy = (FLOAT64)(ctx.screen_h / 2);
    rollout_project_cue(rs, 520.0, ctx.screen_w, ctx.screen_h,
                         cx, cy, cue);
}

// ============================================================================
//  CAT III  —  Airbus-enhanced: sensor fusion, confidence weighting
// ============================================================================

void AirbusHUDBehavior::compute_cat3(
    const HudBehaviorContext& ctx,
    ConfidenceState*          cs,
    ConfidenceRenderParams*   render)
{
    if (cs == 0 || render == 0) return;

    // 1. Initialise A350 CAT III state on first frame
    if (!m_cat3_init) {
        a350_cat3_init(&m_a350_cat3);
        m_a350_cat3.loc_weight_setting       = m_a350_profile.cat3.loc_confidence_weight;
        m_a350_cat3.gs_weight_setting        = m_a350_profile.cat3.gs_confidence_weight;
        m_a350_cat3.ra_weight_setting        = m_a350_profile.cat3.ra_confidence_weight;
        m_a350_cat3.gps_weight_setting       = m_a350_profile.cat3.gps_confidence_weight;
        m_a350_cat3.confidence_smooth_alpha  = m_a350_profile.cat3.confidence_smooth_alpha;
        m_a350_cat3.confidence_min_cat3      = m_a350_profile.cat3.confidence_min_cat3;
        m_a350_cat3.runway_stab_gain_setting = m_a350_profile.cat3.runway_stab_gain;
        m_a350_cat3.loc_predictive_smooth_s  = m_a350_profile.cat3.loc_predictive_smooth_s;
        m_a350_cat3.gs_stab_gain_setting     = m_a350_profile.cat3.gs_stabilisation_gain;
        m_a350_cat3.gs_conf_boost_captured   = m_a350_profile.cat3.gs_confidence_boost_captured;
        m_a350_cat3.flare_cue_stab_gain      = m_a350_profile.cat3.flare_cue_stab_gain;
        m_a350_cat3.flare_cue_min_conf       = m_a350_profile.cat3.flare_cue_min_confidence;
        m_a350_cat3.rollout_conf_amplifier   = m_a350_profile.cat3.rollout_confidence_amplifier;
        m_a350_cat3.rollout_degraded_fallback_setting = m_a350_profile.cat3.rollout_degraded_fallback;
        m_a350_cat3.low_vis_enhancement_gain = m_a350_profile.cat3.low_vis_enhancement_gain;
        m_a350_cat3.degraded_grace_seconds   = m_a350_profile.cat3.degraded_mode_grace_seconds;
        m_cat3_init = true;
    }

    // 2. Compute standard confidence first
    const bool loc_captured = (ctx.ils_loc_dots < 0.5);
    const bool gs_captured  = (ctx.ils_gs_dots  < 0.5);
    const bool cat3_mode    = (ctx.ac_radio_alt_m < 200.0);

    confidence_init(cs);
    confidence_compute(cs, ctx.dt_s,
                        ctx.ils_loc_dots, ctx.ils_gs_dots,
                        loc_captured, gs_captured,
                        (ctx.ac_radio_alt_m > 0.0),
                        ctx.ac_groundspeed_ms,
                        cat3_mode);

    // 3. Apply Airbus CAT III augmentation on top
    m_a350_cat3.ils_loc_dots     = ctx.ils_loc_dots;
    m_a350_cat3.ils_gs_dots      = ctx.ils_gs_dots;
    m_a350_cat3.loc_captured     = loc_captured;
    m_a350_cat3.gs_captured      = gs_captured;
    m_a350_cat3.radio_alt_valid  = (ctx.ac_radio_alt_m > 0.0);
    m_a350_cat3.groundspeed_ms   = ctx.ac_groundspeed_ms;
    m_a350_cat3.radio_altitude_m = ctx.ac_radio_alt_m;

    a350_cat3_compute(&m_a350_cat3, ctx.dt_s, cs);

    // 4. Apply CAT III enhancements to render params
    a350_cat3_apply_to_render(&m_a350_cat3, &cs->render);
    *render = cs->render;
}

// ============================================================================
//  Declutter  —  Airbus-style: aggressive phase-based declutter
// ============================================================================

void AirbusHUDBehavior::compute_declutter(
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

    // Apply Airbus-specific declutter boosts from profile
    // (The declutter system provides base priorities; Airbus extends them)
    if (!m_symbology_init) {
        a350_symbology_init(&m_a350_symbology);
        m_symbology_init = true;
    }

    // Airbus-style: more aggressive declutter during flare and rollout
    if (phase == HudFlightPhase::FLARE || phase == HudFlightPhase::ROLLOUT) {
        for (int i = 0; i < SYM_TYPE_COUNT; ++i) {
            // Reduce non-critical symbols further
            if (ds->symbols[i].base_priority < SYM_PRIO_HIGH) {
                ds->symbols[i].dimming_factor *= 0.5f;
                if (ds->symbols[i].dimming_factor < 0.1f) {
                    ds->symbols[i].suppressed = true;
                }
            }
        }
    }

    // Compute symbology styling parameters
    a350_symbology_compute(&m_a350_symbology, ctx.dt_s,
                            m_a350_profile.brightness_easing,
                            m_a350_profile.oscillation_reduction);
}

// ============================================================================
//  Optics  —  Airbus-style: refined, clean, optically stable
// ============================================================================

void AirbusHUDBehavior::compute_optics(
    const HudBehaviorContext& ctx,
    const HUDProfile*         profile,
    VisualResponseState*      vs,
    VisualRenderParams*       render)
{
    if (vs == 0 || render == 0) return;

    // Initialise symbology styling if not yet done
    if (!m_symbology_init) {
        a350_symbology_init(&m_a350_symbology);
        m_symbology_init = true;
    }

    // Compute A350 symbology styling
    const FLOAT64 target_bright = profile->optical_calmness;
    const FLOAT64 turbulence = 0.0;  // would come from turbulence estimation
    a350_symbology_compute(&m_a350_symbology, ctx.dt_s,
                            target_bright, turbulence);

    // Compute visual response
    visual_response_init(vs);

    const FLOAT64 ambient_lux = ctx.ambient_luminance;
    const bool runway_light_boom = (ctx.ac_radio_alt_m < 60.0);

    visual_response_compute(vs, ctx.dt_s,
                             ambient_lux,
                             0.0,  // rain_intensity
                             runway_light_boom);

    // Airbus optical profile: reduced bloom, higher calmness
    render->brightness             = a350_symbology_ease_brightness(
                                        &m_a350_symbology,
                                        vs->current_brightness,
                                        target_bright);
    render->contrast               = vs->contrast_gain * m_a350_symbology.line_cleanliness;
    render->phosphor_persistence_ms = vs->phosphor_current_ms *
                                       (1.0 + m_a350_symbology.symbol_persistence);
    render->bloom_intensity        = vs->bloom_amount *
                                       m_a350_profile.bloom_reduction;
    render->glare_amount           = vs->rain_glare * 0.5;  // reduced glare perceived
    render->edge_fade_night_boost  = 1.0 - vs->dark_adaptation;
    render->active                 = vs->active || m_a350_symbology.active;
}
