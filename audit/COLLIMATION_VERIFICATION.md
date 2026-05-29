# Collimation Verification
## Phase 5 — Semi-Collimated Rendering Correctness

**Date:** 2025-01-XX  
**Auditor:** DeepSeek Senior Avionics Engineer  
**Methodology:** Full code path trace from camera offset delta → screen pixel compensation

---

## 1. Theory of Operation

A real HGS combiner uses collimating optics to project symbology at optical infinity. This means:
- Symbology appears attached to the outside world regardless of pilot head movement
- Moving the pilot's head (eyepoint) does NOT move symbols on the combiner
- Symbols remain in their correct world-referenced position at all times

Our simulation achieves this by:
1. Tracking camera position changes (eyepoint deltas) each frame
2. Compensating the projection origin by an equal and opposite amount
3. Publishing a screen-space delta for the JS renderer to apply as a canvas translate

---

## 2. Pipeline Trace

```
module_update_project()
  │
  ├── collimation_update(&g_hud.camera_delta, eye_offset, ac_ref, ...)
  │   │
  │   ├── First frame: init, no correction
  │   │
  │   ├── Subsequent frames:
  │   │   ├── eye_delta_body = current_eye - prev_eye_offset
  │   │   ├── cd->delta_body = cd->delta_body * 0.995 + eye_delta_body  (leaky)
  │   │   ├── Clamp to max_compensation_m (=0.15m)
  │   │   └── cc->correction_vector = cd->delta_body * (-0.85)  (invert + gain)
  │   │
  │   └── cc->active = (correction_mag_m > 0.001)
  │
  ├── corrected_eye = collimation_apply(eye_offset, &cc)
  │   └── base_offset + cc->correction_vector  (for 3D projection pipeline)
  │
  └── (all subsequent projections use corrected_eye)
```

During publish:

```
module_update_publish()
  │
  ├── scale = combiner_geom.scale_x (> 0 ? combiner_geom.scale_x : 1.0)
  ├── LVAR_COLL_SCREEN_DX = correction_vector.x * scale
  ├── LVAR_COLL_SCREEN_DY = correction_vector.y * scale
  ├── LVAR_COLLIMATED = cc->active ? 1.0 : 0.0
  │
  └── (JS reads and applies)
```

During JS render:

```
conformal_renderer.js draw():
  ├── coll_dx = read_lvar("L:C_HUD_Coll_ScreenDX") || 0
  ├── coll_dy = read_lvar("L:C_HUD_Coll_ScreenDY") || 0
  ├── ctx.save()
  ├── ctx.translate(coll_dx, coll_dy)  ← collimation compensation
  ├── ctx.clip(combiner rect)
  ├── (draw all symbology)
  └── ctx.restore()
```

---

## 3. Component Verification

### 3.1 CameraDelta Tracking

| Aspect | Status | Evidence |
|--------|--------|----------|
| Eye offset delta computed | ✅ **VERIFIED** | `collimation.cpp:60-61` — `proj_vec3_sub(current_eye, cd->prev_eye_offset)` |
| Leaky integrator prevents drift | ✅ **VERIFIED** | `collimation.cpp:65-68` — `cd->delta_body = cd->delta_body * 0.995 + eye_delta_body` |
| Max compensation clamp | ✅ **VERIFIED** | `collimation.cpp:72-77` — clamps to `max_compensation_m` (0.15m) |
| Compensation gain applied | ✅ **VERIFIED** | `collimation.cpp:81` — `cc->correction_vector = proj_vec3_scale(cd->delta_body, -cd->compensation_gain)` |
| Correction magnitude sanity | ✅ **VERIFIED** | `cc->correction_mag_m = proj_vec3_len(cc->correction_vector)` |
| Active threshold | ✅ **VERIFIED** | `cc->active = (cc->correction_mag_m > 0.001)` |

### 3.2 Collimation Application (3D Projection)

| Aspect | Status | Evidence |
|--------|--------|----------|
| corrected_eye used in projection | ✅ **VERIFIED** | `main.cpp` — `corrected_eye` passed to FPV, runway, flare, etc. |
| Correction in body frame | ✅ **VERIFIED** | `collimation_apply()` adds to body-frame eye offset |
| 3D projection uses corrected eye | ✅ **VERIFIED** | All `fpv_project_to_hud()`, `runway_project_to_hud()` etc. receive `corrected_eye` |

