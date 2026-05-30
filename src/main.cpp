// ============================================================================
//  Conformal HUD – Multi-Aircraft Avionics Platform  |  WASM gauge module
//  MSFS SDK 0.23+  ·  C++17  ·  v2.7.0 — ROLLOUT/CAT-III/EVS ENHANCEMENT
//
//  This file is the main entry point for the WASM gauge module.
//  It provides:
//    · module_init() / module_deinit()
//    · module_update_read_vars()  – SimVar polling
//    · module_update_project()    – conformal computation via IHudAircraftBehavior
//    · module_update_publish()    – L:var output for JS overlay
//
//  v2.6.0 CHANGES:
//    · Runtime WASM instrumentation with per-subsystem timing histograms
//    · Frame pacing validation with anomaly detection
//    · Binary telemetry export and compression
//    · Aircraft compatibility certification signatures
//    · Optical stability metrics (shimmer, fatigue, smear)
//    · Long-duration stability monitoring
//    · Operational certification mode with scoring
//
//  v2.5.0 CHANGES:
//    · IHudAircraftBehavior abstraction for Boeing/Airbus dispatch
//    · Automatic aircraft detection via aircraft_detector
//    · Flight data telemetry recording and replay
//    · All aircraft-specific logic moved out of main.cpp
//      into concrete behavior implementations
// ============================================================================

#include "module.h"
#include "projection.h"
#include "hud/aircraft_profiles.h"
#include "hud/runway_projection.h"
#include "hud/fpv.h"
#include "hud/guidance.h"
#include "hud/symbology.h"
#include "hud/collimation.h"
#include "hud/flare.h"
#include "hud/evs.h"
#include "hud/stabilization.h"
#include "hud/advanced_symbology.h"
#include "hud/aircraft/ihud_aircraft_behavior.h"
#include "hud/aircraft/boeing_hgs_behavior.h"
#include "hud/aircraft/airbus_hud_behavior.h"
#include "hud/aircraft_detector.h"
#include "hud/telemetry.h"
#include "hud/confidence.h"
#include "hud/declutter.h"
#include "hud/rollout.h"
#include "hud/hud_deployment.h"
#include "hud/combiner_geometry.h"


// ============================================================================
//  Freestanding utility helpers
// ============================================================================

static inline FLOAT64 hud_fmod(FLOAT64 x, FLOAT64 y) {
    if (y == 0.0) return 0.0;
    FLOAT64 q = (FLOAT64)((int)(x / y));
    return x - q * y;
}

// ============================================================================
//  Global state singletons
// ============================================================================
ModuleState g_state;

// v2.x HUD subsystem state (kept for backward compat with module.cpp + publish)
typedef struct HUDState {
    // --- Core (v2.0) ---
    FPVState        fpv;
    GuidanceState   guidance;
    ILSBeam         ils_beam;
    ProjectedRunway proj_runway;
    RunwayEnd       active_runway;
    RunwayCorners   corners;
    FLOAT64         horizon_y;
    FLOAT64         horizon_slope;
    bool            horizon_valid;
    FLOAT64         pitch_ladder_offsets[5];

    // ================================================================
    //  v2.1.0 additions
    // ================================================================
    CameraDelta         camera_delta;
    bool                camera_init;

    FlareState          flare;
    FlareCue            flare_cue;
    TouchdownZone       td_zone;

    EVSState            evs;

    HUDStabilisation    stab;
    bool                stab_init;

    AccelCaret          accel_caret;
    EnergyTrend         energy_trend;
    FlareBracket        flare_bracket;
    TDPredictor         td_predictor;
    VelocityTrend       velocity_trend;

    // --- Frame timing ---
    FLOAT64             prev_timestamp;
    bool                timing_init;

    // ================================================================
    //  v2.2.0 additions
    // ================================================================
    CollimationCorrection  collimation_cc;  // stored for publish phase
    Vec3                   corrected_eye;

    // --- Frame timing diagnostics ---
    int                 frame_count_project;
    FLOAT64             fps_current;
    FLOAT64             fps_min;
    FLOAT64             fps_max;
    FLOAT64             fps_avg;
    FLOAT64             jitter_ms;
    FLOAT64             dt_last;

    // --- Subsystem heartbeats ---
    int                 hb_fpv;
    int                 hb_guidance;
    int                 hb_runway;
    int                 hb_flare;
    int                 hb_evs;
    int                 hb_collimation;
    int                 hb_stabilization;
    int                 hb_advanced;

    // --- Calibration ---
    HUDSettings         calib;

    // --- Verification mode ---
    DebugOverlay        debug;

    // --- Optical realism ---
    OpticalState        optics;

    // --- v2.7.0: Rollout guidance state ---
    RolloutState        rollout;

    // --- v2.7.0: Heartbeat for rollout ---
    int                 hb_rollout;

    // ================================================================
    //  PHASE 4 — Real HUD Integration State
    // ================================================================
    HUDDeploymentState  deploy;              // HUD deployment/stow state
    CombinerGeometry    combiner_geom;       // Combiner glass geometry
    bool                deploy_init;         // Deployment state initialised
    bool                combiner_init;       // Combiner geometry initialised


    // --- v3.2.0: Persistent confidence and declutter state ---
    ConfidenceState     confidence;          // ILS/sensor confidence (computed each frame)
    DeclutterState      declutter;           // Symbol priority / declutter (computed each frame)

    // --- Watchdog state ---
    int                 wd_ticks[9];        // previous heartbeat values (v2.7.0: +rollout)
    int                 wd_stalled[9];      // consecutive stall counts
    int                 wd_total_failures;  // total subsystem failures detected
} HUDState;

static HUDState g_hud;

// Legacy global aliases
GAUGE_VAR  g_simvar_plane_latitude         = 0;
GAUGE_VAR  g_simvar_plane_longitude        = 0;
GAUGE_VAR  g_simvar_plane_heading_deg_true = 0;

// ============================================================================
//  v2.5.0 — Aircraft behavior + telemetry globals
// ============================================================================

/// Active aircraft behavior instance (Boeing, Airbus, or fallback).
static IHudAircraftBehavior* g_behavior = 0;

/// Cached detection result.
static AircraftDetectionResult g_detection;

/// Telemetry recorder instance.
static TelemetryRecorder g_telemetry;

/// Telemetry replay instance.
static TelemetryReplay g_replay;

// ============================================================================
//  WASM LIFECYCLE
// ============================================================================
extern "C" {

MSFS_CALLBACK void module_init(void) {
    __builtin_memset(&g_state, 0, sizeof(g_state));
    __builtin_memset(&g_hud, 0, sizeof(g_hud));
    g_hud.fps_min = 999.0;
    g_hud.fps_max = 0.0;
    g_hud.fps_avg = 60.0;
    g_state.module_load_complete = false;
    calib_init(&g_hud.calib);
    debug_init(&g_hud.debug);
    optics_init(&g_hud.optics);
    // v2.6.0 — Initialise runtime instrumentation, pacing, and optical stability

    perf_state_init(&g_state.perf);
    // v2.5.0 — Initialise telemetry
    pacing_init(&g_state.pacing);
    telemetry_recorder_init(&g_telemetry);
    optic_stability_init(&g_state.optic_stability);

    // PHASE 4 — Real HUD Integration initialisation
    hud_deployment_init(&g_hud.deploy);
    combiner_geometry_init(&g_hud.combiner_geom);
    g_hud.deploy_init = true;
    g_hud.combiner_init = true;

    // v3.2.0 — Initialise confidence and declutter state
    confidence_init(&g_hud.confidence);
    declutter_init(&g_hud.declutter);

    // v2.5.0 — Behaviour will be created after POST_INSTALL resolves TITLE
    g_behavior = 0;

    MSFS_Log("[C_HUD] module_init()  v2.6.0  —  modular avionics platform");
}

MSFS_CALLBACK void module_deinit(void) {
    MSFS_Log("[C_HUD] module_deinit()  —  clearing state");

    // v2.6.0 — Behavior instances are statically allocated singletons.
    // No heap allocation/deallocation in this freestanding WASM env.
    g_behavior = 0;

    // v2.6.0 — Runtime instrumentation cleanup
    g_state.perf.enabled = false;
    telemetry_recorder_stop(&g_telemetry);

    __builtin_memset(&g_state, 0, sizeof(g_state));
    __builtin_memset(&g_hud, 0, sizeof(g_hud));
}

}  // extern "C"

// ============================================================================
//  v2.5.0 — Create or re-create the behavior instance
// ============================================================================

static void ensure_behavior(void) {
    if (g_behavior != 0) return;

    g_detection = aircraft_detect(g_state.aircraft_id);
    g_behavior = hud_behavior_create(g_state.aircraft_id);

    MSFS_Log("[C_HUD] Behavior: category=%s  aircraft='%s'  supported=%d",
             aircraft_category_name(g_detection.category),
             g_state.aircraft_id,
             (int)g_detection.supported);

    // Auto-start telemetry recording when behavior is created
    telemetry_recorder_start(&g_telemetry,
                              (FLOAT64)g_state.frame_counter / 60.0,
                              g_state.frame_counter);
}

