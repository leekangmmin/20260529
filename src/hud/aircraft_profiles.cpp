// ============================================================================
//  Conformal HUD – Aircraft Profiles Implementation
//  MSFS 2024  ·  C++17  ·  WASM
//
//  v2.3.0 — FINAL AIRCRAFT TUNING & FLIGHT VALIDATION
//  Defines the built-in HUD profiles for supported aircraft with
//  aircraft-grade tuning presets calibrated for realistic Boeing HGS
//  optical behaviour.
// ============================================================================

#include "../../include/hud/aircraft_profiles.h"
#include "../../include/projection.h"

// ============================================================================
//  1.  Profile database  —  v2.3.0 calibrated values
// ============================================================================

// --------------------------------------------------------------------------
//  PMDG 737-800 / 737-700 HUD profile
//  Based on Collins HGS-4000 system.
//  Eye position: ~0.5 m forward, centred laterally, ~1.2 m above CG.
//  FOV: 30° × 22.5°  (4:3 aspect, typical HGS)
//  Flare: moderate aggressiveness (flare_constant=0.10)
//  Pitch spacing: 1.0 (standard Boeing calibration)
// --------------------------------------------------------------------------
static const HUDProfile profile_pmdg_737 = {
    .aircraft_id_prefix     = "PMDG 737",
    .eye_position           = { 0.50, 0.0, -1.20 },
    .hfov_deg               = 30.0,
    .vfov_deg               = 22.5,
    .focal_length_px        = 0.0,
    .focal_length_mm        = 0.0,
    .combiner               = { 150, 250, 724, 524 },
    .symbology_mask         = (uint32_t)(HUD_SYM_FPV | HUD_SYM_HORIZON |
                                HUD_SYM_PITCH_LADDER | HUD_SYM_RUNWAY_BOX |
                                HUD_SYM_LOCALIZER | HUD_SYM_GLIDESLOPE |
                                HUD_SYM_DRIFT_CUE | HUD_SYM_CENTERLINE |
                                HUD_SYM_ILS_CROSSHAIR),
    .power_lvar_name        = "L:HUD_POWER_SWITCH",
    .scale_x                = 1.0,
    .scale_y                = 1.0,
    .offset_x               = 0.0,
    .offset_y               = 0.0,
    .ils_loc_sensitivity    = 0.16,
    .ils_gs_sensitivity     = 0.16,

    // --- v2.3.0 tuning presets ---
    .optical_center_offset_x  = 0.0,
    .optical_center_offset_y  = 0.0,
    .fpv_align_offset_x       = 0.0,
    .fpv_align_offset_y       = 0.0,
    .runway_align_offset      = 0.0,
    .pitch_spacing_factor     = 1.0,
    .horizon_offset           = 0.0,

    .flare_constant           = 0.10,
    .flare_max_rise_px        = 80.0,
    .flare_cue_min_size       = 12.0,
    .flare_cue_max_size       = 28.0,

    .drift_cue_response       = 0.70,
    .drift_cue_damping        = 0.60,

    .turbulence_stab_gain     = 0.65,
    .motion_confidence_weight = 0.75,

    .optical_calmness           = 0.80,
    .phosphor_persistence_ms    = 40.0,
    .bloom_intensity            = 0.15,
    .edge_fade_factor           = 0.20,

    .has_pmdg_style_power    = true,
    .has_787_style_power     = false,
    .invert_pitch            = false,
    .has_speed_tape          = false,
    .has_altitude_tape       = false,
};

// --------------------------------------------------------------------------
//  PMDG 777-300ER HUD profile
//  Wider FOV than 737 (33° × 24°).
//  Eye position: slightly further forward and higher.
//  Flare: slightly more aggressive to account for higher approach speeds.
//  Includes speed and altitude tapes (777 HUD is more feature-rich).
// --------------------------------------------------------------------------
static const HUDProfile profile_pmdg_777 = {
    .aircraft_id_prefix     = "PMDG 777",
    .eye_position           = { 0.60, 0.0, -1.30 },
    .hfov_deg               = 33.0,
    .vfov_deg               = 24.0,
    .focal_length_px        = 0.0,
    .focal_length_mm        = 0.0,
    .combiner               = { 140, 240, 744, 544 },
    .symbology_mask         = (uint32_t)(HUD_SYM_FPV | HUD_SYM_HORIZON |
                                HUD_SYM_PITCH_LADDER | HUD_SYM_RUNWAY_BOX |
                                HUD_SYM_LOCALIZER | HUD_SYM_GLIDESLOPE |
                                HUD_SYM_DRIFT_CUE | HUD_SYM_CENTERLINE |
                                HUD_SYM_ILS_CROSSHAIR |
                                HUD_SYM_ALTITUDE_SCALE | HUD_SYM_SPEED_SCALE),
    .power_lvar_name        = "L:HUD_POWER_SWITCH",
    .scale_x                = 1.0,
    .scale_y                = 1.0,
    .offset_x               = 0.0,
    .offset_y               = 0.0,
    .ils_loc_sensitivity    = 0.14,
    .ils_gs_sensitivity     = 0.14,

    // --- v2.3.0 tuning presets ---
    .optical_center_offset_x  = 2.0,
    .optical_center_offset_y  = -1.0,
    .fpv_align_offset_x       = 0.0,
    .fpv_align_offset_y       = 1.0,
    .runway_align_offset      = 0.0,
    .pitch_spacing_factor     = 0.98,
    .horizon_offset           = 0.0,

    .flare_constant           = 0.12,
    .flare_max_rise_px        = 90.0,
    .flare_cue_min_size       = 14.0,
    .flare_cue_max_size       = 30.0,

    .drift_cue_response       = 0.75,
    .drift_cue_damping        = 0.55,

    .turbulence_stab_gain     = 0.70,
    .motion_confidence_weight = 0.80,

    .optical_calmness           = 0.75,
    .phosphor_persistence_ms    = 45.0,
    .bloom_intensity            = 0.18,
    .edge_fade_factor           = 0.25,

    .has_pmdg_style_power    = true,
    .has_787_style_power     = false,
    .invert_pitch            = false,
    .has_speed_tape          = true,
    .has_altitude_tape       = true,
};

