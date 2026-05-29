#ifndef C_HUD_RUNWAY_PROJECTION_H
#define C_HUD_RUNWAY_PROJECTION_H

// ============================================================================
//  Conformal HUD – Projection Math  |  header-only utility
//  MSFS 2024  ·  C++17
//
//  Converts 3-D world coordinates (latitude / longitude / altitude) into
//  2-D HUD screen coordinates using the current aircraft attitude and a
//  virtual-camera model.
//
//  All functions are static inline so the compiler can decide whether to
//  inline them for performance.  No heap allocations – all scratch data
//  lives on the stack or in pre-allocated g_state.runway buffers.
//
//  NO libc dependency — all math uses compiler builtins (__builtin_*)
//  which are always available in the wasm32-unknown-unknown target.
// ============================================================================

#include "module.h"

// ============================================================================
//  1.  Constants
// ============================================================================

/// Earth mean radius (metres), WGS-84.
#define PROJ_EARTH_RADIUS_M  6378137.0

/// Deg → rad.
#define PROJ_DEG2RAD(d)     ((d) * 0.017453292519943295)

/// Rad → deg.
#define PROJ_RAD2DEG(r)     ((r) * 57.29577951308232)

/// FLOAT64 quiet NaN constant  (avoids dependency on <math.h> NAN macro).
#define PROJ_F64_NAN  0.0 / 0.0

/// Small epsilon for floating-point comparisons.
#define PROJ_EPSILON 1e-12

/// Default near clipping plane distance (metres).
#define PROJ_NEAR_CLIP  0.1

/// Default far clipping plane distance (metres).
#define PROJ_FAR_CLIP   50000.0

// ============================================================================
//  2.  Built-in math wrappers  (portable across MSFS WASM toolchains)
// ============================================================================

static inline FLOAT64 proj_sqrt(FLOAT64 x) {
    return __builtin_sqrt(x);
}

static inline FLOAT64 proj_cos(FLOAT64 x) {
    return __builtin_cos(x);
}

static inline FLOAT64 proj_sin(FLOAT64 x) {
    return __builtin_sin(x);
}

static inline FLOAT64 proj_tan(FLOAT64 x) {
    return proj_sin(x) / proj_cos(x);
}

static inline FLOAT64 proj_atan2(FLOAT64 y, FLOAT64 x) {
    return __builtin_atan2(y, x);
}

static inline FLOAT64 proj_atan(FLOAT64 x) {
    return __builtin_atan(x);
}

static inline FLOAT64 proj_fabs(FLOAT64 x) {
    return __builtin_fabs(x);
}

static inline FLOAT64 proj_floor(FLOAT64 x) {
    return __builtin_floor(x);
}

static inline FLOAT64 proj_fmin(FLOAT64 a, FLOAT64 b) {
    return (a < b) ? a : b;
}

static inline FLOAT64 proj_fmax(FLOAT64 a, FLOAT64 b) {
    return (a > b) ? a : b;
}

static inline FLOAT64 proj_clamp(FLOAT64 x, FLOAT64 lo, FLOAT64 hi) {
    return (x < lo) ? lo : (x > hi) ? hi : x;
}

// ============================================================================
//  3.  Vector math (operating on our POD Vec3 / Mat4 structs)
// ============================================================================

/// Zero-fill a Vec3.
static inline Vec3 proj_vec3_zero(void) {
    const Vec3 v = { 0.0, 0.0, 0.0 };
    return v;
}

/// Create a Vec3 from components.
static inline Vec3 proj_vec3_make(FLOAT64 x, FLOAT64 y, FLOAT64 z) {
    const Vec3 v = { x, y, z };
    return v;
}

/// Add two vectors.
static inline Vec3 proj_vec3_add(Vec3 a, Vec3 b) {
    const Vec3 r = { a.x + b.x, a.y + b.y, a.z + b.z };
    return r;
}

/// Subtract b from a.
static inline Vec3 proj_vec3_sub(Vec3 a, Vec3 b) {
    const Vec3 r = { a.x - b.x, a.y - b.y, a.z - b.z };
    return r;
}

/// Scale a vector by scalar.
static inline Vec3 proj_vec3_scale(Vec3 v, FLOAT64 s) {
    const Vec3 r = { v.x * s, v.y * s, v.z * s };
    return r;
}

