// ============================================================================
//  Conformal HUD – L:Var Token Table (v2.7.0)
//  MSFS 2024  ·  C++17  ·  WASM
//
//  Flat token table indexed by LVarID enum. All tokens resolved once
//  in POST_INSTALL, then writes are O(1) table lookups.
//
//  Note: lvar_write() and lvar_read() are defined as static inline
//  in module.h — this file only manages the token table and init.
// ============================================================================

#include "module.h"

// Static token table — one GAUGE_VAR per LVarID.
// Initialised to 0 (invalid token) by virtue of BSS zero-init.
static GAUGE_VAR g_lvar_tokens[LVAR_COUNT];

// L:var name table — maps LVarID → name string for token resolution.
static const char* const g_lvar_names[LVAR_COUNT] = {
    // --- Module diagnostics ---
    [LVAR_VERSION]        = "L:C_HUD_Version",
    [LVAR_FRAME]          = "L:C_HUD_Frame",
    [LVAR_FPS]            = "L:C_HUD_FPS",
    [LVAR_FPS_MIN]        = "L:C_HUD_FPS_Min",
    [LVAR_FPS_MAX]        = "L:C_HUD_FPS_Max",
    [LVAR_FPS_AVG]        = "L:C_HUD_FPS_Avg",
    [LVAR_JITTER_MS]      = "L:C_HUD_Jitter_ms",
    [LVAR_INIT]           = "L:C_HUD_Init",

    [LVAR_HUD_ACTIVE]     = "L:C_HUD_HUD_Active",
    [LVAR_SCREEN_CX]      = "L:C_HUD_ScreenCX",
    [LVAR_SCREEN_CY]      = "L:C_HUD_ScreenCY",
    [LVAR_WEATHER_LINE_W] = "L:C_HUD_WeatherLineW",
    [LVAR_WEATHER_ALPHA]  = "L:C_HUD_WeatherAlpha",
    [LVAR_ILS_GS]         = "L:C_HUD_ILS_GS",
    [LVAR_ILS_LOC]        = "L:C_HUD_ILS_LOC",
    [LVAR_CDI_GS]         = "L:C_HUD_CDI_GS",
    [LVAR_CDI_LOC]        = "L:C_HUD_CDI_LOC",
    [LVAR_RWY_VERT_COUNT] = "L:C_HUD_RunwayVertCount",
    [LVAR_RWY_V0_X] = "L:C_HUD_RunwayV0_X",
    [LVAR_RWY_V0_Y] = "L:C_HUD_RunwayV0_Y",
    [LVAR_RWY_V1_X] = "L:C_HUD_RunwayV1_X",
    [LVAR_RWY_V1_Y] = "L:C_HUD_RunwayV1_Y",
    [LVAR_RWY_V2_X] = "L:C_HUD_RunwayV2_X",
    [LVAR_RWY_V2_Y] = "L:C_HUD_RunwayV2_Y",
    [LVAR_RWY_V3_X] = "L:C_HUD_RunwayV3_X",
    [LVAR_RWY_V3_Y] = "L:C_HUD_RunwayV3_Y",
    [LVAR_RWY_V4_X] = "L:C_HUD_RunwayV4_X",
    [LVAR_RWY_V4_Y] = "L:C_HUD_RunwayV4_Y",
    [LVAR_RWY_V5_X] = "L:C_HUD_RunwayV5_X",
    [LVAR_RWY_V5_Y] = "L:C_HUD_RunwayV5_Y",
    [LVAR_RWY_V6_X] = "L:C_HUD_RunwayV6_X",
    [LVAR_RWY_V6_Y] = "L:C_HUD_RunwayV6_Y",
    [LVAR_RWY_V7_X] = "L:C_HUD_RunwayV7_X",
    [LVAR_RWY_V7_Y] = "L:C_HUD_RunwayV7_Y",

    [LVAR_FPV_X]          = "L:C_HUD_FPV_X",
    [LVAR_FPV_Y]          = "L:C_HUD_FPV_Y",
    [LVAR_FPV_ONSCREEN]   = "L:C_HUD_FPV_OnScreen",
    [LVAR_FPV_DRIFT]      = "L:C_HUD_FPV_Drift",
    [LVAR_FPV_PITCH]      = "L:C_HUD_FPV_Pitch",

    [LVAR_HORIZON_Y]      = "L:C_HUD_HorizonY",
    [LVAR_HORIZON_SLOPE]  = "L:C_HUD_HorizonSlope",
    [LVAR_HORIZON_VALID]  = "L:C_HUD_HorizonValid",

    [LVAR_PITCH_COUNT]    = "L:C_HUD_PitchLadder_Count",
    [LVAR_PITCH_Y_0]      = "L:C_HUD_PitchLadder_0_Y",
    [LVAR_PITCH_Y_1]      = "L:C_HUD_PitchLadder_1_Y",
    [LVAR_PITCH_Y_2]      = "L:C_HUD_PitchLadder_2_Y",
    [LVAR_PITCH_Y_3]      = "L:C_HUD_PitchLadder_3_Y",
    [LVAR_PITCH_Y_4]      = "L:C_HUD_PitchLadder_4_Y",

    [LVAR_GS_TARGET_X]    = "L:C_HUD_GS_Target_X",
    [LVAR_GS_TARGET_Y]    = "L:C_HUD_GS_Target_Y",
    [LVAR_LOC_TARGET_X]   = "L:C_HUD_LOC_Target_X",
    [LVAR_LOC_TARGET_Y]   = "L:C_HUD_LOC_Target_Y",
    [LVAR_LOC_CAPTURED]   = "L:C_HUD_LOC_Captured",
    [LVAR_GS_CAPTURED]    = "L:C_HUD_GS_Captured",
    [LVAR_STEER_PITCH]    = "L:C_HUD_Steer_Pitch",
    [LVAR_STEER_BANK]     = "L:C_HUD_Steer_Bank",

    [LVAR_COMB_X]         = "L:C_HUD_CombinerX",
    [LVAR_COMB_Y]         = "L:C_HUD_CombinerY",
    [LVAR_COMB_W]         = "L:C_HUD_CombinerW",
    [LVAR_COMB_H]         = "L:C_HUD_CombinerH",

    [LVAR_DRIFT_ANGLE]    = "L:C_HUD_Drift_Angle",
    [LVAR_DRIFT_CUE_X]    = "L:C_HUD_Drift_Cue_X",
    [LVAR_DRIFT_CUE_Y]    = "L:C_HUD_Drift_Cue_Y",

    [LVAR_FLARE_ACTIVE]     = "L:C_HUD_Flare_Active",
    [LVAR_FLARE_FULL_ACTIVE]= "L:C_HUD_Flare_FullyActive",
    [LVAR_FLARE_CUE_X]      = "L:C_HUD_Flare_Cue_X",
    [LVAR_FLARE_CUE_Y]      = "L:C_HUD_Flare_Cue_Y",
    [LVAR_FLARE_CUE_SIZE]   = "L:C_HUD_Flare_Cue_Size",
    [LVAR_FLARE_CUE_ALPHA]  = "L:C_HUD_Flare_Cue_Alpha",
    [LVAR_FLARE_RISE]       = "L:C_HUD_Flare_Rise",
    [LVAR_FLARE_ERROR]      = "L:C_HUD_Flare_Error",
    [LVAR_FLARE_VS_CMD]     = "L:C_HUD_Flare_VS_Cmd",
    [LVAR_TDZ_VISIBLE]      = "L:C_HUD_TDZone_Visible",
    [LVAR_TDZ_X]            = "L:C_HUD_TDZone_X",
    [LVAR_TDZ_Y]            = "L:C_HUD_TDZone_Y",
    [LVAR_TDZ_SIZE]         = "L:C_HUD_TDZone_Size",

    [LVAR_COLL_ACTIVE]    = "L:C_HUD_Collimation_Active",
    [LVAR_COLL_CORR_MAG]  = "L:C_HUD_Collimation_CorrMag",
    [LVAR_COLL_CORR_X]    = "L:C_HUD_Collimation_CorrX",
    [LVAR_COLL_CORR_Y]    = "L:C_HUD_Collimation_CorrY",
    [LVAR_COLL_CORR_Z]    = "L:C_HUD_Collimation_CorrZ",
    [LVAR_COLL_GAIN]      = "L:C_HUD_Collimation_Gain",
    [LVAR_COLL_DELTA_X]   = "L:C_HUD_Collimation_DeltaX",
    [LVAR_COLL_DELTA_Y]   = "L:C_HUD_Collimation_DeltaY",
    [LVAR_COLL_DELTA_Z]   = "L:C_HUD_Collimation_DeltaZ",

    [LVAR_EVS_ACTIVE]     = "L:C_HUD_EVS_Active",
    [LVAR_EVS_INTENSITY]  = "L:C_HUD_EVS_Intensity",
    [LVAR_EVS_CONTRAST]   = "L:C_HUD_EVS_ContrastBoost",
    [LVAR_EVS_GLOW]       = "L:C_HUD_EVS_GlowAmount",
    [LVAR_EVS_RUNWAY_BOOST]= "L:C_HUD_EVS_RunwayBoost",

    [LVAR_ACCEL_DOTS]     = "L:C_HUD_Accel_Dots",
    [LVAR_ACCEL_X]        = "L:C_HUD_Accel_X",
    [LVAR_ACCEL_Y]        = "L:C_HUD_Accel_Y",
    [LVAR_ENERGY_DOTS]    = "L:C_HUD_Energy_Dots",
    [LVAR_ENERGY_Y]       = "L:C_HUD_Energy_Y",
    [LVAR_FLARE_BR_VISIBLE]   = "L:C_HUD_FlareBr_Visible",
    [LVAR_FLARE_BR_VISIBILITY]= "L:C_HUD_FlareBr_Visibility",
    [LVAR_FLARE_BR_SIZE]  = "L:C_HUD_FlareBr_Size",
    [LVAR_FLARE_BR_ALT_ERR]   = "L:C_HUD_FlareBr_AltError",
    [LVAR_TD_PRED_VALID]  = "L:C_HUD_TDPred_Valid",
    [LVAR_TD_PRED_X]      = "L:C_HUD_TDPred_X",
    [LVAR_TD_PRED_Y]      = "L:C_HUD_TDPred_Y",
    [LVAR_TD_PRED_RANGE]  = "L:C_HUD_TDPred_Range",
    [LVAR_TD_PRED_CONFIDENCE] = "L:C_HUD_TDPred_Confidence",
    [LVAR_VTREND_DIR]     = "L:C_HUD_VTrend_Dir",
    [LVAR_VTREND_MAG]     = "L:C_HUD_VTrend_Mag",

    // --- Calibration ---
    [LVAR_CALIB_CENTER_X]  = "L:C_HUD_Calib_CenterX",
    [LVAR_CALIB_CENTER_Y]  = "L:C_HUD_Calib_CenterY",
    [LVAR_CALIB_FOV]       = "L:C_HUD_Calib_FOV",
    [LVAR_CALIB_EYE_FWD]   = "L:C_HUD_Calib_EyeFwd",
    [LVAR_CALIB_EYE_RIGHT] = "L:C_HUD_Calib_EyeRight",
    [LVAR_CALIB_EYE_DOWN]  = "L:C_HUD_Calib_EyeDown",
    [LVAR_CALIB_SCALE_X]   = "L:C_HUD_Calib_ScaleX",
    [LVAR_CALIB_SCALE_Y]   = "L:C_HUD_Calib_ScaleY",
    [LVAR_CALIB_OPTICAL_GAIN] = "L:C_HUD_Calib_OpticalGain",
    [LVAR_CALIB_FPV_ALIGN_X]  = "L:C_HUD_Calib_FPVAlignX",
    [LVAR_CALIB_FPV_ALIGN_Y]  = "L:C_HUD_Calib_FPVAlignY",
    [LVAR_CALIB_RWY_ALIGN]    = "L:C_HUD_Calib_RwyAlign",
    [LVAR_CALIB_FLARE_POS]    = "L:C_HUD_Calib_FlarePos",
    [LVAR_CALIB_HORIZON_OFFSET] = "L:C_HUD_Calib_HorizonOffset",

    // --- Verification / Debug ---
    [LVAR_DEBUG_SHOW_RWY_CORNERS] = "L:C_HUD_Debug_ShowRwyCorners",
    [LVAR_DEBUG_SHOW_AXES]        = "L:C_HUD_Debug_ShowAxes",
    [LVAR_DEBUG_SHOW_FPV_TRACE]   = "L:C_HUD_Debug_ShowFPVTrace",
    [LVAR_DEBUG_SHOW_GUIDANCE_BEAM] = "L:C_HUD_Debug_ShowGuidanceBeam",
    [LVAR_DEBUG_SHOW_CLIP]        = "L:C_HUD_Debug_ShowClip",
    [LVAR_DEBUG_SHOW_OPTICAL_CENTER] = "L:C_HUD_Debug_ShowOpticalCenter",
    [LVAR_DEBUG_SHOW_COLLIMATION] = "L:C_HUD_Debug_ShowCollimation",

    // --- Optical realism ---
    [LVAR_OPTICS_PHOSPHOR]      = "L:C_HUD_Optics_Phosphor",
    [LVAR_OPTICS_BLOOM]         = "L:C_HUD_Optics_Bloom",
    [LVAR_OPTICS_LUMINANCE]     = "L:C_HUD_Optics_Luminance",
    [LVAR_OPTICS_BRIGHTNESS]    = "L:C_HUD_Optics_Brightness",
    [LVAR_OPTICS_EDGE_FADE]     = "L:C_HUD_Optics_EdgeFade",
    [LVAR_OPTICS_TEMPORAL_BLEND]= "L:C_HUD_Optics_TemporalBlend",

    // --- Subsystem heartbeats ---
    [LVAR_HB_FPV]          = "L:C_HUD_HB_FPV",
    [LVAR_HB_GUIDANCE]     = "L:C_HUD_HB_Guidance",
    [LVAR_HB_RUNWAY]       = "L:C_HUD_HB_Runway",
    [LVAR_HB_FLARE]        = "L:C_HUD_HB_Flare",
    [LVAR_HB_EVS]          = "L:C_HUD_HB_EVS",
    [LVAR_HB_COLLIMATION]  = "L:C_HUD_HB_Collimation",
    [LVAR_HB_STABILIZATION]= "L:C_HUD_HB_Stabilization",
    [LVAR_HB_ADVANCED]     = "L:C_HUD_HB_Advanced",
    [LVAR_HB_ROLLOUT]      = "L:C_HUD_HB_Rollout",

    // --- v2.4.0: Rollout guidance ---
    [LVAR_ROLL_PHASE]            = "L:C_HUD_Roll_Phase",
    [LVAR_ROLL_ACTIVE]           = "L:C_HUD_Roll_Active",
    [LVAR_ROLL_CENTERLINE_X]     = "L:C_HUD_Roll_CL_X",
    [LVAR_ROLL_CENTERLINE_Y]     = "L:C_HUD_Roll_CL_Y",
    [LVAR_ROLL_CENTERLINE_W]     = "L:C_HUD_Roll_CL_W",
    [LVAR_ROLL_CENTERLINE_ALPHA] = "L:C_HUD_Roll_CL_Alpha",
    [LVAR_ROLL_STEERING]          = "L:C_HUD_Roll_Steering",
    [LVAR_ROLL_DAMPING]          = "L:C_HUD_Roll_Damping",
    [LVAR_ROLL_CONFIDENCE]       = "L:C_HUD_Roll_Confidence",
    [LVAR_ROLL_NOSEWHEEL]        = "L:C_HUD_Roll_Nosewheel",
    [LVAR_ROLL_TRANSITION]       = "L:C_HUD_Roll_Transition",
    [LVAR_ROLL_BRAKE_ADVISORY]    = "L:C_HUD_Roll_BrakeAdv",
    [LVAR_ROLL_DECEL_CUE_X]      = "L:C_HUD_Roll_DecelX",
    [LVAR_ROLL_DECEL_CUE_ALPHA]  = "L:C_HUD_Roll_DecelAlpha",
    [LVAR_ROLL_COMPRESSION]      = "L:C_HUD_Roll_Compression",

    // --- v2.7.0: Rollout rendering L:vars (Boeing HGS style) ---
    [LVAR_ROLL_CENTERLINE]       = "L:C_HUD_Roll_Centerline",
    [LVAR_ROLL_DEVIATION]        = "L:C_HUD_Roll_Deviation",
    [LVAR_ROLL_COMMAND]          = "L:C_HUD_Roll_Command",

    // --- v2.7.0: CAT III Annunciation L:vars ---
    [LVAR_CAT_CATEGORY]          = "L:C_HUD_CAT_Category",
    [LVAR_LAND_MODE]             = "L:C_HUD_LAND_Mode",
    [LVAR_FLARE_ANNOUNCE]        = "L:C_HUD_FLARE_Announce",
    [LVAR_ROLLOUT_ANNOUNCE]      = "L:C_HUD_ROLLOUT_Announce",
    [LVAR_NO_DH]                 = "L:C_HUD_NO_DH",

    // --- v2.7.0: EVS Visualization L:vars ---
    [LVAR_EVS_ACTIVE_BOX]       = "L:C_HUD_EVS_ActiveBox",
    [LVAR_EVS_CONTRAST_CUE]     = "L:C_HUD_EVS_ContrastCue",
    [LVAR_EVS_VIS_IND]          = "L:C_HUD_EVS_VisibilityInd",

    // --- v2.4.0: Visual response ---
    [LVAR_VIS_ACTIVE]            = "L:C_HUD_Vis_Active",
    [LVAR_VIS_DARK_ADAPT]        = "L:C_HUD_Vis_DarkAdapt",
    [LVAR_VIS_BLOOM]             = "L:C_HUD_Vis_Bloom",
    [LVAR_VIS_RAIN_GLARE]        = "L:C_HUD_Vis_RainGlare",
    [LVAR_VIS_PHOSPHOR_MS]       = "L:C_HUD_Vis_PhosphorMs",
    [LVAR_VIS_BRIGHTNESS]        = "L:C_HUD_Vis_Brightness",
    [LVAR_VIS_CONTRAST]          = "L:C_HUD_Vis_Contrast",
    [LVAR_VIS_FATIGUE]           = "L:C_HUD_Vis_Fatigue",

    // --- v2.4.0: Declutter ---
    [LVAR_DCL_PHASE]             = "L:C_HUD_DCL_Phase",
    [LVAR_DCL_VISIBLE_COUNT]     = "L:C_HUD_DCL_VisCount",
    [LVAR_DCL_ACTIVE]            = "L:C_HUD_DCL_Active",

    // --- v2.4.0: Confidence & Depth ---
    [LVAR_CONF_INTEGRITY]        = "L:C_HUD_Conf_Integrity",
    [LVAR_CONF_CATIII]           = "L:C_HUD_Conf_CATIII",
    [LVAR_CONF_LOC_MODE]         = "L:C_HUD_Conf_LocMode",
    [LVAR_CONF_GS_MODE]          = "L:C_HUD_Conf_GSMode",
    [LVAR_CONF_LOC_ALPHA]        = "L:C_HUD_Conf_LocAlpha",
    [LVAR_CONF_GS_ALPHA]         = "L:C_HUD_Conf_GSAlpha",
    [LVAR_DEPTH_ACTIVE]          = "L:C_HUD_Depth_Active",
    [LVAR_DEPTH_INTENSITY]       = "L:C_HUD_Depth_Intensity",
    // --- v2.4.0: Airbus A350 HUD LVars ---
    [LVAR_A350_FLARE_GAIN]        = "L:A350_HUD_FLARE_GAIN",
    [LVAR_A350_FPV_SMOOTHING]     = "L:A350_HUD_FPV_SMOOTHING",
    [LVAR_A350_CAT3_CONFIDENCE]   = "L:A350_HUD_CAT3_CONFIDENCE",
    [LVAR_A350_RUNWAY_STABILITY]  = "L:A350_HUD_RUNWAY_STABILITY",
    [LVAR_A350_ROLLOUT_DAMPING]   = "L:A350_HUD_ROLLOUT_DAMPING",
    [LVAR_A350_PROFILE_ACTIVE]    = "L:A350_HUD_PROFILE_ACTIVE",
    [LVAR_A350_CAT3_ENHANCED]     = "L:A350_HUD_CAT3_ENHANCED",
    [LVAR_A350_FPV_PREDICTIVE]    = "L:A350_HUD_FPV_PREDICTIVE",
    [LVAR_A350_FLARE_SOFTNESS]    = "L:A350_HUD_FLARE_SOFTNESS",
    [LVAR_A350_DECLUTTER_AGGRESSIVE] = "L:A350_HUD_DECLUTTER_AGGRESSIVE",
    [LVAR_A350_SYM_PERSISTENCE]   = "L:A350_HUD_SYM_PERSISTENCE",
    [LVAR_A350_HORIZON_STABILITY] = "L:A350_HUD_HORIZON_STABILITY",
    [LVAR_A350_BLOOM_REDUCTION]   = "L:A350_HUD_BLOOM_REDUCTION",
    [LVAR_A350_ANTI_SHIMMER]      = "L:A350_HUD_ANTI_SHIMMER",
    [LVAR_A350_ROLLOUT_CROSSWIND] = "L:A350_HUD_ROLLOUT_CROSSWIND",
    [LVAR_A350_ROLLOUT_WET_ASSIST] = "L:A350_HUD_ROLLOUT_WET_ASSIST",

    // ================================================================
    //  v2.6.0 — Runtime instrumentation L:vars
    // ================================================================
    [LVAR_PERF_FRAME_TOTAL_US]      = "L:C_HUD_Perf_FrameTotal_us",
    [LVAR_PERF_SIMVAR_READ_US]      = "L:C_HUD_Perf_SimVarRead_us",
    [LVAR_PERF_FPV_US]              = "L:C_HUD_Perf_FPV_us",
    [LVAR_PERF_GUIDANCE_US]         = "L:C_HUD_Perf_Guidance_us",
    [LVAR_PERF_RUNWAY_PROJ_US]      = "L:C_HUD_Perf_RunwayProj_us",
    [LVAR_PERF_FLARE_US]            = "L:C_HUD_Perf_Flare_us",
    [LVAR_PERF_ROLLOUT_US]          = "L:C_HUD_Perf_Rollout_us",
    [LVAR_PERF_COLLIMATION_US]      = "L:C_HUD_Perf_Collimation_us",
    [LVAR_PERF_EVS_US]              = "L:C_HUD_Perf_EVS_us",
    [LVAR_PERF_STABILIZATION_US]    = "L:C_HUD_Perf_Stabilization_us",
    [LVAR_PERF_ADV_SYMBOLOGY_US]    = "L:C_HUD_Perf_AdvSymbology_us",
    [LVAR_PERF_CONFIDENCE_US]       = "L:C_HUD_Perf_Confidence_us",
    [LVAR_PERF_DECLUTTER_US]        = "L:C_HUD_Perf_Declutter_us",
    [LVAR_PERF_OPTICAL_US]          = "L:C_HUD_Perf_Optical_us",
    [LVAR_PERF_SYM_PUBLISH_US]      = "L:C_HUD_Perf_SymPublish_us",
    [LVAR_PERF_TELEMETRY_US]        = "L:C_HUD_Perf_Telemetry_us",
    [LVAR_PERF_JS_BRIDGE_US]        = "L:C_HUD_Perf_JSBridge_us",
    [LVAR_PERF_P50_US]              = "L:C_HUD_Perf_P50_us",
    [LVAR_PERF_P95_US]              = "L:C_HUD_Perf_P95_us",
    [LVAR_PERF_P99_US]              = "L:C_HUD_Perf_P99_us",
    [LVAR_PERF_BUDGET_OK]           = "L:C_HUD_Perf_BudgetOK",
    [LVAR_PERF_OVER_BUDGET_COUNT]   = "L:C_HUD_Perf_OverBudget",

    // ================================================================
    //  v2.6.0 — Frame pacing L:vars
    // ================================================================
    [LVAR_PACING_CONTINUITY]        = "L:C_HUD_Pacing_Continuity",
    [LVAR_PACING_ANOMALY_COUNT]     = "L:C_HUD_Pacing_AnomalyCount",
    [LVAR_PACING_IN_RECOVERY]       = "L:C_HUD_Pacing_InRecovery",
    [LVAR_PACING_STABLE_FRAMES]     = "L:C_HUD_Pacing_StableFrames",
    [LVAR_PACING_ANOMALY_TYPE]      = "L:C_HUD_Pacing_AnomalyType",

    // ================================================================
    //  v2.6.0 — Aircraft compatibility L:vars
    // ================================================================
    [LVAR_COMPAT_SIGNATURE]         = "L:C_HUD_Compat_Signature",
    [LVAR_COMPAT_VERSION_MAJOR]     = "L:C_HUD_Compat_VersionMajor",
    [LVAR_COMPAT_VERSION_MINOR]     = "L:C_HUD_Compat_VersionMinor",
    [LVAR_COMPAT_SUPPORTED]         = "L:C_HUD_Compat_Supported",
    [LVAR_COMPAT_SELF_REPAIR]       = "L:C_HUD_Compat_SelfRepair",
    [LVAR_COMPAT_FALLBACK_ACTIVE]   = "L:C_HUD_Compat_Fallback",

    // ================================================================
    //  v2.6.0 — Optical stability L:vars
    // ================================================================
    [LVAR_OPTIC_STABILITY_SCORE]    = "L:C_HUD_Optic_StabilityScore",
    [LVAR_OPTIC_SHIMMER_LEVEL]      = "L:C_HUD_Optic_ShimmerLevel",
    [LVAR_OPTIC_FATIGUE]            = "L:C_HUD_Optic_Fatigue",
    [LVAR_OPTIC_PHOSPHOR_SMEAR]     = "L:C_HUD_Optic_PhosphorSmear",

    // ================================================================
    //  v2.6.0 — Long-duration stability L:vars
    // ================================================================
    [LVAR_STABLE_MEMORY_KB]         = "L:C_HUD_Stable_MemKB",
    [LVAR_STABLE_TIMING_DRIFT_US]   = "L:C_HUD_Stable_TimingDrift_us",
    [LVAR_STABLE_TELEMETRY_CHECKSUM]= "L:C_HUD_Stable_TelemetryChecksum",
    [LVAR_STABLE_RUNTIME_S]         = "L:C_HUD_Stable_Runtime_s",
    [LVAR_STABLE_SUBSYS_STALLS]     = "L:C_HUD_Stable_SubsysStalls",

    // ================================================================
    //  v2.6.0 — Certification mode L:vars
    // ================================================================
    [LVAR_CERT_MODE_ACTIVE]         = "L:C_HUD_Cert_ModeActive",
    [LVAR_CERT_SCENARIO_SCORE]      = "L:C_HUD_Cert_ScenarioScore",
    [LVAR_CERT_AIRCRAFT_SCORE]      = "L:C_HUD_Cert_AircraftScore",
    [LVAR_CERT_REGRESSION_DETECTED] = "L:C_HUD_Cert_RegressionDetected",
    [LVAR_CERT_RELEASE_READY]       = "L:C_HUD_Cert_ReleaseReady",
    [LVAR_CERT_TOTAL_SCORE]         = "L:C_HUD_Cert_TotalScore",
    // ================================================================
    //  v3.0.0 — A350 XWB Certification Package L:vars
    // ================================================================
    [LVAR_A350_HUD_FPV_STABILITY]        = "L:A350_HUD_FPV_STABILITY",
    [LVAR_A350_HUD_RUNWAY_CONFIDENCE]    = "L:A350_HUD_RUNWAY_CONFIDENCE",
    [LVAR_A350_HUD_AUTOLAND_CONFIDENCE]  = "L:A350_HUD_AUTOLAND_CONFIDENCE",
    [LVAR_A350_HUD_FLARE_ASSIST]         = "L:A350_HUD_FLARE_ASSIST",
    [LVAR_A350_HUD_ROLLOUT_STABILITY]    = "L:A350_HUD_ROLLOUT_STABILITY",
    [LVAR_A350_HUD_TURBULENCE_DAMPING]   = "L:A350_HUD_TURBULENCE_DAMPING",
    [LVAR_A350_HUD_OPTICAL_STABILITY]    = "L:A350_HUD_OPTICAL_STABILITY",
    [LVAR_A350_HUD_CAT3_STATE]           = "L:A350_HUD_CAT3_STATE",
    [LVAR_A350_HUD_ENERGY_SCORE]         = "L:A350_HUD_ENERGY_SCORE",
    [LVAR_A350_HUD_FLARE_AGGRESSIVENESS] = "L:A350_HUD_FLARE_AGGRESSIVENESS",
    // ================================================================
    //  PHASE 4 — Real HUD Integration L:vars
    // ================================================================
    [LVAR_HUD_DEPLOY_PHASE]      = "L:C_HUD_Deploy_Phase",
    [LVAR_HUD_DEPLOY_FRACTION]   = "L:C_HUD_Deploy_Fraction",
    [LVAR_HUD_DEPLOY_POWER]      = "L:C_HUD_Deploy_Power",
    [LVAR_COMB_SCREEN_X]         = "L:C_HUD_CombinerScreenX",
    [LVAR_COMB_SCREEN_Y]         = "L:C_HUD_CombinerScreenY",
    [LVAR_COMB_SCREEN_W]         = "L:C_HUD_CombinerScreenW",
    [LVAR_COMB_SCREEN_H]         = "L:C_HUD_CombinerScreenH",
    [LVAR_OPTICAL_CX]            = "L:C_HUD_OpticalCX",
    [LVAR_OPTICAL_CY]            = "L:C_HUD_OpticalCY",
    [LVAR_COLL_SCREEN_DX]        = "L:C_HUD_Coll_ScreenDX",
    [LVAR_COLL_SCREEN_DY]        = "L:C_HUD_Coll_ScreenDY",
    [LVAR_HUD_RENDER_IN_COMBINER]= "L:C_HUD_RenderInCombiner",
    [LVAR_HUD_COLLIMATED]        = "L:C_HUD_Collimated",


};

// ============================================================================
//  L:Var table init token resolution
// ============================================================================

/// Resolve all L:Var tokens during POST_INSTALL.
void lvar_register_tokens(void) {
    int resolved = 0;
    for (int i = 0; i < LVAR_COUNT; ++i) {
        if (g_lvar_names[i] != 0 && g_lvar_names[i][0] != '\0') {
            g_lvar_tokens[i] = gauge_get_var_by_name(g_lvar_names[i]);
            if (g_lvar_tokens[i] != 0) {
                ++resolved;
            }
        }
    }
    MSFS_Log("[C_HUD_LVAR] Registered %d / %d L:var tokens",
             resolved, LVAR_COUNT);
}

// ============================================================================
//  lvar_init — called from module.cpp POST_INSTALL
//  Forwarding wrapper that delegates to lvar_register_tokens.
// ============================================================================

void lvar_init(void) {
    lvar_register_tokens();
}
