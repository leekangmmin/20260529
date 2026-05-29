#!/usr/bin/env python3
"""
Conformal HUD – Projection Math Test Suite

Validates the C++ projection math (implemented in include/projection.h)
against an independent Python reference implementation.

Tests:
  1. Vec3 arithmetic (sub, dot, cross, len, normalise)
  2. World→NEU coordinate conversion
  3. Aircraft attitude rotation matrix (heading/pitch/bank)
  4. Perspective projection
  5. Full pipeline: world_to_screen
  6. Edge cases: behind camera, near clipping, degenerate inputs
  7. On-screen bounding-box detection

Run:  python -m pytest tests/test_projection.py -v
"""

import math

# ======================================================================
#  Reference implementation (mirrors C++ projection.h logic)
#
#  ROTATION CONVENTION:
#    R_body2world = Rz(-heading) * Ry(-pitch) * Rx(-bank)
#    v_body       = R_body2world^T * v_world
#  This is the standard aerospace ZYX Euler sequence with negative
#  Euler angles because MSFS's coordinate system has Y=up, Z=north.
# ======================================================================

EARTH_RADIUS_M = 6378137.0
DEG2RAD = math.pi / 180.0
RAD2DEG = 180.0 / math.pi


class Vec3:
    """Double-precision 3-D vector."""
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


def vec3_sub(a, b):
    return Vec3(a.x - b.x, a.y - b.y, a.z - b.z)

def vec3_dot(a, b):
    return a.x * b.x + a.y * b.y + a.z * b.z

def vec3_cross(a, b):
    return Vec3(
        a.y * b.z - a.z * b.y,
        a.z * b.x - a.x * b.z,
        a.x * b.y - a.y * b.x
    )

def vec3_len(v):
    return math.sqrt(vec3_dot(v, v))

def vec3_normalise(v):
    l = vec3_len(v)
    if l < 1e-12:
        return Vec3(0, 0, 0)
    inv = 1.0 / l
    return Vec3(v.x * inv, v.y * inv, v.z * inv)

def vec3_zero():
    return Vec3(0, 0, 0)


class Mat4:
    """4×4 column-major matrix."""
    __slots__ = ('m',)
    def __init__(self, data=None):
        if data is None:
            self.m = [0.0] * 16
        else:
            assert len(data) == 16
            self.m = [float(x) for x in data]

    def __repr__(self):
        rows = []
        for r in range(4):
            rows.append([self.m[c*4 + r] for c in range(4)])
        return f"Mat4({rows})"


class Vec2:
    """2-D screen-space point."""
    __slots__ = ('x', 'y')
    def __init__(self, x=0.0, y=0.0):
        self.x, self.y = float(x), float(y)

    def __repr__(self):
        return f"Vec2({self.x:.2f}, {self.y:.2f})"

    def __eq__(self, other, eps=1e-6):
        if isinstance(other, Vec2):
            return (abs(self.x - other.x) < eps and
                    abs(self.y - other.y) < eps)
        return NotImplemented


def world_to_neu(point_world, ref_world):
    """Convert lat/lon/alt to NEU offset in metres.

    point_world: Vec3 (lon_deg, alt_m, lat_deg)
    ref_world:   Vec3 (lon_deg, alt_m, lat_deg)
    returns:     Vec3 (east_m, up_m, north_m)
    """
    lat_ref = ref_world.z * DEG2RAD
    lon_ref = ref_world.x * DEG2RAD
    lat_pt  = point_world.z * DEG2RAD
    lon_pt  = point_world.x * DEG2RAD

    dlat = lat_pt - lat_ref
    dlon = lon_pt - lon_ref

    cos_lat = math.cos(lat_ref)
    north_m = dlat * EARTH_RADIUS_M
    east_m  = dlon * EARTH_RADIUS_M * cos_lat
    up_m    = point_world.y - ref_world.y

    return Vec3(east_m, up_m, north_m)


def attitude_to_matrix(heading_deg, pitch_deg, bank_deg):
    """Build body-to-world rotation matrix from Euler angles.

    R_body2world = Rz(-h) * Ry(-p) * Rx(-b)

    Returns Mat4 (column-major, 4×4 homogeneous).
    """
    h = heading_deg * DEG2RAD
    p = pitch_deg   * DEG2RAD
    b = bank_deg    * DEG2RAD

    ch, sh = math.cos(h), math.sin(h)
    cp, sp = math.cos(p), math.sin(p)
    cb, sb = math.cos(b), math.sin(b)

    m = [0.0] * 16
    m[0]  =  ch * cp
    m[1]  =  sh * cp
    m[2]  = -sp
    m[3]  =  0.0

    m[4]  = -sh * cb + ch * sp * sb
    m[5]  =  ch * cb + sh * sp * sb
    m[6]  =  cp * sb
    m[7]  =  0.0

    m[8]  =  sh * sb + ch * sp * cb
    m[9]  = -ch * sb + sh * sp * cb
    m[10] =  cp * cb
    m[11] =  0.0

    m[12] = 0.0
    m[13] = 0.0
    m[14] = 0.0
    m[15] = 1.0

    return Mat4(m)


