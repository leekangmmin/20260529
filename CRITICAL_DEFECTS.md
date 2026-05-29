# CRITICAL DEFECTS — Boeing HGS Realism Blockers

**Defects that prevent Boeing HGS-level realism, verified by source code analysis.**

---

## P0 — BLOCKING (Cannot achieve HGS equivalence with these defects)

### DEFECT-001: No Optical Collimation

**Severity:** P0 — BLOCKING  
**File:** `src/hud/collimation.cpp`, `include/hud/collimation.h`  
**Type:** Architecture / Physics

**Description:**
The "collimation" implementation is actually camera-delta compensation in body-frame coordinates. It tracks how much the virtual camera has moved and adds an offset to counteract the movement. True optical collimation requires: (a) projecting symbology to appear at optical infinity (parallel rays), (b) maintaining world-aligned symbology regardless of eye position, and (c) using the combiner's physical optics to make the image appear outside the aircraft.

**Code Evidence:**
```cpp
// src/hud/collimation.cpp:72-76
cc->correction_vector = proj_vec3_scale(cd->delta_body, -cd->compensation_gain);
```
This computes `correction = -delta * gain` and adds it to the eye offset. There is no infinity projection, no ray-to-world math, no collimation matrix. The correction is purely a body-frame offset.

**Fix Required:** Complete rewrite of the projection pipeline to use optical infinity model. Within MSFS WASM sandbox, this may not be achievable.

---

### DEFECT-002: No Physical Combiner Model

**Severity:** P0 — BLOCKING  
**File:** `panel/HUD/hud_overlay.js`, `panel/HUD/conformal_renderer.js`  
**Type:** Rendering

**Description:**
The combiner glass is modelled as a simple rectangle used for `ctx.clip()`. A real HGS combiner: (a) is a beam splitter with specific reflectivity (70/30 or 50/50), (b) has shaped, curved glass, (c) introduces veiling glare, ghosting, and chromatic effects, (d) has gradual transmission changes across its surface, (e) has a physical bezel/ mounting structure.

**Code Evidence:**
```javascript
// panel/HUD/hud_overlay.js:56-67
var comb = get_combiner();
ctx.save();
if (comb && comb.w > 0 && comb.h > 0) {
    ctx.beginPath();
    ctx.rect(comb.x, comb.y, comb.w, comb.h);
    ctx.clip();
}
```
This is a simple rectangular clip. No shape mask, no gradient transmission, no ghosting model, no bezel.

**Fix Required:** Implement a full combiner optical model. Likely requires moving to WebGL with fragment shaders for proper beam-splitter simulation, reflection/transmission modelling, and ghosting.

---

### DEFECT-003: Screen-Space Perspective Projection Instead of World-Aligned Rendering

**Severity:** P0 — BLOCKING  
**File:** `include/projection.h`, `src/hud/runway_projection.cpp`  
**Type:** Architecture

**Description:**
All symbology is projected from 3D world coordinates to 2D screen coordinates using a standard pinhole perspective camera model (`proj_world_to_hud`). The FPV, runway, horizon, and ILS bars are all drawn at screen-space pixel positions. In a real HGS, symbology appears fixed in the outside world regardless of head movement because it's projected at optical infinity through collimating optics.

**Code Evidence:**
```cpp
// projection.h — standard perspective projection
static inline Vec3 proj_mat4_transform_point(const Mat4* m, Vec3 p) {
    // Standard 4x4 matrix transform with homogeneous divide
    // Used for all world-to-screen transforms
}
```

**Fix Required:** Must rearchitect to project symbology as if from infinite distance, not from a virtual camera at the pilot's eye.

---

### DEFECT-004: No Head/Eye Position Tracking from MSFS Camera

**Severity:** P0 — BLOCKING  
**File:** `src/main.cpp` (comment at line 485)  
**Type:** Integration

**Description:**
The HUD eye position is set statically in aircraft profiles (e.g., `eye_position = {0.50, 0.0, -1.20}` for PMDG 737). Real HGS computes symbology based on the pilot's actual eye position relative to the combiner. MSFS provides `CAMERA POSITION` and `EYE POSITION` SimVars that are not being read.

**Code Evidence:**
```cpp
// src/main.cpp:485 comment
"Apply live camera offsets from calibration (TrackIR/head tracking)"
```
This is just a comment. No `get_simvar("CAMERA POSITION")` or equivalent exists anywhere in the codebase.