// --------------------------------------------------------------------------
//  WT / Asobo 787-10 HUD profile
//  Largest FOV of the three (36° × 26°).
//  Lower eye position (787 cockpit sits lower relative to CG).
//  Full symbology set including heading scale.
//  Flare: smoother (higher inertia, larger aircraft feel).
// --------------------------------------------------------------------------
static const HUDProfile profile_wt_787 = {
    .aircraft_id_prefix     = "ASOBO BOEING 787",
    .eye_position           = { 0.40, 0.0, -1.10 },
    .hfov_deg               = 36.0,
    .vfov_deg               = 26.0,
    .focal_length_px        = 0.0,
    .focal_length_mm        = 0.0,
    .combiner               = { 100, 200, 824, 624 },
    .symbology_mask         = (uint32_t)(HUD_SYM_FPV | HUD_SYM_HORIZON |
                                HUD_SYM_PITCH_LADDER | HUD_SYM_RUNWAY_BOX |
                                HUD_SYM_LOCALIZER | HUD_SYM_GLIDESLOPE |
                                HUD_SYM_DRIFT_CUE | HUD_SYM_CENTERLINE |
                                HUD_SYM_ILS_CROSSHAIR |
                                HUD_SYM_ALTITUDE_SCALE | HUD_SYM_HEADING_SCALE |
                                HUD_SYM_SPEED_SCALE),
    .power_lvar_name        = "L:HUD_POWER_SWITCH",
    .scale_x                = 1.0,
    .scale_y                = 1.0,
    .offset_x               = 0.0,
    .offset_y               = 0.0,
    .ils_loc_sensitivity    = 0.14,
    .ils_gs_sensitivity     = 0.14,

    // --- v2.3.0 tuning presets ---
    .optical_center_offset_x  = -1.0,
    .optical_center_offset_y  = 1.0,
    .fpv_align_offset_x       = 0.0,
    .fpv_align_offset_y       = -1.0,
    .runway_align_offset      = 0.0,
    .pitch_spacing_factor     = 1.02,
    .horizon_offset           = 0.0,

    .flare_constant           = 0.09,
    .flare_max_rise_px        = 85.0,
    .flare_cue_min_size       = 10.0,
    .flare_cue_max_size       = 26.0,

    .drift_cue_response       = 0.65,
    .drift_cue_damping        = 0.65,

    .turbulence_stab_gain     = 0.60,
    .motion_confidence_weight = 0.70,

    .optical_calmness           = 0.85,
    .phosphor_persistence_ms    = 35.0,
    .bloom_intensity            = 0.12,
    .edge_fade_factor           = 0.15,

    .has_pmdg_style_power    = false,
    .has_787_style_power     = true,
    .invert_pitch            = false,
    .has_speed_tape          = false,
    .has_altitude_tape       = false,
};