### 3.3 Screen-Space Collimation Publish

| Aspect | Status | Evidence |
|--------|--------|----------|
| Correction published as L:Var | ✅ **VERIFIED** | `LVAR_COLL_SCREEN_DX/DY` written in publish |
| JS reads and applies translate | ✅ **VERIFIED** | `conformal_renderer.js:1084` — `ctx.translate(coll_dx, coll_dy)` |
| Legacy renderer (hud_overlay.js) | ✅ **NOT LOADED** | HTML only loads conformal_renderer.js |
| Unit conversion correct | ❌ **BROKEN** | See Finding CL-1 below |

---

## 4. Critical Finding CL-1: Incorrect Units in Screen-Space Publish

### The Problem

```cpp
// main.cpp publish phase
const FLOAT64 scale = g_hud.combiner_geom.scale_x > 0.0
                       ? g_hud.combiner_geom.scale_x : 1.0;
lvar_write(LVAR_COLL_SCREEN_DX,
           g_hud.collimation_cc.correction_vector.x * scale);
lvar_write(LVAR_COLL_SCREEN_DY,
           g_hud.collimation_cc.correction_vector.y * scale);
```

Where:
- `correction_vector` is in **body-frame metres** (from collimation_update)
- `scale_x = screen_w / 1024.0` is a **dimensionless panel-to-screen ratio**

Multiplying metres by a dimensionless ratio does NOT produce meaningful screen pixels.

### Why This Is Wrong

To convert a 3D body offset to a 2D screen shift, the correct approach is:

```
screen_delta_px = focal_length_px * atan(body_delta_m / distance_to_target_m)
```

Or for small angles (which is the normal case for head movement of 0.15m at ≥10m distance):

```
screen_delta_px ≈ focal_length_px * (body_delta_m / distance_m)
```

The current code effectively assumes `distance_m = 1.0` and `focal_length_px = scale_x`, which is physically meaningless.

### Impact

- The magnitude of the collimation translate on canvas is incorrect
- At typical approach distances (100m+ from objects), the compensation will be **massively over-amplified** if focal_px is ~500 and distance is ~80m (should be ~6% of current value)
- At close range (flare/rollout), the compensation may be **under-amplified** relative to correct projection
- The direction (sign) is correct since it's derived from the body delta sign

### Severity: HIGH

### Flow Attempt: Fix Proposal

**Root cause:** `collimation_update()` computes a body-frame correction vector in metres. The publish phase multiplies this by a dimensionless panel-scale factor instead of projecting through the camera focal length.

**Fix:**
```cpp
// Correct conversion: body-offset (m) → screen offset (px)
// For collimated HUD at infinity focus, use:
//   screen_delta_px = focal_px * atan(correction_m / focus_distance_m)
const FLOAT64 FOCUS_DISTANCE_M = 80.0;  // Typical HGS infinity focus distance
const FLOAT64 coll_dx = focal_px * atan2(g_hud.collimation_cc.correction_vector.x, FOCUS_DISTANCE_M);
const FLOAT64 coll_dy = focal_px * atan2(g_hud.collimation_cc.correction_vector.y, FOCUS_DISTANCE_M);
```

**Risk:** Low — only changes the unit conversion, not the collimation logic itself. If `FOCUS_DISTANCE_M` is wrong, the magnitude will be off, but it will be a constant factor that can be tuned.

---

## 5. Finding CL-2: Camera Delta Tracks Static Eye Offset, Not Dynamic Camera

### The Problem

```cpp
// main.cpp project phase:
collimation_update(&g_hud.camera_delta, eye_offset, ac_ref, ...);
```

Where `eye_offset` is the profile's static design eye position (e.g., `{0.50, 0.0, -1.20}` for PMDG 737).

### Analysis

The profile eye offset is a **static constant** — it doesn't change between frames under normal operation (only when calibration adjustments are applied). Therefore:
- `eye_delta_body = current_eye - cd->prev_eye_offset` will be **zero every frame after initialisation**
- The leaky integrator (`cd->delta_body * 0.995`) will decay toward zero
- `cd->delta_body` will quickly approach (0,0,0)

**This means collimation is effectively disabled for realistic pilot head movement.**