**Fix Required:** Read CAMERA POSITION SimVar each frame and use it to compute eye offset dynamically. This is a medium-difficulty fix.

---

## P1 — HIGH (Significantly degrades realism)

### DEFECT-005: FBW A32NX Misclassified as Boeing HGS

**Severity:** P1 — HIGH  
**File:** `src/hud/aircraft_detector.cpp` line 49  
**Type:** Aircraft Compatibility

**Description:**
The FBW A32NX (Airbus A320neo) is classified as `BOEING_HGS`, causing Boeing-specific behaviors (flare law, FPV filtering, declutter priorities) to be applied to an Airbus aircraft. Boeing and Airbus have fundamentally different HUD philosophies: Boeing uses the HGS as a primary flight reference with conformal ILS guidance; Airbus uses a Thales/Elbit HUD with different symbiology and logic.

**Code Evidence:**
```cpp
// src/hud/aircraft_detector.cpp:49
{ "FBW A32NX", HudAircraftCategory::BOEING_HGS },
```

**Fix Required:** Either create an Airbus A32NX category or use the AIRBUS_HUD behavior.

---

### DEFECT-006: 787 Panel State Deployment Not Implemented

**Severity:** P1 — HIGH  
**File:** `src/hud/hud_deployment.cpp`  
**Type:** Functionality

**Description:**
The 787 profile declares `use_panel_state = true`, but `hud_deployment_update()` never reads panel state variables. Only L:Vars are read. This means the 787 HUD deployment is likely broken regardless of panel state.

**Code Evidence:**
```cpp
// src/hud/hud_deployment.cpp:56 (declaration)
.use_panel_state = true,

// hud_deployment_update() lines 126-216 — no panel state reading code path
// All paths read L:Vars via module_read_f64() only
```

**Fix Required:** Implement panel state reading in the deployment update function.

---

### DEFECT-007: Speed/Altitude/Heading Tapes in Profiles But Not Rendered

**Severity:** P1 — HIGH  
**File:** `panel/HUD/conformal_renderer.js`  
**Type:** Feature Gaps

**Description:**
The PMDG 777 and 787 profiles enable `HUD_SYM_SPEED_SCALE`, `HUD_SYM_ALTITUDE_SCALE`, and `HUD_SYM_HEADING_SCALE`, but the Canvas renderer does not contain drawing code for any tape-style displays. These symbols are configured but will never appear.

**Code Evidence:**
```cpp
// src/hud/aircraft_profiles.cpp:91-96
.symbology_mask = ... | HUD_SYM_ALTITUDE_SCALE | HUD_SYM_SPEED_SCALE,

// conformal_renderer.js — search for "speed", "altitude", "heading_scale" yields nothing
```

**Fix Required:** Implement tape rendering in the JS renderer, or remove the flags from profiles.

---

### DEFECT-008: No Ultrawide / Multi-Monitor / Aspect Ratio Handling

**Severity:** P1 — HIGH  
**File:** `src/hud/combiner_geometry.cpp`  
**Type:** Visual Compatibility

**Description:**
The combiner geometry assumes a square 1024×1024 panel coordinate space mapped linearly to the full viewport. On ultrawide (21:9, 32:9) or multi-monitor setups, the HUD will stretch or appear incorrectly positioned. There is no aspect-ratio correction, no multi-monitor spanning logic, and no FOV-based field-of-view calibration.

**Code Evidence:**
```cpp
// src/hud/combiner_geometry.cpp:37-40
cg->scale_x = (FLOAT64)screen_w / 1024.0;
cg->scale_y = (FLOAT64)screen_h / 1024.0;
```
Single uniform scale, no aspect-ratio preservation.

**Fix Required:** Implement aspect-ratio correction and multi-monitor detection.

---

### DEFECT-009: Flare Constants Hardcoded Overriding Profile Values

**Severity:** P1 — HIGH  
**File:** `src/hud/flare.cpp` lines 22–28  
**Type:** Functionality

**Description:**
The flare constants (`FLARE_CONSTANT 0.10`, `FLARE_ACTIVATE_ALT_M 24.384`, `FLARE_FULLY_ACTIVE_M 15.24`) are `#define` macros in flare.cpp. The `flare_compute()` function uses these, ignoring the profile-tuned values passed to `flare_project_cue()`. The profile values are only used for visual rendering of the cue, not for the actual flare physics.

