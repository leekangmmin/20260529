#ifndef C_HUD_RUNWAY_MODULE_H
#define C_HUD_RUNWAY_MODULE_H

// ============================================================================
//  Conformal HUD – Boeing HGS-style Guidance  |  WASM gauge module header
//  MSFS SDK 0.23+  ·  C++17  ·  v2.7.0 — ROLLOUT/CAT-III/EVS ENHANCEMENT
//
//  Core types and state for the conformal HUD system.
//  v2.7.0: Added rollout rendering L:Vars, CAT III annunciation L:Vars,
//          EVS visualization L:Vars, dead code deprecation marks.
// ============================================================================

#include <MSFS/MSFS.h>
#include <MSFS/Legacy/gauges.h>

#ifdef C_HUD_USE_NANOVG
    #include <nanovg.h>
#endif

// ============================================================================
//  1.  Compile-time constants
// ============================================================================

#define C_HUD_MAX_RUNWAY_VERTS  16
#define C_HUD_SIMVAR_NAME_MAX   64
#define C_HUD_PANEL_WIDTH       1024
#define C_HUD_PANEL_HEIGHT      1024
#define C_HUD_F64_NAN           (0.0 / 0.0)
#define C_HUD_AIRCRAFT_ID_MAX   64
#define C_HUD_ILS_HISTORY       8
#define C_HUD_VIS_MAX_M         30000.0
#define C_HUD_VIS_MIN_M         200.0

#define C_HUD_LVAR_COUNT        200  // Max L:var tokens in the table (v2.4.0 expanded)

// v2.6.0 — Timing histogram config
#define C_HUD_PERF_HIST_BINS    32
#define C_HUD_PERF_MAX_HISTORY  1024  // rolling window sample count for percentiles

// ============================================================================
//  2.  POD types
// ============================================================================

typedef struct Vec3 {
    FLOAT64 x;
    FLOAT64 y;
    FLOAT64 z;
} Vec3;

typedef struct Mat4 {
    FLOAT64 m[16];
} Mat4;

typedef struct Vec2 {
    FLOAT64 x;
    FLOAT64 y;
} Vec2;

typedef struct RunwayVertex {
    Vec3    world_pos;
    Vec2    screen_pos;
    bool    behind_camera;
} RunwayVertex;

typedef struct RunwayGeometry {
    RunwayVertex  verts[C_HUD_MAX_RUNWAY_VERTS];
    int           vert_count;
    bool          valid;
} RunwayGeometry;

typedef struct EMASmooth {
    FLOAT64 value;
    FLOAT64 alpha;
    bool    initialised;
} EMASmooth;

typedef struct ILSFilter {
    EMASmooth gs;
    EMASmooth loc;
} ILSFilter;

typedef struct WeatherState {
    FLOAT64 visibility_m;
    FLOAT64 line_width_px;
    FLOAT64 opacity;
    bool    valid;
} WeatherState;

// ============================================================================
//  2b.  Calibration state (v2.2.0)
// ============================================================================

typedef struct HUDSettings {
    FLOAT64 center_offset_x;
    FLOAT64 center_offset_y;
    FLOAT64 combiner_offset_x;
    FLOAT64 combiner_offset_y;
    FLOAT64 combiner_scale_w;
    FLOAT64 combiner_scale_h;
    FLOAT64 eye_offset_forward_m;
    FLOAT64 eye_offset_right_m;
    FLOAT64 eye_offset_down_m;
    FLOAT64 fov_scale;
    FLOAT64 projection_scale_x;
    FLOAT64 projection_scale_y;
    FLOAT64 optical_gain;
    FLOAT64 fpv_align_x;
    FLOAT64 fpv_align_y;
    FLOAT64 runway_align_offset;
    FLOAT64 flare_cue_pos_offset;
    FLOAT64 horizon_line_offset;
    int     active_profile_slot;
    bool    dirty;
} HUDSettings;

// ============================================================================
//  2c.  Verification / Debug overlay state (v2.2.0)
// ============================================================================

typedef struct DebugOverlay {
    bool show_runway_corners;
    bool show_world_axes;
    bool show_fpv_trace;
    bool show_guidance_beam;
    bool show_clipping;
    bool show_optical_center;
    bool show_collimation_vectors;
    bool show_timing_overlay;     // v2.6.0 — Show runtime timing overlay
    bool show_histogram;          // v2.6.0 — Show timing histogram
} DebugOverlay;

// ============================================================================
//  2d.  Optical realism state (v2.2.0)
// ============================================================================

typedef struct OpticalState {
    FLOAT64 phosphor_decay;
    FLOAT64 bloom_amount;
    FLOAT64 luminance_gain;
    FLOAT64 brightness_auto_gain;
    FLOAT64 edge_fade_amount;
    FLOAT64 temporal_blend_factor;
    FLOAT64 phosphor_buffer[64];
    FLOAT64 current_brightness;
} OpticalState;

// ============================================================================
//  2e.  Subsystem timing infrastructure (v2.6.0 — Runtime instrumentation)
// ============================================================================

/// Identifiers for every measurable subsystem.
typedef enum SubsystemID {
    SUBSYS_SIMVAR_READ     = 0,
    SUBSYS_FPV             = 1,
    SUBSYS_GUIDANCE        = 2,
    SUBSYS_RUNWAY_PROJ     = 3,
    SUBSYS_FLARE           = 4,
    SUBSYS_ROLLOUT         = 5,
    SUBSYS_COLLIMATION     = 6,
    SUBSYS_EVS             = 7,
    SUBSYS_STABILIZATION   = 8,
    SUBSYS_ADV_SYMBOLOGY   = 9,
    SUBSYS_CONFIDENCE      = 10,
    SUBSYS_DECLUTTER       = 11,
    SUBSYS_OPTICAL         = 12,
    SUBSYS_SYM_PUBLISH     = 13,
    SUBSYS_TELEMETRY       = 14,
    SUBSYS_TOTAL           = 15,  // Total frame time
    SUBSYS_JS_BRIDGE       = 16,  // JS bridge latency
    SUBSYS_COUNT           = 17
} SubsystemID;

/// Human-readable names for each subsystem.
static inline const char* subsystem_name(SubsystemID id) {
    static const char* names[] = {
        "SimVarRead", "FPV", "Guidance", "RunwayProj",
        "Flare", "Rollout", "Collimation", "EVS",
        "Stabilization", "AdvSymbology", "Confidence", "Declutter",
        "Optical", "SymPublish", "Telemetry", "TotalFrame", "JSBridge"
    };
    if (id >= 0 && id < SUBSYS_COUNT) return names[id];
    return "Unknown";
}

/// A single timing sample in the rolling window.
typedef struct TimingSample {
    FLOAT64 us;             // Execution time in microseconds
    int     frame_index;    // Frame counter when sampled
} TimingSample;