/// Dot product.
static inline FLOAT64 proj_vec3_dot(Vec3 a, Vec3 b) {
    return a.x * b.x + a.y * b.y + a.z * b.z;
}

/// Cross product:  a × b.
static inline Vec3 proj_vec3_cross(Vec3 a, Vec3 b) {
    const Vec3 r = {
        a.y * b.z - a.z * b.y,
        a.z * b.x - a.x * b.z,
        a.x * b.y - a.y * b.x
    };
    return r;
}

/// Magnitude (Euclidean norm).
static inline FLOAT64 proj_vec3_len(Vec3 v) {
    return proj_sqrt(proj_vec3_dot(v, v));
}

/// Normalise (safe – returns zero vector on degenerate input).
static inline Vec3 proj_vec3_normalise(Vec3 v) {
    const FLOAT64 len = proj_vec3_len(v);
    if (len < PROJ_EPSILON) {
        return proj_vec3_zero();
    }
    const FLOAT64 inv = 1.0 / len;
    const Vec3 r = { v.x * inv, v.y * inv, v.z * inv };
    return r;
}

/// Negate a vector.
static inline Vec3 proj_vec3_neg(Vec3 v) {
    const Vec3 r = { -v.x, -v.y, -v.z };
    return r;
}

// ============================================================================
//  3b.  Matrix operations
// ============================================================================

/// Identity matrix.
static inline Mat4 proj_mat4_identity(void) {
    Mat4 m = {{ 0 }};
    m.m[0]  = 1.0;
    m.m[5]  = 1.0;
    m.m[10] = 1.0;
    m.m[15] = 1.0;
    return m;
}

/// Multiply two 4×4 matrices:  out = a * b.
static inline Mat4 proj_mat4_mul(const Mat4* a, const Mat4* b) {
    Mat4 r = {{ 0 }};
    for (int col = 0; col < 4; ++col) {
        for (int row = 0; row < 4; ++row) {
            FLOAT64 sum = 0.0;
            for (int k = 0; k < 4; ++k) {
                sum += a->m[k * 4 + row] * b->m[col * 4 + k];
            }
            r.m[col * 4 + row] = sum;
        }
    }
    return r;
}

/// Create a translation matrix.
static inline Mat4 proj_mat4_translate(FLOAT64 tx, FLOAT64 ty, FLOAT64 tz) {
    Mat4 m = proj_mat4_identity();
    m.m[12] = tx;
    m.m[13] = ty;
    m.m[14] = tz;
    return m;
}

/// Create a look-at matrix (world → camera).
/// Equivalent to gluLookAt.
static inline Mat4 proj_mat4_lookat(Vec3 eye, Vec3 target, Vec3 up) {
    const Vec3 f = proj_vec3_normalise(proj_vec3_sub(target, eye));
    const Vec3 s = proj_vec3_normalise(proj_vec3_cross(f, up));
    const Vec3 u = proj_vec3_cross(s, f);

    Mat4 m = {{ 0 }};
    m.m[0]  =  s.x;
    m.m[1]  =  u.x;
    m.m[2]  = -f.x;
    m.m[3]  =  0.0;

    m.m[4]  =  s.y;
    m.m[5]  =  u.y;
    m.m[6]  = -f.y;
    m.m[7]  =  0.0;

    m.m[8]  =  s.z;
    m.m[9]  =  u.z;
    m.m[10] = -f.z;
    m.m[11] =  0.0;

    m.m[12] = -proj_vec3_dot(s, eye);
    m.m[13] = -proj_vec3_dot(u, eye);
    m.m[14] =  proj_vec3_dot(f, eye);
    m.m[15] =  1.0;

    return m;
}

/// Create a perspective projection matrix.
/// Equivalent to gluPerspective.
static inline Mat4 proj_mat4_perspective(FLOAT64 fov_y_deg,
                                          FLOAT64 aspect,
                                          FLOAT64 near_clip,
                                          FLOAT64 far_clip) {
    const FLOAT64 fov_y_rad = PROJ_DEG2RAD(fov_y_deg);
    const FLOAT64 f = 1.0 / proj_tan(fov_y_rad * 0.5);

    Mat4 m = {{ 0 }};
    m.m[0]  = f / aspect;
    m.m[5]  = f;
    m.m[10] = (far_clip + near_clip) / (near_clip - far_clip);
    m.m[11] = -1.0;
    m.m[14] = (2.0 * far_clip * near_clip) / (near_clip - far_clip);
    return m;
}