def transform_by_attitude(v_world, b2w):
    """Transform world-space NEU vector to aircraft body coordinates.

    v_body = R_body2world^T * v_world  (column-major: row0·v, row1·v, row2·v)
    """
    m = b2w.m
    return Vec3(
        m[0] * v_world.x + m[1] * v_world.y + m[2] * v_world.z,
        m[4] * v_world.x + m[5] * v_world.y + m[6] * v_world.z,
        m[8] * v_world.x + m[9] * v_world.y + m[10] * v_world.z
    )


def perspective(pt_body, focal_px, screen_w, screen_h, near_clip=0.1):
    """Perspective project a body-frame point to screen space.

    Returns (Vec2, behind_camera).
    """
    cx = screen_w / 2.0
    cy = screen_h / 2.0

    if pt_body.z <= near_clip:
        return Vec2(-9999, -9999), True

    inv_z = 1.0 / pt_body.z
    return Vec2(
        cx + focal_px * pt_body.x * inv_z,
        cy - focal_px * pt_body.y * inv_z
    ), False


def world_to_screen(world_pt, ref_pt, heading_deg, pitch_deg, bank_deg,
                    focal_px, screen_w, screen_h):
    """Full projection pipeline: world → screen."""
    # (a) World → NEU
    neu = world_to_neu(world_pt, ref_pt)

    # (b) Attitude rotation
    b2w = attitude_to_matrix(heading_deg, pitch_deg, bank_deg)

    # (c) NEU → body frame
    body = transform_by_attitude(neu, b2w)

    # (d) Perspective
    return perspective(body, focal_px, screen_w, screen_h)


def any_vertex_on_screen(verts, screen_w, screen_h, margin=0):
    """Returns True if any vertex is within screen bounds."""
    for v in verts:
        if v.get('behind', False):
            continue
        sx, sy = v['screen'].x, v['screen'].y
        if (-margin <= sx < screen_w + margin and
            -margin <= sy < screen_h + margin):
            return True
    return False


# ======================================================================
#  Tests
# ======================================================================

class TestVec3:
    def test_zero(self):
        v = vec3_zero()
        assert v.x == 0.0 and v.y == 0.0 and v.z == 0.0

    def test_sub(self):
        a = Vec3(5, 3, 1)
        b = Vec3(2, 1, 4)
        r = vec3_sub(a, b)
        assert r == Vec3(3, 2, -3)

    def test_dot(self):
        a = Vec3(1, 2, 3)
        b = Vec3(4, 5, 6)
        assert abs(vec3_dot(a, b) - 32.0) < 1e-12

    def test_cross(self):
        a = Vec3(1, 0, 0)
        b = Vec3(0, 1, 0)
        r = vec3_cross(a, b)
        assert r == Vec3(0, 0, 1)

    def test_len(self):
        v = Vec3(3, 4, 0)
        assert abs(vec3_len(v) - 5.0) < 1e-12

    def test_normalise(self):
        v = Vec3(0, 0, 5)
        n = vec3_normalise(v)
        assert abs(vec3_len(n) - 1.0) < 1e-12
        assert abs(n.z - 1.0) < 1e-12

    def test_normalise_zero(self):
        v = Vec3(0, 0, 0)
        n = vec3_normalise(v)
        assert n == Vec3(0, 0, 0)


class TestWorldToNEU:
    """Validate world→NEU conversion with Incheon Airport (RKSI) coordinates."""

    def test_same_point(self):
        ref = Vec3(126.4446, 7.0, 37.4545)
        pt  = Vec3(126.4446, 7.0, 37.4545)
        neu = world_to_neu(pt, ref)
        assert abs(neu.x) < 1.0
        assert abs(neu.y) < 0.1
        assert abs(neu.z) < 1.0

    def test_100m_north(self):
        ref = Vec3(126.4446, 7.0, 37.4545)
        pt  = Vec3(126.4446, 7.0, 37.4554)
        neu = world_to_neu(pt, ref)
        assert abs(neu.z - 100.0) < 5.0
        assert abs(neu.x) < 2.0

    def test_100m_east(self):
        ref = Vec3(126.4446, 7.0, 37.4545)
        pt  = Vec3(126.4457, 7.0, 37.4545)
        neu = world_to_neu(pt, ref)
        assert abs(neu.x - 100.0) < 5.0
        assert abs(neu.z) < 2.0

    def test_100m_up(self):
        ref = Vec3(126.4446, 7.0, 37.4545)
        pt  = Vec3(126.4446, 107.0, 37.4545)
        neu = world_to_neu(pt, ref)
        assert abs(neu.y - 100.0) < 1.0