/// Rolling-window histogram for one subsystem (v2.6.0).
typedef struct SubsystemHistogram {
    // --- Rolling window of raw samples for percentile computation ---
    TimingSample samples[C_HUD_PERF_MAX_HISTORY];
    int          sample_write_pos;
    int          sample_count;

    // --- Running statistics ---
    FLOAT64 running_sum_us;
    FLOAT64 running_sum_sq_us;
    FLOAT64 min_us;
    FLOAT64 max_us;
    int     total_frames_measured;

    // --- Percentile cache (updated every N frames) ---
    FLOAT64 p50_us;
    FLOAT64 p95_us;
    FLOAT64 p99_us;
    int     last_percentile_update;

    // --- Histogram bins (for visualization) ---
    int     bins[C_HUD_PERF_HIST_BINS];
    FLOAT64 bin_lower[C_HUD_PERF_HIST_BINS];
    FLOAT64 bin_upper[C_HUD_PERF_HIST_BINS];

    bool    valid;
} SubsystemHistogram;

/// Per-subsystem timing overhead measurement (v2.6.0).
typedef struct SubsystemTiming {
    SubsystemHistogram hist;
    FLOAT64            last_us;       // Most recent sample
    FLOAT64            peak_us;       // All-time peak
    FLOAT64            budget_us;     // Budget for this subsystem
    bool               over_budget;   // True if last sample exceeded budget
} SubsystemTiming;

/// Complete runtime performance state (v2.6.0).
typedef struct PerfState {
    SubsystemTiming subsystems[SUBSYS_COUNT];
    FLOAT64         frame_start_us;       // Timestamp when frame began
    FLOAT64         frame_end_us;         // Timestamp when frame ended
    FLOAT64         js_bridge_latency_us;  // Measured JS bridge round-trip
    bool            enabled;              // True when instrumentation active
    bool            frame_active;         // True during frame measurement
} PerfState;

// ============================================================================
//  2f.  Frame pacing anomaly detection (v2.6.0)
// ============================================================================

/// Types of frame pacing anomalies we can detect.
typedef enum PacingAnomalyType {
    ANOMALY_NONE          = 0,
    ANOMALY_HITCH         = 1,   // Single-frame spike > 50ms
    ANOMALY_STUTTER       = 2,   // Repeated small spikes
    ANOMALY_PAUSE         = 3,   // Sim pause detected
    ANOMALY_FOCUS_LOSS    = 4,   // Window focus lost
    ANOMALY_MENU_OVERLAY  = 5,   // Menu overlay interruption
    ANOMALY_AIRCRAFT_LOAD = 6,   // Aircraft reload transition
} PacingAnomalyType;

/// Anomaly event log entry.
typedef struct PacingAnomalyEvent {
    PacingAnomalyType type;
    int     frame_index;
    FLOAT64 timestamp_s;
    FLOAT64 duration_ms;
    FLOAT64 recovery_ms;
} PacingAnomalyEvent;

/// Frame pacing validation state.
typedef struct PacingState {
    // --- Detection ---
    FLOAT64 expected_frame_interval_ms;   // Expected ~16.67ms at 60fps
    FLOAT64 hitch_threshold_ms;           // > this = hitch
    FLOAT64 stutter_threshold_ms;         // > this = stutter concern

    // --- Rolling metrics ---
    FLOAT64 dt_history[60];               // Last 60 frame intervals
    int     dt_write_pos;
    int     dt_sample_count;
    FLOAT64 dt_min;
    FLOAT64 dt_max;
    FLOAT64 dt_mean;
    FLOAT64 dt_stddev;

    // --- Anomaly tracking ---
    PacingAnomalyEvent anomalies[32];     // Circular anomaly log
    int anomaly_write_pos;
    int anomaly_count;

    // --- Recovery state ---
    bool    in_recovery;                  // Currently recovering from anomaly
    int     recovery_frames;              // Frames since recovery start
    bool    stabilization_reset_pending;  // Reset stabilization on recovery

    // --- Temporal continuity ---
    FLOAT64 continuity_metric;            // 0..1 — 1 = perfectly smooth
    int     consecutive_stable_frames;    // For stability scoring

    bool    valid;
} PacingState;

// ============================================================================
//  2g.  Aircraft compatibility signature (v2.6.0)
// ============================================================================

/// Known aircraft with compatibility metadata.
typedef struct AircraftCompatibilitySignature {
    const char* aircraft_prefix;          // Title prefix for matching
    int         profile_index;            // HUDProfile index
    uint32_t    version_major;            // Known good version major
    uint32_t    version_minor;            // Known good version minor
    bool        requires_panel_fix;       // True if panel.cfg needs adjustment
    bool        requires_eye_offset;      // True if eye position needs offset
    FLOAT64     eye_offset_correction_m;  // Vertical eye offset correction
    bool        optical_center_verified;  // True if optical center validated
    FLOAT64     optical_center_cx;        // Verified optical center X
    FLOAT64     optical_center_cy;        // Verified optical center Y
} AircraftCompatibilitySignature;

// ============================================================================
//  2h.  Optical stability metrics (v2.6.0)
// ============================================================================

typedef struct OpticalStabilityMetrics {
    // --- Shimmer detection ---
    FLOAT64 shimmer_accumulator;         // Accumulated high-frequency deviation
    int     shimmer_sample_count;        // Samples in window
    FLOAT64 shimmer_threshold;           // Threshold to flag shimmer

    // --- Visual fatigue ---
    FLOAT64 fatigue_accumulator;         // Fatigue build-up over time
    FLOAT64 fatigue_decay_rate;          // Recovery rate
    FLOAT64 current_fatigue;             // 0..1 current fatigue level

    // --- Phosphor smearing ---
    FLOAT64 phosphor_smear_amount;       // Measured smearing
    int     phosphor_exceedance_count;   // Times phosphor exceeded limit

    // --- Overall stability score ---
    FLOAT64 optical_stability_score;     // 0..1 — 1 = perfectly stable

    bool    valid;
} OpticalStabilityMetrics;

// ============================================================================
//  2i.  L:Var ID table (v2.2.0, expanded v2.4.0, v2.7.0)
// ============================================================================