/// Create a frustum projection matrix.
static inline Mat4 proj_mat4_frustum(FLOAT64 left, FLOAT64 right,
                                      FLOAT64 bottom, FLOAT64 top,
                                      FLOAT64 near_clip, FLOAT64 far_clip) {
    const FLOAT64 rl = 1.0 / (right - left);
    const FLOAT64 tb = 1.0 / (top - bottom);
    const FLOAT64 nf = 1.0 / (near_clip - far_clip);

    Mat4 m = {{ 0 }};
    m.m[0]  = 2.0 * near_clip * rl;
    m.m[5]  = 2.0 * near_clip * tb;
    m.m[8]  = (right + left) * rl;
    m.m[9]  = (top + bottom) * tb;
    m.m[10] = (far_clip + near_clip) * nf;
    m.m[11] = -1.0;
    m.m[14] = 2.0 * far_clip * near_clip * nf;
    return m;
}

/// Transform a 3-D point by a 4×4 matrix (homogeneous divide).
static inline Vec3 proj_mat4_transform_point(const Mat4* m, Vec3 p) {
    const FLOAT64 x = m->m[0] * p.x + m->m[4] * p.y + m->m[8]  * p.z + m->m[12];
    const FLOAT64 y = m->m[1] * p.x + m->m[5] * p.y + m->m[9]  * p.z + m->m[13];
    const FLOAT64 z = m->m[2] * p.x + m->m[6] * p.y + m->m[10] * p.z + m->m[14];
    const FLOAT64 w = m->m[3] * p.x + m->m[7] * p.y + m->m[11] * p.z + m->m[15];
    if (proj_fabs(w) < PROJ_EPSILON) {
        return proj_vec3_zero();
    }
    const Vec3 r = { x / w, y / w, z / w };
    return r;
}

// ============================================================================
//  4.  Coordinate transforms
// ============================================================================

/// Convert a lat/lon/alt point to a local North-East-Up (NEU) Cartesian
/// frame centred at the given reference point (aircraft position).
///
/// @param point_world   World point in (lon_deg, alt_m, lat_deg).
/// @param ref_world     Reference point (aircraft) in (lon_deg, alt_m, lat_deg).
/// @param out_neu       [out] North-East-Up offset in metres (east, up, north).
static inline void proj_world_to_neu(Vec3  point_world,
                                     Vec3  ref_world,
                                     Vec3* out_neu) {
    if (out_neu == 0) { return; }

    const FLOAT64 lat_ref  = PROJ_DEG2RAD(ref_world.z);
    const FLOAT64 lon_ref  = PROJ_DEG2RAD(ref_world.x);
    const FLOAT64 lat_pt   = PROJ_DEG2RAD(point_world.z);
    const FLOAT64 lon_pt   = PROJ_DEG2RAD(point_world.x);

    const FLOAT64 dlat     = lat_pt - lat_ref;
    const FLOAT64 dlon     = lon_pt - lon_ref;

    // Flat-Earth approximation (valid for < 100 km; sufficient for ILS
    // final approach).
    const FLOAT64 cos_lat  = proj_cos(lat_ref);
    const FLOAT64 north_m  = dlat * PROJ_EARTH_RADIUS_M;
    const FLOAT64 east_m   = dlon * PROJ_EARTH_RADIUS_M * cos_lat;
    const FLOAT64 up_m     = point_world.y - ref_world.y;

    out_neu->x = east_m;
    out_neu->y = up_m;
    out_neu->z = north_m;
}

/// Convert a world-space heading/bearing to a unit direction vector in NEU.
/// heading_deg: true heading (0 = north, 90 = east).
static inline Vec3 proj_heading_to_vec3(FLOAT64 heading_deg) {
    const FLOAT64 h = PROJ_DEG2RAD(heading_deg);
    // NEU: East = sin(h), North = cos(h), Up = 0
    const Vec3 v = { proj_sin(h), 0.0, proj_cos(h) };
    return v;
}

