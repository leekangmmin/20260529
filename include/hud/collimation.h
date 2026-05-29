#ifndef C_HUD_COLLIMATION_H
#define C_HUD_COLLIMATION_H

// ============================================================================
//  Conformal HUD – Semi-Collimated (Optically Stabilised) Rendering
//  MSFS 2024  ·  C++17  ·  WASM
//
//  Implements semi-collimated HUD behaviour that compensates for small
//  eyepoint movements, maintains runway symbol stability, and reduces
//  symbol drift during head movement via adaptive reprojection using
//  camera offset deltas.
//
//  A real HGS combiner collimates symbology so it appears at optical
//  infinity, making it visually attached to the outside world regardless
//  of small head movements. This module simulates that behaviour by
//  tracking camera position deltas and adjusting the projection
//  accordingly.
// ============================================================================

#include "../module.h"
#include "../projection.h"

// ============================================================================
//  1.  Camera delta tracking state
// ============================================================================

/// Tracks cumulative camera offset that should be compensated.
/// In the real HUD, the combiner glass and collimating optics keep
/// symbology fixed in world space; here we track how much the virtual
/// camera (HUD eye) has moved each frame and compensate the projection
/// origin so symbology stays anchored to the world.
typedef struct CameraDelta {
    Vec3    delta_body;         // cumulative head offset from reference (m)
    Vec3    delta_world;        // cumulative head offset in world NEU (m)
    Vec3    prev_eye_offset;    // previous frame eye offset (body frame)
    Vec3    prev_ac_ref;        // previous frame aircraft reference position
    FLOAT64 prev_heading;       // previous heading (deg)
    FLOAT64 prev_pitch;         // previous pitch (deg)
    FLOAT64 prev_bank;          // previous bank (deg)

    // Adaptive compensation parameters
    FLOAT64 compensation_gain;  // how much to compensate (0-1)
    FLOAT64 max_compensation_m; // maximum compensation magnitude (m)
    bool    initialised;
} CameraDelta;

// ============================================================================
//  2.  Eye offset compensation state
// ============================================================================

/// Computes the effective eye offset for a given frame, taking into
/// account the profile's design eye point plus any dynamic compensation
/// from head tracking / camera movement.
typedef struct EyeCompensation {
    Vec3    base_offset;        // profile design eye offset (body frame, m)
    Vec3    dynamic_offset;     // additional dynamic compensation (body frame, m)
    Vec3    effective_offset;   // base + dynamic (body frame, m)
    FLOAT64 head_offset_x;      // debug: head offset forward (m)
    FLOAT64 head_offset_y;      // debug: head offset right (m)
    FLOAT64 head_offset_z;      // debug: head offset down (m)
    bool    valid;
} EyeCompensation;

// ============================================================================
//  3.  Collimation correction output
// ============================================================================

/// The stabilised eye position used for projection, after collimation-
/// style correction has been applied.
typedef struct CollimationCorrection {
    Vec3    stabilised_eye;     // the effective eye position for projection
    Vec3    raw_eye;            // the raw (uncorrected) eye position
    Vec3    correction_vector;  // delta = stabilised - raw
    FLOAT64 correction_mag_m;  // magnitude of correction (m)
    bool    active;             // true when correction is being applied

    // Debug telemetry
    FLOAT64 debug_camera_delta_x;
    FLOAT64 debug_camera_delta_y;
    FLOAT64 debug_camera_delta_z;
    FLOAT64 debug_compensation_gain;
} CollimationCorrection;

// ============================================================================
//  4.  Initialisation
// ============================================================================

/// Initialise the camera delta tracker.
static inline void camera_delta_init(CameraDelta* cd) {
    if (cd == 0) return;
    cd->delta_body    = proj_vec3_zero();
    cd->delta_world   = proj_vec3_zero();
    cd->prev_eye_offset  = proj_vec3_zero();
    cd->prev_ac_ref      = proj_vec3_zero();
    cd->prev_heading = 0.0;
    cd->prev_pitch   = 0.0;
    cd->prev_bank    = 0.0;
    cd->compensation_gain    = 0.85;   // 85% compensation (HGS typical)
    cd->max_compensation_m   = 0.15;   // max 15 cm compensation
    cd->initialised = false;
}

/// Initialise eye compensation structure from a profile eye offset.
static inline void eye_comp_init(EyeCompensation* ec, Vec3 base_offset) {
    if (ec == 0) return;
    ec->base_offset      = base_offset;
    ec->dynamic_offset   = proj_vec3_zero();
    ec->effective_offset = base_offset;
    ec->head_offset_x    = 0.0;
    ec->head_offset_y    = 0.0;
    ec->head_offset_z    = 0.0;
    ec->valid = true;
}

/// Initialise collimation correction to identity.
static inline void collimation_init(CollimationCorrection* cc) {
    if (cc == 0) return;
    cc->stabilised_eye     = proj_vec3_zero();
    cc->raw_eye            = proj_vec3_zero();
    cc->correction_vector  = proj_vec3_zero();
    cc->correction_mag_m   = 0.0;
    cc->active             = false;
    cc->debug_camera_delta_x = 0.0;
    cc->debug_camera_delta_y = 0.0;
    cc->debug_camera_delta_z = 0.0;
    cc->debug_compensation_gain = 0.85;
}

// ============================================================================
//  5.  Core compensation update
// ============================================================================

/// Update camera delta tracking and compute collimation correction.
///
/// Should be called each frame with the current eye offset and aircraft
/// position BEFORE the main projection pipeline runs.
///
/// @param cd            [in/out] Camera delta tracker state
/// @param current_eye   Current eye offset (body frame, m)
/// @param ac_ref        Current aircraft reference position (lon, alt, lat)
/// @param heading_deg   Current heading (deg)
/// @param pitch_deg     Current pitch (deg)
/// @param bank_deg      Current bank (deg)
/// @param dt_s          Frame delta time (seconds)
/// @param cc            [out] Collimation correction to apply
void collimation_update(CameraDelta*        cd,
                         Vec3                current_eye,
                         Vec3                ac_ref,
                         FLOAT64             heading_deg,
                         FLOAT64             pitch_deg,
                         FLOAT64             bank_deg,
                         FLOAT64             dt_s,
                         CollimationCorrection* cc);

/// Apply collimation correction to an eye offset for projection.
///
/// This modifies the eye offset so that symbology remains world-stable
/// despite small camera movements.
///
/// @param base_offset   Original eye offset (body frame)
/// @param cc            Collimation correction from collimation_update()
/// @returns             Corrected eye offset for projection
static inline Vec3 collimation_apply(Vec3 base_offset,
                                      const CollimationCorrection* cc) {
    if (cc == 0 || !cc->active) {
        return base_offset;
    }
    // The correction vector is applied to the eye offset
    return proj_vec3_add(base_offset, cc->correction_vector);
}

// ============================================================================
//  6.  Debug logging
// ============================================================================

void collimation_debug_log(const CameraDelta* cd,
                            const CollimationCorrection* cc);

#endif // C_HUD_COLLIMATION_H
