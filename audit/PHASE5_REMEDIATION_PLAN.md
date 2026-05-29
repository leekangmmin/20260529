# Phase 5 Remediation Plan
## Prioritized Fixes for Real HUD Compliance

**Date:** 2025-01-XX  
**Based on:** REAL_HUD_COMPLIANCE_AUDIT.md, COMBINER_GEOMETRY_AUDIT.md, COLLIMATION_VERIFICATION.md, AIRCRAFT_HUD_MATRIX.md  
**Principle:** No new features. No architecture redesign. No performance optimization. Fix only: real HUD behavior, aircraft integration, combiner correctness, deployment correctness, collimation correctness.

---

## 1. CRITICAL FIXES (Must Fix — System Non-Functional Without These)

### C-1: Register Deploy L:Var Tokens for All Aircraft

**Files:** `src/module.cpp`, `include/module.h`, `src/hud/hud_deployment.cpp`  
**Issue:** Deploy animation L:Vars (`L:AS1001_HUD`, `L:HUD_DEPLOY`, `L:A350_HUD_DEPLOY`, `L:A350_HUD_DEPLOY_PCT`) are defined in `hud_deployment.cpp` config but NEVER registered as `GAUGE_VAR` tokens.  
**Root cause:** `g_hud` is `static` to `main.cpp`; `module.cpp` (which handles token registration) cannot access `g_hud.deploy.tok_deploy_lvar`.  
**Impact:** Deployment detection is permanently broken for ALL aircraft with deployable HUDs. 787 HUD never disappears when stowed. PMDG HUD always shows as "deployed".  
**Fix:** Move deploy token storage to `ModuleState` (which IS extern'd via `include/module.h`), then register in `gauge_callback_post_install()`.

**Option A (Recommended):**
```cpp
// include/module.h — add to ModuleState struct
GAUGE_VAR tok_deploy_lvar;   // Current aircraft's deploy animation L:Var
GAUGE_VAR tok_deploy_pct;    // Current aircraft's deploy percentage L:Var (if available)

// src/module.cpp — in gauge_callback_post_install()
register_simvar("L:AS1001_HUD", &g_state.tok_deploy_lvar);
register_simvar("L:A350_HUD_DEPLOY", &g_state.tok_deploy_lvar); // Overwritten when A350 detected
// OR: register all, let aircraft detection pick which to use

// src/hud/hud_deployment.cpp — use g_state.tok_deploy_lvar instead of ds->tok_deploy_lvar
```

**Lines affected:** ~3 files, ~10 lines added  
**Effort:** Small  
**Risk:** Low

### C-2: Fix Collimation Unit Conversion (Body Metres → Screen Pixels)

**File:** `src/main.cpp` (publish phase)  
**Issue:** `lvar_write(LVAR_COLL_SCREEN_DX, correction_vector.x * scale_x)` multiplies body-frame metres by dimensionless panel scale.  
**Impact:** Collimation translate magnitude is physically meaningless — massively over-amplified at typical approach distances.  
**Fix:** Compute correct screen-space delta using focal length and focus distance.

**Before:**
```cpp
const FLOAT64 scale = g_hud.combiner_geom.scale_x > 0.0
                       ? g_hud.combiner_geom.scale_x : 1.0;
lvar_write(LVAR_COLL_SCREEN_DX,
           g_hud.collimation_cc.correction_vector.x * scale);
lvar_write(LVAR_COLL_SCREEN_DY,
           g_hud.collimation_cc.correction_vector.y * scale);
```

**After:**
```cpp
// Use focal length + focus distance for proper pixel conversion
const FLOAT64 HUD_FOCUS_DISTANCE_M = 80.0;  // HGS infinity focus distance
const FLOAT64 coll_dx = focal_px * atan2(g_hud.collimation_cc.correction_vector.x, HUD_FOCUS_DISTANCE_M);
const FLOAT64 coll_dy = focal_px * atan2(g_hud.collimation_cc.correction_vector.y, HUD_FOCUS_DISTANCE_M);
lvar_write(LVAR_COLL_SCREEN_DX, coll_dx);
lvar_write(LVAR_COLL_SCREEN_DY, coll_dy);
```

**Effort:** <1h  
**Risk:** Low — only changes mapping, not logic

### C-3: Fix JS Clip-Translate Order

**File:** `panel/HUD/conformal_renderer.js`  
**Issue:** `ctx.translate()` called BEFORE `ctx.clip()`, causing clip region to shift with collimation compensation.  
**Impact:** Combiner clipping region moves with head compensation; possible edge artifacts.  
**Fix:** Reorder to clip first, then translate:

```javascript
// Before:
ctx.save();
ctx.translate(coll_dx, coll_dy);
ctx.clip();
// draw
ctx.restore();

// After:
ctx.save();
ctx.clip();  // clip to fixed combiner
ctx.save();
ctx.translate(coll_dx, coll_dy);  // shift symbols within clip
// draw
ctx.restore();  // restore translate
ctx.restore();  // restore clip
```

**Effort:** <1h  
**Risk:** Low

### C-4: Determine PMDG 777 Native HUD Status

**File:** `audit/PMDG777_VIRTUAL_HUD_FEASIBILITY.md` (read existing analysis)  
**Issue:** Unknown whether PMDG 777 has native deployable HUD combiner glass.  
**Impact:** Cannot create appropriate integration strategy.  
**Fix:** 
1. Read existing audit file for conclusions
2. If no HUD exists: document as overlay-only, OR implement retrofit HUD geometry
3. If HUD exists: verify deploy detection works (same pattern as 737 after C-1 fix)

**Effort:** Investigation (2h)  
**Risk:** Low — investigation only

---

## 2. HIGH PRIORITY FIXES (Should Fix — Correctness Issues)

### H-1: Track Actual Camera Position Instead of Static Eye Offset

**Files:** `src/main.cpp`, `src/hud/collimation.cpp`  
**Issue:** Collimation currently passes profile's static eye offset to `collimation_update()`. This value doesn't change frame-to-frame, so `eye_delta_body ≈ 0` and collimation stays disabled.  
**Impact:** Collimation never activates for real pilot head movements.  
**Fix:** 
1. Add SimVar read for actual camera offset in `module_update_read_vars()`
2. Store previous camera position
3. Compute frame-to-frame camera delta  
4. Pass camera delta to `collimation_update()`

**SimVar candidates:**
- `EYEPOINT POSITION` (FLOAT64[3] — X,Y,Z body frame offset from design eye)
- Check `sGaugeDrawData` for any camera offset fields
- `CAMERA OFFSET X/Y/Z` for TrackIR/pan integration

**Effort:** Medium (4h)  
**Risk:** Medium — graceful fallback needed if SimVar unavailable

### H-2: Remove Hardcoded Screen Centre

**File:** `src/main.cpp` (publish phase)  
**Issue:** `lvar_write(LVAR_SCREEN_CX, 512.0)` hardcoded regardless of viewport.  
**Impact:** Wrong centre on ultrawide/multi-monitor.  
**Fix:**
```cpp
lvar_write(LVAR_SCREEN_CX, (FLOAT64)win_w * 0.5);
lvar_write(LVAR_SCREEN_CY, (FLOAT64)win_h * 0.5);
```

**Effort:** <1h  
**Risk:** Low

### H-3: Add Deploy State Re-initialization on Aircraft Change

**File:** `src/hud/hud_deployment.cpp`  
**Issue:** Deployment state initialized once per session. If aircraft changes mid-session, deploy config may mismatch.  
**Fix:** Detect aircraft ID change in `hud_deployment_update()`:

```cpp
if (ds->initialised && aircraft_id != ds->last_aircraft_id) {
    hud_deployment_init(ds);  // Re-init with new aircraft config
}
```

**Effort:** 1h  
**Risk:** Low

---

## 3. MEDIUM PRIORITY FIXES (Should Fix — Edge Cases)

### M-1: Add FOV Compensation to Combiner Geometry

**File:** `src/hud/combiner_geometry.cpp`  
**Issue:** Combiner geometry ignores camera FOV. Combiner should appear smaller when FOV increases.  
**Fix:** 
```cpp
// Read current camera FOV
const FLOAT64 current_hfov = get_camera_hfov();  // from SimVar or draw data
const FLOAT64 fov_scale = profile->hfov_deg / current_hfov;
cg->scale_x = (screen_w / 1024.0) * fov_scale;
cg->scale_y = (screen_h / 1024.0) * fov_scale;
```

**Effort:** 4h  
**Risk:** Low

### M-2: Compute Profile Focal Length from FOV

**File:** `src/hud/aircraft_profiles.cpp`  
**Issue:** `focal_length_px` is 0.0 for all profiles, always falls back to hardcoded 520px.  
**Fix:** Compute at init:
```cpp
profile->focal_length_px = (panel_width * 0.5) / tan(hfov_deg * 0.5 * PI/180.0);
// For PMDG 737 (30° HFOV): focal_px ≈ 512 / tan(15°) ≈ 1910px
// (not 520 as currently hardcoded)
```

**Effort:** 1h  
**Risk:** Low

### M-3: Add Zoom Level Handling

**File:** `src/main.cpp`, `src/hud/combiner_geometry.cpp`  
**Issue:** No zoom level tracking. Zoom in = symbols should scale.  
**Fix:** Read zoom from camera SimVar; multiply combiner rect scale by zoom factor.  
**Effort:** 4h  
**Risk:** Medium — zoom behavior is complex in MSFS

### M-4: Add devicePixelRatio Handling

**File:** `panel/HUD/conformal_renderer.js` `fit_canvas()`  
**Issue:** Canvas sized to `window.innerWidth/Height` without devicePixelRatio.  
**Fix:** Apply DPI scaling to canvas internal resolution.  
**Effort:** 2h  
**Risk:** Medium — coordinate system shift

### M-5: Read PMDG777_VIRTUAL_HUD_FEASIBILITY.md

**File:** `audit/PMDG777_VIRTUAL_HUD_FEASIBILITY.md`  
**Issue:** This file exists but hasn't been read/acted upon in this audit cycle.  
**Fix:** Read file, update matrix, implement findings.  
**Effort:** 1h  
**Risk:** Low

---

## 4. LOW PRIORITY FIXES (Nice to Have)

### L-1: Add Multi-Monitor Viewport Handling

**File:** `src/hud/combiner_geometry.cpp`  
**Effort:** 8h | **Risk:** High

### L-2: Add A350-Specific Power L:Var Registration

**File:** `src/module.cpp`  
**Issue:** `L:A350_HUD_POWER` not registered (A350 uses different power L:Var).  
**Effort:** 1h | **Risk:** Low

### L-3: Remove Unused `hud_overlay.js` from Layout

**File:** `layout.json`  
**Issue:** `hud_overlay.js` exists on disk and in layout.json but is not loaded by HTML.  
**Effort:** <1h | **Risk:** Low (but may break installer checks)

### L-4: Validate Combiner Rectangles vs Actual Cockpit Geometry

**Files:** N/A (testing)  
**Issue:** Profile combiner rects assumed correct but never validated in-sim.  
**Effort:** 8h (manual) | **Risk:** Low

---

## 5. Implementation Order (Updated)

| Step | Fix ID | Description | Effort | Dependencies |
|------|--------|-------------|--------|--------------|
| 1 | **C-1** | Register deploy L:Var tokens in ModuleState | 2h | None |
| 2 | **C-2** | Fix collimation unit conversion | 1h | None |
| 3 | **C-3** | Fix JS clip-translate order | <1h | None |
| 4 | **H-2** | Remove hardcoded screen centre | <1h | None |
| 5 | **C-4** | Determine PMDG 777 native HUD status | 2h | None |
| 6 | **H-1** | Track actual camera position for collimation | 4h | C-2 |
| 7 | **H-3** | Deploy state re-init on aircraft change | 1h | C-1 |
| 8 | **M-2** | Compute profile focal length from FOV | 1h | None |
| 9 | **M-1** | FOV compensation for combiner | 4h | None |
| 10 | **M-5** | Read PMDG777_VIRTUAL_HUD_FEASIBILITY.md | 1h | C-4 |
| 11 | **M-4** | devicePixelRatio handling | 2h | C-3 |
| 12 | **M-3** | Zoom level handling | 4h | M-1 |
| 13 | **L-2** | A350 power L:Var registration | 1h | C-1 |
| 14 | **L-3** | Clean up unused hud_overlay.js from layout | <1h | None |
| 15 | **L-1** | Multi-monitor handling | 8h | M-1, M-3 |
| 16 | **L-4** | Combiner rect validation | 8h | L-1 |

---

## 6. Risk Assessment

| Fix ID | Risk | Failure Mode | Mitigation |
|--------|------|-------------|------------|
| C-1 | LOW | Token fails to resolve | `module_read_f64()` handles NULL gracefully |
| C-2 | LOW | Focus distance wrong | Make it a profile parameter |
| C-3 | LOW | Visual difference in clipping | Test with debug overlay |
| H-1 | MEDIUM | Camera SimVar unavailable | Add graceful fallback |
| H-2 | LOW | Window size ≠ draw area | Use same win_w/win_h as project phase |
| M-1 | MEDIUM | FOV reading unreliable | Test with various FOVs |
| M-3 | MEDIUM | Zoom ≠ FOV in MSFS | Keep zoom and FOV independent |

---

## 7. Verification Checklist

After each fix:
- [ ] All 1230 unit tests pass
- [ ] No new compilation warnings
- [ ] JS console in MSFS dev mode shows no errors
- [ ] Deploy L:Vars readable via MSFS dev mode
- [ ] Combiner screen rects within screen bounds
- [ ] Deployment phase changes with power switch

---

## 8. Summary of Changes

| Category | Count | Total Lines |
|----------|-------|-------------|
| CRITICAL | 4 | ~60 lines |
| HIGH | 3 | ~60 lines |
| MEDIUM | 5 | ~100 lines |
| LOW | 4 | ~120 lines |
| **Total** | **16** | **~340 lines** |

The most impactful changes (C-1, C-2, C-3, H-2) can be completed in approximately **4 hours** and will resolve the majority of the "broken pipeline" issues.