**Code Evidence:**
```cpp
// src/hud/flare.cpp:22-28
#define FLARE_CONSTANT 0.10
#define FLARE_ACTIVATE_ALT_M  24.384  // 80 ft
#define FLARE_FULLY_ACTIVE_M  15.24   // 50 ft

// flare_compute() uses these hardcoded values
const FLOAT64 k = proj_sqrt(2.0 * FLARE_G * FLARE_CONSTANT);
```

**Fix Required:** Pass profile values into `flare_compute()` or make them configurable via the `FlareState` struct.

---

### DEFECT-010: Certification Scores Are Estimated, Not Measured

**Severity:** P1 — HIGH  
**File:** `installer/certification.py`  
**Type:** Process

**Description:**
The `_get_test_pass_rate()` method returns a hardcoded 0.90 (90%) instead of running actual tests. The readiness score `stability_score` is based on version number, not actual stability metrics. This means the certification reports are essentially fictional.

**Code Evidence:**
```python
# installer/certification.py:170
return (0.90, 0, 0, 0)  # Hardcoded 90% pass rate
```

**Fix Required:** Connect the certification engine to the actual pytest output.

---

## P2 — MEDIUM (Significantly degrades experience)

### DEFECT-011: No Dedicated A350 Profile in Profiles Database

**File:** `src/hud/aircraft_profiles.cpp`  
**Issue:** A350 falls to default profile

### DEFECT-012: FPV Lacks Acceleration Prediction

**File:** `src/hud/fpv.cpp`  
**Issue:** Real HGS FPV includes predictive lead based on acceleration

### DEFECT-013: Flight Director is Proportional-Only

**File:** `src/hud/guidance.cpp` — `guidance_flight_director()`  
**Issue:** No integral term, no lead compensation

### DEFECT-014: ILS Beam Hardcoded to 3° Glideslope

**File:** `src/hud/guidance.cpp` line 42  
**Issue:** `gs_angle_deg = 3.0` hardcoded, not read from airport data

### DEFECT-015: Canvas 2D Instead of WebGL

**File:** `panel/HUD/conformal_renderer.js`  
**Issue:** No GPU acceleration, no shaders, limited visual effects

### DEFECT-016: No Go-Around Guidance

**File:** None  
**Issue:** Go-around mode not implemented

### DEFECT-017: No Takeoff Guidance

**File:** None  
**Issue:** Takeoff mode not implemented

---

## P3 — LOW (Minor deviations from realism)

### DEFECT-018: Combiner Clip is Simple Rectangle

**File:** `panel/HUD/hud_overlay.js`  
**Issue:** No shape mask, no gradient, no bezel

### DEFECT-019: No Chromatic Aberration

**File:** None  
**Issue:** Real combiners introduce colour fringing

### DEFECT-020: No Phosphor Scan-Line Effect

**File:** None  
**Issue:** No CRT scan-line simulation

### DEFECT-021: No Ghosting/Double-Image

**File:** None  
**Issue:** Real combiners produce weak double images

### DEFECT-022: No Stereo Rendering for VR

**File:** None  
**Issue:** VR users see the same image in both eyes

### DEFECT-023: L:AS1001_HUD Variable Name Not Verified

**File:** `src/hud/hud_deployment.cpp`  
**Issue:** Variable name is a guess, not confirmed from PMDG SDK

---

## Deployment Blockers Summary

| Blocker | Severity | Category |
|---|---|---|
| No optical collimation | P0 — BLOCKING | Physics |
| No physical combiner model | P0 — BLOCKING | Rendering |
| Screen-space projection | P0 — BLOCKING | Architecture |
| No head tracking | P0 — BLOCKING | Integration |
| Cannot achieve HGS equivalence within WASM sandbox | P0 — INHERENT LIMITATION | Platform |

## Realism Blockers Summary

| Blocker | Severity | Category |
|---|---|---|
| FBW A32NX misclassified | P1 — HIGH | Compatibility |
| 787 panel state not implemented | P1 — HIGH | Functionality |
| Tapes configured but not rendered | P1 — HIGH | Feature |
| No ultrawide/multi-monitor | P1 — HIGH | Compatibility |
| Flare constants hardcoded | P1 — HIGH | Physics |
| Fake certification scores | P1 — HIGH | Process |

---

**Total: 23 defects** (4 P0, 6 P1, 7 P2, 6 P3)

*Report generated from static source-code analysis.*