typedef enum LVarID {
    LVAR_VERSION,
    LVAR_FRAME,
    LVAR_FPS,
    LVAR_FPS_MIN,
    LVAR_FPS_MAX,
    LVAR_FPS_AVG,
    LVAR_JITTER_MS,
    LVAR_INIT,

    LVAR_HUD_ACTIVE,
    LVAR_SCREEN_CX,
    LVAR_SCREEN_CY,
    LVAR_WEATHER_LINE_W,
    LVAR_WEATHER_ALPHA,
    LVAR_ILS_GS,
    LVAR_ILS_LOC,
    LVAR_CDI_GS,
    LVAR_CDI_LOC,

    // Runway vertex L:vars (16 verts → 32 X/Y L:vars)
    LVAR_RWY_VERT_COUNT,
    LVAR_RWY_V0_X,  LVAR_RWY_V0_Y,
    LVAR_RWY_V1_X,  LVAR_RWY_V1_Y,
    LVAR_RWY_V2_X,  LVAR_RWY_V2_Y,
    LVAR_RWY_V3_X,  LVAR_RWY_V3_Y,
    LVAR_RWY_V4_X,  LVAR_RWY_V4_Y,
    LVAR_RWY_V5_X,  LVAR_RWY_V5_Y,
    LVAR_RWY_V6_X,  LVAR_RWY_V6_Y,
    LVAR_RWY_V7_X,  LVAR_RWY_V7_Y,

    // FPV
    LVAR_FPV_X,
    LVAR_FPV_Y,
    LVAR_FPV_ONSCREEN,
    LVAR_FPV_DRIFT,
    LVAR_FPV_PITCH,

    // Horizon
    LVAR_HORIZON_Y,
    LVAR_HORIZON_SLOPE,
    LVAR_HORIZON_VALID,

    // Pitch ladder
    LVAR_PITCH_COUNT,
    LVAR_PITCH_Y_0,
    LVAR_PITCH_Y_1,
    LVAR_PITCH_Y_2,
    LVAR_PITCH_Y_3,
    LVAR_PITCH_Y_4,

    // Guidance
    LVAR_GS_TARGET_X,
    LVAR_GS_TARGET_Y,
    LVAR_LOC_TARGET_X,
    LVAR_LOC_TARGET_Y,
    LVAR_LOC_CAPTURED,
    LVAR_GS_CAPTURED,
    LVAR_STEER_PITCH,
    LVAR_STEER_BANK,

    // Combiner
    LVAR_COMB_X,
    LVAR_COMB_Y,
    LVAR_COMB_W,
    LVAR_COMB_H,

    // Drift
    LVAR_DRIFT_ANGLE,
    LVAR_DRIFT_CUE_X,
    LVAR_DRIFT_CUE_Y,

    // Flare guidance
    LVAR_FLARE_ACTIVE,
    LVAR_FLARE_FULL_ACTIVE,
    LVAR_FLARE_CUE_X,
    LVAR_FLARE_CUE_Y,
    LVAR_FLARE_CUE_SIZE,
    LVAR_FLARE_CUE_ALPHA,
    LVAR_FLARE_RISE,
    LVAR_FLARE_ERROR,
    LVAR_FLARE_VS_CMD,
    LVAR_TDZ_VISIBLE,
    LVAR_TDZ_X,
    LVAR_TDZ_Y,
    LVAR_TDZ_SIZE,

    // Collimation
    LVAR_COLL_ACTIVE,
    LVAR_COLL_CORR_MAG,
    LVAR_COLL_CORR_X,
    LVAR_COLL_CORR_Y,
    LVAR_COLL_CORR_Z,
    LVAR_COLL_GAIN,
    LVAR_COLL_DELTA_X,
    LVAR_COLL_DELTA_Y,
    LVAR_COLL_DELTA_Z,

    // --- EVS ---
    LVAR_EVS_ACTIVE,
    LVAR_EVS_INTENSITY,
    LVAR_EVS_CONTRAST,
    LVAR_EVS_GLOW,
    LVAR_EVS_RUNWAY_BOOST,

    // --- Advanced symbology ---
    LVAR_ACCEL_DOTS,
    LVAR_ACCEL_X,
    LVAR_ACCEL_Y,
    LVAR_ENERGY_DOTS,
    LVAR_ENERGY_Y,
    LVAR_FLARE_BR_VISIBLE,
    LVAR_FLARE_BR_VISIBILITY,
    LVAR_FLARE_BR_SIZE,
    LVAR_FLARE_BR_ALT_ERR,
    LVAR_TD_PRED_VALID,
    LVAR_TD_PRED_X,
    LVAR_TD_PRED_Y,
    LVAR_TD_PRED_RANGE,
    LVAR_TD_PRED_CONFIDENCE,
    LVAR_VTREND_DIR,
    LVAR_VTREND_MAG,

    // --- Calibration ---
    LVAR_CALIB_CENTER_X,
    LVAR_CALIB_CENTER_Y,
    LVAR_CALIB_FOV,
    LVAR_CALIB_EYE_FWD,
    LVAR_CALIB_EYE_RIGHT,
    LVAR_CALIB_EYE_DOWN,
    LVAR_CALIB_SCALE_X,
    LVAR_CALIB_SCALE_Y,
    LVAR_CALIB_OPTICAL_GAIN,
    LVAR_CALIB_FPV_ALIGN_X,
    LVAR_CALIB_FPV_ALIGN_Y,
    LVAR_CALIB_RWY_ALIGN,
    LVAR_CALIB_FLARE_POS,
    LVAR_CALIB_HORIZON_OFFSET,

    // --- Verification / Debug ---
    LVAR_DEBUG_SHOW_RWY_CORNERS,
    LVAR_DEBUG_SHOW_AXES,
    LVAR_DEBUG_SHOW_FPV_TRACE,
    LVAR_DEBUG_SHOW_GUIDANCE_BEAM,
    LVAR_DEBUG_SHOW_CLIP,
    LVAR_DEBUG_SHOW_OPTICAL_CENTER,
    LVAR_DEBUG_SHOW_COLLIMATION,
    LVAR_DEBUG_SHOW_TIMING,      // v2.6.0
    LVAR_DEBUG_SHOW_HISTOGRAM,   // v2.6.0

    // --- Optical realism ---
    LVAR_OPTICS_PHOSPHOR,
    LVAR_OPTICS_BLOOM,
    LVAR_OPTICS_LUMINANCE,
    LVAR_OPTICS_BRIGHTNESS,
    LVAR_OPTICS_EDGE_FADE,
    LVAR_OPTICS_TEMPORAL_BLEND,

    // --- Subsystem heartbeats ---
    LVAR_HB_FPV,
    LVAR_HB_GUIDANCE,
    LVAR_HB_RUNWAY,
    LVAR_HB_FLARE,
    LVAR_HB_EVS,
    LVAR_HB_COLLIMATION,
    LVAR_HB_STABILIZATION,
    LVAR_HB_ADVANCED,
    LVAR_HB_ROLLOUT,      // v2.7.0 — Rollout subsystem heartbeat

    // ================================================================
    //  v2.4.0 — Rollout guidance L:vars
    // ================================================================
    LVAR_ROLL_PHASE,
    LVAR_ROLL_ACTIVE,
    LVAR_ROLL_CENTERLINE_X,
    LVAR_ROLL_CENTERLINE_Y,
    LVAR_ROLL_CENTERLINE_W,
    LVAR_ROLL_CENTERLINE_ALPHA,
    LVAR_ROLL_STEERING,
    LVAR_ROLL_DAMPING,
    LVAR_ROLL_CONFIDENCE,
    LVAR_ROLL_NOSEWHEEL,
    LVAR_ROLL_TRANSITION,
    LVAR_ROLL_BRAKE_ADVISORY,
    LVAR_ROLL_DECEL_CUE_X,
    LVAR_ROLL_DECEL_CUE_ALPHA,
    LVAR_ROLL_COMPRESSION,

    // ================================================================
    //  v2.7.0 — Rollout rendering L:vars (Boeing HGS style)
    // ================================================================
    LVAR_ROLL_CENTERLINE,      // L:C_HUD_Roll_Centerline — centerline tracking cue pos (composite 0..1)
    LVAR_ROLL_DEVIATION,       // L:C_HUD_Roll_Deviation — lateral deviation indicator (-1..1)
    LVAR_ROLL_COMMAND,         // L:C_HUD_Roll_Command — steering command indicator (-1..1)

    // ================================================================
    //  v2.4.0 — Visual response L:vars
    // ================================================================
    LVAR_VIS_ACTIVE,
    LVAR_VIS_DARK_ADAPT,
    LVAR_VIS_BLOOM,
    LVAR_VIS_RAIN_GLARE,
    LVAR_VIS_PHOSPHOR_MS,
    LVAR_VIS_BRIGHTNESS,
    LVAR_VIS_CONTRAST,
    LVAR_VIS_FATIGUE,

    // ================================================================
    //  v2.4.0 — Declutter L:vars
    // ================================================================
    LVAR_DCL_PHASE,
    LVAR_DCL_VISIBLE_COUNT,
    LVAR_DCL_ACTIVE,

    // ================================================================
    //  v2.4.0 — Confidence / Depth L:vars
    // ================================================================
    LVAR_CONF_INTEGRITY,
    LVAR_CONF_CATIII,
    LVAR_CONF_LOC_MODE,
    LVAR_CONF_GS_MODE,
    LVAR_CONF_LOC_ALPHA,
    LVAR_CONF_GS_ALPHA,
    LVAR_DEPTH_ACTIVE,
    LVAR_DEPTH_INTENSITY,

    // ================================================================
    //  v2.4.0 — Airbus A350-specific L:vars
    // ================================================================
    LVAR_A350_FLARE_GAIN,
    LVAR_A350_FPV_SMOOTHING,
    LVAR_A350_CAT3_CONFIDENCE,
    LVAR_A350_RUNWAY_STABILITY,
    LVAR_A350_ROLLOUT_DAMPING,
    LVAR_A350_PROFILE_ACTIVE,
    LVAR_A350_CAT3_ENHANCED,
    LVAR_A350_FPV_PREDICTIVE,
    LVAR_A350_FLARE_SOFTNESS,
    LVAR_A350_DECLUTTER_AGGRESSIVE,
    LVAR_A350_SYM_PERSISTENCE,
    LVAR_A350_HORIZON_STABILITY,
    LVAR_A350_BLOOM_REDUCTION,
    LVAR_A350_ANTI_SHIMMER,
    LVAR_A350_ROLLOUT_CROSSWIND,
    LVAR_A350_ROLLOUT_WET_ASSIST,

    // ================================================================
    //  v2.7.0 — CAT III Annunciation L:vars
    // ================================================================
    LVAR_CAT_CATEGORY,         // L:C_HUD_CAT_Category — 0=none, 2=CATII, 3=CATIIIA, 4=CATIIIB
    LVAR_LAND_MODE,            // L:C_HUD_LAND_Mode — 0=none, 2=LAND2, 3=LAND3
    LVAR_FLARE_ANNOUNCE,       // L:C_HUD_FLARE_Announce — 1 when FLARE annunciated
    LVAR_ROLLOUT_ANNOUNCE,     // L:C_HUD_ROLLOUT_Announce — 1 when ROLLOUT annunciated
    LVAR_NO_DH,                // L:C_HUD_NO_DH — 1 when NO DH mode active

    // ================================================================
    //  v2.7.0 — EVS Visualization L:vars
    // ================================================================
    LVAR_EVS_ACTIVE_BOX,       // L:C_HUD_EVS_ActiveBox — 1 when EVS active box should show
    LVAR_EVS_CONTRAST_CUE,     // L:C_HUD_EVS_ContrastCue — EVS contrast cue level (0..1)
    LVAR_EVS_VIS_IND,          // L:C_HUD_EVS_VisibilityInd — visibility indication text on/off

    // ================================================================
    //  v2.6.0 — Runtime instrumentation L:vars
    // ================================================================
    LVAR_PERF_FRAME_TOTAL_US,
    LVAR_PERF_SIMVAR_READ_US,
    LVAR_PERF_FPV_US,
    LVAR_PERF_GUIDANCE_US,
    LVAR_PERF_RUNWAY_PROJ_US,
    LVAR_PERF_FLARE_US,
    LVAR_PERF_ROLLOUT_US,
    LVAR_PERF_COLLIMATION_US,
    LVAR_PERF_EVS_US,
    LVAR_PERF_STABILIZATION_US,
    LVAR_PERF_ADV_SYMBOLOGY_US,
    LVAR_PERF_CONFIDENCE_US,
    LVAR_PERF_DECLUTTER_US,
    LVAR_PERF_OPTICAL_US,
    LVAR_PERF_SYM_PUBLISH_US,
    LVAR_PERF_TELEMETRY_US,
    LVAR_PERF_JS_BRIDGE_US,
    LVAR_PERF_P50_US,
    LVAR_PERF_P95_US,
    LVAR_PERF_P99_US,
    LVAR_PERF_BUDGET_OK,
    LVAR_PERF_OVER_BUDGET_COUNT,

    // ================================================================
    //  v2.6.0 — Frame pacing L:vars
    // ================================================================
    LVAR_PACING_CONTINUITY,
    LVAR_PACING_ANOMALY_COUNT,
    LVAR_PACING_IN_RECOVERY,
    LVAR_PACING_STABLE_FRAMES,
    LVAR_PACING_ANOMALY_TYPE,

    // ================================================================
    //  v2.6.0 — Aircraft compatibility L:vars
    // ================================================================
    LVAR_COMPAT_SIGNATURE,
    LVAR_COMPAT_VERSION_MAJOR,
    LVAR_COMPAT_VERSION_MINOR,
    LVAR_COMPAT_SUPPORTED,
    LVAR_COMPAT_SELF_REPAIR,
    LVAR_COMPAT_FALLBACK_ACTIVE,

    // ================================================================
    //  v2.6.0 — Optical stability L:vars
    // ================================================================
    LVAR_OPTIC_STABILITY_SCORE,
    LVAR_OPTIC_SHIMMER_LEVEL,
    LVAR_OPTIC_FATIGUE,
    LVAR_OPTIC_PHOSPHOR_SMEAR,

    // ================================================================
    //  v2.6.0 — Long-duration stability L:vars
    // ================================================================
    LVAR_STABLE_MEMORY_KB,
    LVAR_STABLE_TIMING_DRIFT_US,
    LVAR_STABLE_TELEMETRY_CHECKSUM,
    LVAR_STABLE_RUNTIME_S,
    LVAR_STABLE_SUBSYS_STALLS,

    // ================================================================
    //  v2.6.0 — Certification mode L:vars
    // ================================================================
    LVAR_CERT_MODE_ACTIVE,
    LVAR_CERT_SCENARIO_SCORE,
    LVAR_CERT_AIRCRAFT_SCORE,
    LVAR_CERT_REGRESSION_DETECTED,
    LVAR_CERT_RELEASE_READY,
    LVAR_CERT_TOTAL_SCORE,

    // ================================================================
    //  v3.0.0 — A350 XWB Certification Package L:vars
    // ================================================================
    LVAR_A350_HUD_FPV_STABILITY,       // L:A350_HUD_FPV_STABILITY — 0..1 FPV stability score
    LVAR_A350_HUD_RUNWAY_CONFIDENCE,   // L:A350_HUD_RUNWAY_CONFIDENCE — 0..1 runway confidence
    LVAR_A350_HUD_AUTOLAND_CONFIDENCE, // L:A350_HUD_AUTOLAND_CONFIDENCE — 0..1 autoland confidence
    LVAR_A350_HUD_FLARE_ASSIST,        // L:A350_HUD_FLARE_ASSIST — 0..1 flare assist level
    LVAR_A350_HUD_ROLLOUT_STABILITY,   // L:A350_HUD_ROLLOUT_STABILITY — 0..1 rollout stability
    LVAR_A350_HUD_TURBULENCE_DAMPING,  // L:A350_HUD_TURBULENCE_DAMPING — 0..1 turbulence damping
    LVAR_A350_HUD_OPTICAL_STABILITY,   // L:A350_HUD_OPTICAL_STABILITY — 0..1 optical stability
    LVAR_A350_HUD_CAT3_STATE,          // L:A350_HUD_CAT3_STATE — CAT III state (0=NONE, 1=IIIA, 2=IIIB, 3=IIIC)
    LVAR_A350_HUD_ENERGY_SCORE,        // L:A350_HUD_ENERGY_SCORE — 0..1 landing energy score
    LVAR_A350_HUD_FLARE_AGGRESSIVENESS, // L:A350_HUD_FLARE_AGGRESSIVENESS — 0..1 flare aggressiveness

    // ================================================================
    //  PHASE 4 — Real HUD Integration L:vars
    // ================================================================
    LVAR_HUD_DEPLOY_PHASE,      // L:C_HUD_Deploy_Phase — 0=unknown, 1=stowed, 2=transition, 3=deployed
    LVAR_HUD_DEPLOY_FRACTION,   // L:C_HUD_Deploy_Fraction — 0.0 .. 1.0
    LVAR_HUD_DEPLOY_POWER,      // L:C_HUD_Deploy_Power — 1 when HUD powered
    LVAR_COMB_SCREEN_X,         // L:C_HUD_CombinerScreenX — combiner left edge (screen px)
    LVAR_COMB_SCREEN_Y,         // L:C_HUD_CombinerScreenY — combiner top edge (screen px)
    LVAR_COMB_SCREEN_W,         // L:C_HUD_CombinerScreenW — combiner width (screen px)
    LVAR_COMB_SCREEN_H,         // L:C_HUD_CombinerScreenH — combiner height (screen px)
    LVAR_OPTICAL_CX,            // L:C_HUD_OpticalCX — optical centre X (screen px)
    LVAR_OPTICAL_CY,            // L:C_HUD_OpticalCY — optical centre Y (screen px)
    LVAR_COLL_SCREEN_DX,        // L:C_HUD_Coll_ScreenDX — collimation delta X (px)
    LVAR_COLL_SCREEN_DY,        // L:C_HUD_Coll_ScreenDY — collimation delta Y (px)
    LVAR_HUD_RENDER_IN_COMBINER,// L:C_HUD_RenderInCombiner — 1 when clipped to combiner
    LVAR_HUD_COLLIMATED,        // L:C_HUD_Collimated — 1 when collimation active

    // ================================================================
    //  v3.1.0 — Speed and altitude tape L:vars
    // ================================================================
    LVAR_TAPE_IAS_KT,           // L:C_HUD_Tape_IAS_kt — indicated airspeed (knots)
    LVAR_TAPE_ALT_FT,           // L:C_HUD_Tape_Alt_ft — altitude (feet)
    LVAR_TAPE_VS_FPM,           // L:C_HUD_Tape_VS_fpm — vertical speed (fpm)
    LVAR_TAPE_IAS_TREND,        // L:C_HUD_Tape_IAS_Trend — IAS trend (knots/frame, EMA)
    LVAR_TAPE_ALT_TREND,        // L:C_HUD_Tape_Alt_Trend — altitude trend (ft/frame, EMA)
    LVAR_TAPE_SPEED_ACTIVE,     // L:C_HUD_Tape_Speed_Active — 1 when speed tape active
    LVAR_TAPE_ALT_ACTIVE,       // L:C_HUD_Tape_Alt_Active — 1 when altitude tape active
    LVAR_COUNT  // Must be last — total number of L:vars
} LVarID;