/// Build a 3×3 rotation matrix from aircraft heading (ψ), pitch (θ), and
/// bank (φ) — standard aerospace ZYX Euler convention:
///
///   R = Rz(-ψ) · Ry(-θ) · Rx(-φ)      (body → world)
///
/// We store the transpose (world → body) in the output matrix so a
/// world-space vector post-multiplied by out_b2w gives body-frame coords.
///
/// @param heading_deg   True heading (0 = north, 90 = east).
/// @param pitch_deg     Pitch angle (positive = nose up).
/// @param bank_deg      Bank angle (positive = right wing down).
/// @param out_b2w       [out] 3×3 body-to-world rotation (column-major 4×4).
static inline void proj_attitude_to_matrix(FLOAT64 heading_deg,
                                           FLOAT64 pitch_deg,
                                           FLOAT64 bank_deg,
                                           Mat4*   out_b2w) {
    if (out_b2w == 0) { return; }

    const FLOAT64 h = PROJ_DEG2RAD(heading_deg);
    const FLOAT64 p = PROJ_DEG2RAD(pitch_deg);
    const FLOAT64 b = PROJ_DEG2RAD(bank_deg);

    const FLOAT64 ch = proj_cos(h), sh = proj_sin(h);
    const FLOAT64 cp = proj_cos(p), sp = proj_sin(p);
    const FLOAT64 cb = proj_cos(b), sb = proj_sin(b);

    // R_body2world = Rz(-h) * Ry(-p) * Rx(-b)
    //
    // Column-major layout (OpenGL convention):
    //   m[0] m[4]  m[8]  m[12]
    //   m[1] m[5]  m[9]  m[13]
    //   m[2] m[6]  m[10] m[14]
    //   m[3] m[7]  m[11] m[15]    (m[3]=m[7]=m[11]=0, m[15]=1)

    out_b2w->m[0]  =  ch * cp;
    out_b2w->m[1]  =  sh * cp;
    out_b2w->m[2]  = -sp;
    out_b2w->m[3]  =  0.0;

    out_b2w->m[4]  = -sh * cb + ch * sp * sb;
    out_b2w->m[5]  =  ch * cb + sh * sp * sb;
    out_b2w->m[6]  =  cp * sb;
    out_b2w->m[7]  =  0.0;

    out_b2w->m[8]  =  sh * sb + ch * sp * cb;
    out_b2w->m[9]  = -ch * sb + sh * sp * cb;
    out_b2w->m[10] =  cp * cb;
    out_b2w->m[11] =  0.0;

    out_b2w->m[12] =  0.0;
    out_b2w->m[13] =  0.0;
    out_b2w->m[14] =  0.0;
    out_b2w->m[15] =  1.0;
}

/// Transform a world-space NEU vector by the body-to-world rotation matrix.
/// Equivalent to  v_body = R_world2body * v_world.
///
/// @param v_world   World-space vector (NEU metres).
/// @param b2w       Body-to-world rotation matrix.
/// @returns         Vector in aircraft body coordinates.
static inline Vec3 proj_transform_by_attitude(Vec3 v_world, const Mat4* b2w) {
    const FLOAT64* m = b2w->m;
    const Vec3 r = {
        m[0] * v_world.x + m[1] * v_world.y + m[2] * v_world.z,
        m[4] * v_world.x + m[5] * v_world.y + m[6] * v_world.z,
        m[8] * v_world.x + m[9] * v_world.y + m[10]* v_world.z
    };
    return r;
}

