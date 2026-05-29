#ifndef C_HUD_RUNWAY_PROJECTION_ENGINE_H
#define C_HUD_RUNWAY_PROJECTION_ENGINE_H

// ============================================================================
//  Conformal HUD – Runway Projection Engine
//  MSFS 2024  ·  C++17  ·  WASM
//
//  Computes world-space runway corner coordinates from ILS frequency,
//  projects them into HUD combiner coordinates, and maintains stable
//  conformal alignment during approach.
//
//  RESPONSIBILITIES:
//    · Active runway selection from ILS frequency / airport data
//    · Runway corner computation (threshold + far end + width)
//    · World → NEU → Body → HUD projection pipeline
//    · Conformal alignment stability during aircraft motion
//    · Debug logging of all projection stages
//
//  v2.2.0 additions:
//    · Database-integrated runway detection (runway_detect_active_db)
//    · Displaced threshold support (runway_compute_end_from_record)
//    · Backward-compatible with existing callers
// ============================================================================

#include "../module.h"
#include "../projection.h"
#include "aircraft_profiles.h"

// Forward declaration for airport database integration
struct AirportDatabase;
struct RunwayRecord;

// ============================================================================
//  1.  Runway data structures
// ============================================================================

/// Maximum number of runway vertices.
#define PROJ_MAX_RUNWAY_VERTS  16

/// Full description of a single runway end (threshold + far end).
typedef struct RunwayEnd {
    Vec3 threshold;         // (lon_deg, alt_m, lat_deg) – threshold position
    Vec3 far_end;           // (lon_deg, alt_m, lat_deg) – opposite end
    FLOAT64 true_heading;   // runway true heading (degrees)
    FLOAT64 width_m;        // runway width (metres)
    bool    valid;          // true if data is populated
} RunwayEnd;

/// Complete runway geometry with left/right edge vertices.
typedef struct RunwayCorners {
    Vec3 verts[8];          // up to 8 vertices (4 for basic, 8 for extended)
    int   vert_count;       // number of valid vertices
    bool  valid;            // true after computation
} RunwayCorners;

/// Extended runway geometry with conformal projection results.
typedef struct ProjectedRunway {
    RunwayEnd   end;                // the active runway end
    RunwayCorners corners;          // world-space corner vertices
    Vec2        screen_corners[8];  // projected 2-D screen positions
    bool        behind[8];          // behind-camera flags
    int         visible_count;      // number of on-screen vertices
    bool        valid;              // true after successful projection
} ProjectedRunway;

// ============================================================================
//  2.  ILS frequency → runway selection
// ============================================================================

/// Extract ILS frequency from NAV radio.
/// Returns the tuned frequency in MHz, or 0.0 if not tuned.
FLOAT64 runway_get_ils_frequency(void);

// ============================================================================
//  3.  Runway geometry computation
// ============================================================================

/// Build runway corner vertices from runway end data.
/// Creates 4 corners: near-left, far-left, far-right, near-right.
///
/// @param end         Runway end data (threshold, far end, width, heading)
/// @param out_corners [out] 4 or 8 corner vertices
void runway_compute_corners(const RunwayEnd* end, RunwayCorners* out_corners);

/// Compute world-space position of runway threshold from lat/lon/alt.
static inline Vec3 runway_make_position(FLOAT64 lon_deg,
                                         FLOAT64 lat_deg,
                                         FLOAT64 alt_m) {
    const Vec3 p = { lon_deg, alt_m, lat_deg };
    return p;
}

// ============================================================================
//  4.  Conformal projection pipeline
// ============================================================================

/// Project runway corners into HUD screen coordinates.
///
/// @param corners     World-space corner vertices
/// @param ac_ref      Aircraft position (lon_deg, alt_m, lat_deg)
/// @param b2w         Body-to-world rotation matrix (from attitude)
/// @param eye_offset  HUD eye offset (body frame)
/// @param focal_px    Focal length in pixels
/// @param screen_w    Screen width
/// @param screen_h    Screen height
/// @param out_proj    [out] Projected runway screen coordinates and flags
void runway_project_to_hud(const RunwayCorners* corners,
                            Vec3                  ac_ref,
                            const Mat4*           b2w,
                            Vec3                  eye_offset,
                            FLOAT64               focal_px,
                            int                   screen_w,
                            int                   screen_h,
                            ProjectedRunway*      out_proj);

/// Project a single world point to HUD screen.
/// Returns screen position and sets behind flag.
static inline Vec2 runway_world_to_hud(Vec3    world_pt,
                                        Vec3    ac_ref,
                                        const Mat4* b2w,
                                        Vec3    eye_offset,
                                        FLOAT64 focal_px,
                                        int     screen_w,
                                        int     screen_h,
                                        bool*   out_behind) {
    Vec2 screen = { 0.0, 0.0 };
    proj_world_to_hud(world_pt, ac_ref, b2w, eye_offset,
                       focal_px, screen_w, screen_h,
                       &screen, out_behind);
    return screen;
}

// ============================================================================
//  5.  Active runway auto-detection
// ============================================================================

/// Attempt to determine the active runway from the aircraft's NAV1/NAV2
/// ILS frequency.  Returns true if runway data was populated.
///
/// This is a placeholder that uses a lookup table of well-known airports.
/// In production, this should query the MSFS airport facilities API.
bool runway_detect_active(RunwayEnd* out_end);

// ============================================================================
//  6.  Debug logging
// ============================================================================

/// Log the current runway state for debugging.
void runway_debug_log(const ProjectedRunway* proj);

// ============================================================================
//  7.  Phase 1 – Database-integrated runway queries
//
//  These functions augment the existing runway_detect_active() with
//  the global airport/runway database.  They preserve backward
//  compatibility – existing callers continue to work unchanged.
// ============================================================================

/// Detect the active runway using the full airport database.
///
/// Tries (in order):
///   1. ILS frequency lookup via db_find_by_ils_freq()
///   2. Nearest-airport + heading alignment
///   3. Falls back to the legacy runway_detect_active() if all fail
///
/// @param db           Initialised airport database
/// @param ac_lat_deg   Aircraft latitude
/// @param ac_lon_deg   Aircraft longitude
/// @param ac_hdg_true  Aircraft true heading (degrees)
/// @param ils_freq_mhz Tuned ILS frequency (0.0 if unknown)
/// @param out_end      [out] Populated RunwayEnd for projection
/// @return             true if a valid runway was detected
// [DEPRECATED in v2.7.0 - not called from production code]
bool runway_detect_active_db(struct AirportDatabase* db,
                              FLOAT64 ac_lat_deg,
                              FLOAT64 ac_lon_deg,
                              FLOAT64 ac_hdg_true,
                              FLOAT64 ils_freq_mhz,
                              RunwayEnd* out_end);

/// Project runway corners with displaced threshold support.
///
/// Handles displaced thresholds properly by shifting the threshold
/// position before computing corners.
///
/// @param rwy          Runway record from the database
/// @param use_reciprocal  If true, use the reciprocal runway end
/// @param out_end      [out] RunwayEnd with corrected threshold
/// @return             true if geometry was computed successfully
bool runway_compute_end_from_record(const struct RunwayRecord* rwy,
                                     bool use_reciprocal,
                                     RunwayEnd* out_end);

#endif // C_HUD_RUNWAY_PROJECTION_ENGINE_H
