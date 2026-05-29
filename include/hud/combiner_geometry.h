#ifndef C_HUD_COMBINER_GEOMETRY_H
#define C_HUD_COMBINER_GEOMETRY_H

// ============================================================================
//  Conformal HUD – Combiner Glass Geometry Management
//  MSFS 2024  ·  C++17  ·  WASM
//
//  PHASE 4 — REAL HUD INTEGRATION
//
//  Manages the HUD combiner glass geometry and provides:
//    1. Combiner clipping rectangle (from aircraft profile)
//    2. Dynamic combiner position tracking (for animated HUDs)
//    3. Screen-space to combiner-space coordinate conversion
//    4. Viewport-relative combiner positioning
//    5. FOV-dependent combinator scaling
//
//  Symbology must only render inside the combiner glass area.  This
//  module provides the geometry that the JS renderer uses for clipping.
// ============================================================================

#include "../module.h"
#include "aircraft_profiles.h"

// ============================================================================
//  1.  Combiner geometry state
// ============================================================================

/// Full combiner geometry state for the current frame.
typedef struct CombinerGeometry {
    // --- Combiner rectangle in panel coordinates (1024x1024 space) ---
    int     panel_x;
    int     panel_y;
    int     panel_w;
    int     panel_h;

    // --- Screen-space combiner rect (scaled to current viewport) ---
    FLOAT64 screen_x;           // Left edge in screen pixels
    FLOAT64 screen_y;           // Top edge in screen pixels
    FLOAT64 screen_w;           // Width in screen pixels
    FLOAT64 screen_h;           // Height in screen pixels

    // --- Scale factors ---
    FLOAT64 scale_x;            // Panel-to-screen horizontal scale
    FLOAT64 scale_y;            // Panel-to-screen vertical scale

    // --- Combiner optical centre (screen space) ---
    FLOAT64 optical_cx;         // Optical centre X (screen pixels)
    FLOAT64 optical_cy;         // Optical centre Y (screen pixels)

    // --- Validity ---
    bool    valid;
    bool    profile_available;
} CombinerGeometry;

// ============================================================================
//  2.  Screen configuration
// ============================================================================

/// Screen/viewport dimensions.
typedef struct ScreenConfig {
    int     width;              // Screen width in pixels
    int     height;             // Screen height in pixels
    FLOAT64 panel_to_screen_x;  // Panel-to-screen scale X
    FLOAT64 panel_to_screen_y;  // Panel-to-screen scale Y
    bool    valid;
} ScreenConfig;

// ============================================================================
//  3.  Initialisation
// ============================================================================

/// Initialise combiner geometry to default (fallback) values.
///
/// @param cg   [out] Combiner geometry to initialise
static inline void combiner_geometry_init(CombinerGeometry* cg) {
    if (cg == 0) return;
    cg->panel_x = 150;
    cg->panel_y = 250;
    cg->panel_w = 724;
    cg->panel_h = 524;

    cg->screen_x   = 0.0;
    cg->screen_y   = 0.0;
    cg->screen_w   = 724.0;
    cg->screen_h   = 524.0;

    cg->scale_x = 1.0;
    cg->scale_y = 1.0;

    cg->optical_cx = 512.0;
    cg->optical_cy = 512.0;

    cg->valid = false;
    cg->profile_available = false;
}

// ============================================================================
//  4.  Per-frame update
// ============================================================================

/// Update combiner geometry from current aircraft profile and screen size.
///
/// @param cg          [in/out] Combiner geometry state
/// @param profile     Current aircraft HUD profile
/// @param screen_w    Current viewport width
/// @param screen_h    Current viewport height
void combiner_geometry_update(CombinerGeometry* cg,
                               const HUDProfile* profile,
                               int               screen_w,
                               int               screen_h);

// ============================================================================
//  5.  Coordinate conversion helpers
// ============================================================================

/// Convert a panel coordinate (1024x1024) to screen space.
///
/// @param cg      Combiner geometry
/// @param px      Panel X coordinate
/// @param py      Panel Y coordinate
/// @param out_sx  [out] Screen X coordinate
/// @param out_sy  [out] Screen Y coordinate
static inline void combiner_panel_to_screen(const CombinerGeometry* cg,
                                             FLOAT64 px, FLOAT64 py,
                                             FLOAT64* out_sx,
                                             FLOAT64* out_sy) {
    if (cg == 0 || out_sx == 0 || out_sy == 0) return;

    // First, compute position relative to combiner origin in panel space
    const FLOAT64 rel_x = px - (FLOAT64)cg->panel_x;
    const FLOAT64 rel_y = py - (FLOAT64)cg->panel_y;

    // Scale to screen space and offset to screen combiner origin
    *out_sx = cg->screen_x + rel_x * cg->scale_x;
    *out_sy = cg->screen_y + rel_y * cg->scale_y;
}

/// Convert a screen coordinate back to panel space.
///
/// @param cg      Combiner geometry
/// @param sx      Screen X coordinate
/// @param sy      Screen Y coordinate
/// @param out_px  [out] Panel X coordinate
/// @param out_py  [out] Panel Y coordinate
static inline void combiner_screen_to_panel(const CombinerGeometry* cg,
                                             FLOAT64 sx, FLOAT64 sy,
                                             FLOAT64* out_px,
                                             FLOAT64* out_py) {
    if (cg == 0 || out_px == 0 || out_py == 0) return;

    const FLOAT64 rel_x = (sx - cg->screen_x) / cg->scale_x;
    const FLOAT64 rel_y = (sy - cg->screen_y) / cg->scale_y;

    *out_px = (FLOAT64)cg->panel_x + rel_x;
    *out_py = (FLOAT64)cg->panel_y + rel_y;
}

/// Check if a screen-space point is within the combiner region.
///
/// @param cg       Combiner geometry
/// @param sx       Screen X coordinate
/// @param sy       Screen Y coordinate
/// @param margin   Extra margin (pixels) to include around the combiner
/// @return         True if the point is within the combiner (+ margin)
static inline bool combiner_contains_point(const CombinerGeometry* cg,
                                            FLOAT64 sx, FLOAT64 sy,
                                            FLOAT64 margin) {
    if (cg == 0 || !cg->valid) return true;  // No combiner = no clipping
    return (sx >= cg->screen_x - margin &&
            sx <= cg->screen_x + cg->screen_w + margin &&
            sy >= cg->screen_y - margin &&
            sy <= cg->screen_y + cg->screen_h + margin);
}

/// Get the combiner rectangle in screen space as a simple struct returned by value.
typedef struct CombinerScreenRect {
    FLOAT64 x;
    FLOAT64 y;
    FLOAT64 w;
    FLOAT64 h;
} CombinerScreenRect;

static inline CombinerScreenRect combiner_screen_rect(const CombinerGeometry* cg) {
    CombinerScreenRect r = { 0, 0, 0, 0 };
    if (cg == 0 || !cg->valid) return r;
    r.x = cg->screen_x;
    r.y = cg->screen_y;
    r.w = cg->screen_w;
    r.h = cg->screen_h;
    return r;
}

// ============================================================================
//  6.  Debug validation
// ============================================================================

/// Validate combiner geometry for consistency.
///
/// @param cg   Combiner geometry to validate
/// @return     True if geometry is valid and self-consistent
bool combiner_geometry_validate(const CombinerGeometry* cg);

#endif // C_HUD_COMBINER_GEOMETRY_H
