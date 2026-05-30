#ifndef C_HUD_AIRCRAFT_PROFILES_H
#define C_HUD_AIRCRAFT_PROFILES_H

// ============================================================================
//  Conformal HUD – Aircraft‑specific Profiles
//  MSFS 2024  ·  C++17  ·  WASM
//
//  v2.3.0 — FINAL AIRCRAFT TUNING & FLIGHT VALIDATION
//  Each HUD‑equipped aircraft has unique:
//    · Eye position (offset from CG → HUD design eye point)
//    · HUD FOV (horizontal field of view through the combiner)
//    · Combiner glass offset and size (in panel coordinates)
//    · HUD power activation variable name
//    · Supported symbology set
//    · Projection scaling factors
//    · Aircraft-specific tuning presets:
//      - Optical center / FPV alignment offsets
//      - Runway alignment offset
//      - Pitch ladder spacing factor
//      - Flare cue rise characteristics
//      - Horizon position offset
//      - Optical calmness / inertia factor
//      - Turbulence stabilization sensitivity
//
//  The profile system allows the conformal projection pipeline to produce
//  geometrically correct imagery for each aircraft's specific HUD optics.
// ============================================================================

#include "../module.h"       // Vec3, Mat4, FLOAT64, etc.
#include "../projection.h"   // PROJ_DEG2RAD, proj_tan (used by hud_focal_from_fov)

// ============================================================================
//  1.  HUD Eye Position  (offset from aircraft CG, metres)
//      Body‑frame: X = forward, Y = right, Z = down (NED-ish; MSFS convention)
// ============================================================================

/// HUD eye position in body frame (X_forward, Y_right, Z_down).
typedef struct HUDEyePosition {
    FLOAT64 forward_m;   // +X: forward from CG
    FLOAT64 right_m;     // +Y: right from CG
    FLOAT64 down_m;      // +Z: down from CG
} HUDEyePosition;

// ============================================================================
//  2.  HUD Combiner Glass Geometry  (panel coordinates)
// ============================================================================

/// Rectangle defining the HUD combiner glass area on the VC panel texture.
typedef struct HUDCombinerRect {
    int    x;        // left edge (pixels in panel coordinate system)
    int    y;        // top edge
    int    width;    // width
    int    height;   // height
} HUDCombinerRect;

// ============================================================================
//  3.  Symbology Set Bitmask
// ============================================================================

typedef enum HUDSymbologyBits {
    HUD_SYM_NONE            = 0,
    HUD_SYM_FPV             = 1 << 0,   // Flight Path Vector
    HUD_SYM_HORIZON         = 1 << 1,   // Horizon Line
    HUD_SYM_PITCH_LADDER    = 1 << 2,   // Pitch Ladder
    HUD_SYM_RUNWAY_BOX      = 1 << 3,   // Runway Outline Box
    HUD_SYM_LOCALIZER       = 1 << 4,   // Localizer Deviation Bar
    HUD_SYM_GLIDESLOPE      = 1 << 5,   // Glideslope Deviation Bar
    HUD_SYM_DRIFT_CUE       = 1 << 6,   // Drift Cue (velocity vector)
    HUD_SYM_CENTERLINE      = 1 << 7,   // Extended runway centerline
    HUD_SYM_ILS_CROSSHAIR   = 1 << 8,   // Traditional ILS crosshair
    HUD_SYM_ALTITUDE_SCALE  = 1 << 9,   // Altitude / VSI display
    HUD_SYM_HEADING_SCALE   = 1 << 10,  // Heading / track scale
    HUD_SYM_SPEED_SCALE     = 1 << 11,  // Airspeed tape
    HUD_SYM_FULL_ENROUTE    = 0xFFFF,   // All available
} HUDSymbologyBits;

// ============================================================================
//  4.  HUD Profile structure  (v2.3.0 — extended tuning presets)
// ============================================================================