// ============================================================================
//  3.  Module state (v2.2.0 + v2.6.0)
// ============================================================================

typedef struct ModuleState {
    bool        initialised;
    bool        module_load_complete;
    int         frame_counter;
    bool        sim_paused;
    bool        sim_pause_just_resumed;
    int         sim_pause_counter;
    int         sim_pause_frame;

    // --- SimVar tokens (resolved via gauge_get_var_by_name) ---
    GAUGE_VAR   tok_plane_lat;
    GAUGE_VAR   tok_plane_lon;
    GAUGE_VAR   tok_plane_hdg;
    GAUGE_VAR   tok_plane_alt;
    GAUGE_VAR   tok_plane_pitch;
    GAUGE_VAR   tok_plane_bank;

    GAUGE_VAR   tok_hud_power;
    GAUGE_VAR   tok_aircraft_title;
    bool        hud_power_on;
    char        aircraft_id[C_HUD_AIRCRAFT_ID_MAX];
    bool        hud_allowed;

    GAUGE_VAR   tok_nav_gs_error;
    GAUGE_VAR   tok_nav_loc_error;
    ILSFilter   ils_filter;

    GAUGE_VAR   tok_ambient_vis;
    WeatherState weather;

    GAUGE_VAR   tok_screen_cx;   // legacy L:C_HUD_ScreenCX
    GAUGE_VAR   tok_screen_cy;   // legacy L:C_HUD_ScreenCY

    // --- Runway box vertex output L:vars (L:C_HUD_RunwayV0..7_X / _Y) ---
    GAUGE_VAR   tok_runway_vx[8];
    GAUGE_VAR   tok_runway_vy[8];

    // --- Pitch ladder line output L:vars (L:C_HUD_PitchLadder_0..4_Y) ---
    GAUGE_VAR   tok_pitch_line_y[5];

    // --- v2.0: FPV / guidance SimVar tokens ---
    GAUGE_VAR   tok_groundspeed;
    GAUGE_VAR   tok_true_airspeed;
    GAUGE_VAR   tok_vertical_speed;
    GAUGE_VAR   tok_track;

    // --- v2.1.0: Additional SimVar tokens ---
    GAUGE_VAR   tok_radio_height;
    GAUGE_VAR   tok_accel;
    GAUGE_VAR   tok_indicated_airspeed;
    GAUGE_VAR   tok_on_ground;

    // --- v3.1.0: Live eyepoint position (meters, body frame from design eye) ---
    GAUGE_VAR   tok_eyepoint_x;   // EYEPOINT POSITION X  (right,  meters)
    GAUGE_VAR   tok_eyepoint_y;   // EYEPOINT POSITION Y  (up,     meters)
    GAUGE_VAR   tok_eyepoint_z;   // EYEPOINT POSITION Z  (forward,meters)
    FLOAT64     ac_eyepoint_x_m;  // Current live X value
    FLOAT64     ac_eyepoint_y_m;  // Current live Y value
    FLOAT64     ac_eyepoint_z_m;  // Current live Z value

    // --- v2.2.0: NAV1 frequency for ILS runway detection ---
    GAUGE_VAR   tok_nav1_freq;
    FLOAT64     nav1_freq_mhz;

    // --- Calibration state ---
    HUDSettings calib;

    // --- Debug overlay state ---
    DebugOverlay debug;

    // --- Optical realism state ---
    OpticalState optics;

    // --- Runway geometry ---
    RunwayGeometry runway;

    // --- v2.0: Aircraft state ---
    FLOAT64     ac_lat;
    FLOAT64     ac_lon;
    FLOAT64     ac_alt_m;
    FLOAT64     ac_hdg_true;
    FLOAT64     ac_pitch_deg;
    FLOAT64     ac_bank_deg;

    FLOAT64     ac_groundspeed_ms;
    FLOAT64     ac_true_airspeed_ms;
    FLOAT64     ac_vertical_speed_ms;
    FLOAT64     ac_track_deg_true;

    // --- v2.1.0: Additional state ---
    FLOAT64     ac_radio_alt_m;
    FLOAT64     ac_accel_ms2;
    FLOAT64     ac_indicated_airspeed_ms;
    bool        ac_on_ground;

    // --- v2.5.0: Aircraft detection ---
    char        aircraft_title[C_HUD_AIRCRAFT_ID_MAX];
    int         aircraft_id_len;

    // --- v2.6.0: Runtime performance state ---
    PerfState   perf;

    // --- v2.6.0: Frame pacing state ---
    PacingState pacing;

    // --- v2.6.0: Optical stability ---
    OpticalStabilityMetrics optic_stability;

    // --- v2.6.0: Compatibility signatures ---
    AircraftCompatibilitySignature compat_sig;
    bool        compat_verified;
    bool        compat_self_repair_active;
    bool        compat_fallback_active;

    // --- v2.6.0: Long-duration stability monitoring ---
    FLOAT64     stable_memory_usage_kb;
    FLOAT64     stable_timing_drift_us;
    int         stable_subsystem_stalls;
    FLOAT64     stable_runtime_s;

    // --- v2.6.0: Certification mode ---
    bool        cert_mode_active;
    FLOAT64     cert_scenario_score;
    FLOAT64     cert_aircraft_score;
    bool        cert_regression_detected;
    bool        cert_release_ready;
    FLOAT64     cert_total_score;
} ModuleState;