// --------------------------------------------------------------------------
//  WT_787_10 profile (alternative prefix for WT-authored variant).
//  Shares same geometry as the ASOBO 787 profile.
// --------------------------------------------------------------------------
static const HUDProfile profile_wt_787_alt = {
    .aircraft_id_prefix     = "WT_787",
    .eye_position           = { 0.40, 0.0, -1.10 },
    .hfov_deg               = 36.0,
    .vfov_deg               = 26.0,
    .focal_length_px        = 0.0,
    .focal_length_mm        = 0.0,
    .combiner               = { 100, 200, 824, 624 },
    .symbology_mask         = (uint32_t)(HUD_SYM_FPV | HUD_SYM_HORIZON |
                                HUD_SYM_PITCH_LADDER | HUD_SYM_RUNWAY_BOX |
                                HUD_SYM_LOCALIZER | HUD_SYM_GLIDESLOPE |
                                HUD_SYM_DRIFT_CUE | HUD_SYM_CENTERLINE |
                                HUD_SYM_ILS_CROSSHAIR),
    .power_lvar_name        = "L:HUD_POWER_SWITCH",
    .scale_x                = 1.0,
    .scale_y                = 1.0,
    .offset_x               = 0.0,
    .offset_y               = 0.0,
    .ils_loc_sensitivity    = 0.14,
    .ils_gs_sensitivity     = 0.14,

    // --- v2.3.0 tuning presets ---
    .optical_center_offset_x  = -1.0,
    .optical_center_offset_y  = 1.0,
    .fpv_align_offset_x       = 0.0,
    .fpv_align_offset_y       = -1.0,
    .runway_align_offset      = 0.0,
    .pitch_spacing_factor     = 1.02,
    .horizon_offset           = 0.0,

    .flare_constant           = 0.09,
    .flare_max_rise_px        = 85.0,
    .flare_cue_min_size       = 10.0,
    .flare_cue_max_size       = 26.0,

    .drift_cue_response       = 0.65,
    .drift_cue_damping        = 0.65,

    .turbulence_stab_gain     = 0.60,
    .motion_confidence_weight = 0.70,

    .optical_calmness           = 0.85,
    .phosphor_persistence_ms    = 35.0,
    .bloom_intensity            = 0.12,
    .edge_fade_factor           = 0.15,

    .has_pmdg_style_power    = false,
    .has_787_style_power     = true,
    .invert_pitch            = false,
    .has_speed_tape          = false,
    .has_altitude_tape       = false,
};

// --------------------------------------------------------------------------
//  Default / fallback profile (generic HUD).
//  Conservative tuning suitable for any aircraft.
// --------------------------------------------------------------------------
static const HUDProfile profile_default = {
    .aircraft_id_prefix     = "",
    .eye_position           = { 0.50, 0.0, -1.20 },
    .hfov_deg               = 30.0,
    .vfov_deg               = 22.5,
    .focal_length_px        = 0.0,
    .focal_length_mm        = 0.0,
    .combiner               = { 150, 250, 724, 524 },
    .symbology_mask         = (uint32_t)(HUD_SYM_FPV | HUD_SYM_HORIZON |
                                HUD_SYM_PITCH_LADDER | HUD_SYM_RUNWAY_BOX |
                                HUD_SYM_LOCALIZER | HUD_SYM_GLIDESLOPE |
                                HUD_SYM_DRIFT_CUE | HUD_SYM_CENTERLINE),
    .power_lvar_name        = "L:HUD_POWER_SWITCH",
    .scale_x                = 1.0,
    .scale_y                = 1.0,
    .offset_x               = 0.0,
    .offset_y               = 0.0,
    .ils_loc_sensitivity    = 0.15,
    .ils_gs_sensitivity     = 0.15,

    // --- v2.3.0 tuning presets ---
    .optical_center_offset_x  = 0.0,
    .optical_center_offset_y  = 0.0,
    .fpv_align_offset_x       = 0.0,
    .fpv_align_offset_y       = 0.0,
    .runway_align_offset      = 0.0,
    .pitch_spacing_factor     = 1.0,
    .horizon_offset           = 0.0,

    .flare_constant           = 0.10,
    .flare_max_rise_px        = 80.0,
    .flare_cue_min_size       = 12.0,
    .flare_cue_max_size       = 28.0,

    .drift_cue_response       = 0.60,
    .drift_cue_damping        = 0.50,

    .turbulence_stab_gain     = 0.50,
    .motion_confidence_weight = 0.50,

    .optical_calmness           = 0.70,
    .phosphor_persistence_ms    = 30.0,
    .bloom_intensity            = 0.10,
    .edge_fade_factor           = 0.15,

    .has_pmdg_style_power    = false,
    .has_787_style_power     = false,
    .invert_pitch            = false,
    .has_speed_tape          = false,
    .has_altitude_tape       = false,
};