The code tracks changes in the DESIGN EYE POSITION (which is constant), not the actual PILOT CAMERA POSITION (which changes when the user moves their head via TrackIR/VR/pan).

### Evidence that actual camera position is NOT tracked

Searched codebase for:
- `CAMERA POSITION` SimVar — **NOT PRESENT**
- `EYEPOINT POSITION` — **NOT PRESENT**
- `CAMERA OFFSET` — **NOT PRESENT**
- Any head-tracking data source — **NOT PRESENT**

The only camera-adjacent data used is:
- `g_hud.camera_delta` (which tracks static offset changes)
- No delta between actual camera positions is ever computed

### Impact

The collimation compensation corrects for changes in the HUD design eye position (which never changes in flight), NOT for pilot head movements. The desired effect — symbols staying world-fixed when the pilot moves their head — is NOT achieved.

### Severity: CRITICAL

The entire collimation subsystem as implemented corrects the wrong thing. It corrects for static eye offset between aircraft (different profiles) instead of dynamic camera movement during flight.

### Flow Attempt: Fix Proposal

**Root cause:** `collimation_update()` receives the profile's constant eye offset instead of the frame-to-frame camera position delta.

**Fix:** 
1. Add SimVar read for actual camera position/offset in `module_update_read_vars()`
2. Store previous camera position in a persistent variable
3. Compute delta between previous and current camera position each frame
4. Pass this delta to `collimation_update()` instead of the static eye offset

**SimVar candidates:**
- `EYEPOINT POSITION` (returns current eye offset from reference)
- Track changes in `CAMERA OFFSET X/Y/Z` 
- GDI: Check if `sGaugeDrawData` contains any eye/camera offset fields

**Risk:** Medium — adds new SimVar read. If the SimVar is not available in all MSFS versions, fall back gracefully to current behavior (effectively disabled).

---

## 6. Finding CL-3: JS Translate Affects Clipping Region

### The Problem

```javascript
ctx.save();
ctx.translate(coll_dx, coll_dy);  // applied FIRST
ctx.clip(combiner_rect);          // applied AFTER translate → shifted!
// draw symbology
ctx.restore();
```

Because `ctx.translate()` is called BEFORE `ctx.clip()`, the clipping region is also shifted by the collimation delta. This means the clip rect moves with head movement compensation.

### Correct Order

If collimation truly makes symbols world-fixed, the combiner glass should remain fixed on screen and only the symbology should shift:

```javascript
ctx.save();
ctx.clip(combiner_rect);           // clip to fixed glass position
ctx.save();
ctx.translate(coll_dx, coll_dy);   // shift symbols within the glass
// draw symbols
ctx.restore();  // restore translate
ctx.restore();  // restore clip
```

### Severity: MEDIUM

The clip region shift may cause edge artifacts where symbols near the combiner edge are incorrectly clipped or shown. However, since collimation correction is effectively disabled (CL-2), this issue is not currently observable.

---

## 7. Verification: Viewpoint Movement Symbology Behavior

| Test Scenario | Expected Behavior | Actual Behavior | Status |
|---------------|-------------------|-----------------|--------|
| Move camera left 10cm | Symbols stay fixed on outside world | No camera tracking → no correction | ❌ **BROKEN** |
| Move camera right 10cm | Symbols stay fixed | Same as above | ❌ **BROKEN** |
| Zoom in | Symbols scale with view | No zoom tracking | ❌ **MISSING** |
| Pan camera up | Symbols don't drift | No pan tracking | ❌ **MISSING** |
| TrackIR head movement | Symbols collimated | No head tracking | ❌ **MISSING** |
| VR head movement | Symbols collimated | No VR integration | ❌ **MISSING** |

---

## 8. Summary of Correctness

| Property | Verified? |
|----------|-----------|
| Collimation logic C++ is mathematically correct | ✅ **YES** (leaky integrator, clamp, gain) |
| Collimation corrects the right thing | ❌ **NO** (tracks static eye offset, not dynamic camera) |
| Screen-space unit conversion | ❌ **NO** (metres × dimensionless scale) |
| JS translate order | ❌ **NO** (translate before clip shifts clip) |
| Collimation compensates pilot head movement | ❌ **NO** (no camera position input) |
| Both renderers apply collimation | ✅ **N/A** (only one renderer active) |
| FOV/zoom considered in collimation | ❌ **NO** |