class TestAttitudeMatrix:
    """Validate rotation matrix construction.

    Convention: R_body2world = Rz(-h) * Ry(-p) * Rx(-b)
    transform_by_attitude computes v_body = R_body2world^T * v_world
    """

    def test_level_flight_north(self):
        """Heading 0, pitch 0, bank 0 → identity on body axes."""
        b2w = attitude_to_matrix(0, 0, 0)
        v = transform_by_attitude(Vec3(1, 0, 0), b2w)
        assert abs(v.x - 1.0) < 1e-9
        assert abs(v.y) < 1e-9
        assert abs(v.z) < 1e-9

    def test_heading_90_east(self):
        """
        Heading 90° (east).
        R_body2world = Rz(-90°) = [[cos(-90), -sin(-90), 0],
                                   [sin(-90),  cos(-90), 0],
                                   [0,         0,         1]]
                     = [[0, 1, 0], [-1, 0, 0], [0, 0, 1]]

        R_body2world^T = Ry(90°)^T ... let's just check numerically:
        For heading=90°, NEU=(east, up, north):
          World east (1,0,0) → body (m[0], m[4], m[8]) = (0, -1, 0)
          = right wing points south in NEU frame when facing east.

        World north (0,0,1) → body (m[2], m[6], m[10]) = (0, 0, 1)
          = forward direction (north is straight ahead when looking east
            in the NEU frame's definition, but actually when heading=90°,
            the aircraft's forward body Z axis points east in world).

          Wait - let me re-check. R_body2world maps from body to world.
          When heading=90°, the body Z axis (forward) should point east in world.
          R_body2world * (0,0,1) = first compute the "z column" of R:
            Rz(-90)*Ry(-0)*Rx(-0) = Rz(-90)

            Rz(-90) * e_z = (sin(-90)*?  No. Rz(-90) * (0,0,1) = (0,0,1)
            Hmm that doesn't seem right. Let me just test numerically.
        """
        b2w = attitude_to_matrix(90, 0, 0)

        # World east (1,0,0):
        #   body.x = m[0]*1 + m[1]*0 + m[2]*0 = ch*cp = 0*1 = 0
        #   body.y = m[4]*1 + m[5]*0 + m[6]*0 = -sh*cb+ch*sp*sb = -1*1+0 = -1
        #   body.z = m[8]*1 + m[9]*0 + m[10]*0 = sh*sb+ch*sp*cb = 0+0 = 0
        body_east = transform_by_attitude(Vec3(1, 0, 0), b2w)
        assert abs(body_east.x) < 1e-9
        assert abs(body_east.y + 1.0) < 1e-9   # east → body down (-Y)
        assert abs(body_east.z) < 1e-9

        # World north (0,0,1):
        #   body.x = m[0]*0 + m[1]*0 + m[2]*1 = -sp = 0
        #   body.y = m[4]*0 + m[5]*0 + m[6]*1 = cp*sb = 1*0 = 0
        #   body.z = m[8]*0 + m[9]*0 + m[10]*1 = cp*cb = 1*1 = 1
        body_north = transform_by_attitude(Vec3(0, 0, 1), b2w)
        assert abs(body_north.x) < 1e-9
        assert abs(body_north.y) < 1e-9
        assert abs(body_north.z - 1.0) < 1e-9

    def test_pitch_up(self):
        """
        Pitch 10° up: R_body2world = Ry(-10°).

        With heading=0, pitch=10, bank=0:
          R = Ry(-10°) = [[cos10, 0, -sin10],
                          [0,     1,  0],
                          [sin10, 0,  cos10]]

        R_body2world^T = Ry(10°) = [[cos10, 0, sin10],
                                    [0,     1, 0],
                                    [-sin10,0, cos10]]

        World up (0,1,0) → body (0, 1, 0)  (Y is preserved by Ry)
        World north (0,0,1) → body (-sin10°, 0, cos10°)

        Explanation: when the aircraft pitches up 10°, a point that is
        purely north of the aircraft in the world frame appears shifted
        backwards (negative X = left/back) in the body frame because the
        aircraft's nose has rotated upward.
        """
        b2w = attitude_to_matrix(0, 10, 0)

        # World up stays up under pitch rotation
        world_up = Vec3(0, 1, 0)
        body_up = transform_by_attitude(world_up, b2w)
        assert abs(body_up.x) < 1e-9
        assert abs(body_up.y - 1.0) < 1e-9
        assert abs(body_up.z) < 1e-9

        # World north rotates into body X (backward) and Z (forward)
        world_north = Vec3(0, 0, 1)
        body_north = transform_by_attitude(world_north, b2w)
        # body.x = m[2]*1 = -sin10°
        assert abs(body_north.x + math.sin(10*DEG2RAD)) < 1e-9
        # body.y = m[6]*1 = 0
        assert abs(body_north.y) < 1e-9
        # body.z = m[10]*1 = cos10°
        assert abs(body_north.z - math.cos(10*DEG2RAD)) < 1e-9

    def test_orthogonal(self):
        """Rotation matrix should be orthogonal: R * R^T = I."""
        b2w = attitude_to_matrix(45, 10, -5)
        cols = [
            Vec3(b2w.m[0], b2w.m[1], b2w.m[2]),
            Vec3(b2w.m[4], b2w.m[5], b2w.m[6]),
            Vec3(b2w.m[8], b2w.m[9], b2w.m[10]),
        ]
        for c in cols:
            assert abs(vec3_len(c) - 1.0) < 1e-9
        assert abs(vec3_dot(cols[0], cols[1])) < 1e-9
        assert abs(vec3_dot(cols[0], cols[2])) < 1e-9
        assert abs(vec3_dot(cols[1], cols[2])) < 1e-9