// --------------------------------------------------------------------------
//  Airbus A350-900 / A350-1000 HUD profile
//  Based on Honeywell HUD (Airbus-standard).
//  Eye position: ~0.60 m forward, centred laterally, ~1.25 m above CG.
//  FOV: 32° × 24° (wider than 737, similar to 777).
//  Flare: soft (Airbus-style, flare_constant=0.08)
//  Pitch spacing: 1.0 (standard Airbus calibration)
//  Includes speed and altitude tapes.
//  Power: uses "L:A350_HUD_POWER" L:var.
//  Full CAT III capability.
// --------------------------------------------------------------------------
static const HUDProfile profile_a350 = {
    .aircraft_id_prefix     = "A350",
    .eye_position           = { 0.60, 0.0, -1.25 },
    .hfov_deg               = 32.0,
    .vfov_deg               = 24.0,
    .focal_length_px        = 0.0,
    .focal_length_mm        = 0.0,
    .combiner               = { 140, 240, 744, 544 },
    .symbology_mask         = (uint32_t)(HUD_SYM_FPV | HUD_SYM_HORIZON |
                                HUD_SYM_PITCH_LADDER | HUD_SYM_RUNWAY_BOX |
                                HUD_SYM_LOCALIZER | HUD_SYM_GLIDESLOPE |
                                HUD_SYM_DRIFT_CUE | HUD_SYM_CENTERLINE |
                                HUD_SYM_ILS_CROSSHAIR |
                                HUD_SYM_ALTITUDE_SCALE | HUD_SYM_SPEED_SCALE |
                                HUD_SYM_HEADING_SCALE),
    .power_lvar_name        = "L:A350_HUD_POWER",
    .scale_x                = 1.0,
    .scale_y                = 1.0,
    .offset_x               = 0.0,
    .offset_y               = 0.0,
    .ils_loc_sensitivity    = 0.14,
    .ils_gs_sensitivity     = 0.14,

    // --- v2.3.0 tuning presets — Airbus calmness ---
    .optical_center_offset_x  = 0.0,
    .optical_center_offset_y  = 0.0,
    .fpv_align_offset_x       = 1.0,
    .fpv_align_offset_y       = 0.0,
    .runway_align_offset      = 0.0,
    .pitch_spacing_factor     = 1.0,
    .horizon_offset           = 0.0,

    // Airbus flare: softer than Boeing (0.08 vs 0.10-0.12)
    .flare_constant           = 0.08,
    .flare_max_rise_px        = 75.0,
    .flare_cue_min_size       = 10.0,
    .flare_cue_max_size       = 26.0,

    // Airbus drift cue: slightly slower response
    .drift_cue_response       = 0.55,
    .drift_cue_damping        = 0.70,

    // Airbus turbulence: heavier damping
    .turbulence_stab_gain     = 0.75,
    .motion_confidence_weight = 0.85,

    // Airbus optical: calmer, less bloom, more persistence
    .optical_calmness           = 0.90,
    .phosphor_persistence_ms    = 45.0,
    .bloom_intensity            = 0.08,
    .edge_fade_factor           = 0.20,

    .has_pmdg_style_power    = false,
    .has_787_style_power     = false,
    .invert_pitch            = false,
    .has_speed_tape          = false,
    .has_altitude_tape       = false,
};

// --------------------------------------------------------------------------
//  iniBuilds A350 (INI A350 prefix) — same tuning as A350 profile.
//  Real iniBuilds A350 titles start with "INI A350".
// --------------------------------------------------------------------------
static const HUDProfile profile_a350_ini = {
    .aircraft_id_prefix     = "INI A350",
    .eye_position           = { 0.60, 0.0, -1.25 },
    .hfov_deg               = 32.0,
    .vfov_deg               = 24.0,
    .focal_length_px        = 0.0,
    .focal_length_mm        = 0.0,
    .combiner               = { 140, 240, 744, 544 },
    .symbology_mask         = (uint32_t)(HUD_SYM_FPV | HUD_SYM_HORIZON |
                                HUD_SYM_PITCH_LADDER | HUD_SYM_RUNWAY_BOX |
                                HUD_SYM_LOCALIZER | HUD_SYM_GLIDESLOPE |
                                HUD_SYM_DRIFT_CUE | HUD_SYM_CENTERLINE |
                                HUD_SYM_ILS_CROSSHAIR |
                                HUD_SYM_ALTITUDE_SCALE | HUD_SYM_SPEED_SCALE |
                                HUD_SYM_HEADING_SCALE),
    .power_lvar_name        = "L:A350_HUD_POWER",
    .scale_x                = 1.0,
    .scale_y                = 1.0,
    .offset_x               = 0.0,
    .offset_y               = 0.0,
    .ils_loc_sensitivity    = 0.14,
    .ils_gs_sensitivity     = 0.14,

    // --- v2.3.0 tuning presets — Airbus calmness ---
    .optical_center_offset_x  = 0.0,
    .optical_center_offset_y  = 0.0,
    .fpv_align_offset_x       = 1.0,
    .fpv_align_offset_y       = 0.0,
    .runway_align_offset      = 0.0,
    .pitch_spacing_factor     = 1.0,
    .horizon_offset           = 0.0,

    // Airbus flare: softer than Boeing (0.08 vs 0.10-0.12)
    .flare_constant           = 0.08,
    .flare_max_rise_px        = 75.0,
    .flare_cue_min_size       = 10.0,
    .flare_cue_max_size       = 26.0,

    // Airbus drift cue: slightly slower response
    .drift_cue_response       = 0.55,
    .drift_cue_damping        = 0.70,

    // Airbus turbulence: heavier damping
    .turbulence_stab_gain     = 0.75,
    .motion_confidence_weight = 0.85,

    // Airbus optical: calmer, less bloom, more persistence
    .optical_calmness           = 0.90,
    .phosphor_persistence_ms    = 45.0,
    .bloom_intensity            = 0.08,
    .edge_fade_factor           = 0.20,

    .has_pmdg_style_power    = false,
    .has_787_style_power     = false,
    .invert_pitch            = false,
    .has_speed_tape          = false,
    .has_altitude_tape       = false,
};

