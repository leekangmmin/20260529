// ============================================================================
//  Conformal HUD – Semi-Collimated (Optically Stabilised) Rendering
//  MSFS 2024  ·  C++17  ·  WASM
//
//  Implements the compensation logic for semi-collimated HUD rendering.
//  Tracks camera deltas and computes correction vectors so that
//  symbology remains visually attached to the outside world despite
//  small eyepoint movements.
// ============================================================================

#include "../../include/hud/collimation.h"
#include "../../include/projection.h"

// ============================================================================
//  1.  Collimation update
// ============================================================================

void collimation_update(CameraDelta*        cd,
                         Vec3                current_eye,
                         Vec3                ac_ref,
                         FLOAT64             heading_deg,
                         FLOAT64             pitch_deg,
                         FLOAT64             bank_deg,
                         FLOAT64             dt_s,
                         CollimationCorrection* cc) {
    if (cd == 0 || cc == 0) {
        return;
    }

    // Initialise outputs
    cc->active = false;
    cc->correction_vector = proj_vec3_zero();
    cc->correction_mag_m = 0.0;
    cc->debug_compensation_gain = cd->compensation_gain;

    if (!cd->initialised) {
        // First frame: store everything, no correction yet
        cd->prev_eye_offset = current_eye;
        cd->prev_ac_ref     = ac_ref;
        cd->prev_heading    = heading_deg;
        cd->prev_pitch      = pitch_deg;
        cd->prev_bank       = bank_deg;
        cd->delta_body      = proj_vec3_zero();
        cd->delta_world     = proj_vec3_zero();
        cd->initialised     = true;

        cc->stabilised_eye    = current_eye;
        cc->raw_eye           = current_eye;
        cc->correction_vector = proj_vec3_zero();
        cc->correction_mag_m  = 0.0;
        cc->active            = false;
        return;
    }

    // --- Compute body-frame delta ---
    // The delta is how much the eye offset has changed relative to
    // the previous frame, plus any change due to aircraft motion.
    Vec3 eye_delta_body = proj_vec3_sub(current_eye, cd->prev_eye_offset);

    // --- Accumulate the delta (leaky integrator to prevent drift) ---
    const FLOAT64 leak = 0.995;  // slow decay over ~200 frames
    cd->delta_body.x = cd->delta_body.x * leak + eye_delta_body.x;
    cd->delta_body.y = cd->delta_body.y * leak + eye_delta_body.y;
    cd->delta_body.z = cd->delta_body.z * leak + eye_delta_body.z;

    // Clamp accumulated delta to max compensation
    FLOAT64 delta_len = proj_vec3_len(cd->delta_body);
    if (delta_len > cd->max_compensation_m) {
        const FLOAT64 scale = cd->max_compensation_m / delta_len;
        cd->delta_body = proj_vec3_scale(cd->delta_body, scale);
    }

    // --- Compute correction vector ---
    // Apply compensation gain, then invert so it counteracts the movement
    cc->correction_vector = proj_vec3_scale(cd->delta_body, -cd->compensation_gain);
    cc->correction_mag_m = proj_vec3_len(cc->correction_vector);

    // --- Fill debug telemetry ---
    cc->debug_camera_delta_x = cd->delta_body.x;
    cc->debug_camera_delta_y = cd->delta_body.y;
    cc->debug_camera_delta_z = cd->delta_body.z;

    // --- Compute stabilised eye ---
    cc->raw_eye = current_eye;
    cc->stabilised_eye = proj_vec3_add(current_eye, cc->correction_vector);

    // Activate if the correction is significant (> 1 mm)
    cc->active = (cc->correction_mag_m > 0.001);

    // --- Store for next frame ---
    cd->prev_eye_offset = current_eye;
    cd->prev_ac_ref     = ac_ref;
    cd->prev_heading    = heading_deg;
    cd->prev_pitch      = pitch_deg;
    cd->prev_bank       = bank_deg;
}

// ============================================================================
//  2.  Debug logging
// ============================================================================

void collimation_debug_log(const CameraDelta* cd,
                            const CollimationCorrection* cc) {
    if (cd == 0 || cc == 0) {
        MSFS_Log("[C_HUD_COLL] CameraDelta or CollimationCorrection: NULL");
        return;
    }

    MSFS_Log("[C_HUD_COLL] delta_body=(%.4f, %.4f, %.4f)  "
             "comp_gain=%.2f  max_comp=%.3f  init=%d",
             cd->delta_body.x, cd->delta_body.y, cd->delta_body.z,
             cd->compensation_gain, cd->max_compensation_m,
             (int)cd->initialised);

    MSFS_Log("[C_HUD_COLL] Correction: active=%d  mag=%.4fm  "
             "vec=(%.4f, %.4f, %.4f)  "
             "raw_eye=(%.4f, %.4f, %.4f)  stab_eye=(%.4f, %.4f, %.4f)",
             (int)cc->active, cc->correction_mag_m,
             cc->correction_vector.x, cc->correction_vector.y,
             cc->correction_vector.z,
             cc->raw_eye.x, cc->raw_eye.y, cc->raw_eye.z,
             cc->stabilised_eye.x, cc->stabilised_eye.y,
             cc->stabilised_eye.z);
}
