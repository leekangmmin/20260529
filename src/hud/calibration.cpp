// ============================================================================
//  Conformal HUD – Calibration System Implementation
//  MSFS 2024  ·  C++17  ·  WASM  ·  v2.2.0
//
//  Live HUD calibration framework with hot-reload support.
//  Reads calibration L:vars written by the JS overlay each frame.
// ============================================================================

#include "../../include/module.h"

// ============================================================================
//  Read calibration L:vars from Sim (written by JS overlay)
// ============================================================================

void calib_read_lvars(HUDSettings* s) {
    if (s == 0) return;

    #define READ_CALIB_LVAR(name, field) do { \
        GAUGE_VAR tok = gauge_get_var_by_name(name, "number"); \
        if (tok != 0) { \
            FLOAT64 val = 0.0; \
            gauge_var_get(tok, &val, (int)sizeof(val)); \
            s->field = val; \
        } \
    } while(0)

    READ_CALIB_LVAR("L:C_HUD_Calib_CenterX", center_offset_x);
    READ_CALIB_LVAR("L:C_HUD_Calib_CenterY", center_offset_y);
    READ_CALIB_LVAR("L:C_HUD_Calib_CombX", combiner_offset_x);
    READ_CALIB_LVAR("L:C_HUD_Calib_CombY", combiner_offset_y);
    READ_CALIB_LVAR("L:C_HUD_Calib_CombW", combiner_scale_w);
    READ_CALIB_LVAR("L:C_HUD_Calib_CombH", combiner_scale_h);
    READ_CALIB_LVAR("L:C_HUD_Calib_EyeFwd", eye_offset_forward_m);
    READ_CALIB_LVAR("L:C_HUD_Calib_EyeRight", eye_offset_right_m);
    READ_CALIB_LVAR("L:C_HUD_Calib_EyeDown", eye_offset_down_m);

    {
        GAUGE_VAR tok = gauge_get_var_by_name("L:C_HUD_Calib_FOV", "number");
        if (tok != 0) {
            FLOAT64 val = 0.0;
            gauge_var_get(tok, &val, (int)sizeof(val));
            if (val >= 0.5 && val <= 3.0) s->fov_scale = val;
        }
    }

    READ_CALIB_LVAR("L:C_HUD_Calib_ScaleX", projection_scale_x);
    READ_CALIB_LVAR("L:C_HUD_Calib_ScaleY", projection_scale_y);

    {
        GAUGE_VAR tok = gauge_get_var_by_name("L:C_HUD_Calib_OpticalGain", "number");
        if (tok != 0) {
            FLOAT64 val = 0.0;
            gauge_var_get(tok, &val, (int)sizeof(val));
            if (val >= 0.1 && val <= 5.0) s->optical_gain = val;
        }
    }

    READ_CALIB_LVAR("L:C_HUD_Calib_FPVAlignX", fpv_align_x);
    READ_CALIB_LVAR("L:C_HUD_Calib_FPVAlignY", fpv_align_y);
    READ_CALIB_LVAR("L:C_HUD_Calib_RwyAlign", runway_align_offset);
    READ_CALIB_LVAR("L:C_HUD_Calib_FlarePos", flare_cue_pos_offset);
    READ_CALIB_LVAR("L:C_HUD_Calib_HorizonOffset", horizon_line_offset);

    #undef READ_CALIB_LVAR
}

// ============================================================================
//  Read debug overlay toggles from L:vars (written by JS overlay)
// ============================================================================

void debug_read_lvars(DebugOverlay* d) {
    if (d == 0) return;

    #define READ_DEBUG_LVAR(name, field) do { \
        GAUGE_VAR tok = gauge_get_var_by_name(name, "number"); \
        if (tok != 0) { \
            FLOAT64 val = 0.0; \
            gauge_var_get(tok, &val, (int)sizeof(val)); \
            d->field = (val >= 0.5); \
        } \
    } while(0)

    READ_DEBUG_LVAR("L:C_HUD_Debug_ShowRwyCorners", show_runway_corners);
    READ_DEBUG_LVAR("L:C_HUD_Debug_ShowAxes", show_world_axes);
    READ_DEBUG_LVAR("L:C_HUD_Debug_ShowFPVTrace", show_fpv_trace);
    READ_DEBUG_LVAR("L:C_HUD_Debug_ShowGuidanceBeam", show_guidance_beam);
    READ_DEBUG_LVAR("L:C_HUD_Debug_ShowClip", show_clipping);
    READ_DEBUG_LVAR("L:C_HUD_Debug_ShowOpticalCenter", show_optical_center);
    READ_DEBUG_LVAR("L:C_HUD_Debug_ShowCollimation", show_collimation_vectors);

    READ_DEBUG_LVAR("L:C_HUD_Debug_ShowTiming", show_timing_overlay);
    READ_DEBUG_LVAR("L:C_HUD_Debug_ShowHistogram", show_histogram);
    #undef READ_DEBUG_LVAR
}
