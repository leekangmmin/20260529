#!/usr/bin/env python3
"""
Conformal HUD – Semi-Collimated Rendering Test Suite (v2.1.0)

Tests:
  1. Camera delta initialisation
  2. Delta tracking on eye position change
  3. Collimation correction magnitude limits
  4. Compensation gain application
  5. Leaky integrator behaviour
  6. Debug telemetry

Run:  python -m pytest tests/test_collimation.py -v
"""

import math
import pytest


# ======================================================================
#  Reference implementation (mirrors C++ collimation.h/.cpp)
# ======================================================================

class Vec3:
    __slots__ = ('x', 'y', 'z')
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.x, self.y, self.z = float(x), float(y), float(z)
    def __repr__(self):
        return f"Vec3({self.x:.6f}, {self.y:.6f}, {self.z:.6f})"
    def __eq__(self, other, eps=1e-9):
        if isinstance(other, Vec3):
            return (abs(self.x - other.x) < eps and
                    abs(self.y - other.y) < eps and
                    abs(self.z - other.z) < eps)
        return NotImplemented


def vec3_zero():
    return Vec3(0, 0, 0)

def vec3_sub(a, b):
    return Vec3(a.x - b.x, a.y - b.y, a.z - b.z)

def vec3_add(a, b):
    return Vec3(a.x + b.x, a.y + b.y, a.z + b.z)

def vec3_scale(v, s):
    return Vec3(v.x * s, v.y * s, v.z * s)

def vec3_len(v):
    return math.sqrt(v.x*v.x + v.y*v.y + v.z*v.z)


class CameraDelta:
    """Camera delta tracking state."""
    def __init__(self, compensation_gain=0.85, max_compensation_m=0.15):
        self.delta_body = vec3_zero()
        self.prev_eye = vec3_zero()
        self.prev_ac_ref = vec3_zero()
        self.prev_heading = 0.0
        self.prev_pitch = 0.0
        self.prev_bank = 0.0
        self.compensation_gain = compensation_gain
        self.max_compensation_m = max_compensation_m
        self.initialised = False


class CollimationCorrection:
    """Collimation correction output."""
    def __init__(self):
        self.stabilised_eye = vec3_zero()
        self.raw_eye = vec3_zero()
        self.correction_vector = vec3_zero()
        self.correction_mag_m = 0.0
        self.active = False
        self.debug_camera_delta_x = 0.0
        self.debug_camera_delta_y = 0.0
        self.debug_camera_delta_z = 0.0
        self.debug_compensation_gain = 0.85


def collimation_update(cd, current_eye, ac_ref, heading, pitch, bank, dt_s):
    """Update camera delta tracking and compute collimation correction."""
    cc = CollimationCorrection()
    cc.debug_compensation_gain = cd.compensation_gain

    if not cd.initialised:
        cd.prev_eye = current_eye
        cd.prev_ac_ref = ac_ref
        cd.prev_heading = heading
        cd.prev_pitch = pitch
        cd.prev_bank = bank
        cd.delta_body = vec3_zero()
        cd.initialised = True
        cc.stabilised_eye = current_eye
        cc.raw_eye = current_eye
        cc.correction_vector = vec3_zero()
        cc.correction_mag_m = 0.0
        cc.active = False
        return cc

    # Body-frame delta
    eye_delta = vec3_sub(current_eye, cd.prev_eye)

    # Leaky integrator
    leak = 0.995
    cd.delta_body.x = cd.delta_body.x * leak + eye_delta.x
    cd.delta_body.y = cd.delta_body.y * leak + eye_delta.y
    cd.delta_body.z = cd.delta_body.z * leak + eye_delta.z

    # Clamp
    delta_len = vec3_len(cd.delta_body)
    if delta_len > cd.max_compensation_m:
        scale = cd.max_compensation_m / delta_len
        cd.delta_body = vec3_scale(cd.delta_body, scale)

    # Correction vector
    cc.correction_vector = vec3_scale(cd.delta_body, -cd.compensation_gain)
    cc.correction_mag_m = vec3_len(cc.correction_vector)

    cc.debug_camera_delta_x = cd.delta_body.x
    cc.debug_camera_delta_y = cd.delta_body.y
    cc.debug_camera_delta_z = cd.delta_body.z

    cc.raw_eye = current_eye
    cc.stabilised_eye = vec3_add(current_eye, cc.correction_vector)
    cc.active = (cc.correction_mag_m > 0.001)

    # Store for next frame
    cd.prev_eye = current_eye
    cd.prev_ac_ref = ac_ref
    cd.prev_heading = heading
    cd.prev_pitch = pitch
    cd.prev_bank = bank

    return cc


# ======================================================================
#  Tests
# ======================================================================

