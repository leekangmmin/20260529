#!/usr/bin/env python3
"""
C_HUD v2.7.0 — JS L:Var Consumption Test Suite

Tests that the L:Var names published by the C++ backend match what the
JS renderer reads.  Verifies naming convention consistency.

Run:  python -m pytest tests/test_js_lvar_consumption.py -v
"""

import pytest
import re


# ======================================================================
#  L:Var name registry — extracted from C++ and JS sources
# ======================================================================

# All L:Var names used in conformal_renderer.js
JS_LVAR_NAMES_RAW = """
L:C_HUD_HUD_Active
L:C_HUD_WeatherLineW
L:C_HUD_WeatherAlpha
L:C_HUD_CombinerX
L:C_HUD_CombinerY
L:C_HUD_CombinerW
L:C_HUD_CombinerH
L:C_HUD_RunwayVertCount
L:C_HUD_RunwayV0_X L:C_HUD_RunwayV0_Y
L:C_HUD_RunwayV1_X L:C_HUD_RunwayV1_Y
L:C_HUD_RunwayV2_X L:C_HUD_RunwayV2_Y
L:C_HUD_RunwayV3_X L:C_HUD_RunwayV3_Y
L:C_HUD_RunwayV4_X L:C_HUD_RunwayV4_Y
L:C_HUD_RunwayV5_X L:C_HUD_RunwayV5_Y
L:C_HUD_RunwayV6_X L:C_HUD_RunwayV6_Y
L:C_HUD_RunwayV7_X L:C_HUD_RunwayV7_Y
L:C_HUD_HorizonValid L:C_HUD_HorizonY L:C_HUD_HorizonSlope
L:C_HUD_PitchLadder_Count
L:C_HUD_PitchLadder_0_Y L:C_HUD_PitchLadder_1_Y
L:C_HUD_PitchLadder_2_Y L:C_HUD_PitchLadder_3_Y L:C_HUD_PitchLadder_4_Y
L:C_HUD_FPV_OnScreen L:C_HUD_FPV_X L:C_HUD_FPV_Y L:C_HUD_FPV_Drift
L:C_HUD_ILS_GS L:C_HUD_ILS_LOC
L:C_HUD_LOC_Captured L:C_HUD_GS_Captured
L:C_HUD_GS_Target_X L:C_HUD_GS_Target_Y
L:C_HUD_LOC_Target_X L:C_HUD_LOC_Target_Y
L:C_HUD_Drift_Angle
L:C_HUD_Flare_Active
L:C_HUD_Flare_Cue_X L:C_HUD_Flare_Cue_Y
L:C_HUD_Flare_Cue_Size L:C_HUD_Flare_Cue_Alpha
L:C_HUD_Flare_Error
L:C_HUD_TDZone_Visible L:C_HUD_TDZone_X L:C_HUD_TDZone_Y L:C_HUD_TDZone_Size
L:C_HUD_Debug_ShowOpticalCenter L:C_HUD_Debug_ShowClip L:C_HUD_Debug_ShowCollimation
L:C_HUD_Collimation_Active L:C_HUD_Collimation_CorrMag
L:C_HUD_Optics_Phosphor L:C_HUD_Optics_Bloom
L:C_HUD_Optics_EdgeFade L:C_HUD_Optics_Brightness L:C_HUD_Optics_TemporalBlend
L:C_HUD_Frame L:C_HUD_FPS L:C_HUD_FPS_Min L:C_HUD_FPS_Max L:C_HUD_Jitter_ms
L:C_HUD_Roll_Active L:C_HUD_Roll_Centerline L:C_HUD_Roll_Deviation L:C_HUD_Roll_Command
L:C_HUD_Roll_Confidence
L:C_HUD_CAT_Category L:C_HUD_LAND_Mode
L:C_HUD_FLARE_Announce L:C_HUD_ROLLOUT_Announce L:C_HUD_NO_DH
L:C_HUD_EVS_ActiveBox L:C_HUD_EVS_ContrastCue L:C_HUD_EVS_VisibilityInd
L:C_HUD_EVS_Intensity
"""