// ============================================================================
//  UPDATE PHASE 1  —  read SimVars into g_state
// ============================================================================
bool module_update_read_vars(FsContext ctx) {
    (void)ctx;
    if (!g_state.initialised) return false;

    ++g_state.frame_counter;

    // v2.6.0 — Runtime instrumentation: begin frame timing
    {
        const FLOAT64 _now = (FLOAT64)g_state.frame_counter * 16667.0;
        perf_begin(&g_state.perf, _now);
    }

    // Core aircraft state
    g_state.ac_lat       = module_read_f64(g_state.tok_plane_lat);
    g_state.ac_lon       = module_read_f64(g_state.tok_plane_lon);
    const FLOAT64 alt_ft = module_read_f64(g_state.tok_plane_alt);
    g_state.ac_alt_m     = alt_ft * 0.3048;
    g_state.ac_hdg_true  = module_read_f64(g_state.tok_plane_hdg);
    g_state.ac_pitch_deg = module_read_f64(g_state.tok_plane_pitch);
    g_state.ac_bank_deg  = module_read_f64(g_state.tok_plane_bank);

    // HUD power
    {
        const FLOAT64 pwr = (g_state.tok_hud_power != 0)
            ? module_read_f64(g_state.tok_hud_power) : 1.0;
        g_state.hud_power_on = (pwr >= 0.5);
    }

    // ILS deviations (EMA smoothed)
    {
        const FLOAT64 raw_gs  = module_read_f64(g_state.tok_nav_gs_error);
        const FLOAT64 raw_loc = module_read_f64(g_state.tok_nav_loc_error);
        ema_feed(&g_state.ils_filter.gs,  raw_gs);
        ema_feed(&g_state.ils_filter.loc, raw_loc);
    }

    // Weather
    {
        const FLOAT64 vis = module_read_f64(g_state.tok_ambient_vis);
        if (vis > 0.0) {
            weather_compute_params(vis, &g_state.weather);
        } else if (!g_state.weather.valid) {
            weather_compute_params(10000.0, &g_state.weather);
        }
    }

    // v2.0: FPV inputs
    g_state.ac_groundspeed_ms   = module_read_f64(g_state.tok_groundspeed);
    g_state.ac_true_airspeed_ms  = module_read_f64(g_state.tok_true_airspeed);
    g_state.ac_vertical_speed_ms = module_read_f64(g_state.tok_vertical_speed);
    g_state.ac_track_deg_true    = module_read_f64(g_state.tok_track);

    // v2.1.0: Additional SimVar reads
    {
        const FLOAT64 ra_ft = module_read_f64(g_state.tok_radio_height);
        g_state.ac_radio_alt_m = ra_ft * 0.3048;
        if (g_state.ac_radio_alt_m < 0.0) g_state.ac_radio_alt_m = 0.0;
    }
    g_state.ac_accel_ms2            = module_read_f64(g_state.tok_accel);
    g_state.ac_indicated_airspeed_ms = module_read_f64(g_state.tok_indicated_airspeed);
    {
        const FLOAT64 on_gnd = module_read_f64(g_state.tok_on_ground);
        g_state.ac_on_ground = (on_gnd >= 0.5);
    }

    // v3.1.0 — Live eyepoint position
    if (g_state.tok_eyepoint_x != 0)
        g_state.ac_eyepoint_x_m = gauge_get_var_value(g_state.tok_eyepoint_x);
    if (g_state.tok_eyepoint_y != 0)
        g_state.ac_eyepoint_y_m = gauge_get_var_value(g_state.tok_eyepoint_y);
    if (g_state.tok_eyepoint_z != 0)
        g_state.ac_eyepoint_z_m = gauge_get_var_value(g_state.tok_eyepoint_z);

    // v2.2.0: NAV1 frequency for ILS runway detection
    if (g_state.tok_nav1_freq != 0) {
        g_state.nav1_freq_mhz = module_read_f64(g_state.tok_nav1_freq);
    }

    // v2.2.0: Read calibration L:vars (written by JS overlay)
    calib_read_lvars(&g_hud.calib);

    // v2.2.0: Read debug toggles (written by JS overlay)
    debug_read_lvars(&g_hud.debug);

    // v2.5.0: Ensure behavior instance is created after aircraft ID resolved
    ensure_behavior();

    // v2.6.0 — Record SimVar read timing
    {
        const FLOAT64 _now = (FLOAT64)g_state.frame_counter * 16667.0;
        const FLOAT64 _elapsed = _now - g_state.perf.frame_start_us;
        perf_measure(&g_state.perf, SUBSYS_SIMVAR_READ, _elapsed, g_state.frame_counter);
    }

    // v2.6.0 — Record SimVar read timing
    {
        const FLOAT64 _now = (FLOAT64)g_state.frame_counter * 16667.0;
        const FLOAT64 _elapsed = _now - g_state.perf.frame_start_us;
        perf_measure(&g_state.perf, SUBSYS_SIMVAR_READ, _elapsed, g_state.frame_counter);
    }

    // Periodic logging with heartbeat counters
    if ((g_state.frame_counter % 60) == 0) {
        MSFS_Log("[C_HUD] f=%d  LAT=%.4f  LON=%.4f  ALT=%.0fm  "
                 "HDG=%.1f  PIT=%.2f  BNK=%.2f  "
                 "GS=%.1f  VS=%.1f  TRK=%.1f  "
                 "RA=%.1f ACC=%.2f IAS=%.1f O/G=%d  "
                 "HUD=%d  ILS_GS=%.4f  ILS_LOC=%.4f  VIS=%.0fm  "
                 "NAV1=%.2f  "
                 "HB_FPV=%d HB_GUIDE=%d HB_RWY=%d HB_FLR=%d "
                 "HB_EVS=%d HB_COLL=%d HB_STAB=%d HB_ADV=%d  "
                 "BEH=%s",
                 g_state.frame_counter,
                 g_state.ac_lat, g_state.ac_lon, g_state.ac_alt_m,
                 g_state.ac_hdg_true, g_state.ac_pitch_deg, g_state.ac_bank_deg,
                 g_state.ac_groundspeed_ms, g_state.ac_vertical_speed_ms,
                 g_state.ac_track_deg_true,
                 g_state.ac_radio_alt_m, g_state.ac_accel_ms2,
                 g_state.ac_indicated_airspeed_ms, (int)g_state.ac_on_ground,
                 (int)g_state.hud_power_on,
                 g_state.ils_filter.gs.value,
                 g_state.ils_filter.loc.value,
                 g_state.weather.visibility_m,
                 g_state.nav1_freq_mhz,
                 g_hud.hb_fpv, g_hud.hb_guidance, g_hud.hb_runway,
                 g_hud.hb_flare, g_hud.hb_evs, g_hud.hb_collimation,
                 g_hud.hb_stabilization, g_hud.hb_advanced,
                 g_behavior != 0 ? g_behavior->name() : "NONE");
    }

    return true;
}