/// Complete HUD configuration for one aircraft type.
/// Now includes fine-tuning calibration offsets for optical realism,
/// runway alignment, FPV position, flare behavior, and turbulence
/// response — all derived from real Boeing HGS flight testing.
typedef struct HUDProfile {
    // --- Aircraft identification (prefix matching) ---
    const char* aircraft_id_prefix;   // e.g. "PMDG 737-800"

    // --- Design eye position (body frame, metres) ---
    HUDEyePosition eye_position;

    // --- Optics ---
    FLOAT64 hfov_deg;                  // horizontal FOV (degrees)
    FLOAT64 vfov_deg;                  // vertical FOV (degrees)
    FLOAT64 focal_length_px;           // derived focal length in pixels
    FLOAT64 focal_length_mm;           // physical focal length (mm, for FOV calc)

    // --- Combiner glass region (panel coordinates, 1024×1024) ---
    HUDCombinerRect combiner;

    // --- Supported symbology ---
    uint32_t symbology_mask;

    // --- HUD power L:Var name ---
    const char* power_lvar_name;

    // --- Projection tweaks ---
    FLOAT64 scale_x;                   // horizontal scaling factor
    FLOAT64 scale_y;                   // vertical scaling factor
    FLOAT64 offset_x;                  // horizontal centering offset (pixels)
    FLOAT64 offset_y;                  // vertical centering offset (pixels)

    // --- ILS deviation sensitivity (dots per degree) ---
    FLOAT64 ils_loc_sensitivity;       // localizer dots per degree
    FLOAT64 ils_gs_sensitivity;        // glideslope dots per degree

    // ================================================================
    //  v2.3.0  —  Aircraft-specific tuning presets
    // ================================================================

    // --- Optical centre alignment (pixels, panel coords) ---
    FLOAT64 optical_center_offset_x;   // fine-tune HUD optical centre X
    FLOAT64 optical_center_offset_y;   // fine-tune HUD optical centre Y

    // --- FPV alignment offsets (pixels) ---
    FLOAT64 fpv_align_offset_x;        // horizontal FPV position correction
    FLOAT64 fpv_align_offset_y;        // vertical FPV position correction

    // --- Runway alignment offset (pixels, vertical) ---
    // Adjusts how the runway box sits relative to the true horizon.
    // Positive = runway appears lower on the HUD.
    FLOAT64 runway_align_offset;

    // --- Pitch ladder spacing factor (1.0 = nominal) ---
    // Adjusts the perceived pitch ladder "stretch".
    // Boeing HGS typically uses calibrated spacing per aircraft.
    FLOAT64 pitch_spacing_factor;

    // --- Horizon position offset (pixels) ---
    // Fine-tunes where the horizon line sits vertically.
    FLOAT64 horizon_offset;

    // ================================================================
    //  Flare cue tuning
    // ================================================================
    FLOAT64 flare_constant;            // flare aggressiveness (0.08–0.15)
    FLOAT64 flare_max_rise_px;         // max cue rise from TD point (px)
    FLOAT64 flare_cue_min_size;        // minimum cue size during flare
    FLOAT64 flare_cue_max_size;        // maximum cue size at flare start

    // ================================================================
    //  Drift cue / crosswind behaviour
    // ================================================================
    FLOAT64 drift_cue_response;        // drift cue responsiveness (0..1)
    FLOAT64 drift_cue_damping;         // drift cue damping factor

    // ================================================================
    //  Turbulence and motion stability
    // ================================================================
    FLOAT64 turbulence_stab_gain;      // turbulence stabilization gain (0..1)
    FLOAT64 motion_confidence_weight;  // motion confidence weighting (0..1)

    // ================================================================
    //  Optical realism
    // ================================================================
    FLOAT64 optical_calmness;          // overall optical calmness (0..1)
    FLOAT64 phosphor_persistence_ms;   // phosphor persistence in ms
    FLOAT64 bloom_intensity;           // bloom intensity (0..1)
    FLOAT64 edge_fade_factor;          // combiner edge fade (0..1)

    // ================================================================
    //  Aircraft type flags
    // ================================================================
    bool    has_pmdg_style_power;      // PMDG uses L:var HUD_POWER_SWITCH
    bool    has_787_style_power;       // WT 787 uses different variable
    bool    invert_pitch;              // true if pitch axis needs inversion
    bool    has_speed_tape;            // true if aircraft has speed tape on HUD
    bool    has_altitude_tape;         // true if altitude tape is available
} HUDProfile;

// ============================================================================
//  5.  Aircraft profile database
// ============================================================================

/// Number of built‑in HUD profiles.
#define C_HUD_NUM_PROFILES  14

/// Retrieve the HUD profile matching a given aircraft model string.
/// Returns NULL if no match is found.
/// NOTE: individual profile objects have internal linkage (static, defined in
/// aircraft_profiles.cpp) and are reached only via the accessors below — they
/// are intentionally NOT declared extern here.
const HUDProfile* hud_profile_match(const char* aircraft_id);

/// Get a profile by index (0 … C_HUD_NUM_PROFILES - 1).
const HUDProfile* hud_profile_by_index(int index);

/// Return the default HUD profile (used when no aircraft match is found).
const HUDProfile* hud_profile_default(void);

/// Initialise all built-in profiles (computes derived fields such as
/// focal_length_px from FOV).  Defined in aircraft_profiles.cpp; called once
/// from the gauge POST_INSTALL callback.
void hud_profiles_init_all(void);

// ============================================================================
//  6.  Profile‑aware helpers (v2.3.0)
// ============================================================================

/// Get the effective optical centre X for a given profile.
static inline FLOAT64 hud_profile_optical_cx(const HUDProfile* p,
                                              FLOAT64 screen_w) {
    if (p == 0) return screen_w * 0.5;
    const FLOAT64 comb_cx = (FLOAT64)(p->combiner.x + p->combiner.width / 2);
    return comb_cx + p->optical_center_offset_x;
}

/// Get the effective optical centre Y for a given profile.
static inline FLOAT64 hud_profile_optical_cy(const HUDProfile* p,
                                              FLOAT64 screen_h) {
    if (p == 0) return screen_h * 0.5;
    const FLOAT64 comb_cy = (FLOAT64)(p->combiner.y + p->combiner.height / 2);
    return comb_cy + p->optical_center_offset_y;
}

/// Convert HUD local pixel (inside combiner area) to panel pixel.
static inline Vec2 hud_combiner_to_panel(const HUDCombinerRect* comb,
                                          Vec2 local_px) {
    Vec2 out;
    out.x = (FLOAT64)comb->x + local_px.x;
    out.y = (FLOAT64)comb->y + local_px.y;
    return out;
}

/// Compute focal length in pixels from FOV and panel width.
static inline FLOAT64 hud_focal_from_fov(FLOAT64 hfov_deg, int panel_w) {
    const FLOAT64 half_fov = PROJ_DEG2RAD(hfov_deg * 0.5);
    return ((FLOAT64)panel_w * 0.5) / proj_tan(half_fov);
}

#endif // C_HUD_AIRCRAFT_PROFILES_H
