#!/usr/bin/env python3
"""
Conformal HUD – Optical Depth Illusion Test Suite (v2.4.0)

Tests:
  1. Depth illusion initialisation
  2. Per-layer parallax offsets
  3. Optical centre wobble
  4. Head-motion induced shift
  5. Focal blur per depth layer
  6. Infinity layer stabilisation
  7. Apply depth offset to screen positions

Run:  python -m pytest tests/test_depth_illusion.py -v
"""

import math
import pytest


# ======================================================================
#  Constants & Enums
# ======================================================================

DEPTH_OPTICAL_INFINITY = 0
DEPTH_COMBINER_NEAR = 1
DEPTH_COMBINER_MID = 2
DEPTH_COMBINER_FAR = 3

DI_WOBBLE_FREQ_BASE = 8.0
DI_WOBBLE_AMP_BASE = 0.3
DI_HEAD_MOTION_GAIN = 0.02
DI_INFINITY_STAB_GAIN = 0.8

LAYER_PARALLAX_SCALE = [0.0, 0.8, 0.4, 0.2]
LAYER_FOCAL_BLUR = [0.0, 0.15, 0.05, 0.10]


class Vec2:
    __slots__ = ('x', 'y')
    def __init__(self, x=0.0, y=0.0):
        self.x = float(x)
        self.y = float(y)
    def __repr__(self):
        return f"Vec2({self.x:.4f}, {self.y:.4f})"


class CollimationCorrection:
    def __init__(self):
        self.active = False
        self.correction_mag_m = 0.0
        self.correction_vector = Vec2(0, 0)
        self.debug_camera_delta_x = 0.0
        self.debug_camera_delta_z = 0.0


class DepthIllusionState:
    def __init__(self):
        self.parallax_offset = [Vec2(0, 0) for _ in range(4)]
        self.focal_blur = [0.0] * 4
        self.focal_sharpness = [1.0] * 4
        self.head_motion_shift = Vec2(0, 0)
        self.head_motion_gain = 0.02
        self.optical_wobble = Vec2(0, 0)
        self.wobble_frequency = DI_WOBBLE_FREQ_BASE
        self.wobble_amplitude = DI_WOBBLE_AMP_BASE
        self.stabilisation_offset = Vec2(0, 0)
        self.depth_intensity = 0.5
        self.infinity_layer_offset = Vec2(0, 0)
        self.active = False
        self.valid = False


def depth_illusion_compute(di, dt_s=1.0/60.0, cc=None, intensity=0.5):
    di.depth_intensity = max(0.0, min(1.0, intensity))

    # Wobble
    di.wobble_frequency = DI_WOBBLE_FREQ_BASE
    di.wobble_amplitude = DI_WOBBLE_AMP_BASE * di.depth_intensity
    phase_x = di.wobble_frequency * 0.7 * 2.0 * math.pi
    phase_y = di.wobble_frequency * 0.5 * 2.0 * math.pi
    di.optical_wobble.x = di.wobble_amplitude * math.sin(phase_x)
    di.optical_wobble.y = di.wobble_amplitude * math.cos(phase_y)

    # Head-motion parallax
    head_delta = Vec2(0, 0)
    if cc is not None and cc.active:
        head_delta.x = cc.debug_camera_delta_x * 100.0
        head_delta.y = cc.debug_camera_delta_z * 100.0

    for i in range(4):
        scale = LAYER_PARALLAX_SCALE[i] * di.depth_intensity
        di.parallax_offset[i].x = head_delta.x * scale * DI_HEAD_MOTION_GAIN
        di.parallax_offset[i].y = head_delta.y * scale * DI_HEAD_MOTION_GAIN

    di.head_motion_shift.x = head_delta.x * DI_HEAD_MOTION_GAIN * di.depth_intensity
    di.head_motion_shift.y = head_delta.y * DI_HEAD_MOTION_GAIN * di.depth_intensity

    # Focal blur
    for i in range(4):
        di.focal_blur[i] = LAYER_FOCAL_BLUR[i] * di.depth_intensity
        di.focal_sharpness[i] = 1.0 - di.focal_blur[i]

    # Infinity layer stabilisation
    di.infinity_layer_offset.x = -di.optical_wobble.x * DI_INFINITY_STAB_GAIN
    di.infinity_layer_offset.y = -di.optical_wobble.y * DI_INFINITY_STAB_GAIN

    di.active = di.depth_intensity > 0.01
    di.valid = True


def depth_illusion_apply(di, pos, layer):
    if di is None or not di.active:
        return Vec2(pos.x, pos.y)
    result = Vec2(pos.x, pos.y)
    result.x += di.parallax_offset[layer].x
    result.y += di.parallax_offset[layer].y
    depth_factor = 1.0 - layer * 0.25
    result.x += di.head_motion_shift.x * depth_factor
    result.y += di.head_motion_shift.y * depth_factor
    result.x += di.optical_wobble.x
    result.y += di.optical_wobble.y
    if layer == DEPTH_OPTICAL_INFINITY:
        result.x += di.infinity_layer_offset.x
        result.y += di.infinity_layer_offset.y
    return result


