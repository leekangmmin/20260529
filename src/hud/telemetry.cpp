// ============================================================================
//  Conformal HUD – Flight Data Recording & Replay Implementation
//  MSFS 2024  ·  C++17  ·  WASM
//
//  PHASE 2 — FLIGHT DATA RECORDING & REPLAY
//
//  Implements the ring-buffer telemetry recorder and deterministic
//  replay engine for frame-by-frame analysis and regression testing.
// ============================================================================

#include "hud/telemetry.h"
#include "hud/stabilization.h"   // full HUDStabilisation definition (used at line ~299)
#include <MSFS/MSFS.h>   // MSFS_Log

// ============================================================================
//  Recorder — Record a single frame
// ============================================================================

void telemetry_recorder_record_frame(TelemetryRecorder* tr,
                                      int                frame_index,
                                      FLOAT64            timestamp_s,
                                      const TelemetryFrame* frame)
{
    if (tr == 0 || frame == 0 || !tr->recording || tr->paused) return;

    // Save as latest snapshot
    tr->snapshot = *frame;

    // Write into ring buffer
    if (tr->frame_count < C_HUD_TELEMETRY_MAX_FRAMES) {
        tr->frames[tr->frame_write_pos] = *frame;
        tr->frame_write_pos = (tr->frame_write_pos + 1) % C_HUD_TELEMETRY_MAX_FRAMES;
        tr->frame_count++;
    } else {
        tr->buffer_full = true;
        // Continue overwriting oldest frames
        tr->frames[tr->frame_write_pos] = *frame;
        tr->frame_write_pos = (tr->frame_write_pos + 1) % C_HUD_TELEMETRY_MAX_FRAMES;
    }
}

// ============================================================================
//  Recorder — Record a timestamped event
// ============================================================================

void telemetry_recorder_record_event(TelemetryRecorder* tr,
                                      int                frame_index,
                                      FLOAT64            timestamp_s,
                                      const char*        label,
                                      FLOAT64            value)
{
    if (tr == 0 || label == 0 || !tr->recording || tr->paused) return;

    if (tr->event_count >= C_HUD_TELEMETRY_MAX_EVENTS) {
        // Ring-buffer overwrite for events too
        tr->event_write_pos = 0;
        tr->event_count = C_HUD_TELEMETRY_MAX_EVENTS;
    }

    TelemetryEvent* ev = &tr->events[tr->event_write_pos];
    ev->frame_index  = frame_index;
    ev->timestamp_s  = timestamp_s;
    ev->value        = value;

    // Copy label safely
    unsigned int i = 0;
    while (i < C_HUD_TELEMETRY_LABEL_MAX - 1 && label[i] != '\0') {
        ev->label[i] = label[i];
        ++i;
    }
    ev->label[i] = '\0';

    tr->event_write_pos = (tr->event_write_pos + 1) % C_HUD_TELEMETRY_MAX_EVENTS;
    if (tr->event_count < C_HUD_TELEMETRY_MAX_EVENTS) {
        tr->event_count++;
    }
}

// ============================================================================
//  Recorder — Get frame by index
// ============================================================================

const TelemetryFrame* telemetry_recorder_get_frame(const TelemetryRecorder* tr,
                                                     int absolute_frame_index)
{
    if (tr == 0 || tr->frame_count == 0) return 0;

    // Handle wrap-around for ring buffer
    const int available = tr->frame_count;
    if (absolute_frame_index < 0 || absolute_frame_index >= available) return 0;

    // The ring buffer stores frames from oldest to newest.
    // Calculate the actual buffer index.
    int buffer_index;
    if (!tr->buffer_full) {
        // Buffer not yet wrapped: frames are stored from index 0
        buffer_index = absolute_frame_index;
    } else {
        // Buffer has wrapped: the write position is the "newest" + 1
        buffer_index = (tr->frame_write_pos + absolute_frame_index) % C_HUD_TELEMETRY_MAX_FRAMES;
    }

    if (buffer_index < 0 || buffer_index >= C_HUD_TELEMETRY_MAX_FRAMES) return 0;
    return &tr->frames[buffer_index];
}