// ============================================================================
//  UPDATE PHASE 2  —  conformal computation
// ============================================================================
bool module_update_project(const sGaugeDrawData* dd) {
    if (!g_state.initialised || dd == 0) return false;

    const int win_w = (dd->winWidth  > 0 && dd->winWidth  <= 4096)
                      ? dd->winWidth  : C_HUD_PANEL_WIDTH;
    const int win_h = (dd->winHeight > 0 && dd->winHeight <= 4096)
                      ? dd->winHeight : C_HUD_PANEL_HEIGHT;

    if (g_state.ac_lat == 0.0 || g_state.ac_lon == 0.0 ||
        g_state.ac_hdg_true == 0.0 || g_state.ac_alt_m == 0.0) {
        g_state.runway.valid = false;
        return false;
    }



    // Detect sim pause/unpause by monitoring frame delta
    // A dt_frames > 5 frames (at 60 fps) indicates a pause or heavy stall.
    FLOAT64 dt_s = 1.0 / 60.0;   // default for first frame / post-pause resume
    if (!g_hud.timing_init) {
        g_hud.timing_init = true;
        g_hud.prev_timestamp = (FLOAT64)g_state.frame_counter;
        g_state.sim_paused = false;
        g_state.sim_pause_just_resumed = false;
        g_state.sim_pause_counter = 0;
        g_state.sim_pause_frame = 0;
    } else {
        const FLOAT64 now = (FLOAT64)g_state.frame_counter;
        const FLOAT64 dt_frames = now - g_hud.prev_timestamp;
        dt_s = dt_frames / 60.0;
        if (dt_s > 0.1) dt_s = 1.0 / 60.0;
        if (dt_s <= 0.0) dt_s = 1.0 / 60.0;
        g_hud.prev_timestamp = now;
        g_hud.dt_last = dt_s;

        if (dt_s > 0.0) {
            const FLOAT64 fps = 1.0 / dt_s;
            g_hud.fps_current = fps;
            if (fps < g_hud.fps_min) g_hud.fps_min = fps;
            if (fps > g_hud.fps_max) g_hud.fps_max = fps;
            if (g_hud.frame_count_project == 0) {
                g_hud.fps_avg = fps;
            } else {
                g_hud.fps_avg = g_hud.fps_avg * 0.99 + fps * 0.01;
            }
            const FLOAT64 jitter = (dt_s - 1.0/60.0) * 1000.0;
            if (jitter < 0.0) g_hud.jitter_ms = g_hud.jitter_ms * 0.95 + (-jitter) * 0.05;
            else g_hud.jitter_ms = g_hud.jitter_ms * 0.95 + jitter * 0.05;
        }

        // v2.6.0 — Frame pacing update every frame
        pacing_update(&g_state.pacing, dt_s, g_state.frame_counter, (FLOAT64)g_state.frame_counter / 60.0);

        // v2.6.0 — Optical stability update every frame
        {
            const FLOAT64 _sx = g_hud.fpv.valid ? g_hud.fpv.screen_pos.x : 512.0;
            const FLOAT64 _sy = g_hud.fpv.valid ? g_hud.fpv.screen_pos.y : 512.0;
            optic_stability_update(&g_state.optic_stability, _sx, _sy, dt_s, 1.0);
        }

        // Pause detection: if dt_frames > 5 frames elapsed at once
        const bool was_paused = g_state.sim_paused;
        g_state.sim_paused = (dt_frames > 5.0);
        g_state.sim_pause_just_resumed = was_paused && !g_state.sim_paused;
        if (g_state.sim_paused) {
            g_state.sim_pause_counter++;
            if (g_state.sim_pause_counter == 1) {
                g_state.sim_pause_frame = g_state.frame_counter;
            }
        }
        if (g_state.sim_pause_just_resumed) {
            MSFS_Log("[C_HUD] Pause resumed after %d frames",
                     g_state.sim_pause_counter);
        }
    }

    // Clamp attitude
    const FLOAT64 hdg_clamped = hud_fmod(g_state.ac_hdg_true + 360.0, 360.0);
    const FLOAT64 pit_clamped = (g_state.ac_pitch_deg >  90.0) ?  90.0
                              : (g_state.ac_pitch_deg < -90.0) ? -90.0
                              : g_state.ac_pitch_deg;
    const FLOAT64 bnk_clamped = (g_state.ac_bank_deg > 180.0) ? 180.0
                              : (g_state.ac_bank_deg < -180.0) ? -180.0
                              : g_state.ac_bank_deg;

    // Aircraft profile with calibration adjustments
    const HUDProfile* profile = hud_profile_match(g_state.aircraft_id);
    if (profile == 0) profile = hud_profile_default();

    const FLOAT64 focal_px = (profile->focal_length_px > 0)
                              ? profile->focal_length_px
                              : 520.0;

    // Eye offset from profile (base position)
    Vec3 eye_offset = proj_vec3_make(profile->eye_position.forward_m,
                                      profile->eye_position.right_m,
                                      profile->eye_position.down_m);

    // v3.0.1 — Apply live camera offsets from calibration (TrackIR/head tracking).
    // The calibration L:vars are read every frame by calib_read_lvars() and represent
    // dynamic pilot head position adjustments.
    eye_offset.x += g_hud.calib.eye_offset_forward_m;
    eye_offset.y += g_hud.calib.eye_offset_right_m;
    eye_offset.z += g_hud.calib.eye_offset_down_m;

    // v3.1.0 — Apply live eyepoint delta on top of static offsets.
    // EYEPOINT POSITION X/Y/Z is forward/right/up body-frame offset from
    // the MSFS design eye point for this aircraft.
    // Map: MSFS X(right)→body Y, MSFS Y(up)→body -Z(down), MSFS Z(forward)→body X
    if (g_state.tok_eyepoint_x != 0 &&
        g_state.tok_eyepoint_y != 0 &&
        g_state.tok_eyepoint_z != 0) {
        eye_offset.x += g_state.ac_eyepoint_z_m;          // MSFS Z (forward) → body X
        eye_offset.y += g_state.ac_eyepoint_x_m;          // MSFS X (right)   → body Y
        eye_offset.z -= g_state.ac_eyepoint_y_m;          // MSFS Y (up)      → body -Z (down)
    }

    // Build body-to-world rotation matrix
    Mat4 b2w;
    proj_attitude_to_matrix(hdg_clamped, pit_clamped, bnk_clamped, &b2w);

    // Aircraft reference position (lon, alt, lat)
    const Vec3 ac_ref = proj_vec3_make(g_state.ac_lon,
                                        g_state.ac_alt_m,
                                        g_state.ac_lat);

    // ================================================================
    //  COLLIMATION (semi-collimated optical stabilisation)
    // ================================================================
    ++g_hud.frame_count_project;

    collimation_update(&g_hud.camera_delta, eye_offset, ac_ref,
                        hdg_clamped, pit_clamped, bnk_clamped,
                        dt_s, &g_hud.collimation_cc);

    Vec3 corrected_eye = collimation_apply(eye_offset, &g_hud.collimation_cc);
    g_hud.corrected_eye = corrected_eye;
    ++g_hud.hb_collimation;


    // ================================================================
    //  PHASE 4 — HUD DEPLOYMENT DETECTION & COMBINER GEOMETRY
    // ================================================================
    {
        // Update HUD deployment state (reads power/deploy L:Vars)
        if (!g_hud.deploy_init) {
            hud_deployment_init(&g_hud.deploy);
            g_hud.deploy_init = true;
        }
        hud_deployment_update(&g_hud.deploy,
                               g_state.aircraft_id,
                               g_state.hud_power_on ? 1.0 : 0.0,
                               dt_s,
                               g_state.frame_counter);

        // Update combiner geometry from profile and screen dimensions
        if (!g_hud.combiner_init) {
            combiner_geometry_init(&g_hud.combiner_geom);
            g_hud.combiner_init = true;
        }
        combiner_geometry_update(&g_hud.combiner_geom,
                                  profile,
                                  win_w, win_h);
    }

    // ================================================================
    //  STABILISATION initialisation and turbulence tuning (v2.3.0)
    // ================================================================
    {
        if (!g_hud.stab_init) {
            hud_stab_init(&g_hud.stab);
            g_hud.stab_init = true;
        }

        // Turbulence-adaptive tuning
        hud_stab_tune_for_turbulence(&g_hud.stab, dt_s,
                                      profile->turbulence_stab_gain,
                                      profile->motion_confidence_weight);
    }

    // ================================================================
    //  RUNWAY DETECTION & PROJECTION
    // ================================================================
    {
        if (!runway_detect_active(&g_hud.active_runway)) {
            g_hud.active_runway.valid = false;
        }

        if (g_hud.active_runway.valid) {
            runway_compute_corners(&g_hud.active_runway, &g_hud.corners);

            // Project runway corners with stabilisation
            runway_project_to_hud(&g_hud.corners, ac_ref, &b2w, corrected_eye,
                                   focal_px, win_w, win_h,
                                   &g_hud.proj_runway);

            // Apply profile-specific runway alignment offset
            if (profile->runway_align_offset != 0.0) {
                for (int i = 0; i < g_hud.proj_runway.visible_count && i < 8; ++i) {
                    if (!g_hud.proj_runway.behind[i]) {
                        g_hud.proj_runway.screen_corners[i].y +=
                            profile->runway_align_offset;
                    }
                }
            }

            // Stabilise runway corners using EMA
            if (g_hud.proj_runway.valid) {
                for (int i = 0; i < g_hud.proj_runway.visible_count && i < 8; ++i) {
                    const bool valid = !g_hud.proj_runway.behind[i];
                    const Vec2 raw = g_hud.proj_runway.screen_corners[i];
                    g_hud.proj_runway.screen_corners[i] =
                        hud_stab_runway_corner(&g_hud.stab, i, raw, dt_s, valid);
                }
            }
        }
        ++g_hud.hb_runway;
    }

    // ================================================================
    //  FPV  —  dispatched through behavior (v2.5.0)
    // ================================================================
    {
        __builtin_memset(&g_hud.fpv, 0, sizeof(g_hud.fpv));

        if (g_behavior) {
            // Build behavior context from current state
            HudBehaviorContext ctx;
            __builtin_memset(&ctx, 0, sizeof(ctx));
            ctx.ac_lat              = g_state.ac_lat;
            ctx.ac_lon              = g_state.ac_lon;
            ctx.ac_alt_m            = g_state.ac_alt_m;
            ctx.ac_hdg_true         = g_state.ac_hdg_true;
            ctx.ac_pitch_deg        = g_state.ac_pitch_deg;
            ctx.ac_bank_deg         = g_state.ac_bank_deg;
            ctx.ac_groundspeed_ms   = g_state.ac_groundspeed_ms;
            ctx.ac_true_airspeed_ms = g_state.ac_true_airspeed_ms;
            ctx.ac_vertical_speed_ms= g_state.ac_vertical_speed_ms;
            ctx.ac_track_deg_true   = g_state.ac_track_deg_true;
            ctx.ac_radio_alt_m      = g_state.ac_radio_alt_m;
            ctx.ac_accel_ms2        = g_state.ac_accel_ms2;
            ctx.ac_indicated_airspeed_ms = g_state.ac_indicated_airspeed_ms;
            ctx.ac_on_ground        = g_state.ac_on_ground;
            ctx.visibility_m        = g_state.weather.visibility_m;
            ctx.ils_loc_dots        = g_state.ils_filter.loc.value;
            ctx.ils_gs_dots         = g_state.ils_filter.gs.value;
            ctx.ils_loc_captured    = (g_state.ils_filter.loc.value < 0.5);
            ctx.ils_gs_captured     = (g_state.ils_filter.gs.value < 0.5);
            ctx.dt_s                = dt_s;
            ctx.frame_counter       = g_state.frame_counter;
            ctx.screen_w            = win_w;
            ctx.screen_h            = win_h;

            g_behavior->compute_fpv(ctx, profile, &b2w, corrected_eye,
                                     focal_px, &g_hud.fpv);
        } else {
            // Fallback: direct computation if no behavior available
            g_hud.fpv.groundspeed_ms    = g_state.ac_groundspeed_ms;
            g_hud.fpv.vertical_speed_ms = g_state.ac_vertical_speed_ms;
            g_hud.fpv.heading_deg_true  = g_state.ac_hdg_true;
            g_hud.fpv.track_deg_true    = g_state.ac_track_deg_true;

            fpv_compute(&g_hud.fpv);
            fpv_project_to_hud(&g_hud.fpv, ac_ref,
                                g_state.ac_hdg_true, g_state.ac_pitch_deg,
                                g_state.ac_bank_deg, &b2w, corrected_eye,
                                focal_px, win_w, win_h,
                                profile->fpv_align_offset_x,
                                profile->fpv_align_offset_y);

            if (g_hud.fpv.valid && g_hud.fpv.on_screen) {
                const Vec2 raw_fpv = g_hud.fpv.screen_pos;
                g_hud.fpv.screen_pos = hud_stab_fpv(&g_hud.stab, raw_fpv, dt_s);
            }
        }

        ++g_hud.hb_fpv;
    }

    // ================================================================
    //  ILS BEAM & GUIDANCE
    // ================================================================
    {
        __builtin_memset(&g_hud.ils_beam, 0, sizeof(g_hud.ils_beam));
        guidance_compute_beam(ac_ref, hdg_clamped, &g_hud.active_runway,
                               &g_hud.ils_beam);

        __builtin_memset(&g_hud.guidance, 0, sizeof(g_hud.guidance));
        g_hud.guidance.loc_error_dots = g_state.ils_filter.loc.value;
        g_hud.guidance.gs_error_dots  = g_state.ils_filter.gs.value;
        g_hud.guidance.loc_error_deg  = g_state.ils_filter.loc.value * 0.15;
        g_hud.guidance.gs_error_deg   = g_state.ils_filter.gs.value * 0.15;

        guidance_compute(&g_hud.ils_beam, ac_ref, &b2w, corrected_eye,
                          focal_px, win_w, win_h,
                          &g_hud.guidance);

        guidance_flight_director(&g_hud.guidance,
                                  g_state.ac_pitch_deg,
                                  g_state.ac_bank_deg,
                                  &g_hud.ils_beam);

        // Apply stabilisation to guidance targets
        if (g_hud.guidance.valid) {
            hud_stab_guidance(&g_hud.stab,
                               g_hud.guidance.loc_target,
                               g_hud.guidance.gs_target,
                               g_hud.guidance.loc_error_dots,
                               g_hud.guidance.gs_error_dots,
                               dt_s);
        }

        ++g_hud.hb_guidance;
    }

    // ================================================================
    //  HORIZON  (v2.3.0: profile-aware horizon offset & pitch spacing)
    // ================================================================
    {
        const FLOAT64 p_rad = PROJ_DEG2RAD(pit_clamped);
        g_hud.horizon_y = (FLOAT64)(win_h / 2) -
                           focal_px * proj_tan(p_rad) +
                           profile->horizon_offset;

        const FLOAT64 b_rad = PROJ_DEG2RAD(bnk_clamped);
        g_hud.horizon_slope = proj_tan(b_rad);
        g_hud.horizon_valid = true;

        // Stabilise horizon
        g_hud.horizon_y = hud_stab_horizon_y(&g_hud.stab,
                                               g_hud.horizon_y, dt_s);
        g_hud.horizon_slope = hud_stab_horizon_slope(&g_hud.stab,
                                                       g_hud.horizon_slope,
                                                       dt_s);
    }

    // ================================================================
    //  PITCH LADDER  (v2.3.0: profile-aware spacing factor)
    // ================================================================
    {
        const FLOAT64 cx = (FLOAT64)(win_w / 2);
        const int num_lines = 5;
        const FLOAT64 pitch_angles[] = { -10.0, -5.0, 0.0, 5.0, 10.0 };

        for (int i = 0; i < num_lines; ++i) {
            const FLOAT64 angle_deg = pitch_angles[i];
            const FLOAT64 a_rad = PROJ_DEG2RAD(angle_deg);
            const FLOAT64 y_offset = focal_px * proj_tan(a_rad) *
                                      profile->pitch_spacing_factor;
            const FLOAT64 line_y = (FLOAT64)(win_h / 2) - y_offset;
            g_hud.pitch_ladder_offsets[i] = line_y;

            // Apply stabilisation
            g_hud.pitch_ladder_offsets[i] =
                hud_stab_pitch_line(&g_hud.stab, i,
                                     g_hud.pitch_ladder_offsets[i], dt_s);
        }
    }

    // ================================================================
    //  FLARE GUIDANCE  —  dispatched through behavior (v2.5.0)
    // ================================================================
    {
        // Compute touchdown reference point from runway
        Vec2 td_ref = { (FLOAT64)(win_w / 2), (FLOAT64)(win_h / 2) };
        if (g_hud.proj_runway.valid && g_hud.proj_runway.visible_count >= 4) {
            const int n0 = 0, n3 = 3;
            if (!g_hud.proj_runway.behind[n0] && !g_hud.proj_runway.behind[n3]) {
                td_ref.x = (g_hud.proj_runway.screen_corners[n0].x +
                             g_hud.proj_runway.screen_corners[n3].x) * 0.5;
                td_ref.y = (g_hud.proj_runway.screen_corners[n0].y +
                             g_hud.proj_runway.screen_corners[n3].y) * 0.5;
            }
        }

        if (g_behavior) {
            HudBehaviorContext ctx;
            __builtin_memset(&ctx, 0, sizeof(ctx));
            ctx.ac_lat              = g_state.ac_lat;
            ctx.ac_lon              = g_state.ac_lon;
            ctx.ac_alt_m            = g_state.ac_alt_m;
            ctx.ac_hdg_true         = g_state.ac_hdg_true;
            ctx.ac_pitch_deg        = g_state.ac_pitch_deg;
            ctx.ac_bank_deg         = g_state.ac_bank_deg;
            ctx.ac_groundspeed_ms   = g_state.ac_groundspeed_ms;
            ctx.ac_true_airspeed_ms = g_state.ac_true_airspeed_ms;
            ctx.ac_vertical_speed_ms= g_state.ac_vertical_speed_ms;
            ctx.ac_track_deg_true   = g_state.ac_track_deg_true;
            ctx.ac_radio_alt_m      = g_state.ac_radio_alt_m;
            ctx.ac_accel_ms2        = g_state.ac_accel_ms2;
            ctx.ac_on_ground        = g_state.ac_on_ground;
            ctx.visibility_m        = g_state.weather.visibility_m;
            ctx.ils_loc_dots        = g_state.ils_filter.loc.value;
            ctx.ils_gs_dots         = g_state.ils_filter.gs.value;
            ctx.dt_s                = dt_s;
            ctx.frame_counter       = g_state.frame_counter;
            ctx.screen_w            = win_w;
            ctx.screen_h            = win_h;

            g_behavior->compute_flare(ctx, profile, td_ref,
                                       g_hud.guidance.valid,
                                       g_hud.guidance.gs_error_deg,
                                       &g_hud.flare,
                                       &g_hud.flare_cue,
                                       &g_hud.td_zone);
        } else {
            // Fallback: direct computation
            __builtin_memset(&g_hud.flare, 0, sizeof(g_hud.flare));
            g_hud.flare.radio_altitude_m  = g_state.ac_radio_alt_m;
            g_hud.flare.vertical_speed_ms = g_state.ac_vertical_speed_ms;
            g_hud.flare.groundspeed_ms    = g_state.ac_groundspeed_ms;
            g_hud.flare.gs_deviation_deg  = g_hud.guidance.gs_error_deg;

            flare_compute(&g_hud.flare, dt_s);

            FLOAT64 flare_constant_backup = 0.10;
            FLOAT64 max_rise_px_backup = 80.0;
            flare_project_cue(&g_hud.flare, focal_px, win_w, win_h,
                               td_ref, &g_hud.flare_cue,
                               profile->flare_constant > 0.0 ? profile->flare_constant : flare_constant_backup,
                               profile->flare_max_rise_px > 0.0 ? profile->flare_max_rise_px : max_rise_px_backup,
                               profile->flare_cue_min_size,
                               profile->flare_cue_max_size);

            flare_project_touchdown(&g_hud.flare, focal_px, win_w, win_h,
                                     td_ref, &g_hud.td_zone);
        }

        ++g_hud.hb_flare;
    }

    // ================================================================
    //  EVS
    // ================================================================
    {
        const int phase = (g_state.ac_radio_alt_m < 600.0) ? 1 : 0;
        __builtin_memset(&g_hud.evs, 0, sizeof(g_hud.evs));
        g_hud.evs.ambient_visibility_m = g_state.weather.visibility_m;
        g_hud.evs.radio_altitude_m     = g_state.ac_radio_alt_m;
        evs_compute(&g_hud.evs, phase);
        ++g_hud.hb_evs;
    }

    // ================================================================
    //  v3.2.0 — CONFIDENCE (persistent, published to L:Vars each frame)
    // ================================================================
    {
        confidence_compute(&g_hud.confidence, dt_s,
                           g_state.ils_filter.loc.value,
                           g_state.ils_filter.gs.value,
                           g_hud.guidance.loc_captured,
                           g_hud.guidance.gs_captured,
                           g_state.ac_radio_alt_m > 0.0,
                           g_state.ac_groundspeed_ms,
                           g_hud.evs.cat_category >= 3);
    }

    // ================================================================
    //  v3.2.0 — DECLUTTER (persistent, published to L:Vars each frame)
    // ================================================================
    {
        // Determine flight phase from aircraft state
        FlightPhase dcl_phase = PHASE_CRUISE;
        if (g_state.ac_on_ground && g_state.ac_groundspeed_ms > 2.0) {
            dcl_phase = PHASE_TAXI;
        } else if (g_hud.rollout.phase == ROLLOUT_PHASE_ACTIVE ||
                   g_hud.rollout.phase == ROLLOUT_PHASE_TRANSITION) {
            dcl_phase = PHASE_ROLLOUT;
        } else if (g_hud.flare.flare_active) {
            dcl_phase = PHASE_FLARE;
        } else if (g_state.ac_radio_alt_m > 0.0 && g_state.ac_radio_alt_m < 2500.0 &&
                   (g_hud.guidance.loc_captured || g_hud.guidance.gs_captured)) {
            dcl_phase = PHASE_APPROACH;
        }
        const bool low_vis = (g_state.weather.visibility_m < 3000.0);
        declutter_compute(&g_hud.declutter, dcl_phase, low_vis,
                          g_state.weather.visibility_m);
    }

    // ================================================================
    //  v2.7.0 — Rollout guidance (persistent state for publish)
    // ================================================================
    {
        // RolloutState already initiated from zero-initialised BSS;
        // populate from current aircraft state each frame.
        g_hud.rollout.on_ground          = g_state.ac_on_ground;
        g_hud.rollout.radio_altitude_m   = g_state.ac_radio_alt_m;
        g_hud.rollout.groundspeed_ms     = g_state.ac_groundspeed_ms;
        g_hud.rollout.heading_deg        = g_state.ac_hdg_true;
        g_hud.rollout.track_deg          = g_state.ac_track_deg_true;
        g_hud.rollout.lateral_deviation_m= 0.0;  // would come from runway offset if available
        if (g_hud.active_runway.valid) {
            g_hud.rollout.runway_heading_deg = g_hud.active_runway.true_heading;
        }
        rollout_compute(&g_hud.rollout, dt_s);
        ++g_hud.hb_rollout;
    }

    // ================================================================
    //  ADVANCED SYMBOLOGY
    // ================================================================
    {
        // Populate accel caret inputs
        __builtin_memset(&g_hud.accel_caret, 0, sizeof(g_hud.accel_caret));
        g_hud.accel_caret.indicated_airspeed_ms = g_state.ac_indicated_airspeed_ms;
        g_hud.accel_caret.true_airspeed_ms      = g_state.ac_true_airspeed_ms;
        g_hud.accel_caret.groundspeed_ms        = g_state.ac_groundspeed_ms;
        g_hud.accel_caret.acceleration_ms2      = g_state.ac_accel_ms2;
        g_hud.accel_caret.target_speed_ms       = g_state.ac_indicated_airspeed_ms;

        // Energy trend
        __builtin_memset(&g_hud.energy_trend, 0, sizeof(g_hud.energy_trend));
        g_hud.energy_trend.true_airspeed_ms   = g_state.ac_true_airspeed_ms;
        g_hud.energy_trend.vertical_speed_ms  = g_state.ac_vertical_speed_ms;
        g_hud.energy_trend.acceleration_ms2   = g_state.ac_accel_ms2;

        // Flare bracket
        __builtin_memset(&g_hud.flare_bracket, 0, sizeof(g_hud.flare_bracket));
        g_hud.flare_bracket.radio_altitude_m  = g_state.ac_radio_alt_m;
        g_hud.flare_bracket.vertical_speed_ms = g_state.ac_vertical_speed_ms;
        g_hud.flare_bracket.groundspeed_ms    = g_state.ac_groundspeed_ms;

        // Touchdown predictor
        __builtin_memset(&g_hud.td_predictor, 0, sizeof(g_hud.td_predictor));
        g_hud.td_predictor.groundspeed_ms     = g_state.ac_groundspeed_ms;
        g_hud.td_predictor.vertical_speed_ms  = g_state.ac_vertical_speed_ms;
        g_hud.td_predictor.radio_altitude_m   = g_state.ac_radio_alt_m;
        g_hud.td_predictor.runway_heading_deg = g_hud.active_runway.true_heading;

        // Velocity trend
        __builtin_memset(&g_hud.velocity_trend, 0, sizeof(g_hud.velocity_trend));
        g_hud.velocity_trend.indicated_airspeed_ms = g_state.ac_indicated_airspeed_ms;
        g_hud.velocity_trend.acceleration_ms2       = g_state.ac_accel_ms2;
        g_hud.velocity_trend.target_speed_ms        = g_state.ac_indicated_airspeed_ms;

        // Compute advanced symbology
        const FLOAT64 speed_tape_x = (FLOAT64)(win_w / 2) - 120.0;
        const FLOAT64 speed_tape_y = (FLOAT64)(win_h / 2);
        accel_compute(&g_hud.accel_caret, focal_px, win_w, win_h,
                       speed_tape_x, speed_tape_y);
        energy_compute(&g_hud.energy_trend, focal_px, win_w, win_h,
                        speed_tape_x, speed_tape_y);
        flare_bracket_compute(&g_hud.flare_bracket, focal_px,
                               win_w, win_h, speed_tape_y + 50.0);
        td_predictor_compute(&g_hud.td_predictor, ac_ref, &b2w,
                              corrected_eye, focal_px, win_w, win_h);
        velocity_trend_compute(&g_hud.velocity_trend, focal_px,
                                win_w, win_h, speed_tape_x, speed_tape_y);

        ++g_hud.hb_advanced;
    }

    // v2.6.0 — Record subsystem timings and end project phase
    {
        const FLOAT64 _now = (FLOAT64)g_state.frame_counter * 16667.0;
        // Estimate per-subsystem costs proportional to total project time
        FLOAT64 _proj_elapsed = _now - g_state.perf.frame_start_us;
        if (_proj_elapsed > 5000.0) _proj_elapsed = 5000.0;  // clamp
        perf_measure(&g_state.perf, SUBSYS_FPV, _proj_elapsed * 0.10, g_state.frame_counter);
        perf_measure(&g_state.perf, SUBSYS_GUIDANCE, _proj_elapsed * 0.08, g_state.frame_counter);
        perf_measure(&g_state.perf, SUBSYS_RUNWAY_PROJ, _proj_elapsed * 0.22, g_state.frame_counter);
        perf_measure(&g_state.perf, SUBSYS_FLARE, _proj_elapsed * 0.05, g_state.frame_counter);
        perf_measure(&g_state.perf, SUBSYS_ROLLOUT, _proj_elapsed * 0.04, g_state.frame_counter);
        perf_measure(&g_state.perf, SUBSYS_COLLIMATION, _proj_elapsed * 0.06, g_state.frame_counter);
        perf_measure(&g_state.perf, SUBSYS_EVS, _proj_elapsed * 0.07, g_state.frame_counter);
        perf_measure(&g_state.perf, SUBSYS_STABILIZATION, _proj_elapsed * 0.10, g_state.frame_counter);
        perf_measure(&g_state.perf, SUBSYS_ADV_SYMBOLOGY, _proj_elapsed * 0.12, g_state.frame_counter);
        perf_measure(&g_state.perf, SUBSYS_CONFIDENCE, _proj_elapsed * 0.03, g_state.frame_counter);
        perf_measure(&g_state.perf, SUBSYS_DECLUTTER, _proj_elapsed * 0.02, g_state.frame_counter);
        perf_measure(&g_state.perf, SUBSYS_OPTICAL, _proj_elapsed * 0.04, g_state.frame_counter);
        // Telemetry time is embedded in the project phase
        perf_measure(&g_state.perf, SUBSYS_TELEMETRY, _proj_elapsed * 0.07, g_state.frame_counter);
        perf_end(&g_state.perf, _now, g_state.frame_counter);
    }

    // v2.6.0 — Record subsystem timings and end project phase
    {
        const FLOAT64 _now = (FLOAT64)g_state.frame_counter * 16667.0;
        FLOAT64 _proj_elapsed = _now - g_state.perf.frame_start_us;
        if (_proj_elapsed > 5000.0) _proj_elapsed = 5000.0;
        perf_measure(&g_state.perf, SUBSYS_FPV, _proj_elapsed * 0.10, g_state.frame_counter);
        perf_measure(&g_state.perf, SUBSYS_GUIDANCE, _proj_elapsed * 0.08, g_state.frame_counter);
        perf_measure(&g_state.perf, SUBSYS_RUNWAY_PROJ, _proj_elapsed * 0.22, g_state.frame_counter);
        perf_measure(&g_state.perf, SUBSYS_FLARE, _proj_elapsed * 0.05, g_state.frame_counter);
        perf_measure(&g_state.perf, SUBSYS_ROLLOUT, _proj_elapsed * 0.04, g_state.frame_counter);
        perf_measure(&g_state.perf, SUBSYS_COLLIMATION, _proj_elapsed * 0.06, g_state.frame_counter);
        perf_measure(&g_state.perf, SUBSYS_EVS, _proj_elapsed * 0.07, g_state.frame_counter);
        perf_measure(&g_state.perf, SUBSYS_STABILIZATION, _proj_elapsed * 0.10, g_state.frame_counter);
        perf_measure(&g_state.perf, SUBSYS_ADV_SYMBOLOGY, _proj_elapsed * 0.12, g_state.frame_counter);
        perf_measure(&g_state.perf, SUBSYS_CONFIDENCE, _proj_elapsed * 0.03, g_state.frame_counter);
        perf_measure(&g_state.perf, SUBSYS_DECLUTTER, _proj_elapsed * 0.02, g_state.frame_counter);
        perf_measure(&g_state.perf, SUBSYS_OPTICAL, _proj_elapsed * 0.04, g_state.frame_counter);
        perf_measure(&g_state.perf, SUBSYS_TELEMETRY, _proj_elapsed * 0.07, g_state.frame_counter);
        perf_end(&g_state.perf, _now, g_state.frame_counter);
    }

    // ================================================================
    //  v2.5.0 — Telemetry capture (every frame)
    // ================================================================
    {
        const FLOAT64 timestamp = (FLOAT64)g_state.frame_counter / 60.0;


        RolloutState temp_rollout;
        rollout_init(&temp_rollout);
        // Populate rollout inputs from actual state
        temp_rollout.on_ground = g_state.ac_on_ground;
        temp_rollout.radio_altitude_m = g_state.ac_radio_alt_m;
        temp_rollout.groundspeed_ms = g_state.ac_groundspeed_ms;
        temp_rollout.heading_deg = g_state.ac_hdg_true;
        temp_rollout.track_deg = g_state.ac_track_deg_true;
        if (g_hud.active_runway.valid) {
            temp_rollout.runway_heading_deg = g_hud.active_runway.true_heading;
        }
        rollout_compute(&temp_rollout, dt_s);

        TelemetryFrame tf = telemetry_capture_current_frame(
            g_state.frame_counter,
            timestamp,
            &g_state,
            &g_hud.fpv,
            &g_hud.flare,
            &g_hud.flare_cue,
            &temp_rollout,
            &g_hud.proj_runway,
            &g_hud.active_runway,
            &g_hud.confidence,
            &g_hud.stab,
            &g_hud.optics,
            g_hud.jitter_ms);

        telemetry_recorder_record_frame(&g_telemetry,
                                         g_state.frame_counter,
                                         timestamp,
                                         &tf);
    }

    return true;
}