// --------------------------------------------------------------------------
//  iniBuilds A350 (INIBUILDS A350 prefix) — same tuning as A350 profile.
//  Real iniBuilds A350 titles may also start with "INIBUILDS A350".
// --------------------------------------------------------------------------
static const HUDProfile profile_a350_inibuilds = {
    .aircraft_id_prefix     = "INIBUILDS A350",
    .eye_position           = { 0.60, 0.0, -1.25 },
    .hfov_deg               = 32.0,
    .vfov_deg               = 24.0,
    .focal_length_px        = 0.0,
    .focal_length_mm        = 0.0,
    .combiner               = { 140, 240, 744, 544 },
    .symbology_mask         = (uint32_t)(HUD_SYM_FPV | HUD_SYM_HORIZON |
                                HUD_SYM_PITCH_LADDER | HUD_SYM_RUNWAY_BOX |
                                HUD_SYM_LOCALIZER | HUD_SYM_GLIDESLOPE |
                                HUD_SYM_DRIFT_CUE | HUD_SYM_CENTERLINE |
                                HUD_SYM_ILS_CROSSHAIR |
                                HUD_SYM_ALTITUDE_SCALE | HUD_SYM_SPEED_SCALE |
                                HUD_SYM_HEADING_SCALE),
    .power_lvar_name        = "L:A350_HUD_POWER",
    .scale_x                = 1.0,
    .scale_y                = 1.0,
    .offset_x               = 0.0,
    .offset_y               = 0.0,
    .ils_loc_sensitivity    = 0.14,
    .ils_gs_sensitivity     = 0.14,

    // --- v2.3.0 tuning presets — Airbus calmness ---
    .optical_center_offset_x  = 0.0,
    .optical_center_offset_y  = 0.0,
    .fpv_align_offset_x       = 1.0,
    .fpv_align_offset_y       = 0.0,
    .runway_align_offset      = 0.0,
    .pitch_spacing_factor     = 1.0,
    .horizon_offset           = 0.0,

    // Airbus flare: softer than Boeing (0.08 vs 0.10-0.12)
    .flare_constant           = 0.08,
    .flare_max_rise_px        = 75.0,
    .flare_cue_min_size       = 10.0,
    .flare_cue_max_size       = 26.0,

    // Airbus drift cue: slightly slower response
    .drift_cue_response       = 0.55,
    .drift_cue_damping        = 0.70,

    // Airbus turbulence: heavier damping
    .turbulence_stab_gain     = 0.75,
    .motion_confidence_weight = 0.85,

    // Airbus optical: calmer, less bloom, more persistence
    .optical_calmness           = 0.90,
    .phosphor_persistence_ms    = 45.0,
    .bloom_intensity            = 0.08,
    .edge_fade_factor           = 0.20,

    .has_pmdg_style_power    = false,
    .has_787_style_power     = false,
    .invert_pitch            = false,
    .has_speed_tape          = false,
    .has_altitude_tape       = false,
};

// ----------------------------------------------------------------
//  Fenix A320 — Airbus HUD, narrow-body, short-field ops
// ----------------------------------------------------------------
static const HUDProfile profile_fenix_a320 = {
    .aircraft_id_prefix     = "FENIX A320",
    .eye_position           = { 0.55, 0.0, -1.20 },
    .hfov_deg               = 28.0,
    .vfov_deg               = 20.0,
    .focal_length_px        = 0.0,
    .focal_length_mm        = 0.0,
    .combiner               = { 188, 280, 648, 464 },
    .symbology_mask         = (uint32_t)(HUD_SYM_FPV | HUD_SYM_HORIZON |
                                HUD_SYM_PITCH_LADDER | HUD_SYM_RUNWAY_BOX |
                                HUD_SYM_LOCALIZER | HUD_SYM_GLIDESLOPE |
                                HUD_SYM_DRIFT_CUE | HUD_SYM_CENTERLINE |
                                HUD_SYM_ILS_CROSSHAIR),
    .power_lvar_name        = "L:HUD_POWER_SWITCH",
    .scale_x                = 1.0,
    .scale_y                = 1.0,
    .offset_x               = 0.0,
    .offset_y               = 0.0,
    .ils_loc_sensitivity    = 0.14,
    .ils_gs_sensitivity     = 0.14,

    // --- v2.3.0 tuning presets — Airbus calmness ---
    .optical_center_offset_x  = 0.0,
    .optical_center_offset_y  = 0.0,
    .fpv_align_offset_x       = 1.0,
    .fpv_align_offset_y       = 0.0,
    .runway_align_offset      = 0.0,
    .pitch_spacing_factor     = 1.0,
    .horizon_offset           = 0.0,

    // Airbus flare: softer than Boeing (0.08 vs 0.10-0.12)
    .flare_constant           = 0.08,
    .flare_max_rise_px        = 55.0,
    .flare_cue_min_size       = 8.0,
    .flare_cue_max_size       = 38.0,

    // Airbus drift cue: slightly slower response
    .drift_cue_response       = 0.55,
    .drift_cue_damping        = 0.70,

    // Airbus turbulence: heavier damping
    .turbulence_stab_gain     = 0.75,
    .motion_confidence_weight = 0.85,

    // Airbus optical: calmer, less bloom, more persistence
    .optical_calmness           = 0.90,
    .phosphor_persistence_ms    = 3.2,
    .bloom_intensity            = 0.12,
    .edge_fade_factor           = 0.20,

    .has_pmdg_style_power    = false,
    .has_787_style_power     = false,
    .invert_pitch            = false,
    .has_speed_tape          = false,
    .has_altitude_tape       = false,
};

