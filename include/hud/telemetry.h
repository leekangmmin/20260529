#ifndef C_HUD_TELEMETRY_H
#define C_HUD_TELEMETRY_H

// ============================================================================
//  Conformal HUD – Flight Data Recording & Replay
//  MSFS 2024  ·  C++17  ·  WASM
//
//  PHASE 2 — FLIGHT DATA RECORDING & REPLAY
//
//  Provides deterministic flight telemetry capture and replay for:
//    · Regression analysis after tuning changes
//    · Frame-by-frame debugging of HUD behavior
//    · Repeatable testing of CAT III / flare / rollout sequences
//    · Visual certification against reference footage
//
//  The telemetry recorder captures a timestamped event stream of:
//    · Aircraft state (position, attitude, speeds)
//    · FPV position and validity
//    · Runway geometry and projection
//    · Flare state and cue parameters
//    · Rollout state and steering commands
//    · CAT III confidence and augmentation
//    · Turbulence metrics
//    · Optical state and visual response
// ============================================================================

#include "../module.h"
#include "../projection.h"
#include "../aircraft_profiles.h"
#include "flare.h"
#include "fpv.h"
#include "rollout.h"
#include "confidence.h"
#include "declutter.h"
#include "visual_response.h"
#include "runway_projection.h"

// ============================================================================
//  1.  Telemetry frame — a point-in-time snapshot
// ============================================================================

/// Maximum number of telemetry frames in the ring buffer.
#define C_HUD_TELEMETRY_MAX_FRAMES  36000   // ~10 minutes at 60 fps

/// Maximum length of a telemetry event label.
#define C_HUD_TELEMETRY_LABEL_MAX   64

/// A single telemetry frame capturing all HUD-relevant state.
typedef struct TelemetryFrame {
    // --- Frame identification ---
    int     frame_index;
    FLOAT64 timestamp_s;

    // --- Aircraft state ---
    FLOAT64 ac_lat;
    FLOAT64 ac_lon;
    FLOAT64 ac_alt_m;
    FLOAT64 ac_hdg_true;
    FLOAT64 ac_pitch_deg;
    FLOAT64 ac_bank_deg;
    FLOAT64 ac_groundspeed_ms;
    FLOAT64 ac_true_airspeed_ms;
    FLOAT64 ac_vertical_speed_ms;
    FLOAT64 ac_track_deg_true;
    FLOAT64 ac_radio_alt_m;
    FLOAT64 ac_accel_ms2;
    bool    ac_on_ground;

    // --- FPV ---
    FLOAT64 fpv_x;
    FLOAT64 fpv_y;
    bool    fpv_on_screen;
    bool    fpv_valid;
    FLOAT64 fpv_pitch;
    FLOAT64 fpv_drift;

    // --- Runway geometry ---
    bool    runway_valid;
    int     runway_visible_count;
    Vec2    runway_corners[8];
    FLOAT64 runway_heading_deg;

    // --- Flare state ---
    bool    flare_active;
    bool    flare_fully_active;
    FLOAT64 flare_cue_x;
    FLOAT64 flare_cue_y;
    FLOAT64 flare_cue_size;
    FLOAT64 flare_cue_alpha;
    FLOAT64 flare_rise;
    FLOAT64 flare_error;
    FLOAT64 flare_vs_cmd;

    // --- Rollout state ---
    bool    rollout_active;
    FLOAT64 rollout_steering;
    FLOAT64 rollout_centerline_error;
    FLOAT64 rollout_confidence;
    FLOAT64 rollout_nosewheel;

    // --- CAT III ---
    FLOAT64 cat3_confidence;
    FLOAT64 system_integrity;

    // --- Turbulence ---
    FLOAT64 turbulence_intensity;
    FLOAT64 jitter_ms;

    // --- Optical ---
    FLOAT64 optical_brightness;
    FLOAT64 optical_bloom;
    FLOAT64 optical_phosphor_ms;

    // --- Confidence ---
    FLOAT64 ils_integrity;
    FLOAT64 guidance_integrity;

    // --- Weather ---
    FLOAT64 visibility_m;
} TelemetryFrame;

// ============================================================================
//  2.  Event stream — timestamped annotations
// ============================================================================