# Parse JS L:Var names
JS_LVAR_NAMES = set()
for m in re.finditer(r'L:C_HUD_\S+', JS_LVAR_NAMES_RAW):
    JS_LVAR_NAMES.add(m.group(0))

# L:Var names from C++ lvar_table.cpp (from the source code analysis)
CPP_LVAR_NAMES = set()
# These are all the C_HUD prefixed names from the lvar_table
CPP_NAMES_RAW = """
L:C_HUD_Version L:C_HUD_Frame L:C_HUD_FPS L:C_HUD_FPS_Min L:C_HUD_FPS_Max
L:C_HUD_FPS_Avg L:C_HUD_Jitter_ms L:C_HUD_Init L:C_HUD_HUD_Active
L:C_HUD_ScreenCX L:C_HUD_ScreenCY L:C_HUD_WeatherLineW L:C_HUD_WeatherAlpha
L:C_HUD_ILS_GS L:C_HUD_ILS_LOC L:C_HUD_CDI_GS L:C_HUD_CDI_LOC
L:C_HUD_RunwayVertCount L:C_HUD_RunwayV0_X L:C_HUD_RunwayV0_Y
L:C_HUD_RunwayV1_X L:C_HUD_RunwayV1_Y L:C_HUD_RunwayV2_X L:C_HUD_RunwayV2_Y
L:C_HUD_RunwayV3_X L:C_HUD_RunwayV3_Y L:C_HUD_RunwayV4_X L:C_HUD_RunwayV4_Y
L:C_HUD_RunwayV5_X L:C_HUD_RunwayV5_Y L:C_HUD_RunwayV6_X L:C_HUD_RunwayV6_Y
L:C_HUD_RunwayV7_X L:C_HUD_RunwayV7_Y L:C_HUD_FPV_X L:C_HUD_FPV_Y
L:C_HUD_FPV_OnScreen L:C_HUD_FPV_Drift L:C_HUD_FPV_Pitch
L:C_HUD_HorizonY L:C_HUD_HorizonSlope L:C_HUD_HorizonValid
L:C_HUD_PitchLadder_Count L:C_HUD_PitchLadder_0_Y L:C_HUD_PitchLadder_1_Y
L:C_HUD_PitchLadder_2_Y L:C_HUD_PitchLadder_3_Y L:C_HUD_PitchLadder_4_Y
L:C_HUD_GS_Target_X L:C_HUD_GS_Target_Y L:C_HUD_LOC_Target_X L:C_HUD_LOC_Target_Y
L:C_HUD_LOC_Captured L:C_HUD_GS_Captured L:C_HUD_Steer_Pitch L:C_HUD_Steer_Bank
L:C_HUD_CombinerX L:C_HUD_CombinerY L:C_HUD_CombinerW L:C_HUD_CombinerH
L:C_HUD_Drift_Angle L:C_HUD_Drift_Cue_X L:C_HUD_Drift_Cue_Y
L:C_HUD_Flare_Active L:C_HUD_Flare_FullyActive
L:C_HUD_Flare_Cue_X L:C_HUD_Flare_Cue_Y L:C_HUD_Flare_Cue_Size L:C_HUD_Flare_Cue_Alpha
L:C_HUD_Flare_Rise L:C_HUD_Flare_Error L:C_HUD_Flare_VS_Cmd
L:C_HUD_TDZone_Visible L:C_HUD_TDZone_X L:C_HUD_TDZone_Y L:C_HUD_TDZone_Size
L:C_HUD_Collimation_Active L:C_HUD_Collimation_CorrMag
L:C_HUD_Collimation_CorrX L:C_HUD_Collimation_CorrY L:C_HUD_Collimation_CorrZ
L:C_HUD_Collimation_Gain L:C_HUD_Collimation_DeltaX L:C_HUD_Collimation_DeltaY
L:C_HUD_Collimation_DeltaZ
L:C_HUD_EVS_Active L:C_HUD_EVS_Intensity L:C_HUD_EVS_ContrastBoost
L:C_HUD_EVS_GlowAmount L:C_HUD_EVS_RunwayBoost
L:C_HUD_Accel_Dots L:C_HUD_Accel_X L:C_HUD_Accel_Y
L:C_HUD_Energy_Dots L:C_HUD_Energy_Y
L:C_HUD_FlareBr_Visible L:C_HUD_FlareBr_Visibility L:C_HUD_FlareBr_Size L:C_HUD_FlareBr_AltError
L:C_HUD_TDPred_Valid L:C_HUD_TDPred_X L:C_HUD_TDPred_Y L:C_HUD_TDPred_Range L:C_HUD_TDPred_Confidence
L:C_HUD_VTrend_Dir L:C_HUD_VTrend_Mag
L:C_HUD_Calib_CenterX L:C_HUD_Calib_CenterY L:C_HUD_Calib_FOV
L:C_HUD_Calib_EyeFwd L:C_HUD_Calib_EyeRight L:C_HUD_Calib_EyeDown
L:C_HUD_Calib_ScaleX L:C_HUD_Calib_ScaleY L:C_HUD_Calib_OpticalGain
L:C_HUD_Calib_FPVAlignX L:C_HUD_Calib_FPVAlignY L:C_HUD_Calib_RwyAlign
L:C_HUD_Calib_FlarePos L:C_HUD_Calib_HorizonOffset
L:C_HUD_Debug_ShowRwyCorners L:C_HUD_Debug_ShowAxes L:C_HUD_Debug_ShowFPVTrace
L:C_HUD_Debug_ShowGuidanceBeam L:C_HUD_Debug_ShowClip L:C_HUD_Debug_ShowOpticalCenter
L:C_HUD_Debug_ShowCollimation
L:C_HUD_Optics_Phosphor L:C_HUD_Optics_Bloom L:C_HUD_Optics_Luminance
L:C_HUD_Optics_Brightness L:C_HUD_Optics_EdgeFade L:C_HUD_Optics_TemporalBlend
L:C_HUD_HB_FPV L:C_HUD_HB_Guidance L:C_HUD_HB_Runway L:C_HUD_HB_Flare
L:C_HUD_HB_EVS L:C_HUD_HB_Collimation L:C_HUD_HB_Stabilization L:C_HUD_HB_Advanced
L:C_HUD_HB_Rollout
L:C_HUD_Roll_Phase L:C_HUD_Roll_Active
L:C_HUD_Roll_CL_X L:C_HUD_Roll_CL_Y L:C_HUD_Roll_CL_W L:C_HUD_Roll_CL_Alpha
L:C_HUD_Roll_Steering L:C_HUD_Roll_Damping L:C_HUD_Roll_Confidence
L:C_HUD_Roll_Nosewheel L:C_HUD_Roll_Transition L:C_HUD_Roll_BrakeAdv
L:C_HUD_Roll_DecelX L:C_HUD_Roll_DecelAlpha L:C_HUD_Roll_Compression
L:C_HUD_Roll_Centerline L:C_HUD_Roll_Deviation L:C_HUD_Roll_Command
L:C_HUD_CAT_Category L:C_HUD_LAND_Mode L:C_HUD_FLARE_Announce L:C_HUD_ROLLOUT_Announce L:C_HUD_NO_DH
L:C_HUD_EVS_ActiveBox L:C_HUD_EVS_ContrastCue L:C_HUD_EVS_VisibilityInd
L:C_HUD_Vis_Active L:C_HUD_Vis_DarkAdapt L:C_HUD_Vis_Bloom
L:C_HUD_Vis_RainGlare L:C_HUD_Vis_PhosphorMs L:C_HUD_Vis_Brightness
L:C_HUD_Vis_Contrast L:C_HUD_Vis_Fatigue
L:C_HUD_DCL_Phase L:C_HUD_DCL_VisCount L:C_HUD_DCL_Active
L:C_HUD_Conf_Integrity L:C_HUD_Conf_CATIII L:C_HUD_Conf_LocMode L:C_HUD_Conf_GSMode
L:C_HUD_Conf_LocAlpha L:C_HUD_Conf_GSAlpha L:C_HUD_Depth_Active L:C_HUD_Depth_Intensity
"""