extern ModuleState g_state;

// ============================================================================
//  4.  Utility functions  (v2.0 forward)
// ============================================================================

enum ModuleReadResult {
    MODULE_READ_OK = 0,
    MODULE_READ_FAILED = 1,
};

/// Initialise all L:var tokens. Call once in POST_INSTALL.
/// Tokens are resolved by name and stored in a static table indexed by LVarID.
void lvar_init(void);

/// Read a SimVar value by token (0 = safe NaN).
static inline FLOAT64 module_read_f64(GAUGE_VAR token) {
    if (token == 0) return C_HUD_F64_NAN;
    return gauge_get_var_value(token);
}

/// Write an L:Var by LVarID.
static inline void lvar_write(LVarID id, FLOAT64 value) {
    extern GAUGE_VAR g_lvar_tokens[LVAR_COUNT];
    if (id < 0 || id >= LVAR_COUNT) return;
    if (g_lvar_tokens[id] == 0) return;
    gauge_set_var_value(g_lvar_tokens[id], value);
}

/// Read an L:Var by LVarID (for calibration/debug feedback from JS).
static inline FLOAT64 lvar_read(LVarID id) {
    extern GAUGE_VAR g_lvar_tokens[LVAR_COUNT];
    if (id < 0 || id >= LVAR_COUNT) return C_HUD_F64_NAN;
    if (g_lvar_tokens[id] == 0) return C_HUD_F64_NAN;
    return gauge_get_var_value(g_lvar_tokens[id]);
}

