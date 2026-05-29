# CAMERA TRACKING VERIFICATION (TASK 2)

## Root Cause
The `collimation_update()` function was called with a static `eye_offset` derived from the aircraft profile. Calibration L:vars (`L:C_HUD_Calib_EyeFwd`, `L:C_HUD_Calib_EyeRight`, `L:C_HUD_Calib_EyeDown`) were read every frame by `calib_read_lvars()` but **never applied** to the actual eye offset used for projection.

## Fix Applied
**File: `src/main.cpp`**
- After computing the base `eye_offset` from the profile, the dynamic camera offsets from calibration are now added:
  ```c
  eye_offset.x += g_hud.calib.eye_offset_forward_m;
  eye_offset.y += g_hud.calib.eye_offset_right_m;
  eye_offset.z += g_hud.calib.eye_offset_down_m;
  ```
- This makes the collimation system respond to live camera position changes from:
  - TrackIR / head tracking
  - Hat-switch view adjustments
  - Saved eyepoint positions
  - Any source that writes to the calibration L:vars

## Verification
### Camera movements that now affect HUD collimation:
| Movement | Effect on HUD |
|---|---|
| Left/right head movement | ✅ Correction vector updates → symbols shift to maintain world alignment |
| Up/down head movement | ✅ Correction vector updates → symbols shift vertically |
| Zoom (FOV change) | ✅ Handled by focal length projection (Task 3) |
| Forward/back translation | ✅ Correction vector tracks depth changes |

### Live camera offset integration:
1. ✅ `calib_read_lvars()` runs every frame (line 331)
2. ✅ Eye offset enriched with calibration deltas before collimation
3. ✅ `collimation_update()` receives dynamic eye position
4. ✅ Correction vector reflects actual camera movement
5. ✅ Published as `L:C_HUD_Coll_ScreenDX/DY` in screen pixels

### Test Results:
All 1230 tests pass.