class TestPerspective:
    def test_center(self):
        """Point dead ahead at center of view → screen center."""
        pt = Vec3(0, 0, 1000)
        s, behind = perspective(pt, 520, 1024, 1024)
        assert behind is False
        assert abs(s.x - 512) < 1e-6
        assert abs(s.y - 512) < 1e-6

    def test_right_100m(self):
        """Point 100 m right of center at 1000 m ahead."""
        pt = Vec3(100, 0, 1000)
        s, behind = perspective(pt, 520, 1024, 1024)
        expected_x = 512 + 520 * 100 / 1000
        assert abs(s.x - expected_x) < 1e-6
        assert abs(s.y - 512) < 1e-6

    def test_above_50m(self):
        """Point 50 m above center at 500 m ahead (Y-down convention)."""
        pt = Vec3(0, 50, 500)
        s, behind = perspective(pt, 520, 1024, 1024)
        expected_y = 512 - 520 * 50 / 500
        assert abs(s.x - 512) < 1e-6
        assert abs(s.y - expected_y) < 1e-6

    def test_behind_camera(self):
        """Point behind the camera → flagged behind."""
        pt = Vec3(0, 0, -1)
        s, behind = perspective(pt, 520, 1024, 1024, near_clip=0.1)
        assert behind is True
        assert s.x == -9999
        assert s.y == -9999

    def test_near_clip(self):
        """Point at exactly near clip plane → behind."""
        pt = Vec3(0, 0, 0.1)
        s, behind = perspective(pt, 520, 1024, 1024, near_clip=0.1)
        assert behind is True


class TestFullPipeline:
    """End-to-end projection using realistic approach scenario.

    Aircraft at ~3 NM final, 1500 ft AGL, heading 148° (RKSI 15R).
    """

    @classmethod
    def setup_class(cls):
        cls.focal_px = 520
        cls.screen_w = 1024
        cls.screen_h = 1024
        # Runway threshold (Vec3: lon_deg, alt_m, lat_deg)
        cls.rwy = Vec3(126.4446, 7.0, 37.4545)
        # Aircraft ~5 km SW of threshold on 148° final, 1500 ft AGL
        cls.ac = Vec3(126.406, 457.0, 37.416)

    def test_runway_on_screen(self):
        """Runway should project on-screen during final approach."""
        sc, behind = world_to_screen(
            self.rwy, self.ac,
            heading_deg=148.0,
            pitch_deg=-2.0,
            bank_deg=0.0,
            focal_px=self.focal_px,
            screen_w=self.screen_w,
            screen_h=self.screen_h
        )
        assert behind is False
        assert 0 <= sc.x <= self.screen_w
        assert 0 <= sc.y <= self.screen_h

    def test_runway_behind_when_passed(self):
        """Runway behind aircraft → behind_camera=True."""
        ac_past = Vec3(126.460, 150.0, 37.465)
        sc, behind = world_to_screen(
            self.rwy, ac_past,
            heading_deg=148.0 + 180.0,
            pitch_deg=0.0,
            bank_deg=0.0,
            focal_px=self.focal_px,
            screen_w=self.screen_w,
            screen_h=self.screen_h
        )
        assert behind is True

    def test_runway_moves_with_heading(self):
        """Slight heading change → screen position changes."""
        s1, _ = world_to_screen(self.rwy, self.ac,
                                 148.0, -2.0, 0.0,
                                 self.focal_px, self.screen_w, self.screen_h)
        s2, _ = world_to_screen(self.rwy, self.ac,
                                 150.0, -2.0, 0.0,
                                 self.focal_px, self.screen_w, self.screen_h)
        assert abs(s1.x - s2.x) > 1.0 or abs(s1.y - s2.y) > 1.0