/// Initialise EMA filter with given alpha.
static inline void ema_init(EMASmooth* ema, FLOAT64 alpha) {
    if (ema == 0) return;
    ema->value = 0.0;
    ema->alpha = (alpha > 0.0 && alpha <= 1.0) ? alpha : 0.2;
    ema->initialised = false;
}

/// Feed a new sample into the EMA filter.
static inline void ema_feed(EMASmooth* ema, FLOAT64 sample) {
    if (ema == 0) return;
    if (!ema->initialised) {
        ema->value = sample;
        ema->initialised = true;
    } else {
        ema->value = ema->alpha * sample + (1.0 - ema->alpha) * ema->value;
    }
}



// ============================================================================
//  4a.  v2.6.0 — Timestamp helper for instrumentation (WASM-safe)
// ============================================================================

/// Return a monotonic timestamp in microseconds.
/// In the MSFS WASM environment, this uses the simulation time if available,
/// or falls back to frame_counter-based approximation.
/// Frame_counter * 16667 approximates simulation time at 60 FPS.
static inline FLOAT64 perf_timestamp_us(FLOAT64 frame_counter_f64) {
    // At 60 fps each frame is ~16667 microseconds
    return frame_counter_f64 * 16667.0;
}

// ============================================================================
//  4b.  v2.6.0 — Runtime instrumentation helpers (WASM-safe, no dynamic alloc)
// ============================================================================

/// Record a timing sample into a subsystem histogram.
static inline void histogram_record(SubsystemHistogram* h, FLOAT64 us, int frame_index) {
    if (h == 0 || !h->valid) return;
    if (h->sample_count < C_HUD_PERF_MAX_HISTORY) {
        h->sample_count++;
    }
    const int idx = h->sample_write_pos % C_HUD_PERF_MAX_HISTORY;
    h->samples[idx].us = us;
    h->samples[idx].frame_index = frame_index;
    h->sample_write_pos = (h->sample_write_pos + 1) % C_HUD_PERF_MAX_HISTORY;
    h->running_sum_us += us;
    h->running_sum_sq_us += us * us;
    if (us < h->min_us) h->min_us = us;
    if (us > h->max_us) h->max_us = us;
    h->total_frames_measured++;
    int bin_idx = C_HUD_PERF_HIST_BINS - 1;
    for (int b = 0; b < C_HUD_PERF_HIST_BINS - 1; ++b) {
        if (us >= h->bin_lower[b] && us < h->bin_upper[b]) {
            bin_idx = b;
            break;
        }
    }
    if (bin_idx >= 0 && bin_idx < C_HUD_PERF_HIST_BINS) {
        h->bins[bin_idx]++;
    }
}

