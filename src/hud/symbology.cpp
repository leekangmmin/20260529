// ============================================================================
//  Conformal HUD – Symbology Manager Implementation
//  MSFS 2024  ·  C++17  ·  WASM
//
//  Orchestrates all HUD symbology computation, projection, and publishing.
//  Extended in v2.1.0 with collimation, flare, EVS, advanced symbology,
//  and all publishing helpers.
// ============================================================================

#include "../../include/hud/symbology.h"
#include "../../include/hud/aircraft_profiles.h"
#include "../../include/hud/runway_projection.h"
#include "../../include/hud/fpv.h"
#include "../../include/hud/guidance.h"
#include "../../include/hud/collimation.h"
#include "../../include/hud/flare.h"
#include "../../include/hud/evs.h"
#include "../../include/hud/stabilization.h"
#include "../../include/hud/advanced_symbology.h"
#include "../../include/projection.h"

// ============================================================================
//  1.  Main computation entry point
// ============================================================================

bool sym_compute_all(const ModuleState* state,
                     const sGaugeDrawData* dd,
                     HUDOutput* output) {
    if (output == 0) {
        return false;
    }

    // Reset
    __builtin_memset(output, 0, sizeof(HUDOutput));
    output->valid = false;

    if (state == 0 || dd == 0 || !state->initialised) {
        return false;
    }

    // --- Get aircraft profile ---
    const HUDProfile* profile = hud_profile_match(state->aircraft_id);
    if (profile == 0) {
        profile = hud_profile_default();
    }
    output->profile = profile;

    // --- HUD active check ---
    output->hud_active = state->hud_allowed && state->hud_power_on;
    if (!output->hud_active) {
        output->valid = true;
        return false;
    }

    // --- Screen dimensions ---
    const int screen_w = (dd->winWidth  > 0 && dd->winWidth  <= 4096)
                          ? dd->winWidth  : C_HUD_PANEL_WIDTH;
    const int screen_h = (dd->winHeight > 0 && dd->winHeight <= 4096)
                          ? dd->winHeight : C_HUD_PANEL_HEIGHT;

    // --- Focal length ---
    FLOAT64 focal_px = profile->focal_length_px;
    if (focal_px <= 0.0) {
        focal_px = 520.0;  // fallback
    }
    output->focal_px = focal_px;

    // --- HUD origin (centre of combiner) ---
    output->hud_origin.x = (FLOAT64)(profile->combiner.x + profile->combiner.width / 2);
    output->hud_origin.y = (FLOAT64)(profile->combiner.y + profile->combiner.height / 2);

    // --- Read aircraft state ---
    output->line_width_px = state->weather.line_width_px;
    output->opacity = state->weather.opacity;
    output->frame_count = state->frame_counter;

    output->valid = true;
    return true;
}

// ============================================================================
//  2.  Horizon computation
// ============================================================================

void sym_compute_horizon(const ModuleState* state,
                         const HUDProfile* profile,
                         FLOAT64 focal_px,
                         int screen_w,
                         int screen_h,
                         HUDOutput* output) {
    if (output == 0 || state == 0) return;

    const FLOAT64 pitch_deg = state->ac_pitch_deg;
    const FLOAT64 bank_deg  = state->ac_bank_deg;

    // Horizon Y position in screen space
    const FLOAT64 p_rad = PROJ_DEG2RAD(pitch_deg);
    output->horizon_y = (FLOAT64)(screen_h / 2) -
                         focal_px * proj_tan(p_rad);

    // Horizon slope from bank
    const FLOAT64 b_rad = PROJ_DEG2RAD(bank_deg);
    output->horizon_slope = proj_tan(b_rad);

    output->horizon_valid = true;
}

// ============================================================================
//  3.  Pitch ladder computation
// ============================================================================