// ----------------------------------------------------------------
//  PMDG 737 MAX — Boeing HGS, same combiner geometry as 737 NGXu
// ----------------------------------------------------------------
static const HUDProfile profile_pmdg_737_max = {
    .aircraft_id_prefix     = "PMDG 737 MAX",
    .eye_position           = { 0.60, 0.0, -1.20 },
    .hfov_deg               = 30.0,
    .vfov_deg               = 22.0,
    .focal_length_px        = 0.0,
    .focal_length_mm        = 0.0,
    .combiner               = { 150, 250, 724, 524 },
    .symbology_mask         = (uint32_t)(HUD_SYM_FPV | HUD_SYM_HORIZON |
                                HUD_SYM_PITCH_LADDER | HUD_SYM_RUNWAY_BOX |
                                HUD_SYM_LOCALIZER | HUD_SYM_GLIDESLOPE |
                                HUD_SYM_DRIFT_CUE | HUD_SYM_CENTERLINE |
                                HUD_SYM_ILS_CROSSHAIR),
    .power_lvar_name        = "L:HUD_POWER_SWITCH",
    .scale_x                = 1.0,
    .scale_y                = 1.0,
    .offset_x               = 0.0,
    .offset_y               = 0.0,
    .ils_loc_sensitivity    = 0.14,
    .ils_gs_sensitivity     = 0.14,

    // --- v2.3.0 tuning presets — Boeing HGS ---
    .optical_center_offset_x  = 0.0,
    .optical_center_offset_y  = 0.0,
    .fpv_align_offset_x       = 0.0,
    .fpv_align_offset_y       = 0.0,
    .runway_align_offset      = 0.0,
    .pitch_spacing_factor     = 1.0,
    .horizon_offset           = 0.0,

    // Boeing flare: moderate aggressiveness (0.10)
    .flare_constant           = 0.10,
    .flare_max_rise_px        = 80.0,
    .flare_cue_min_size       = 10.0,
    .flare_cue_max_size       = 45.0,

    // Boeing drift cue: faster response than Airbus
    .drift_cue_response       = 0.70,
    .drift_cue_damping        = 0.60,

    // Boeing turbulence: moderate stabilization
    .turbulence_stab_gain     = 0.65,
    .motion_confidence_weight = 0.75,

    // Boeing optical: more bloom, sharper
    .optical_calmness           = 0.80,
    .phosphor_persistence_ms    = 4.0,
    .bloom_intensity            = 0.15,
    .edge_fade_factor           = 0.18,

    .has_pmdg_style_power    = true,
    .has_787_style_power     = false,
    .invert_pitch            = false,
    .has_speed_tape          = false,
    .has_altitude_tape       = false,
};
// ----------------------------------------------------------------
//  INI A330 — Airbus HUD, wide-body twin, longer combiner
// ----------------------------------------------------------------
static const HUDProfile profile_ini_a330 = {
    .aircraft_id_prefix     = "INI A330",
    .eye_position           = { 0.58, 0.0, -1.25 },
    .hfov_deg               = 30.0,
    .vfov_deg               = 22.0,
    .focal_length_px        = 0.0,
    .focal_length_mm        = 0.0,
    .combiner               = { 170, 260, 684, 504 },
    .symbology_mask         = (uint32_t)(HUD_SYM_FPV | HUD_SYM_HORIZON |
                                HUD_SYM_PITCH_LADDER | HUD_SYM_RUNWAY_BOX |
                                HUD_SYM_LOCALIZER | HUD_SYM_GLIDESLOPE |
                                HUD_SYM_DRIFT_CUE | HUD_SYM_CENTERLINE |
                                HUD_SYM_ILS_CROSSHAIR),
    .power_lvar_name        = "L:HUD_POWER_SWITCH",
    .scale_x                = 1.0,
    .scale_y                = 1.0,
    .offset_x               = 0.0,
    .offset_y               = 0.0,
    .ils_loc_sensitivity    = 0.14,
    .ils_gs_sensitivity     = 0.14,

    // --- v2.3.0 tuning presets — Airbus calmness ---
    .optical_center_offset_x  = 0.0,
    .optical_center_offset_y  = 0.0,
    .fpv_align_offset_x       = 1.0,
    .fpv_align_offset_y       = 0.0,
    .runway_align_offset      = 0.0,
    .pitch_spacing_factor     = 1.0,
    .horizon_offset           = 0.0,

    // Airbus flare: softer than Boeing (0.08 vs 0.10-0.12)
    .flare_constant           = 0.08,
    .flare_max_rise_px        = 58.0,
    .flare_cue_min_size       = 8.0,
    .flare_cue_max_size       = 40.0,

    // Airbus drift cue: slightly slower response
    .drift_cue_response       = 0.55,
    .drift_cue_damping        = 0.70,

    // Airbus turbulence: heavier damping
    .turbulence_stab_gain     = 0.75,
    .motion_confidence_weight = 0.85,

    // Airbus optical: calmer, less bloom, more persistence
    .optical_calmness           = 0.90,
    .phosphor_persistence_ms    = 3.2,
    .bloom_intensity            = 0.12,
    .edge_fade_factor           = 0.20,

    .has_pmdg_style_power    = false,
    .has_787_style_power     = false,
    .invert_pitch            = false,
    .has_speed_tape          = false,
    .has_altitude_tape       = false,
};

