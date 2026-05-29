# Combiner Geometry Audit
## Phase 5 — Production-Grade Combiner Correctness Verification

**Date:** 2025-01-XX  
**Auditor:** DeepSeek Senior Avionics Engineer  
**Standard:** Code path tracing only. All claims of correctness treated as false until proven.

---

## 1. Architecture Overview

The combiner geometry system converts panel-space HUD profiles (in a 1024×1024 coordinate system) into screen-space pixel coordinates for JS canvas clipping. This is the critical link between aircraft 3D model geometry and the 2D overlay renderer.

```
HUDProfile.combiner {x,y,width,height} (panel coords, 1024x1024 space)
    │
    ▼
combiner_geometry_update()
    ├── panel_x/y = profile->combiner.x/y
    ├── panel_w/h = profile->combiner.width/height
    ├── scale_x = screen_w / 1024.0
    ├── scale_y = screen_h / 1024.0
    ├── screen_x = panel_x * scale_x
    ├── screen_y = panel_y * scale_y
    ├── screen_w = panel_w * scale_x
    ├── screen_h = panel_h * scale_y
    └── optical_cx/cy = screen centre + profile offset
    │
    ▼
module_update_publish()
    ├── LVAR_COMB_SCREEN_X/Y/W/H → g_hud.combiner_geom.screen_*
    │
    ▼
JS: get_combiner() → ctx.clip(rect)
```

---

## 2. Component Audit

### 2.1 Combiner Clipping (`ctx.clip()`)

| Aspect | Status | Evidence |
|--------|--------|----------|
| JS calls ctx.clip() | ✅ **VERIFIED** | `conformal_renderer.js:1091` — `ctx.clip()` applied inside `ctx.save()/restore()` |
| Clipping uses screen-space rect | ✅ **VERIFIED** | `conformal_renderer.js:1086-1089` — reads `CombinerScreenX/Y/W/H` |
| Clipping in legacy renderer | ✅ **VERIFIED** | `hud_overlay.js:229-245` — also clips, causing double-clip |
| Clip region is correct | ❌ **UNVERIFIED** | No runtime test confirms pixel-accurate clipping to actual HUD glass |
| Clip region handles DPI | ❌ **MISSING** | No devicePixelRatio handling in clip rect |
| Clip region handles zoom/FOV | ❌ **MISSING** | No zoom compensation in combiner geometry |

### 2.2 Combiner Geometry Calculations (`combiner_geometry_update()`)

| Aspect | Status | Evidence |
|--------|--------|----------|
| Panel coords from profile | ✅ **VERIFIED** | `combiner_geometry.cpp:26-29` reads profile→combiner |
| Scale factor calculation | ✅ **VERIFIED** | `cg->scale_x = (FLOAT64)screen_w / 1024.0` |
| Screen-space rect derivation | ✅ **VERIFIED** | `cg->screen_x = cg->panel_x * cg->scale_x` |
| Fallback when profile=NULL | ✅ **VERIFIED** | Lines 20-44: centres half of screen |
| Validation function | ✅ **VERIFIED** | `combiner_geometry_validate()` checks bounds |
| Optical centre computation | ✅ **VERIFIED** | Uses profile→optical_center_offset_x/y |

**CRITICAL ISSUES:**

#### Issue CG-1: No FOV/Zoom Scaling

```
combiner_geometry_update() currently does:
    scale_x = screen_w / 1024.0

But should be:
    effective_fov = base_fov * zoom_factor
    scale_x = (screen_w / 1024.0) * (base_fov / effective_fov)
```

The combiner rect should SHRINK when FOV increases (zoom out = wider view = combiner covers smaller portion of screen). Currently it's fixed regardless of zoom/FOV changes.

**Impact:** When pilot zooms in/out, the combiner clipping region stays the same size. At wide FOVs, symbology will be clipped incorrectly (too much visible). At narrow FOVs, symbology may be clipped too aggressively.

#### Issue CG-2: Multi-Monitor Ignored

The combiner geometry assumes a single full-window viewport. On multi-monitor setups in MSFS where the window spans multiple displays, the 1024×1024 panel space assumption is incorrect because the VC panel rendering is scaled differently.

**Impact:** On surround/eyefinity setups, combiner clipping will be misaligned.

#### Issue CG-3: Ultrawide Aspect Ratio Not Handled

The scale is isotropic (`scale_x = scale_y` effectively since both use same panel assumption). On ultrawide monitors (21:9, 32:9), the VC panel is typically rendered with proper aspect ratio, but the combiner scale calculation doesn't account for this.