void sym_compute_pitch_ladder(const ModuleState* state,
                              const HUDProfile* profile,
                              FLOAT64 focal_px,
                              int screen_w,
                              int screen_h,
                              HUDOutput* output) {
    (void)state;
    (void)profile;
    if (output == 0) return;

    // Pitch ladder lines at +/-5 deg, +/-10 deg, +/-15 deg
    const int num_lines = 5;
    const FLOAT64 pitch_angles[] = { -10.0, -5.0, 0.0, 5.0, 10.0 };

    const FLOAT64 cx = (FLOAT64)(screen_w / 2);
    const FLOAT64 cy = (FLOAT64)(screen_h / 2);

    for (int i = 0; i < num_lines && i < 5; ++i) {
        const FLOAT64 angle_deg = pitch_angles[i];
        const FLOAT64 a_rad = PROJ_DEG2RAD(angle_deg);
        const FLOAT64 y_offset = focal_px * proj_tan(a_rad);

        const FLOAT64 line_y = cy - y_offset;

        // Line endpoints (80 px wide centered)
        const FLOAT64 half_w = 40.0;
        output->pitch_lines[i].verts[0].x = cx - half_w;
        output->pitch_lines[i].verts[0].y = line_y;
        output->pitch_lines[i].verts[1].x = cx + half_w;
        output->pitch_lines[i].verts[1].y = line_y;
        output->pitch_lines[i].count = 2;
        output->pitch_lines[i].valid = true;
    }

    output->pitch_line_count = num_lines;
    output->pitch_ladder_valid = true;
}

// ============================================================================
//  4.  v2.1.0 - Semi-collimated computation
// ============================================================================

void sym_compute_collimation(CameraDelta* cd,
                              HUDOutput* output,
                              Vec3 current_eye_offset,
                              Vec3 ac_ref,
                              FLOAT64 heading_deg,
                              FLOAT64 pitch_deg,
                              FLOAT64 bank_deg,
                              FLOAT64 dt_s) {
    if (cd == 0 || output == 0) return;

    // Use the externally-managed CameraDelta passed by the caller
    // (main.cpp owns g_hud.camera_delta and initialises it once).
    collimation_update(cd, current_eye_offset,
                        ac_ref, heading_deg, pitch_deg, bank_deg,
                        dt_s, &output->collimation);

    // Apply compensation to get corrected eye offset
    output->corrected_eye_offset = collimation_apply(current_eye_offset,
                                                      &output->collimation);
    output->collimation_active = output->collimation.active;
}

// ============================================================================
//  5.  v2.1.0 - Flare guidance computation
// ============================================================================

void sym_compute_flare(HUDOutput* output,
                        FLOAT64 focal_px,
                        int screen_w,
                        int screen_h,
                        Vec2 td_reference,
                        FLOAT64 dt_s) {
    if (output == 0) return;

    // Compute flare state
    flare_compute(&output->flare, dt_s);

    // Project flare cue
    // v2.3.0: pass default flare tuning parameters
    flare_project_cue(&output->flare, focal_px, screen_w, screen_h,
                       td_reference, &output->flare_cue,
                       0.10,   // default flare_constant
                       80.0,   // default max_rise_px
                       12.0,   // default min_cue_size
                       28.0);  // default max_cue_size

    // Project touchdown zone
    flare_project_touchdown(&output->flare, focal_px, screen_w, screen_h,
                             td_reference, &output->touchdown_zone);

    output->flare_visible = output->flare_cue.visible ||
                            output->touchdown_zone.visible;
}

// ============================================================================
//  6.  v2.1.0 - EVS computation
// ============================================================================

void sym_compute_evs(HUDOutput* output, int phase) {
    if (output == 0) return;

    // Compute EVS enhancement
    evs_compute(&output->evs, phase);

    // Apply EVS to rendering parameters
    // (We pass a temporary WeatherState built from output line_width/opacity)
    WeatherState base;
    __builtin_memset(&base, 0, sizeof(base));
    base.line_width_px = output->line_width_px;
    base.opacity       = output->opacity;
    base.valid         = true;

    evs_apply(&output->evs, &base, &output->evs_render);
    output->evs_active = output->evs_render.evs_active;
}

// ============================================================================
//  7.  v2.1.0 - Advanced symbology computation
// ============================================================================

void sym_compute_advanced(HUDOutput* output,
                           Vec3 ac_ref,
                           const Mat4* b2w,
                           Vec3 eye_offset,
                           FLOAT64 focal_px,
                           int screen_w,
                           int screen_h) {
    if (output == 0 || b2w == 0) return;

    // --- Acceleration caret ---
    // Positioned near the speed indicator (left side of HUD)
    const FLOAT64 speed_tape_x = (FLOAT64)(screen_w / 2) - 120.0;
    const FLOAT64 speed_tape_y = (FLOAT64)(screen_h / 2);
    accel_compute(&output->accel_caret, focal_px, screen_w, screen_h,
                   speed_tape_x, speed_tape_y);

    // --- Energy trend ---
    energy_compute(&output->energy_trend, focal_px, screen_w, screen_h,
                    speed_tape_x, speed_tape_y);

    // --- Flare anticipation bracket ---
    const FLOAT64 ref_y = (FLOAT64)(screen_h / 2) + 50.0;  // below centre
    flare_bracket_compute(&output->flare_bracket, focal_px,
                           screen_w, screen_h, ref_y);

    // --- Touchdown predictor ---
    td_predictor_compute(&output->td_predictor, ac_ref, b2w,
                          eye_offset, focal_px, screen_w, screen_h);

    // --- Velocity trend ---
    velocity_trend_compute(&output->velocity_trend, focal_px,
                            screen_w, screen_h, speed_tape_x, speed_tape_y);
}