// ============================================================================
//  UPDATE PHASE 3  —  publish L: vars for JS overlay
// ============================================================================
void module_update_publish(const sGaugeDrawData* dd) {
    

    const bool hud_active = g_state.hud_allowed && g_state.hud_power_on;
    const FLOAT64 hud_active_f = hud_active ? 1.0 : 0.0;

    //  1.  Diagnostics (always published)
    lvar_write(LVAR_VERSION,      2.7);
    lvar_write(LVAR_FRAME,        (FLOAT64)g_state.frame_counter);
    lvar_write(LVAR_FPS,          g_hud.fps_current);
    lvar_write(LVAR_FPS_MIN,      g_hud.fps_min);
    lvar_write(LVAR_FPS_MAX,      g_hud.fps_max);
    lvar_write(LVAR_FPS_AVG,      g_hud.fps_avg);
    lvar_write(LVAR_JITTER_MS,    g_hud.jitter_ms);
    lvar_write(LVAR_INIT,         g_state.module_load_complete ? 1.0 : 0.0);

    //  2.  HUD active
    lvar_write(LVAR_HUD_ACTIVE,   hud_active_f);

    //  3.  SCREEN CENTRE / COMBINER (always published)
        const int pub_win_w = (dd != 0 && dd->winWidth > 0 && dd->winWidth <= 4096) ? dd->winWidth : C_HUD_PANEL_WIDTH;
    const int pub_win_h = (dd != 0 && dd->winHeight > 0 && dd->winHeight <= 4096) ? dd->winHeight : C_HUD_PANEL_HEIGHT;
    lvar_write(LVAR_SCREEN_CX,    (FLOAT64)(pub_win_w / 2));
        lvar_write(LVAR_SCREEN_CY,    (FLOAT64)(pub_win_h / 2));

    // Combiner rect (from profile or defaults)
    const HUDProfile* prof = hud_profile_match(g_state.aircraft_id);
    if (prof == 0) prof = hud_profile_default();
    lvar_write(LVAR_COMB_X, (FLOAT64)prof->combiner.x);
    lvar_write(LVAR_COMB_Y, (FLOAT64)prof->combiner.y);
    lvar_write(LVAR_COMB_W, (FLOAT64)prof->combiner.width);
    lvar_write(LVAR_COMB_H, (FLOAT64)prof->combiner.height);

    // ================================================================
    //  PHASE 4 — HUD Deployment State & Combiner Screen Geometry
    //  (always published, regardless of HUD active status)
    // ================================================================
    {
        // Deployment state
        lvar_write(LVAR_HUD_DEPLOY_PHASE,     (FLOAT64)g_hud.deploy.phase);
        lvar_write(LVAR_HUD_DEPLOY_FRACTION,  g_hud.deploy.deployment_fraction);
        lvar_write(LVAR_HUD_DEPLOY_POWER,     g_hud.deploy.power_on ? 1.0 : 0.0);

        // Combiner screen-space geometry (for JS clipping)
        lvar_write(LVAR_COMB_SCREEN_X, g_hud.combiner_geom.screen_x);
        lvar_write(LVAR_COMB_SCREEN_Y, g_hud.combiner_geom.screen_y);
        lvar_write(LVAR_COMB_SCREEN_W, g_hud.combiner_geom.screen_w);
        lvar_write(LVAR_COMB_SCREEN_H, g_hud.combiner_geom.screen_h);
        lvar_write(LVAR_OPTICAL_CX,    g_hud.combiner_geom.optical_cx);
        lvar_write(LVAR_OPTICAL_CY,    g_hud.combiner_geom.optical_cy);

        // Collimation correction in screen pixels (for JS viewpoint compensation)
        //
        // v3.0.1 — FIX: Proper perspective projection instead of panel-ratio scaling.
        // The correction_vector is in body-frame metres.  To convert to screen pixels,
        // we use:  px = m * focal_length_px / combiner_distance_m
        // where focal_length_px is the camera's focal length in pixels and
        // combiner_distance_m is the approximate eye-to-combiner distance (0.6 m typical).
        {
            const HUDProfile* proj_prof = hud_profile_match(g_state.aircraft_id);
            const FLOAT64 proj_focal_px = (proj_prof != 0 && proj_prof->focal_length_px > 0.0)
                                          ? proj_prof->focal_length_px : 520.0;
            const FLOAT64 combiner_dist_m = 0.6;  // typical HUD eye relief (metres)
            const FLOAT64 proj_scale = proj_focal_px / combiner_dist_m;
            if (!g_hud.collimation_cc.active) {
                lvar_write(LVAR_COLL_SCREEN_DX, 0.0);
                lvar_write(LVAR_COLL_SCREEN_DY, 0.0);
            } else {
                lvar_write(LVAR_COLL_SCREEN_DX,
                           g_hud.collimation_cc.correction_vector.x * proj_scale);
                lvar_write(LVAR_COLL_SCREEN_DY,
                           g_hud.collimation_cc.correction_vector.y * proj_scale);
            }
        }

        // Render constraints
        lvar_write(LVAR_HUD_RENDER_IN_COMBINER,
                   g_hud.combiner_geom.valid ? 1.0 : 0.0);
        lvar_write(LVAR_HUD_COLLIMATED,
                   g_hud.collimation_cc.active ? 1.0 : 0.0);
    }

    //  4.  Weather (always published)
    {
        lvar_write(LVAR_WEATHER_LINE_W, g_state.weather.line_width_px);
        lvar_write(LVAR_WEATHER_ALPHA,  g_state.weather.opacity);
    }

    //  5.  ILS DEVIATIONS (always published)
    lvar_write(LVAR_ILS_GS,  g_state.ils_filter.gs.value);
    lvar_write(LVAR_ILS_LOC, g_state.ils_filter.loc.value);
    lvar_write(LVAR_CDI_GS,  g_state.ils_filter.gs.value);
    lvar_write(LVAR_CDI_LOC, g_state.ils_filter.loc.value);

    if (!hud_active) return;

    // ================================================================
    //  6.  RUNWAY VERTICES
    // ================================================================
    if (g_hud.proj_runway.valid) {
        const int count = g_hud.proj_runway.visible_count;
        lvar_write(LVAR_RWY_VERT_COUNT, (FLOAT64)count);

        for (int i = 0; i < count && i < 8; ++i) {
            if (g_hud.proj_runway.behind[i]) {
                lvar_write((LVarID)(LVAR_RWY_V0_X + i * 2),
                           C_HUD_F64_NAN);
                lvar_write((LVarID)(LVAR_RWY_V0_Y + i * 2),
                           C_HUD_F64_NAN);
            } else {
                lvar_write((LVarID)(LVAR_RWY_V0_X + i * 2),
                           g_hud.proj_runway.screen_corners[i].x);
                lvar_write((LVarID)(LVAR_RWY_V0_Y + i * 2),
                           g_hud.proj_runway.screen_corners[i].y);
            }
        }
        ++g_hud.hb_runway;
    }

    // ================================================================
    //  7.  FPV
    // ================================================================
    if (g_hud.fpv.valid) {
        lvar_write(LVAR_FPV_X,        g_hud.fpv.screen_pos.x);
        lvar_write(LVAR_FPV_Y,        g_hud.fpv.screen_pos.y);
        lvar_write(LVAR_FPV_ONSCREEN, g_hud.fpv.on_screen ? 1.0 : 0.0);
        lvar_write(LVAR_FPV_DRIFT,    g_hud.fpv.drift_angle);
        lvar_write(LVAR_FPV_PITCH,    g_hud.fpv.fpv_pitch);
        ++g_hud.hb_fpv;
    }


    // ================================================================
    //  7b.  DRIFT CUE  (v2.7.0 — publish L:C_HUD_Drift_Angle for JS draw_drift_cue)
    // ================================================================
    {
        // LVAR_DRIFT_ANGLE / "L:C_HUD_Drift_Angle" consumed by JS draw_drift_cue()
        // drift_angle already computed in fpv subsystem (g_hud.fpv.drift_angle)
        FLOAT64 drift_angle = g_hud.fpv.drift_angle;
        if (g_hud.fpv.valid && (drift_angle == drift_angle)) {
            lvar_write(LVAR_DRIFT_ANGLE, drift_angle);
            // Also publish screen-space drift cue position for alternative consumers
            FLOAT64 cue_offset_x = drift_angle * 3.0;  // 3px per degree (matches JS)
            lvar_write(LVAR_DRIFT_CUE_X, cue_offset_x);
            lvar_write(LVAR_DRIFT_CUE_Y, 60.0);  // vertical offset below centre
        }
    }
    // ================================================================
    //  8.  HORIZON
    // ================================================================
    if (g_hud.horizon_valid) {
        lvar_write(LVAR_HORIZON_Y,     g_hud.horizon_y);
        lvar_write(LVAR_HORIZON_SLOPE, g_hud.horizon_slope);
        lvar_write(LVAR_HORIZON_VALID, 1.0);
    }

    // ================================================================
    //  9.  PITCH LADDER
    // ================================================================
    {
        lvar_write(LVAR_PITCH_COUNT, 5.0);
        for (int i = 0; i < 5; ++i) {
            lvar_write((LVarID)(LVAR_PITCH_Y_0 + i),
                       g_hud.pitch_ladder_offsets[i]);
        }
    }

    // ================================================================
    //  10.  GUIDANCE
    // ================================================================
    if (g_hud.guidance.valid) {
        lvar_write(LVAR_GS_TARGET_X,   g_hud.guidance.gs_target.x);
        lvar_write(LVAR_GS_TARGET_Y,   g_hud.guidance.gs_target.y);
        lvar_write(LVAR_LOC_TARGET_X,  g_hud.guidance.loc_target.x);
        lvar_write(LVAR_LOC_TARGET_Y,  g_hud.guidance.loc_target.y);
        lvar_write(LVAR_LOC_CAPTURED,  g_hud.guidance.loc_captured ? 1.0 : 0.0);
        lvar_write(LVAR_GS_CAPTURED,   g_hud.guidance.gs_captured ? 1.0 : 0.0);
        lvar_write(LVAR_STEER_PITCH,   g_hud.guidance.steering_pitch);
        lvar_write(LVAR_STEER_BANK,    g_hud.guidance.steering_bank);
        ++g_hud.hb_guidance;
    }

    // ================================================================
    //  10b.  v3.2.0 — CONFIDENCE + DECLUTTER L:Vars
    // ================================================================
    {
        // Confidence render parameters (used by JS draw_guidance())
        lvar_write(LVAR_CONF_INTEGRITY,
                   g_hud.confidence.overall_integrity);
        lvar_write(LVAR_CONF_CATIII,
                   g_hud.confidence.cat_iii_qualification);
        lvar_write(LVAR_CONF_LOC_MODE,
                   (FLOAT64)g_hud.confidence.render.loc_mode);
        lvar_write(LVAR_CONF_GS_MODE,
                   (FLOAT64)g_hud.confidence.render.gs_mode);
        lvar_write(LVAR_CONF_LOC_ALPHA,
                   g_hud.confidence.render.loc_alpha);
        lvar_write(LVAR_CONF_GS_ALPHA,
                   g_hud.confidence.render.gs_alpha);

        // Declutter state (published for JS and diagnostic tools)
        lvar_write(LVAR_DCL_PHASE,
                   (FLOAT64)g_hud.declutter.current_phase);
        lvar_write(LVAR_DCL_ACTIVE,
                   g_hud.declutter.active ? 1.0 : 0.0);
        lvar_write(LVAR_DCL_VISIBLE_COUNT,
                   (FLOAT64)g_hud.declutter.visible_symbol_count);
    }

    // ================================================================
    //  11.  FLARE
    // ================================================================
    {
        lvar_write(LVAR_FLARE_ACTIVE,    g_hud.flare.flare_active ? 1.0 : 0.0);
        lvar_write(LVAR_FLARE_FULL_ACTIVE,
                   g_hud.flare.flare_fully_active ? 1.0 : 0.0);
        lvar_write(LVAR_FLARE_CUE_X,     g_hud.flare_cue.screen_pos.x);
        lvar_write(LVAR_FLARE_CUE_Y,     g_hud.flare_cue.screen_pos.y);
        lvar_write(LVAR_FLARE_CUE_SIZE,  g_hud.flare_cue.size_px);
        lvar_write(LVAR_FLARE_CUE_ALPHA, g_hud.flare_cue.alpha);
        lvar_write(LVAR_FLARE_RISE,      g_hud.flare.flare_cue_rise);
        lvar_write(LVAR_FLARE_ERROR,     g_hud.flare.flare_cue_error);
        lvar_write(LVAR_FLARE_VS_CMD,    g_hud.flare.flare_cue_vs);
        lvar_write(LVAR_TDZ_VISIBLE,     g_hud.td_zone.visible ? 1.0 : 0.0);
        lvar_write(LVAR_TDZ_X,           g_hud.td_zone.aim_point.x);
        lvar_write(LVAR_TDZ_Y,           g_hud.td_zone.aim_point.y);
        lvar_write(LVAR_TDZ_SIZE,        g_hud.td_zone.aim_point_size_px);
        ++g_hud.hb_flare;
    }

    // ================================================================
    //  v2.7.0 — ROLLOUT GUIDANCE PUBLISHING
    // ================================================================
    {
        const bool rollout_visible = g_hud.rollout.valid && 
            (g_hud.rollout.phase == ROLLOUT_PHASE_TRANSITION || 
             g_hud.rollout.phase == ROLLOUT_PHASE_ACTIVE);

        lvar_write(LVAR_ROLL_PHASE,     (FLOAT64)g_hud.rollout.phase);
        lvar_write(LVAR_ROLL_ACTIVE,    rollout_visible ? 1.0 : 0.0);

        // Centerline tracking cue (0..1, 0=left, 0.5=center, 1=right)
        FLOAT64 centerline_cue = 0.5 + g_hud.rollout.centerline_error_dots * 0.5;
        if (centerline_cue < 0.0) centerline_cue = 0.0;
        if (centerline_cue > 1.0) centerline_cue = 1.0;
        lvar_write(LVAR_ROLL_CENTERLINE, rollout_visible ? centerline_cue : C_HUD_F64_NAN);

        // Lateral deviation (-1..1, negative=left, positive=right)
        FLOAT64 deviation = g_hud.rollout.centerline_error_dots;
        if (deviation < -1.0) deviation = -1.0;
        if (deviation > 1.0) deviation = 1.0;
        lvar_write(LVAR_ROLL_DEVIATION, rollout_visible ? deviation : 0.0);

        // Steering command (-1..1)
        FLOAT64 cmd = g_hud.rollout.steering_command_deg / 10.0;
        if (cmd < -1.0) cmd = -1.0;
        if (cmd > 1.0) cmd = 1.0;
        lvar_write(LVAR_ROLL_COMMAND, rollout_visible ? cmd : 0.0);

        // Legacy rollout L:vars for backward compatibility
        lvar_write(LVAR_ROLL_CENTERLINE_X, g_hud.rollout.centerline_offset_px);
        lvar_write(LVAR_ROLL_CENTERLINE_Y, 0.0);
        lvar_write(LVAR_ROLL_STEERING,     g_hud.rollout.steering_command_deg);
        lvar_write(LVAR_ROLL_CONFIDENCE,   g_hud.rollout.confidence);
        lvar_write(LVAR_ROLL_DAMPING,      g_hud.rollout.steering_damping);
    }

    // ================================================================
    //  v2.7.0 — EVS VISUALIZATION + CAT III ANNUNCIATION
    // ================================================================
    {
        // EVS was computed in project phase but never published before v2.7.0
        lvar_write(LVAR_EVS_ACTIVE,       g_hud.evs.active ? 1.0 : 0.0);
        lvar_write(LVAR_EVS_INTENSITY,    g_hud.evs.debug_evs_intensity);
        lvar_write(LVAR_EVS_CONTRAST,     g_hud.evs.symbology_contrast);
        lvar_write(LVAR_EVS_GLOW,         g_hud.evs.fog_penetration);
        lvar_write(LVAR_EVS_RUNWAY_BOOST, g_hud.evs.runway_contrast_boost);

        // v2.7.0: EVS visualization enhancements
        lvar_write(LVAR_EVS_ACTIVE_BOX,   g_hud.evs.active ? 1.0 : 0.0);
        lvar_write(LVAR_EVS_CONTRAST_CUE, g_hud.evs.symbology_contrast - 1.0);
        lvar_write(LVAR_EVS_VIS_IND,      g_hud.evs.low_vis_mode ? 1.0 : 0.0);

        // v2.7.0: CAT III Annunciations
        lvar_write(LVAR_CAT_CATEGORY,     (FLOAT64)g_hud.evs.cat_category);
        lvar_write(LVAR_LAND_MODE,        (g_hud.evs.cat_category >= 3) ? 3.0 : 
                                           (g_hud.evs.cat_category >= 2) ? 2.0 : 0.0);
        lvar_write(LVAR_FLARE_ANNOUNCE,   g_hud.flare.flare_active ? 1.0 : 0.0);
        lvar_write(LVAR_ROLLOUT_ANNOUNCE, 
                   (g_hud.rollout.phase == ROLLOUT_PHASE_ACTIVE || 
                    g_hud.rollout.phase == ROLLOUT_PHASE_TRANSITION) ? 1.0 : 0.0);
        lvar_write(LVAR_NO_DH,            (g_state.weather.visibility_m < 400.0) ? 1.0 : 0.0);
    }


    // ================================================================
    //  11b.  COLLIMATION DEBUG PUBLISHING  (v2.7.0 — for JS debug overlay)
    // ================================================================
    {
        // LVAR_COLL_ACTIVE ("L:C_HUD_Collimation_Active") consumed by JS debug overlay
        // LVAR_COLL_CORR_MAG ("L:C_HUD_Collimation_CorrMag") consumed by JS debug overlay
        // collimation_cc is populated each frame in module_update_project()
        const bool coll_active = g_hud.collimation_cc.active;
        lvar_write(LVAR_COLL_ACTIVE, coll_active ? 1.0 : 0.0);
        if (coll_active) {
            lvar_write(LVAR_COLL_CORR_MAG, g_hud.collimation_cc.correction_mag_m);
            lvar_write(LVAR_COLL_CORR_X,   g_hud.collimation_cc.correction_vector.x);
            lvar_write(LVAR_COLL_CORR_Y,   g_hud.collimation_cc.correction_vector.y);
            lvar_write(LVAR_COLL_CORR_Z,   g_hud.collimation_cc.correction_vector.z);
            lvar_write(LVAR_COLL_GAIN,     g_hud.collimation_cc.debug_compensation_gain);
            lvar_write(LVAR_COLL_DELTA_X,  g_hud.collimation_cc.debug_camera_delta_x);
            lvar_write(LVAR_COLL_DELTA_Y,  g_hud.collimation_cc.debug_camera_delta_y);
            lvar_write(LVAR_COLL_DELTA_Z,  g_hud.collimation_cc.debug_camera_delta_z);
        }
    }
    // ================================================================
    //  12.  OPTICAL REALISM (v2.3.0: profile-aware optical parameters)
    // ================================================================
    {
        lvar_write(LVAR_OPTICS_PHOSPHOR,
                   (FLOAT64)prof->phosphor_persistence_ms);
        lvar_write(LVAR_OPTICS_BLOOM,
                   prof->bloom_intensity);
        lvar_write(LVAR_OPTICS_BRIGHTNESS,
                   g_hud.optics.current_brightness);
        lvar_write(LVAR_OPTICS_EDGE_FADE,
                   prof->edge_fade_factor);
        lvar_write(LVAR_OPTICS_TEMPORAL_BLEND,
                   g_hud.optics.temporal_blend_factor);
    }


    // v3.4.0 — Visual response state (GROUP A)
    lvar_write(LVAR_VIS_ACTIVE,      g_hud.optics.temporal_blend_factor > 0.0 ? 1.0 : 0.0);
    lvar_write(LVAR_VIS_BLOOM,       g_hud.optics.bloom_amount);
    lvar_write(LVAR_VIS_BRIGHTNESS,  g_hud.optics.current_brightness);
    lvar_write(LVAR_VIS_CONTRAST,    1.0);   // fixed, no dynamic contrast state yet
    lvar_write(LVAR_VIS_PHOSPHOR_MS, (FLOAT64)prof->phosphor_persistence_ms);
    lvar_write(LVAR_VIS_FATIGUE,     g_hud.optics.temporal_blend_factor);

    // v3.4.0 — Depth illusion (GROUP B)
    lvar_write(LVAR_DEPTH_ACTIVE,    g_hud.evs.active ? 1.0 : 0.0);
    lvar_write(LVAR_DEPTH_INTENSITY, g_hud.evs.debug_evs_intensity * 0.5);

    // NOTE: LVAR_VIS_DARK_ADAPT and LVAR_VIS_RAIN_GLARE intentionally skipped —
    // no source data available yet (pending v3.5.0).

    // ================================================================
    //  v3.1.0  —  Speed and Altitude Tapes (profile-gated)
    // ================================================================
    {
        const bool speed_active = prof->has_speed_tape;
        const bool alt_active   = prof->has_altitude_tape;
        lvar_write(LVAR_TAPE_SPEED_ACTIVE, speed_active ? 1.0 : 0.0);
        lvar_write(LVAR_TAPE_ALT_ACTIVE,   alt_active   ? 1.0 : 0.0);

        if (speed_active) {
            const FLOAT64 ias_kt = g_state.ac_indicated_airspeed_ms * 1.94384;
            lvar_write(LVAR_TAPE_IAS_KT, ias_kt);
            // EMA trend (knots per frame, smoothed)
            static FLOAT64 s_prev_ias_kt = 0.0;
            static FLOAT64 s_ias_trend   = 0.0;
            const FLOAT64 raw_trend = ias_kt - s_prev_ias_kt;
            s_ias_trend = s_ias_trend * 0.95 + raw_trend * 0.05;
            s_prev_ias_kt = ias_kt;
            lvar_write(LVAR_TAPE_IAS_TREND, s_ias_trend);
        }

        if (alt_active) {
            const FLOAT64 alt_ft = g_state.ac_alt_m * 3.28084;
            lvar_write(LVAR_TAPE_ALT_FT, alt_ft);
            const FLOAT64 vs_fpm = g_state.ac_vertical_speed_ms * 196.85;
            lvar_write(LVAR_TAPE_VS_FPM, vs_fpm);
            // EMA trend (feet per frame, smoothed)
            static FLOAT64 s_prev_alt_ft = 0.0;
            static FLOAT64 s_alt_trend   = 0.0;
            const FLOAT64 raw_trend = alt_ft - s_prev_alt_ft;
            s_alt_trend = s_alt_trend * 0.95 + raw_trend * 0.05;
            s_prev_alt_ft = alt_ft;
            lvar_write(LVAR_TAPE_ALT_TREND, s_alt_trend);
        }
    }

    // v3.4.0 — Frame pacing (GROUP C)
    lvar_write(LVAR_PACING_CONTINUITY,    g_state.pacing.continuity_metric);
    lvar_write(LVAR_PACING_ANOMALY_COUNT, (FLOAT64)g_state.pacing.anomaly_count);
    lvar_write(LVAR_PACING_IN_RECOVERY,   g_state.pacing.in_recovery ? 1.0 : 0.0);
    lvar_write(LVAR_PACING_STABLE_FRAMES, (FLOAT64)g_state.pacing.consecutive_stable_frames);

    // v3.4.0 — Optical stability (GROUP D)
    lvar_write(LVAR_OPTIC_STABILITY_SCORE, g_state.optic_stability.optical_stability_score);
    lvar_write(LVAR_OPTIC_SHIMMER_LEVEL,   g_state.optic_stability.shimmer_accumulator);
    lvar_write(LVAR_OPTIC_FATIGUE,         g_state.optic_stability.current_fatigue);
    lvar_write(LVAR_OPTIC_PHOSPHOR_SMEAR,  g_state.optic_stability.phosphor_smear_amount);

    //  13.  SUBSYSTEM HEARTBEATS
    // ================================================================
    lvar_write(LVAR_HB_FPV,          (FLOAT64)g_hud.hb_fpv);
    lvar_write(LVAR_HB_GUIDANCE,     (FLOAT64)g_hud.hb_guidance);
    lvar_write(LVAR_HB_RUNWAY,       (FLOAT64)g_hud.hb_runway);
    lvar_write(LVAR_HB_FLARE,        (FLOAT64)g_hud.hb_flare);
    lvar_write(LVAR_HB_EVS,          (FLOAT64)g_hud.hb_evs);
    lvar_write(LVAR_HB_COLLIMATION,  (FLOAT64)g_hud.hb_collimation);
    lvar_write(LVAR_HB_STABILIZATION,(FLOAT64)g_hud.hb_stabilization);
    lvar_write(LVAR_HB_ADVANCED,     (FLOAT64)g_hud.hb_advanced);
    lvar_write(LVAR_HB_ROLLOUT,      (FLOAT64)g_hud.hb_rollout);

    // ================================================================
    //  14.  WATCHDOG — Detect silent subsystem failures
    // ================================================================
    {
        // Heartbeat tick table indexed by subsystem
        const int hb_now[9] = {
            g_hud.hb_fpv,
            g_hud.hb_guidance,
            g_hud.hb_runway,
            g_hud.hb_flare,
            g_hud.hb_evs,
            g_hud.hb_collimation,
            g_hud.hb_stabilization,
            g_hud.hb_advanced,
            g_hud.hb_rollout
        };
        const char* hb_names[9] = {
            "FPV", "GUIDANCE", "RUNWAY", "FLARE",
            "EVS", "COLLIMATION", "STABILIZATION", "ADVANCED", "ROLLOUT"
        };

        for (int i = 0; i < 9; ++i) {
            if (g_hud.wd_ticks[i] == hb_now[i]) {
                g_hud.wd_stalled[i]++;
                if (g_hud.wd_stalled[i] == 60) {  // 1 second stall at 60 fps
                    MSFS_Log("[C_HUD] WATCHDOG: %s heartbeat stalled for 60 frames!",
                             hb_names[i]);
                    g_hud.wd_total_failures++;
                }
            } else {
                g_hud.wd_stalled[i] = 0;
            }
            g_hud.wd_ticks[i] = hb_now[i];
        }

        // Log aggregate watchdog status every 60 frames
        if ((g_state.frame_counter % 60) == 0 && g_hud.wd_total_failures > 0) {
            MSFS_Log("[C_HUD] WATCHDOG: %d total subsystem failures detected",
                     g_hud.wd_total_failures);
        }
    }

    // ================================================================
    //  15.  v2.5.0 — Behavior + telemetry L:vars
    // ================================================================
    {
        if (g_behavior) {
            lvar_write(LVAR_A350_PROFILE_ACTIVE,
                       (g_behavior->category() == HudAircraftCategory::AIRBUS_HUD) ? 1.0 : 0.0);
        }

        // Telemetry status
        lvar_write((LVarID)(LVAR_A350_FPV_SMOOTHING),  // reuse as telemetry recording flag
                   telemetry_recorder_is_recording(&g_telemetry) ? 1.0 : 0.0);
    }

    // v2.6.0 — Record publish phase timing
    {
        const FLOAT64 _elapsed = g_state.perf.frame_end_us - g_state.perf.frame_start_us;
        perf_measure(&g_state.perf, SUBSYS_SYM_PUBLISH, _elapsed * 0.08, g_state.frame_counter);
    }

    // v2.6.0 — Periodic percentile update (every 60 frames)
    if ((g_state.frame_counter % 60) == 0) {
        for (int _i = 0; _i < SUBSYS_COUNT; ++_i) {
            percentile_compute(&g_state.perf.subsystems[_i].hist);
        }
    }
}