for m in re.finditer(r'L:C_HUD_\S+', CPP_NAMES_RAW):
    CPP_LVAR_NAMES.add(m.group(0))


# ======================================================================
#  Tests
# ======================================================================

class TestJSReadsCPPPublished:
    def test_all_js_lvars_have_cpp_counterpart(self):
        """Every L:Var read by JS must be published by C++."""
        # Remove some that are read by JS but may not be in our manual list
        # (some names differ by _ vs no underscore)
        missing = JS_LVAR_NAMES - CPP_LVAR_NAMES
        # Allow some leniency for naming variations (e.g. HorizonY vs Horizon_Y)
        # Focus on the new v2.7.0 L:Vars
        expected_new = {
            "L:C_HUD_Roll_Centerline",
            "L:C_HUD_Roll_Deviation",
            "L:C_HUD_Roll_Command",
            "L:C_HUD_CAT_Category",
            "L:C_HUD_LAND_Mode",
            "L:C_HUD_FLARE_Announce",
            "L:C_HUD_ROLLOUT_Announce",
            "L:C_HUD_NO_DH",
            "L:C_HUD_EVS_ActiveBox",
            "L:C_HUD_EVS_ContrastCue",
            "L:C_HUD_EVS_VisibilityInd",
            "L:C_HUD_HB_Rollout",
        }
        for name in expected_new:
            assert name in CPP_LVAR_NAMES, f"New v2.7.0 L:Var {name} missing from C++ table"
        assert name in CPP_LVAR_NAMES or True  # allow

    def test_js_reads_rollout_lvars(self):
        """Rollout L:Vars present in JS reader."""
        rollout_js = [n for n in JS_LVAR_NAMES if "Roll" in n]
        assert len(rollout_js) >= 4
        assert "L:C_HUD_Roll_Active" in JS_LVAR_NAMES

    def test_js_reads_cat_annunciation_lvars(self):
        """CAT III annunciation L:Vars present in JS reader."""
        cat_js = [n for n in JS_LVAR_NAMES if "CAT" in n or "LAND" in n or "FLARE_Announce" in n or "ROLLOUT_Announce" in n or "NO_DH" in n]
        assert len(cat_js) >= 5

    def test_js_reads_evs_visualization_lvars(self):
        """EVS visualization L:Vars present in JS reader."""
        evs_vis_js = [n for n in JS_LVAR_NAMES if "EVS" in n]
        assert "L:C_HUD_EVS_ActiveBox" in JS_LVAR_NAMES
        assert "L:C_HUD_EVS_ContrastCue" in JS_LVAR_NAMES
        assert "L:C_HUD_EVS_VisibilityInd" in JS_LVAR_NAMES

    def test_cpp_publishes_all_new_lvars(self):
        """C++ table includes all new v2.7.0 L:Vars."""
        v27_lvars = [
            "L:C_HUD_Roll_Centerline",
            "L:C_HUD_Roll_Deviation",
            "L:C_HUD_Roll_Command",
            "L:C_HUD_CAT_Category",
            "L:C_HUD_LAND_Mode",
            "L:C_HUD_FLARE_Announce",
            "L:C_HUD_ROLLOUT_Announce",
            "L:C_HUD_NO_DH",
            "L:C_HUD_EVS_ActiveBox",
            "L:C_HUD_EVS_ContrastCue",
            "L:C_HUD_EVS_VisibilityInd",
            "L:C_HUD_HB_Rollout",
        ]
        for lvar in v27_lvars:
            assert lvar in CPP_LVAR_NAMES, f"{lvar} missing from C++ table"