class TestCameraDeltaInit:
    def test_init_not_initialised(self):
        cd = CameraDelta()
        assert cd.initialised is False
        assert cd.delta_body == vec3_zero()
        assert cd.compensation_gain == 0.85
        assert cd.max_compensation_m == 0.15

    def test_first_frame_no_correction(self):
        cd = CameraDelta()
        eye = Vec3(0.5, 0.0, -1.2)
        ac_ref = Vec3(126.4446, 1000.0, 37.4545)
        cc = collimation_update(cd, eye, ac_ref, 180.0, 0.0, 0.0, 1.0/60.0)
        assert cc.active is False
        assert cc.correction_mag_m == 0.0
        assert cd.initialised is True

    def test_delta_tracks_eye_movement(self):
        cd = CameraDelta()
        eye1 = Vec3(0.5, 0.0, -1.2)
        ac_ref = Vec3(126.4446, 1000.0, 37.4545)
        collimation_update(cd, eye1, ac_ref, 180.0, 0.0, 0.0, 1.0/60.0)

        eye2 = Vec3(0.55, 0.0, -1.2)
        cc = collimation_update(cd, eye2, ac_ref, 180.0, 0.0, 0.0, 1.0/60.0)
        assert cc.active is True
        assert abs(cc.correction_mag_m) > 0.0
        assert cc.correction_vector.x < 0.0

    def test_correction_opposes_movement(self):
        cd = CameraDelta()
        eye1 = Vec3(0.5, 0.0, -1.2)
        ac_ref = Vec3(126.4446, 1000.0, 37.4545)
        collimation_update(cd, eye1, ac_ref, 180.0, 0.0, 0.0, 1.0/60.0)

        eye2 = Vec3(0.6, 0.05, -1.25)
        cc = collimation_update(cd, eye2, ac_ref, 180.0, 0.0, 0.0, 1.0/60.0)
        assert cc.active is True
        assert cc.correction_vector.x < 0.0
        assert cc.correction_vector.y < 0.0

    def test_max_compensation_limit(self):
        cd = CameraDelta(max_compensation_m=0.05)
        eye1 = Vec3(0.5, 0.0, -1.2)
        ac_ref = Vec3(126.4446, 1000.0, 37.4545)
        collimation_update(cd, eye1, ac_ref, 180.0, 0.0, 0.0, 1.0/60.0)

        eye2 = Vec3(0.6, 0.1, -1.3)
        for _ in range(5):
            cc = collimation_update(cd, eye2, ac_ref, 180.0, 0.0, 0.0, 1.0/60.0)
        delta_len = vec3_len(cd.delta_body)
        assert delta_len <= 0.051

    def test_leaky_integrator_decay(self):
        cd = CameraDelta()
        eye = Vec3(0.5, 0.0, -1.2)
        ac_ref = Vec3(126.4446, 1000.0, 37.4545)
        collimation_update(cd, eye, ac_ref, 180.0, 0.0, 0.0, 1.0/60.0)

        eye2 = Vec3(0.55, 0.02, -1.22)
        cc1 = collimation_update(cd, eye2, ac_ref, 180.0, 0.0, 0.0, 1.0/60.0)

        # Stay at same position - delta should leak away
        # 0.995^2000 ≈ 0.000045, so 2000 frames is enough
        for _ in range(2000):
            cc = collimation_update(cd, eye2, ac_ref, 180.0, 0.0, 0.0, 1.0/60.0)

        delta_len = vec3_len(cd.delta_body)
        assert delta_len < 0.005  # leaked away

    def test_stabilised_eye_provided(self):
        cd = CameraDelta()
        eye1 = Vec3(0.5, 0.0, -1.2)
        ac_ref = Vec3(126.4446, 1000.0, 37.4545)
        collimation_update(cd, eye1, ac_ref, 180.0, 0.0, 0.0, 1.0/60.0)

        eye2 = Vec3(0.55, 0.0, -1.2)
        cc = collimation_update(cd, eye2, ac_ref, 180.0, 0.0, 0.0, 1.0/60.0)

        assert cc.stabilised_eye.x < eye2.x
        assert cc.stabilised_eye.x > eye1.x
        assert cc.raw_eye == eye2

    def test_debug_telemetry_populated(self):
        cd = CameraDelta()
        eye1 = Vec3(0.5, 0.0, -1.2)
        ac_ref = Vec3(126.4446, 1000.0, 37.4545)
        collimation_update(cd, eye1, ac_ref, 180.0, 0.0, 0.0, 1.0/60.0)

        eye2 = Vec3(0.55, 0.03, -1.25)
        cc = collimation_update(cd, eye2, ac_ref, 180.0, 0.0, 0.0, 1.0/60.0)

        assert cc.debug_camera_delta_x == cd.delta_body.x
        assert cc.debug_camera_delta_y == cd.delta_body.y
        assert cc.debug_camera_delta_z == cd.delta_body.z
        assert cc.debug_compensation_gain == cd.compensation_gain