// ============================================================================
//  Replay — Step one frame
// ============================================================================

bool telemetry_replay_step_frame(TelemetryReplay* tp) {
    if (tp == 0 || !tp->valid || tp->source == 0) return false;

    if (tp->current_frame >= tp->source->frame_count - 1) {
        // End of recording
        if (tp->mode == REPLAY_MODE_LOOP) {
            tp->current_frame = tp->loop_start_frame;
        } else {
            tp->mode = REPLAY_MODE_STOPPED;
            return false;
        }
    }

    tp->current_frame++;
    const TelemetryFrame* frame = telemetry_recorder_get_frame(
        tp->source, tp->current_frame);
    if (frame != 0) {
        tp->current_output = *frame;
        tp->playback_time_s = frame->timestamp_s;
        return true;
    }

    return false;
}

// ============================================================================
//  Replay — Advance by dt
// ============================================================================

bool telemetry_replay_advance(TelemetryReplay* tp, FLOAT64 dt_s) {
    if (tp == 0 || !tp->valid || tp->source == 0) return false;
    if (tp->mode != REPLAY_MODE_PLAYING && tp->mode != REPLAY_MODE_LOOP) return false;

    const FLOAT64 scaled_dt = dt_s * tp->playback_speed;
    tp->playback_time_s += scaled_dt;

    // Find the frame closest to the current playback time
    const int total_frames = tp->source->frame_count;
    if (total_frames == 0) return false;

    // Binary search for the right frame
    int lo = 0;
    int hi = total_frames - 1;
    int best = 0;

    while (lo <= hi) {
        const int mid = lo + (hi - lo) / 2;
        const TelemetryFrame* f = telemetry_recorder_get_frame(tp->source, mid);
        if (f == 0) break;

        if (f->timestamp_s <= tp->playback_time_s) {
            best = mid;
            lo = mid + 1;
        } else {
            hi = mid - 1;
        }
    }

    tp->current_frame = best;
    const TelemetryFrame* frame = telemetry_recorder_get_frame(tp->source, best);
    if (frame != 0) {
        tp->current_output = *frame;
        return true;
    }

    return false;
}

// ============================================================================
//  Replay — Seek to frame
// ============================================================================

bool telemetry_replay_seek(TelemetryReplay* tp, int frame_index) {
    if (tp == 0 || !tp->valid || tp->source == 0) return false;
    if (frame_index < 0 || frame_index >= tp->source->frame_count) return false;

    tp->current_frame = frame_index;
    const TelemetryFrame* frame = telemetry_recorder_get_frame(tp->source, frame_index);
    if (frame != 0) {
        tp->current_output = *frame;
        tp->playback_time_s = frame->timestamp_s;
        return true;
    }

    return false;
}