/// Perspective projection: map a 3-D body-frame point onto the HUD screen.
///
/// Uses a simple pinhole-camera model with the virtual image plane at
/// distance 'focal_px' from the camera node.  Points behind the camera
/// (z_body <= near_clip) are flagged via out_behind.
///
/// @param pt_body      Point in aircraft body frame (metres).
/// @param focal_px     Focal length in pixels (determines FOV).
/// @param screen_w     HUD pixel width.
/// @param screen_h     HUD pixel height.
/// @param near_clip    Near clipping plane distance (metres).
/// @param out_behind   [out] True if point is behind the camera.
/// @returns            Screen-space (x, y) in pixels, origin at top-left.
static inline Vec2 proj_perspective(Vec3    pt_body,
                                    FLOAT64 focal_px,
                                    int     screen_w,
                                    int     screen_h,
                                    FLOAT64 near_clip,
                                    bool*   out_behind) {
    const FLOAT64 cx = (FLOAT64)(screen_w / 2);
    const FLOAT64 cy = (FLOAT64)(screen_h / 2);

    if (out_behind != 0) {
        *out_behind = false;
    }

    // Behind near plane → clip
    if (pt_body.z <= near_clip) {
        if (out_behind != 0) {
            *out_behind = true;
        }
        const Vec2 off = { -9999.0, -9999.0 };
        return off;
    }

    const FLOAT64 inv_z = 1.0 / pt_body.z;
    const Vec2 r = {
        cx + focal_px * pt_body.x * inv_z,
        cy - focal_px * pt_body.y * inv_z  // Y-down screen convention
    };
    return r;
}

/// Perspective project using a full 4×4 projection matrix (NDC coords).
/// Returns screen-space (x, y) in pixels, origin at top-left.
static inline Vec2 proj_perspective_matrix(Vec3    pt_body,
                                           const Mat4* view_proj,
                                           int     screen_w,
                                           int     screen_h,
                                           bool*   out_behind) {
    if (out_behind != 0) {
        *out_behind = false;
    }

    // Transform to clip space
    const Vec3 clip = proj_mat4_transform_point(view_proj, pt_body);

    // Check if behind near plane
    if (clip.z < -1.0 || clip.z > 1.0) {
        if (out_behind != 0) {
            *out_behind = true;
        }
        const Vec2 off = { -9999.0, -9999.0 };
        return off;
    }

    // NDC to screen
    const FLOAT64 sx = (clip.x + 1.0) * 0.5 * (FLOAT64)screen_w;
    const FLOAT64 sy = (1.0 - clip.y) * 0.5 * (FLOAT64)screen_h; // Y-down

    const Vec2 r = { sx, sy };
    return r;
}

// ============================================================================
//  5.  High-level projection pipeline
// ============================================================================

/// Project a single world-space runway vertex onto the HUD screen in one call.
/// Combines world→NEU, attitude transform, and perspective projection.
///
/// @param world_pt       Target vertex in (lon_deg, alt_m, lat_deg).
/// @param ref_pt         Aircraft position (lon_deg, alt_m, lat_deg).
/// @param heading_deg    Aircraft true heading.
/// @param pitch_deg      Aircraft pitch.
/// @param bank_deg       Aircraft bank.
/// @param focal_px       Virtual-camera focal length (pixels).
/// @param screen_w       HUD pixel width.
/// @param screen_h       HUD pixel height.
/// @param out_screen     [out] Screen-space position (pixels).
/// @param out_behind     [out] True if vertex is behind the camera.
static inline void proj_world_to_screen(Vec3    world_pt,
                                        Vec3    ref_pt,
                                        FLOAT64 heading_deg,
                                        FLOAT64 pitch_deg,
                                        FLOAT64 bank_deg,
                                        FLOAT64 focal_px,
                                        int     screen_w,
                                        int     screen_h,
                                        Vec2*   out_screen,
                                        bool*   out_behind) {
    if (out_screen == 0) { return; }

    // (a) World → NEU metres
    Vec3 neu = proj_vec3_zero();
    proj_world_to_neu(world_pt, ref_pt, &neu);

    // (b) Build aircraft attitude rotation
    Mat4 b2w = {{ 0 }};
    proj_attitude_to_matrix(heading_deg, pitch_deg, bank_deg, &b2w);

    // (c) NEU → body frame
    const Vec3 body = proj_transform_by_attitude(neu, &b2w);

    // (d) Perspective projection → screen pixels
    *out_screen = proj_perspective(body, focal_px, screen_w, screen_h,
                                    0.1, out_behind);
}