#### Issue CG-4: Panel Assumption Is Hardcoded

```cpp
cg->scale_x = (FLOAT64)screen_w / 1024.0;
cg->scale_y = (FLOAT64)screen_h / 1024.0;
```

Assumes the VC panel texture is always 1024×1024. If MSFS renders the panel at a different effective resolution (which varies by aircraft and graphics settings), the scale will be wrong.

---

## 3. Viewport Scaling Audit

### 3.1 Screen Centre

| Component | Status |
|-----------|--------|
| LVAR_SCREEN_CX | ❌ **HARDCODED** = 512.0 (should be `win_w * 0.5`) |
| LVAR_SCREEN_CY | ❌ **HARDCODED** = 512.0 (should be `win_h * 0.5`) |

**Impact:** On non-standard viewports, the HUD centre used for symmetric symbology (ILS crosshair, FPV reference) will be offset from the actual screen centre.

### 3.2 Focal Length

| Component | Status |
|-----------|--------|
| Profile `focal_length_px` | ❌ **STUB** — always defaults to 520.0 |
| Profile `hfov_deg`/`vfov_deg` | ✅ **VERIFIED** — defined but → **UNUSED** |
| FOV-dependent scaling | ❌ **MISSING** |

**Evidence:**
```cpp
// main.cpp
const FLOAT64 focal_px = (profile->focal_length_px > 0)
                          ? profile->focal_length_px
                          : 520.0;
```
But `profile->focal_length_px` is 0.0 for ALL profiles (never computed from FOV).

---

## 4. Zoom / FOV Handling Audit

| Component | Status |
|-----------|--------|
| SimVar for zoom level | ❌ **NOT READ** |
| SimVar for camera FOV | ❌ **NOT READ** |
| Profile FOV used in any geometry | ❌ **NOT USED** |
| Zoom compensation in publish | ❌ **NOT PRESENT** |

**Impact:** When pilot uses MSFS zoom (View → Zoom), the HUD symbology and combiner do not scale. The HUD should zoom with the view — symbols should appear larger when zoomed in — because the HUD is attached to the cockpit geometry.

---

## 5. Aspect-Ratio Handling Audit

| Component | Status |
|-----------|--------|
| Separate scale_x/scale_y | ✅ **VERIFIED** — computed independently |
| Non-uniform aspect | ❌ **NOT TESTED** — no test for non-4:3 ratios |
| 21:9 correction | ❌ **NOT PRESENT** |
| 32:9 correction | ❌ **NOT PRESENT** |

---

## 6. Multi-Monitor Behavior Audit

| Component | Status |
|-----------|--------|
| Multi-window aware | ❌ **NOT PRESENT** |
| Surround viewport handling | ❌ **NOT PRESENT** |
| MSFS window bounds query | ❌ **NOT QUERIED** |

**Evidence:** The only screen dimension used is `dd->winWidth` and `dd->winHeight` from `sGaugeDrawData`. In multi-monitor mode, MSFS provides the window dimensions which may span multiple physical monitors, but the gauge system renders each VCockpit01 once per window.

---

## 7. Ultrawide Behavior Audit

| Component | Status |
|-----------|--------|
| Aspect ratio detection | ❌ **NOT PRESENT** |
| Horizontal FOV compensation | ❌ **NOT PRESENT** |
| Symbology distortion at edges | ❌ **NOT COMPENSATED** |

**Impact:** On ultrawide, the horizontal FOV is wider. The combiner should become narrower relative to the total screen width (since the HUD glass has fixed physical width). Currently it stays at the same proportional width.

---

## 8. Combiner Geometry Verification Summary

| Check | Status | Priority |
|-------|--------|----------|
| Panel→screen scale correct for standard 16:9 | ✅ VERIFIED | — |
| Combiner rect from profile | ✅ VERIFIED | — |
| Fallback when no profile | ✅ VERIFIED | — |
| Optical centre computed | ✅ VERIFIED | — |
| FOV compensation | ❌ MISSING | CRITICAL |
| Zoom compensation | ❌ MISSING | HIGH |
| Multi-monitor handling | ❌ MISSING | HIGH |
| Ultrawide aspect ratio | ❌ MISSING | MEDIUM |
| Screen centre not hardcoded | ❌ BROKEN | HIGH |
| focal_length_px from FOV | ❌ STUB | MEDIUM |
| devicePixelRatio handling | ❌ MISSING | MEDIUM |