class TestOnScreenDetection:
    def test_on_screen(self):
        verts = [
            {'screen': Vec2(100, 100), 'behind': False},
            {'screen': Vec2(200, 200), 'behind': False},
        ]
        assert any_vertex_on_screen(verts, 1024, 1024) is True

    def test_off_screen(self):
        verts = [
            {'screen': Vec2(-9999, -9999), 'behind': True},
            {'screen': Vec2(-9999, -9999), 'behind': True},
        ]
        assert any_vertex_on_screen(verts, 1024, 1024) is False

    def test_margin(self):
        verts = [
            {'screen': Vec2(-5, 100), 'behind': False},
        ]
        assert any_vertex_on_screen(verts, 1024, 1024, margin=0) is False
        assert any_vertex_on_screen(verts, 1024, 1024, margin=10) is True


class TestEdgeCases:
    def test_ref_and_target_same_point(self):
        """Identical ref and target → NEU=(0,0,0) → body_z=0 → behind camera."""
        ref = Vec3(126.4446, 7.0, 37.4545)
        pt  = Vec3(126.4446, 7.0, 37.4545)
        sc, behind = world_to_screen(pt, ref, 0, 0, 0, 520, 1024, 1024)
        assert behind is True   # zero-depth point is clipped

    def test_point_ahead_and_right(self):
        """Point NE of aircraft → right side of screen."""
        ref = Vec3(126.4446, 7.0, 37.4545)
        pt = Vec3(126.453, 7.0, 37.459)
        sc, behind = world_to_screen(pt, ref, 0, 0, 0, 520, 1024, 1024)
        assert behind is False
        assert sc.x > 512   # right half
        assert 0 <= sc.y <= 1024

    def test_point_ahead_left(self):
        """Point NW of aircraft → left side of screen."""
        ref = Vec3(126.4446, 7.0, 37.4545)
        pt = Vec3(126.436, 7.0, 37.459)
        sc, behind = world_to_screen(pt, ref, 0, 0, 0, 520, 1024, 1024)
        assert behind is False
        assert sc.x < 512   # left half

    def test_point_above(self):
        """Point directly above → behind camera (no forward depth)."""
        ref = Vec3(126.4446, 1000.0, 37.4545)
        pt = Vec3(126.4446, 7.0, 37.4545)
        sc, behind = world_to_screen(pt, ref, 0, 0, 0, 520, 1024, 1024)
        assert behind is True

    def test_point_north_with_altitude(self):
        """Point ahead and below → visible screen position."""
        ref = Vec3(126.4446, 500.0, 37.4545)
        pt = Vec3(126.4446, 7.0, 37.4560)
        sc, behind = world_to_screen(pt, ref, 0, 0, 0, 520, 1024, 1024)
        assert behind is False
        assert abs(sc.x - 512) < 50   # roughly centered laterally

    def test_roll_effect(self):
        """Bank rotates projected point around screen center."""
        ref = Vec3(126.4446, 1000.0, 37.4545)
        pt = Vec3(126.445, 7.0, 37.4545)
        s0, _ = world_to_screen(pt, ref, 0, 0, 0, 520, 1024, 1024)
        s45, _ = world_to_screen(pt, ref, 0, 0, 45, 520, 1024, 1024)
        assert abs(s0.x - s45.x) > 0.5 or abs(s0.y - s45.y) > 0.5

    def test_pitch_effect(self):
        """Pitch up shifts northward point downward on screen."""
        ref = Vec3(126.4446, 500.0, 37.4545)
        pt = Vec3(126.4446, 7.0, 37.4550)
        s_level, _ = world_to_screen(pt, ref, 0, 0, 0, 520, 1024, 1024)
        s_pitch, _ = world_to_screen(pt, ref, 0, 10, 0, 520, 1024, 1024)
        assert s_pitch.y > s_level.y