// ============================================================================
//  Frame capture helper
// ============================================================================

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
    FLOAT64                     jitter_ms)
{
    TelemetryFrame tf;
    __builtin_memset(&tf, 0, sizeof(tf));

    // --- Frame identification ---
    tf.frame_index  = frame_index;
    tf.timestamp_s  = timestamp_s;

    // --- Aircraft state ---
    if (g_state != 0) {
        tf.ac_lat              = g_state->ac_lat;
        tf.ac_lon              = g_state->ac_lon;
        tf.ac_alt_m            = g_state->ac_alt_m;
        tf.ac_hdg_true         = g_state->ac_hdg_true;
        tf.ac_pitch_deg        = g_state->ac_pitch_deg;
        tf.ac_bank_deg         = g_state->ac_bank_deg;
        tf.ac_groundspeed_ms   = g_state->ac_groundspeed_ms;
        tf.ac_true_airspeed_ms = g_state->ac_true_airspeed_ms;
        tf.ac_vertical_speed_ms= g_state->ac_vertical_speed_ms;
        tf.ac_track_deg_true   = g_state->ac_track_deg_true;
        tf.ac_radio_alt_m      = g_state->ac_radio_alt_m;
        tf.ac_accel_ms2        = g_state->ac_accel_ms2;
        tf.ac_on_ground        = g_state->ac_on_ground;
        tf.visibility_m        = g_state->weather.visibility_m;
    }

    // --- FPV ---
    if (fpv != 0) {
        tf.fpv_x         = fpv->screen_pos.x;
        tf.fpv_y         = fpv->screen_pos.y;
        tf.fpv_on_screen = fpv->on_screen;
        tf.fpv_valid     = fpv->valid;
        tf.fpv_pitch     = fpv->fpv_pitch;
        tf.fpv_drift     = fpv->drift_angle;
    }

    // --- Runway ---
    if (proj_runway != 0) {
        tf.runway_valid        = proj_runway->valid;
        tf.runway_visible_count = proj_runway->visible_count;
        const int copy_count = (proj_runway->visible_count < 8)
                                ? proj_runway->visible_count : 8;
        for (int i = 0; i < copy_count; ++i) {
            tf.runway_corners[i] = proj_runway->screen_corners[i];
        }
    }
    if (active_runway != 0) {
        tf.runway_heading_deg = active_runway->true_heading;
    }

    // --- Flare ---
    if (flare != 0) {
        tf.flare_active       = flare->flare_active;
        tf.flare_fully_active = flare->flare_fully_active;
        tf.flare_rise         = flare->flare_cue_rise;
        tf.flare_error        = flare->flare_cue_error;
        tf.flare_vs_cmd       = flare->flare_cue_vs;
    }
    if (flare_cue != 0) {
        tf.flare_cue_x     = flare_cue->screen_pos.x;
        tf.flare_cue_y     = flare_cue->screen_pos.y;
        tf.flare_cue_size  = flare_cue->size_px;
        tf.flare_cue_alpha = flare_cue->alpha;
    }

    // --- Rollout ---
    if (rollout != 0) {
        tf.rollout_active         = (rollout->phase != ROLLOUT_PHASE_INACTIVE);
        tf.rollout_steering       = rollout->steering_command_deg;
        tf.rollout_centerline_error = rollout->centerline_error_deg;
        tf.rollout_confidence     = rollout->confidence;
        tf.rollout_nosewheel      = rollout->nosewheel_fraction;
    }

    // --- CAT III / Confidence ---
    if (confidence != 0) {
        tf.cat3_confidence     = confidence->cat_iii_qualification;
        tf.system_integrity    = confidence->overall_integrity;
        tf.ils_integrity       = confidence->ils_integrity;
        tf.guidance_integrity  = confidence->guidance_integrity;
    }

    // --- Turbulence ---
    if (stab != 0) {
        tf.turbulence_intensity = stab->turbulence_intensity;
    }
    tf.jitter_ms = jitter_ms;

    // --- Optical ---
    if (optics != 0) {
        tf.optical_brightness  = optics->current_brightness;
        tf.optical_bloom       = optics->bloom_amount;
        tf.optical_phosphor_ms = optics->phosphor_decay;
    }

    return tf;
}

// ============================================================================
//  Debug logging
// ============================================================================

void telemetry_debug_log(const TelemetryRecorder* tr) {
    if (tr == 0) return;

    MSFS_Log("[TELEM] Recorder: frames=%d/%d  events=%d/%d  recording=%d  paused=%d  full=%d",
             tr->frame_count, C_HUD_TELEMETRY_MAX_FRAMES,
             tr->event_count, C_HUD_TELEMETRY_MAX_EVENTS,
             (int)tr->recording, (int)tr->paused, (int)tr->buffer_full);

    if (tr->frame_count > 0) {
        const TelemetryFrame* first = telemetry_recorder_get_frame(tr, 0);
        const TelemetryFrame* last  = telemetry_recorder_get_frame(tr, tr->frame_count - 1);
        if (first != 0 && last != 0) {
            MSFS_Log("[TELEM] Range: frame %d..%d  time %.2f..%.2fs  "
                     "alt %.0f..%.0fm  RA %.1f..%.1fm",
                     first->frame_index, last->frame_index,
                     first->timestamp_s, last->timestamp_s,
                     first->ac_alt_m, last->ac_alt_m,
                     first->ac_radio_alt_m, last->ac_radio_alt_m);
        }
    }
}
