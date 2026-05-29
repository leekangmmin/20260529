// ============================================================================
//  Conformal HUD – Combiner Glass Geometry Implementation
//  MSFS 2024  ·  C++17  ·  WASM
//
//  PHASE 4 — REAL HUD INTEGRATION
//
//  Implements the combiner geometry update logic that translates panel-
//  space combiner rectangles (from aircraft profiles) into screen-space
//  coordinates accounting for viewport size and scaling.
// ============================================================================

#include "hud/combiner_geometry.h"

// ============================================================================
//  1.  Update combiner geometry from profile and screen size
// ============================================================================

void combiner_geometry_update(CombinerGeometry* cg,
                               const HUDProfile* profile,
                               int               screen_w,
                               int               screen_h) {
    if (cg == 0) return;

    // Default fallback: centre half of screen
    if (profile == 0) {
        cg->panel_x = 150;
        cg->panel_y = 250;
        cg->panel_w = 724;
        cg->panel_h = 524;

        // Scale: assume panel is 1024x1024, map to screen centre
        cg->scale_x = (FLOAT64)screen_w / 1024.0;
        cg->scale_y = (FLOAT64)screen_h / 1024.0;

        cg->screen_x = 0.0;
        cg->screen_y = 0.0;
        cg->screen_w = (FLOAT64)screen_w;
        cg->screen_h = (FLOAT64)screen_h;

        cg->optical_cx = (FLOAT64)screen_w * 0.5;
        cg->optical_cy = (FLOAT64)screen_h * 0.5;

        cg->valid = false;
        cg->profile_available = false;
        return;
    }

    // Read combiner rect from profile
    cg->panel_x = profile->combiner.x;
    cg->panel_y = profile->combiner.y;
    cg->panel_w = profile->combiner.width;
    cg->panel_h = profile->combiner.height;

    // Compute panel-to-screen scale
    // The panel coordinate system is 1024x1024, mapping to the full viewport
    cg->scale_x = (FLOAT64)screen_w / 1024.0;
    cg->scale_y = (FLOAT64)screen_h / 1024.0;

    // Scale the combiner rectangle to screen space
    cg->screen_x = (FLOAT64)cg->panel_x * cg->scale_x;
    cg->screen_y = (FLOAT64)cg->panel_y * cg->scale_y;
    cg->screen_w = (FLOAT64)cg->panel_w * cg->scale_x;
    cg->screen_h = (FLOAT64)cg->panel_h * cg->scale_y;

    // Compute optical centre in screen space
    // Use profile optical centre offsets if available
    cg->optical_cx = (cg->screen_x + cg->screen_w * 0.5)
                     + (profile->optical_center_offset_x * cg->scale_x);
    cg->optical_cy = (cg->screen_y + cg->screen_h * 0.5)
                     + (profile->optical_center_offset_y * cg->scale_y);

    // Validate combiner dimensions
    if (cg->panel_w > 0 && cg->panel_h > 0 &&
        cg->screen_w > 0.0 && cg->screen_h > 0.0) {
        cg->valid = true;
    } else {
        cg->valid = false;
    }

    cg->profile_available = true;
}

// ============================================================================
//  2.  Validation
// ============================================================================

bool combiner_geometry_validate(const CombinerGeometry* cg) {
    if (cg == 0) return false;

    // Check that all dimensions are positive and finite
    if (cg->panel_w <= 0 || cg->panel_h <= 0) return false;
    if (cg->screen_w <= 0.0 || cg->screen_h <= 0.0) return false;

    // Check scale factors are positive and finite
    if (cg->scale_x <= 0.0 || cg->scale_x > 10.0) return false;
    if (cg->scale_y <= 0.0 || cg->scale_y > 10.0) return false;

    // Check that screen rect is within reasonable bounds
    if (cg->screen_x < -100.0 || cg->screen_x > 10000.0) return false;
    if (cg->screen_y < -100.0 || cg->screen_y > 10000.0) return false;

    // Check optical centre is within screen bounds
    if (cg->optical_cx < 0.0 || cg->optical_cx > 10000.0) return false;
    if (cg->optical_cy < 0.0 || cg->optical_cy > 10000.0) return false;

    return true;
}
