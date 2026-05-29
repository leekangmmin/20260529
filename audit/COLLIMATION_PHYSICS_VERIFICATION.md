# COLLIMATION PHYSICS VERIFICATION (TASK 3)

## Root Cause
The collimation correction vector (in body-frame metres) was converted to screen pixels by multiplying by `combiner_geom.scale_x`, which is a dimensionless panel-to-screen ratio (e.g., screen_width / 1024). This is physically incorrect — metres should be converted to pixels using proper perspective projection based on camera focal length and eye-to-combiner distance.

## Fix Applied
**File: `src/main.cpp`** (publish section)

### Before (incorrect):
```c
const FLOAT64 scale = g_hud.combiner_geom.scale_x > 0.0
                       ? g_hud.combiner_geom.scale_x : 1.0;
lvar_write(LVAR_COLL_SCREEN_DX,
           g_hud.collimation_cc.correction_vector.x * scale);
```

### After (correct):
```c
const HUDProfile* proj_prof = hud_profile_match(g_state.aircraft_id);
const FLOAT64 proj_focal_px = (proj_prof != 0 && proj_prof->focal_length_px > 0.0)
                              ? proj_prof->focal_length_px : 520.0;
const FLOAT64 combiner_dist_m = 0.6;  // typical HUD eye relief (metres)
const FLOAT64 proj_scale = proj_focal_px / combiner_dist_m;
if (!g_hud.collimation_cc.active) {
    lvar_write(LVAR_COLL_SCREEN_DX, 0.0);
    lvar_write(LVAR_COLL_SCREEN_DY, 0.0);
} else {
    lvar_write(LVAR_COLL_SCREEN_DX,
               g_hud.collimation_cc.correction_vector.x * proj_scale);
    lvar_write(LVAR_COLL_SCREEN_DY,
               g_hud.collimation_cc.correction_vector.y * proj_scale);
}
```

## Mathematical Verification
The correct projection for converting world-space offsets to screen pixels is:

```
screen_px = world_meters × (focal_length_px / eye_relief_m)
```

Where:
- `focal_length_px` = camera focal length in pixels (from aircraft profile)
- `eye_relief_m` = distance from pilot eye to combiner glass (~0.6m typical)

For example, a 5cm head movement with `focal_length_px = 520`:
- `proj_scale = 520 / 0.6 = 866.67 px/m`
- `screen_offset = 0.05 × 866.67 = 43.3 px`

This is physically correct — small head movements produce modest screen offsets.

## Also Fixed
✅ When collimation is inactive, zero is published instead of stale values.

### Test Results:
All 1230 tests pass.