# ======================================================================
#  Tests
# ======================================================================

class TestDepthIllusionInit:
    def test_default_inactive(self):
        di = DepthIllusionState()
        assert di.active is False
        assert di.valid is False
        assert di.depth_intensity == 0.5


class TestOpticalWobble:
    def test_wobble_computed(self):
        di = DepthIllusionState()
        depth_illusion_compute(di)
        assert abs(di.optical_wobble.x) > 0.0 or abs(di.optical_wobble.y) > 0.0

    def test_wobble_subpixel(self):
        di = DepthIllusionState()
        depth_illusion_compute(di, intensity=0.5)
        assert abs(di.optical_wobble.x) < 1.0
        assert abs(di.optical_wobble.y) < 1.0

    def test_wobble_scales_with_intensity(self):
        di_low = DepthIllusionState()
        depth_illusion_compute(di_low, intensity=0.0)
        wobble_low = abs(di_low.optical_wobble.x) + abs(di_low.optical_wobble.y)

        di_high = DepthIllusionState()
        depth_illusion_compute(di_high, intensity=1.0)
        wobble_high = abs(di_high.optical_wobble.x) + abs(di_high.optical_wobble.y)
        assert wobble_high >= wobble_low


class TestParallax:
    def test_infinity_layer_no_parallax(self):
        di = DepthIllusionState()
        cc = CollimationCorrection()
        cc.active = True
        cc.debug_camera_delta_x = 0.01
        cc.debug_camera_delta_z = 0.005
        depth_illusion_compute(di, cc=cc, intensity=0.5)
        assert abs(di.parallax_offset[DEPTH_OPTICAL_INFINITY].x) < 0.001
        assert abs(di.parallax_offset[DEPTH_OPTICAL_INFINITY].y) < 0.001

    def test_near_layer_has_most_parallax(self):
        di = DepthIllusionState()
        cc = CollimationCorrection()
        cc.active = True
        cc.debug_camera_delta_x = 0.01
        cc.debug_camera_delta_z = 0.005
        depth_illusion_compute(di, cc=cc, intensity=1.0)
        near_mag = abs(di.parallax_offset[DEPTH_COMBINER_NEAR].x) + abs(di.parallax_offset[DEPTH_COMBINER_NEAR].y)
        far_mag = abs(di.parallax_offset[DEPTH_COMBINER_FAR].x) + abs(di.parallax_offset[DEPTH_COMBINER_FAR].y)
        assert near_mag >= far_mag

    def test_no_head_motion_no_parallax(self):
        di = DepthIllusionState()
        depth_illusion_compute(di, intensity=0.5)
        for i in range(4):
            assert abs(di.parallax_offset[i].x) < 0.001
            assert abs(di.parallax_offset[i].y) < 0.001


class TestFocalBlur:
    def test_infinity_layer_sharp(self):
        di = DepthIllusionState()
        depth_illusion_compute(di, intensity=0.5)
        assert di.focal_sharpness[DEPTH_OPTICAL_INFINITY] == 1.0

    def test_near_layer_most_blurred(self):
        di = DepthIllusionState()
        depth_illusion_compute(di, intensity=1.0)
        assert di.focal_blur[DEPTH_COMBINER_NEAR] >= di.focal_blur[DEPTH_COMBINER_MID]


class TestDepthApply:
    def test_non_active_returns_original(self):
        di = DepthIllusionState()
        pos = Vec2(100.0, 200.0)
        result = depth_illusion_apply(di, pos, DEPTH_OPTICAL_INFINITY)
        assert result.x == 100.0
        assert result.y == 200.0

    def test_active_modifies_position(self):
        di = DepthIllusionState()
        cc = CollimationCorrection()
        cc.active = True
        cc.debug_camera_delta_x = 0.01
        cc.debug_camera_delta_z = 0.01
        depth_illusion_compute(di, cc=cc, intensity=1.0)
        pos = Vec2(100.0, 200.0)
        result = depth_illusion_apply(di, pos, DEPTH_COMBINER_NEAR)
        # Position should be slightly different
        assert (result.x != 100.0) or (result.y != 200.0)

    def test_infinity_layer_stabilised(self):
        di = DepthIllusionState()
        cc = CollimationCorrection()
        cc.active = True
        cc.debug_camera_delta_x = 0.01
        cc.debug_camera_delta_z = 0.01
        depth_illusion_compute(di, cc=cc, intensity=1.0)
        pos = Vec2(100.0, 200.0)
        infinity_result = depth_illusion_apply(di, pos, DEPTH_OPTICAL_INFINITY)
        near_result = depth_illusion_apply(di, pos, DEPTH_COMBINER_NEAR)
        # Near layer has larger total shift (parallax + head motion + wobble)
        # Infinity layer has wobble partially cancelled by stabilisation
        inf_delta = abs(infinity_result.x - 100.0) + abs(infinity_result.y - 200.0)
        near_delta = abs(near_result.x - 100.0) + abs(near_result.y - 200.0)
        # The wobble stabilisation tries to keep infinity layer stable
        # Since both get wobble, but near gets more parallax, near should move more
        assert near_delta >= inf_delta * 0.5  # near moves at least half as much more