/// A timestamped event marker in the telemetry stream.
typedef struct TelemetryEvent {
    int     frame_index;
    FLOAT64 timestamp_s;
    char    label[C_HUD_TELEMETRY_LABEL_MAX];
    FLOAT64 value;
} TelemetryEvent;

/// Maximum number of events in the ring buffer.
#define C_HUD_TELEMETRY_MAX_EVENTS  1024

// ============================================================================
//  3.  Telemetry recorder state
// ============================================================================

/// Ring-buffer telemetry recorder.
typedef struct TelemetryRecorder {
    // --- Frame ring buffer ---
    TelemetryFrame  frames[C_HUD_TELEMETRY_MAX_FRAMES];
    int             frame_write_pos;        // Next write position
    int             frame_count;            // Total frames recorded
    bool            buffer_full;            // True when buffer is full

    // --- Event ring buffer ---
    TelemetryEvent  events[C_HUD_TELEMETRY_MAX_EVENTS];
    int             event_write_pos;
    int             event_count;

    // --- Recording state ---
    bool            recording;              // True when actively recording
    bool            paused;                 // True when paused
    FLOAT64         start_time_s;           // Timestamp when recording started
    int             start_frame;            // Frame counter when recording started

    // --- Snapshot state ---
    TelemetryFrame  snapshot;               // Most recent captured frame

    // --- Debug ---
    bool            valid;
} TelemetryRecorder;

// ============================================================================
//  4.  Telemetry replay state
// ============================================================================

/// Playback mode for telemetry replay.
typedef enum ReplayMode {
    REPLAY_MODE_STOPPED      = 0,
    REPLAY_MODE_PLAYING      = 1,   // Real-time playback
    REPLAY_MODE_STEP_FRAME   = 2,   // Single-frame step
    REPLAY_MODE_LOOP         = 3,   // Loop playback
} ReplayMode;

/// Telemetry replay engine.
typedef struct TelemetryReplay {
    // --- Source data ---
    const TelemetryRecorder* source;        // Recorder to replay from

    // --- Playback state ---
    ReplayMode  mode;
    int         current_frame;              // Current playback frame
    FLOAT64     playback_time_s;            // Current playback time
    FLOAT64     playback_speed;             // 1.0 = real-time, 2.0 = double speed

    // --- Loop region ---
    int         loop_start_frame;
    int         loop_end_frame;

    // --- State injection ---
    // When replaying, these fields are populated from the source frames
    TelemetryFrame current_output;

    // --- Debug ---
    bool    valid;
} TelemetryReplay;

// ============================================================================
//  5.  Recorder API
// ============================================================================

/// Initialise the telemetry recorder.
static inline void telemetry_recorder_init(TelemetryRecorder* tr) {
    if (tr == 0) return;

    __builtin_memset(tr, 0, sizeof(*tr));
    tr->recording   = false;
    tr->paused      = false;
    tr->start_time_s = 0.0;
    tr->start_frame  = 0;
    tr->frame_write_pos = 0;
    tr->frame_count     = 0;
    tr->buffer_full     = false;
    tr->event_write_pos = 0;
    tr->event_count     = 0;
    tr->valid           = true;
}

/// Start recording telemetry.
static inline void telemetry_recorder_start(TelemetryRecorder* tr,
                                              FLOAT64 current_time_s,
                                              int     current_frame) {
    if (tr == 0) return;
    tr->recording     = true;
    tr->paused        = false;
    tr->start_time_s  = current_time_s;
    tr->start_frame   = current_frame;
    tr->frame_write_pos = 0;
    tr->frame_count     = 0;
    tr->buffer_full     = false;
    tr->event_write_pos = 0;
    tr->event_count     = 0;
}

/// Stop recording telemetry.
static inline void telemetry_recorder_stop(TelemetryRecorder* tr) {
    if (tr == 0) return;
    tr->recording = false;
}

/// Pause/resume recording.
static inline void telemetry_recorder_pause(TelemetryRecorder* tr, bool paused) {
    if (tr == 0) return;
    tr->paused = paused;
}

/// Record a single telemetry frame.
void telemetry_recorder_record_frame(TelemetryRecorder* tr,
                                      int                frame_index,
                                      FLOAT64            timestamp_s,
                                      const TelemetryFrame* frame);

/// Record a timestamped event.
void telemetry_recorder_record_event(TelemetryRecorder* tr,
                                      int                frame_index,
                                      FLOAT64            timestamp_s,
                                      const char*        label,
                                      FLOAT64            value);