// ============================================================================
//  8.  Publishing to L:vars
// ============================================================================

// [DEPRECATED in v2.7.0] Never called from production code.
// Publishing now handled directly in module_update_publish() in main.cpp.
void sym_publish_all(HUDOutput* output) {
    if (output == 0 || !output->valid) {
        return;
    }

    // --- HUD active flag ---
    // (Published via dedicated token in main.cpp)

    // --- Runway ---
    if (output->runway.valid && output->runway_visible) {
        sym_publish_runway(&output->runway);
    }

    // --- FPV ---
    if (output->fpv.valid && output->fpv_visible) {
        sym_publish_fpv(&output->fpv);
    }

    // --- Guidance ---
    if (output->guidance.valid && output->guidance_visible) {
        sym_publish_guidance(&output->guidance);
    }

    // --- Horizon / Pitch ---
    if (output->horizon_valid || output->pitch_ladder_valid) {
        sym_publish_horizon(output);
    }

    // --- Flare ---
    if (output->flare_visible) {
        sym_publish_flare(output);
    }

    // --- Collimation debug ---
    if (output->collimation_active) {
        sym_publish_collimation_debug(output);
    }

    // --- EVS ---
    if (output->evs_active) {
        sym_publish_evs(output);
    }
}

// [DEPRECATED in v2.7.0 - stub, never called]
void sym_publish_runway(const ProjectedRunway* runway) {
    if (runway == 0 || !runway->valid) return;
    (void)runway;
}

// [DEPRECATED in v2.7.0 - stub, never called]
void sym_publish_fpv(const FPVState* fpv) {
    if (fpv == 0 || !fpv->valid) return;
    (void)fpv;
}

// [DEPRECATED in v2.7.0 - stub, never called]
void sym_publish_guidance(const GuidanceState* guidance) {
    if (guidance == 0 || !guidance->valid) return;
    (void)guidance;
}

// [DEPRECATED in v2.7.0 - stub, never called]
void sym_publish_horizon(const HUDOutput* output) {
    if (output == 0) return;
    (void)output;
}

// ============================================================================
//  9.  v2.1.0 Publishing helpers
// ============================================================================

// [DEPRECATED in v2.7.0 - stub, never called from production]
void sym_publish_flare(const HUDOutput* output) {
    if (output == 0) return;

    // L:C_HUD_Flare_Active
    // L:C_HUD_Flare_Cue_X, L:C_HUD_Flare_Cue_Y
    // L:C_HUD_Flare_Cue_Size
    // L:C_HUD_Flare_Cue_Alpha
    // L:C_HUD_TDZone_X, L:C_HUD_TDZone_Y
    // L:C_HUD_TDZone_Size
    // L:C_HUD_Flare_Rise
    // L:C_HUD_Flare_Error
    (void)output;
}

// [DEPRECATED in v2.7.0 - stub, never called]
void sym_publish_collimation_debug(const HUDOutput* output) {
    if (output == 0) return;

    // L:C_HUD_Collimation_Active
    // L:C_HUD_Collimation_CorrMag
    // L:C_HUD_Collimation_CorrX, Y, Z
    // L:C_HUD_Collimation_DeltaX, Y, Z
    // L:C_HUD_Collimation_Gain
    (void)output;
}

// [DEPRECATED in v2.7.0 - stub, never called]
void sym_publish_evs(const HUDOutput* output) {
    if (output == 0) return;

    // L:C_HUD_EVS_Active
    // L:C_HUD_EVS_Intensity
    // L:C_HUD_EVS_ContrastBoost
    // L:C_HUD_EVS_GlowAmount
    // L:C_HUD_EVS_RunwayBoost
    (void)output;
}