// ----------------------------------------------------------------
//  FBW A32NX family — Airbus HUD, narrow-body, same class as Fenix
// ----------------------------------------------------------------
static const HUDProfile profile_fbw_a32nx = {
    .aircraft_id_prefix     = "FBW",
    .eye_position           = { 0.55, 0.0, -1.20 },
    .hfov_deg               = 28.0,
    .vfov_deg               = 20.0,
    .focal_length_px        = 0.0,
    .focal_length_mm        = 0.0,
    .combiner               = { 188, 280, 648, 464 },
    .symbology_mask         = (uint32_t)(HUD_SYM_FPV | HUD_SYM_HORIZON |
                                HUD_SYM_PITCH_LADDER | HUD_SYM_RUNWAY_BOX |
                                HUD_SYM_LOCALIZER | HUD_SYM_GLIDESLOPE |
                                HUD_SYM_DRIFT_CUE | HUD_SYM_CENTERLINE |
                                HUD_SYM_ILS_CROSSHAIR),
    .power_lvar_name        = "L:HUD_POWER_SWITCH",
    .scale_x                = 1.0,
    .scale_y                = 1.0,
    .offset_x               = 0.0,
    .offset_y               = 0.0,
    .ils_loc_sensitivity    = 0.14,
    .ils_gs_sensitivity     = 0.14,

    // --- v2.3.0 tuning presets — Airbus calmness ---
    .optical_center_offset_x  = 0.0,
    .optical_center_offset_y  = 0.0,
    .fpv_align_offset_x       = 1.0,
    .fpv_align_offset_y       = 0.0,
    .runway_align_offset      = 0.0,
    .pitch_spacing_factor     = 1.0,
    .horizon_offset           = 0.0,

    // Airbus flare: softer than Boeing (0.08 vs 0.10-0.12)
    .flare_constant           = 0.08,
    .flare_max_rise_px        = 55.0,
    .flare_cue_min_size       = 8.0,
    .flare_cue_max_size       = 38.0,

    // Airbus drift cue: slightly slower response
    .drift_cue_response       = 0.55,
    .drift_cue_damping        = 0.70,

    // Airbus turbulence: heavier damping
    .turbulence_stab_gain     = 0.75,
    .motion_confidence_weight = 0.85,

    // Airbus optical: calmer, less bloom, more persistence
    .optical_calmness           = 0.90,
    .phosphor_persistence_ms    = 3.2,
    .bloom_intensity            = 0.12,
    .edge_fade_factor           = 0.20,

    .has_pmdg_style_power    = false,
    .has_787_style_power     = false,
    .invert_pitch            = false,
    .has_speed_tape          = false,
    .has_altitude_tape       = false,
};