/// Update percentile caches (p50_us, p95_us, p99_us) from histogram bins.
static inline void percentile_compute(SubsystemHistogram* h) {
    if (h == 0 || !h->valid || h->sample_count == 0) return;
    const int total = h->total_frames_measured;
    if (total == 0) return;
    int cumulative = 0;
    h->p50_us = 0.0;
    h->p95_us = 0.0;
    h->p99_us = 0.0;
    for (int b = 0; b < C_HUD_PERF_HIST_BINS; ++b) {
        cumulative += h->bins[b];
        const FLOAT64 midpoint = (h->bin_lower[b] + h->bin_upper[b]) * 0.5;
        if (cumulative >= (int)(total * 0.50) && h->p50_us == 0.0)
            h->p50_us = midpoint;
        if (cumulative >= (int)(total * 0.95) && h->p95_us == 0.0)
            h->p95_us = midpoint;
        if (cumulative >= (int)(total * 0.99) && h->p99_us == 0.0)
            h->p99_us = midpoint;
    }
    if (h->p50_us == 0.0) h->p50_us = h->bin_upper[C_HUD_PERF_HIST_BINS - 1];
    if (h->p95_us == 0.0) h->p95_us = h->bin_upper[C_HUD_PERF_HIST_BINS - 1];
    if (h->p99_us == 0.0) h->p99_us = h->bin_upper[C_HUD_PERF_HIST_BINS - 1];
    h->last_percentile_update = h->total_frames_measured;
}

/// Begin a frame timing measurement.
static inline void perf_begin(PerfState* p, FLOAT64 timestamp_us) {
    if (p == 0 || !p->enabled) return;
    p->frame_active = true;
    p->frame_start_us = timestamp_us;
}

/// End a frame timing measurement and record total frame time.
static inline void perf_end(PerfState* p, FLOAT64 timestamp_us, int frame_index) {
    if (p == 0 || !p->enabled || !p->frame_active) return;
    p->frame_end_us = timestamp_us;
    const FLOAT64 total_us = p->frame_end_us - p->frame_start_us;
    if (total_us >= 0.0) {
        histogram_record(&p->subsystems[SUBSYS_TOTAL].hist, total_us, frame_index);
        p->subsystems[SUBSYS_TOTAL].last_us = total_us;
        if (total_us > p->subsystems[SUBSYS_TOTAL].peak_us)
            p->subsystems[SUBSYS_TOTAL].peak_us = total_us;
        p->subsystems[SUBSYS_TOTAL].over_budget = (total_us > p->subsystems[SUBSYS_TOTAL].budget_us);
    }
    p->frame_active = false;
}

/// Record a subsystem timing measurement.
static inline void perf_measure(PerfState* p, SubsystemID id, FLOAT64 elapsed_us, int frame_index) {
    if (p == 0 || !p->enabled || id < 0 || id >= SUBSYS_COUNT) return;
    if (elapsed_us < 0.0) elapsed_us = 0.0;
    SubsystemTiming* st = &p->subsystems[id];
    st->last_us = elapsed_us;
    if (elapsed_us > st->peak_us) st->peak_us = elapsed_us;
    st->over_budget = (elapsed_us > st->budget_us);
    histogram_record(&st->hist, elapsed_us, frame_index);
}

/// Update frame pacing state with the latest frame interval.
static inline void pacing_update(PacingState* ps, FLOAT64 dt_s, int frame_index, FLOAT64 timestamp_s) {
    if (ps == 0 || !ps->valid) return;
    const FLOAT64 dt_ms = dt_s * 1000.0;
    const FLOAT64 clamped_dt = (dt_ms < 0.0) ? 0.0 : (dt_ms > 500.0) ? 500.0 : dt_ms;

    // Rolling history
    if (ps->dt_sample_count < 60) ps->dt_sample_count++;
    ps->dt_history[ps->dt_write_pos] = clamped_dt;
    ps->dt_write_pos = (ps->dt_write_pos + 1) % 60;

    // Stats
    if (clamped_dt < ps->dt_min) ps->dt_min = clamped_dt;
    if (clamped_dt > ps->dt_max) ps->dt_max = clamped_dt;
    FLOAT64 sum = 0.0;
    for (int i = 0; i < ps->dt_sample_count; ++i) sum += ps->dt_history[i];
    ps->dt_mean = sum / (FLOAT64)(ps->dt_sample_count > 0 ? ps->dt_sample_count : 1);
    if (ps->dt_sample_count > 1) {
        FLOAT64 variance = 0.0;
        for (int i = 0; i < ps->dt_sample_count; ++i) {
            const FLOAT64 d = ps->dt_history[i] - ps->dt_mean;
            variance += d * d;
        }
        ps->dt_stddev = __builtin_sqrt(variance / (FLOAT64)ps->dt_sample_count);
    }

    // Anomaly detection
    bool anomaly = false;
    if (clamped_dt > ps->hitch_threshold_ms) {
        anomaly = true;
        if (ps->anomaly_count < 32) {
            PacingAnomalyEvent* ev = &ps->anomalies[ps->anomaly_write_pos % 32];
            ev->type = ANOMALY_HITCH;
            ev->frame_index = frame_index;
            ev->timestamp_s = timestamp_s;
            ev->duration_ms = clamped_dt;
            ev->recovery_ms = 0.0;
            ps->anomaly_write_pos = (ps->anomaly_write_pos + 1) % 32;
            ps->anomaly_count++;
        }
    } else if (ps->dt_sample_count >= 10 && ps->dt_mean > ps->stutter_threshold_ms) {
        anomaly = true;
        if (ps->anomaly_count < 32) {
            PacingAnomalyEvent* ev = &ps->anomalies[ps->anomaly_write_pos % 32];
            ev->type = ANOMALY_STUTTER;
            ev->frame_index = frame_index;
            ev->timestamp_s = timestamp_s;
            ev->duration_ms = ps->dt_mean;
            ev->recovery_ms = 0.0;
            ps->anomaly_write_pos = (ps->anomaly_write_pos + 1) % 32;
            ps->anomaly_count++;
        }
    }

    // Update continuity and stable frame count
    if (!anomaly) {
        ps->consecutive_stable_frames++;
        ps->continuity_metric += 0.01f;
        if (ps->continuity_metric > 1.0) ps->continuity_metric = 1.0;
        ps->in_recovery = false;
        ps->recovery_frames = 0;
    } else {
        ps->consecutive_stable_frames = 0;
        ps->continuity_metric -= 0.2f;
        if (ps->continuity_metric < 0.0) ps->continuity_metric = 0.0;
        ps->in_recovery = true;
        ps->recovery_frames = 0;
    }
    if (ps->in_recovery) {
        ps->recovery_frames++;
    }
}

/// Update optical stability metrics with latest element positions.
static inline void optic_stability_update(OpticalStabilityMetrics* osm,
                                            FLOAT64 element_x, FLOAT64 element_y,
                                            FLOAT64 dt_s, FLOAT64 brightness) {
    if (osm == 0 || !osm->valid) return;

    // Shimmer detection: track high-frequency position changes
    osm->shimmer_sample_count++;
    const FLOAT64 prev_shimmer = osm->shimmer_accumulator;
    osm->shimmer_accumulator += __builtin_fabs(element_x) + __builtin_fabs(element_y);
    if (osm->shimmer_sample_count > 60) {
        osm->shimmer_accumulator *= 0.5;
        osm->shimmer_sample_count = 30;
    }
    const FLOAT64 shimmer_per_sample = (osm->shimmer_sample_count > 0)
        ? osm->shimmer_accumulator / (FLOAT64)osm->shimmer_sample_count : 0.0;

    // Visual fatigue
    osm->current_fatigue += osm->fatigue_decay_rate * brightness * dt_s;
    if (brightness < 0.3) {
        osm->current_fatigue -= osm->fatigue_decay_rate * dt_s * 0.5;
    }
    if (osm->current_fatigue < 0.0) osm->current_fatigue = 0.0;
    if (osm->current_fatigue > 1.0) osm->current_fatigue = 1.0;

    // Overall stability score
    FLOAT64 score = 1.0;
    if (shimmer_per_sample > osm->shimmer_threshold) {
        score -= (shimmer_per_sample - osm->shimmer_threshold) * 2.0;
    }
    if (osm->current_fatigue > 0.7) {
        score -= 0.2;
    }
    if (score < 0.0) score = 0.0;
    osm->optical_stability_score = score;
}