/// Get the most recent snapshot.
static inline const TelemetryFrame* telemetry_recorder_snapshot(const TelemetryRecorder* tr) {
    if (tr == 0) return 0;
    return &tr->snapshot;
}

/// Get a frame by index (supports ring-buffer wrap-around).
const TelemetryFrame* telemetry_recorder_get_frame(const TelemetryRecorder* tr,
                                                     int absolute_frame_index);

/// Get the total number of recorded frames.
static inline int telemetry_recorder_frame_count(const TelemetryRecorder* tr) {
    if (tr == 0) return 0;
    return tr->frame_count;
}

/// Check if recording is active.
static inline bool telemetry_recorder_is_recording(const TelemetryRecorder* tr) {
    if (tr == 0) return false;
    return tr->recording && !tr->paused;
}

// ============================================================================
//  6.  Replay API
// ============================================================================

/// Initialise the telemetry replay engine.
static inline void telemetry_replay_init(TelemetryReplay* tp,
                                          const TelemetryRecorder* source) {
    if (tp == 0) return;
    tp->source           = source;
    tp->mode             = REPLAY_MODE_STOPPED;
    tp->current_frame    = 0;
    tp->playback_time_s  = 0.0;
    tp->playback_speed   = 1.0;
    tp->loop_start_frame = 0;
    tp->loop_end_frame   = (source != 0) ? source->frame_count - 1 : 0;
    __builtin_memset(&tp->current_output, 0, sizeof(tp->current_output));
    tp->valid            = (source != 0);
}

/// Start playback from the beginning.
static inline void telemetry_replay_start(TelemetryReplay* tp) {
    if (tp == 0 || !tp->valid) return;
    tp->mode            = REPLAY_MODE_PLAYING;
    tp->current_frame   = 0;
    tp->playback_time_s = 0.0;
    if (tp->source != 0 && tp->source->frame_count > 0) {
        tp->current_output = tp->source->frames[0];
    }
}

/// Step playback by one frame.
bool telemetry_replay_step_frame(TelemetryReplay* tp);

/// Advance playback by dt_s seconds (real-time or scaled).
bool telemetry_replay_advance(TelemetryReplay* tp, FLOAT64 dt_s);

/// Seek to a specific frame index.
bool telemetry_replay_seek(TelemetryReplay* tp, int frame_index);

/// Stop playback.
static inline void telemetry_replay_stop(TelemetryReplay* tp) {
    if (tp == 0) return;
    tp->mode = REPLAY_MODE_STOPPED;
}

/// Get the current output frame (for injecting into the pipeline).
static inline const TelemetryFrame* telemetry_replay_current(const TelemetryReplay* tp) {
    if (tp == 0 || tp->mode == REPLAY_MODE_STOPPED) return 0;
    return &tp->current_output;
}

/// Check if replay is active.
static inline bool telemetry_replay_is_active(const TelemetryReplay* tp) {
    if (tp == 0) return false;
    return tp->mode == REPLAY_MODE_PLAYING ||
           tp->mode == REPLAY_MODE_STEP_FRAME ||
           tp->mode == REPLAY_MODE_LOOP;
}

/// Get the number of available frames for replay.
static inline int telemetry_replay_available_frames(const TelemetryReplay* tp) {
    if (tp == 0 || tp->source == 0) return 0;
    return tp->source->frame_count;
}

// ============================================================================
//  7.  Frame population helper
// ============================================================================

/// Populate a TelemetryFrame from the current global pipeline state.
/// (To be called at the end of module_update_project.)
TelemetryFrame telemetry_capture_current_frame(
    int     frame_index,
    FLOAT64 timestamp_s,
    const struct ModuleState*   g_state,
    const FPVState*             fpv,
    const FlareState*           flare,
    const FlareCue*             flare_cue,
    const RolloutState*         rollout,
    const ProjectedRunway*      proj_runway,
    const RunwayEnd*            active_runway,
    const ConfidenceState*      confidence,
    const struct HUDStabilisation* stab,
    const struct OpticalState*  optics,
    FLOAT64                     jitter_ms
);

// ============================================================================
//  8.  Debug logging
// ============================================================================

/// Dump telemetry summary to the MSFS log.
void telemetry_debug_log(const TelemetryRecorder* tr);

#endif // C_HUD_TELEMETRY_H