// ----------------------------------------------------------------
//  HEADWIND A330-900 — Airbus HUD, wide-body, same class as INI A330
// ----------------------------------------------------------------
static const HUDProfile profile_headwind_a330 = {
    .aircraft_id_prefix     = "HEADWIND A330",
    .eye_position           = { 0.58, 0.0, -1.25 },
    .hfov_deg               = 30.0,
    .vfov_deg               = 22.0,
    .focal_length_px        = 0.0,
    .focal_length_mm        = 0.0,
    .combiner               = { 170, 260, 684, 504 },
    .symbology_mask         = (uint32_t)(HUD_SYM_FPV | HUD_SYM_HORIZON |
                                HUD_SYM_PITCH_LADDER | HUD_SYM_RUNWAY_BOX |
                                HUD_SYM_LOCALIZER | HUD_SYM_GLIDESLOPE |
                                HUD_SYM_DRIFT_CUE | HUD_SYM_CENTERLINE |
                                HUD_SYM_ILS_CROSSHAIR),
    .power_lvar_name        = "L:HUD_POWER_SWITCH",
    .scale_x                = 1.0,
    .scale_y                = 1.0,
    .offset_x               = 0.0,
    .offset_y               = 0.0,
    .ils_loc_sensitivity    = 0.14,
    .ils_gs_sensitivity     = 0.14,

    // --- v2.3.0 tuning presets — Airbus calmness ---
    .optical_center_offset_x  = 0.0,
    .optical_center_offset_y  = 0.0,
    .fpv_align_offset_x       = 1.0,
    .fpv_align_offset_y       = 0.0,
    .runway_align_offset      = 0.0,
    .pitch_spacing_factor     = 1.0,
    .horizon_offset           = 0.0,

    // Airbus flare: softer than Boeing (0.08 vs 0.10-0.12)
    .flare_constant           = 0.08,
    .flare_max_rise_px        = 58.0,
    .flare_cue_min_size       = 8.0,
    .flare_cue_max_size       = 40.0,

    // Airbus drift cue: slightly slower response
    .drift_cue_response       = 0.55,
    .drift_cue_damping        = 0.70,

    // Airbus turbulence: heavier damping
    .turbulence_stab_gain     = 0.75,
    .motion_confidence_weight = 0.85,

    // Airbus optical: calmer, less bloom, more persistence
    .optical_calmness           = 0.90,
    .phosphor_persistence_ms    = 3.2,
    .bloom_intensity            = 0.12,
    .edge_fade_factor           = 0.20,

    .has_pmdg_style_power    = false,
    .has_787_style_power     = false,
    .invert_pitch            = false,
    .has_speed_tape          = false,
    .has_altitude_tape       = false,
};


/// Array of all profiles.
static const HUDProfile* const g_profiles[C_HUD_NUM_PROFILES] = {
    &profile_pmdg_737,
    &profile_pmdg_777,
    &profile_wt_787,
    &profile_wt_787_alt,
    &profile_a350,
    &profile_a350_ini,
    &profile_a350_inibuilds,
    &profile_fenix_a320,
    &profile_pmdg_737_max,
    &profile_ini_a330,
    &profile_fbw_a32nx,
    &profile_headwind_a330,
    &profile_default,
};

// ============================================================================
//  2.  Profile matching logic
// ============================================================================

/// Case-insensitive prefix comparison.
static bool string_prefix_match(const char* str, const char* prefix) {
    if (str == 0 || prefix == 0) return false;
    if (prefix[0] == '\0') return true;

    while (*prefix != '\0') {
        char sc = *str;
        char pc = *prefix;
        if (sc >= 'A' && sc <= 'Z') sc += 32;
        if (pc >= 'A' && pc <= 'Z') pc += 32;
        if (sc != pc) return false;
        ++str;
        ++prefix;
    }
    return true;
}

const HUDProfile* hud_profile_match(const char* aircraft_id) {
    if (aircraft_id == 0 || aircraft_id[0] == '\0') {
        return &profile_default;
    }

    for (int i = 0; i < C_HUD_NUM_PROFILES - 1; ++i) {
        const HUDProfile* p = g_profiles[i];
        if (p->aircraft_id_prefix[0] != '\0' &&
            string_prefix_match(aircraft_id, p->aircraft_id_prefix)) {
            return p;
        }
    }

    return &profile_default;
}

const HUDProfile* hud_profile_by_index(int index) {
    if (index < 0 || index >= C_HUD_NUM_PROFILES) {
        return &profile_default;
    }
    return g_profiles[index];
}

const HUDProfile* hud_profile_default(void) {
    return &profile_default;
}

// ============================================================================
//  3.  Profile initialisation (compute derived fields)
// ============================================================================

void hud_profile_init_derived(HUDProfile* p) {
    if (p == 0) return;

    const FLOAT64 half_hfov = PROJ_DEG2RAD(p->hfov_deg * 0.5);

    const int comb_w = p->combiner.width;

    if (comb_w > 0 && half_hfov > 0.0) {
        p->focal_length_px = ((FLOAT64)comb_w * 0.5) / proj_tan(half_hfov);
    } else {
        p->focal_length_px = 520.0;
    }

    p->focal_length_mm = 25.0;
}

void hud_profiles_init_all(void) {
    for (int i = 0; i < C_HUD_NUM_PROFILES; ++i) {
        HUDProfile* p = (HUDProfile*)g_profiles[i];
        hud_profile_init_derived(p);
    }
}