// ============================================================================
//  5.  v2.6.0 — Runtime init helpers (inline, called once from module_init)
// ============================================================================

/// Initialise the runtime performance monitoring state.
static inline void perf_state_init(PerfState* p) {
    if (p == 0) return;
    p->enabled = true;
    p->frame_active = false;
    p->frame_start_us = 0.0;
    p->frame_end_us = 0.0;
    p->js_bridge_latency_us = 0.0;
    for (int i = 0; i < SUBSYS_COUNT; ++i) {
        SubsystemTiming* st = &p->subsystems[i];
        st->last_us = 0.0;
        st->peak_us = 0.0;
        st->budget_us = 1000.0;  // default 1ms budget
        st->over_budget = false;
        SubsystemHistogram* h = &st->hist;
        h->sample_write_pos = 0;
        h->sample_count = 0;
        h->running_sum_us = 0.0;
        h->running_sum_sq_us = 0.0;
        h->min_us = 1e9;
        h->max_us = 0.0;
        h->total_frames_measured = 0;
        h->p50_us = 0.0;
        h->p95_us = 0.0;
        h->p99_us = 0.0;
        h->last_percentile_update = 0;
        h->valid = true;
        for (int b = 0; b < C_HUD_PERF_HIST_BINS; ++b) {
            h->bins[b] = 0;
            h->bin_lower[b] = (FLOAT64)b * 100.0;
            h->bin_upper[b] = (FLOAT64)(b + 1) * 100.0;
        }
    }
}

/// Initialise the frame pacing validation state.
static inline void pacing_init(PacingState* ps) {
    if (ps == 0) return;
    ps->expected_frame_interval_ms = 16.667;  // ~60fps
    ps->hitch_threshold_ms = 50.0;
    ps->stutter_threshold_ms = 33.0;
    ps->dt_write_pos = 0;
    ps->dt_sample_count = 0;
    ps->dt_min = 1e9;
    ps->dt_max = 0.0;
    ps->dt_mean = 16.667;
    ps->dt_stddev = 0.0;
    for (int i = 0; i < 60; ++i) ps->dt_history[i] = 16.667;
    ps->anomaly_write_pos = 0;
    ps->anomaly_count = 0;
    ps->in_recovery = false;
    ps->recovery_frames = 0;
    ps->stabilization_reset_pending = false;
    ps->continuity_metric = 1.0;
    ps->consecutive_stable_frames = 0;
    ps->valid = true;
}

/// Initialise the optical stability metrics.
static inline void optic_stability_init(OpticalStabilityMetrics* osm) {
    if (osm == 0) return;
    osm->shimmer_accumulator = 0.0;
    osm->shimmer_sample_count = 0;
    osm->shimmer_threshold = 0.05;
    osm->fatigue_accumulator = 0.0;
    osm->fatigue_decay_rate = 0.001;
    osm->current_fatigue = 0.0;
    osm->phosphor_smear_amount = 0.0;
    osm->phosphor_exceedance_count = 0;
    osm->optical_stability_score = 1.0;
    osm->valid = true;
}

// ============================================================================
//  6.  Legacy init helpers (v2.2.0) — restored declarations
// ============================================================================

/// Compute weather line width and opacity from visibility.
static inline void weather_compute_params(FLOAT64 vis_m, WeatherState* ws) {
    if (ws == 0) return;
    if (vis_m < C_HUD_VIS_MIN_M) vis_m = C_HUD_VIS_MIN_M;
    if (vis_m > C_HUD_VIS_MAX_M) vis_m = C_HUD_VIS_MAX_M;
    const FLOAT64 norm = (vis_m - C_HUD_VIS_MIN_M) /
                          (C_HUD_VIS_MAX_M - C_HUD_VIS_MIN_M);
    ws->line_width_px = 4.0 - norm * 2.5;
    ws->opacity = 0.95 - norm * 0.35;
    if (ws->line_width_px < 1.0) ws->line_width_px = 1.0;
    if (ws->line_width_px > 6.0) ws->line_width_px = 6.0;
    if (ws->opacity < 0.1) ws->opacity = 0.1;
    if (ws->opacity > 1.0) ws->opacity = 1.0;
    ws->visibility_m = vis_m;
    ws->valid = true;
}

/// Initialise HUDSettings with sensible defaults.
static inline void calib_init(HUDSettings* s) {
    if (s == 0) return;
    s->center_offset_x = 0.0;
    s->center_offset_y = 0.0;
    s->combiner_offset_x = 0.0;
    s->combiner_offset_y = 0.0;
    s->combiner_scale_w = 1.0;
    s->combiner_scale_h = 1.0;
    s->eye_offset_forward_m = 0.0;
    s->eye_offset_right_m = 0.0;
    s->eye_offset_down_m = 0.0;
    s->fov_scale = 1.0;
    s->projection_scale_x = 1.0;
    s->projection_scale_y = 1.0;
    s->optical_gain = 1.0;
    s->fpv_align_x = 0.0;
    s->fpv_align_y = 0.0;
    s->runway_align_offset = 0.0;
    s->flare_cue_pos_offset = 0.0;
    s->horizon_line_offset = 0.0;
    s->active_profile_slot = 0;
    s->dirty = false;
}

/// Read calibration L:vars from Sim (written by JS overlay).
/// Implemented in calibration.cpp.
void calib_read_lvars(HUDSettings* s);

/// Initialise DebugOverlay flags to defaults (all off).
static inline void debug_init(DebugOverlay* d) {
    if (d == 0) return;
    d->show_runway_corners = false;
    d->show_world_axes = false;
    d->show_fpv_trace = false;
    d->show_guidance_beam = false;
    d->show_clipping = false;
    d->show_optical_center = false;
    d->show_collimation_vectors = false;
    d->show_timing_overlay = false;
    d->show_histogram = false;
}

/// Read debug overlay toggles from L:vars (written by JS overlay).
/// Implemented in calibration.cpp.
void debug_read_lvars(DebugOverlay* d);

/// Initialise OpticalState with realistic defaults.
static inline void optics_init(OpticalState* o) {
    if (o == 0) return;
    o->phosphor_decay = 0.15;
    o->bloom_amount = 0.08;
    o->luminance_gain = 1.0;
    o->brightness_auto_gain = 0.5;
    o->edge_fade_amount = 0.1;
    o->temporal_blend_factor = 0.3;
    for (int i = 0; i < 64; ++i) o->phosphor_buffer[i] = 0.0;
    o->current_brightness = 1.0;
}

#endif // C_HUD_RUNWAY_MODULE_H