/// Full camera-aware projection: world → NEU → body → camera → clip → screen.
/// Uses eye offset from HUD design eye point.
///
/// @param world_pt       World point (lon_deg, alt_m, lat_deg)
/// @param ref_pt         Aircraft reference (lon_deg, alt_m, lat_deg)
/// @param b2w            Body-to-world attitude matrix
/// @param eye_offset     HUD eye offset in body frame (forward, right, down)
/// @param focal_px       Focal length in pixels
/// @param screen_w       Screen width
/// @param screen_h       Screen height
/// @param out_screen     [out] Screen-space position
/// @param out_behind     [out] True if behind camera
static inline void proj_world_to_hud(Vec3          world_pt,
                                     Vec3          ref_pt,
                                     const Mat4*   b2w,
                                     Vec3          eye_offset,
                                     FLOAT64       focal_px,
                                     int           screen_w,
                                     int           screen_h,
                                     Vec2*         out_screen,
                                     bool*         out_behind) {
    if (out_screen == 0 || b2w == 0) { return; }

    // (a) World → NEU metres
    Vec3 neu = proj_vec3_zero();
    proj_world_to_neu(world_pt, ref_pt, &neu);

    // (b) NEU → body frame
    Vec3 body = proj_transform_by_attitude(neu, b2w);

    // (c) Apply eye offset (shift origin to HUD design eye point)
    //     Eye offset is in body frame; we subtract it to get position
    //     relative to the HUD eye.
    body = proj_vec3_sub(body, eye_offset);

    // (d) Perspective projection → screen pixels
    *out_screen = proj_perspective(body, focal_px, screen_w, screen_h,
                                    0.1, out_behind);
}

/// Project an infinite horizon point (perpendicular to aircraft heading).
/// Returns the projected screen y-coordinate for the horizon line.
static inline FLOAT64 proj_project_horizon_y(FLOAT64 pitch_deg,
                                              FLOAT64 focal_px,
                                              int     screen_h) {
    // The horizon in body frame: a point far ahead at pitch altitude.
    // At pitch=0, horizon is at screen vertical center.
    // As pitch increases, horizon moves down.
    const FLOAT64 p_rad = PROJ_DEG2RAD(pitch_deg);
    const FLOAT64 horizon_y = (FLOAT64)(screen_h / 2) -
                               focal_px * proj_tan(p_rad);
    return horizon_y;
}

// ============================================================================
//  6.  Bounding-box test helper  (for JS overlay culling)
// ============================================================================

/// Returns true if any vertex of the runway projects on-screen within the
/// given pixel bounds (with a margin).  Useful for the HTML/JS overlay to
/// skip drawing when the runway is entirely off-screen.
static inline bool proj_any_vertex_on_screen(const RunwayGeometry* rwy,
                                              int screen_w,
                                              int screen_h,
                                              int margin_px) {
    if (rwy == 0 || !rwy->valid) return false;

    for (int i = 0; i < rwy->vert_count; ++i) {
        const RunwayVertex* rv = &rwy->verts[i];
        if (rv->behind_camera) continue;
        const FLOAT64 sx = rv->screen_pos.x;
        const FLOAT64 sy = rv->screen_pos.y;
        if (sx >= -margin_px && sx < (FLOAT64)(screen_w + margin_px) &&
            sy >= -margin_px && sy < (FLOAT64)(screen_h + margin_px)) {
            return true;
        }
    }
    return false;
}

// ============================================================================
//  7.  Debug helpers
// ============================================================================

/// Log a matrix for debugging.
static inline void proj_debug_matrix(const char* label, const Mat4* m) {
    if (m == 0) return;
    MSFS_Log("[C_HUD_PROJ] %s:\n"
             "  [%.4f %.4f %.4f %.4f]\n"
             "  [%.4f %.4f %.4f %.4f]\n"
             "  [%.4f %.4f %.4f %.4f]\n"
             "  [%.4f %.4f %.4f %.4f]",
             label,
             m->m[0], m->m[4], m->m[8],  m->m[12],
             m->m[1], m->m[5], m->m[9],  m->m[13],
             m->m[2], m->m[6], m->m[10], m->m[14],
             m->m[3], m->m[7], m->m[11], m->m[15]);
}

/// Log a Vec3 for debugging.
static inline void proj_debug_vec3(const char* label, Vec3 v) {
    MSFS_Log("[C_HUD_PROJ] %s: (%.6f, %.6f, %.6f)", label, v.x, v.y, v.z);
}

#endif  // C_HUD_RUNWAY_PROJECTION_H
