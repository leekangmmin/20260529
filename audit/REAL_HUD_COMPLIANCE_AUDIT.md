# Real HUD Compliance Audit
## Phase 5 — Production-Grade Avionics Integration

**Date:** 2025-01-XX  
**Auditor:** DeepSeek Senior Avionics Engineer  
**Scope:** Complete pipeline trace from WASM SimVar read → L:Var publish → JS render → Canvas draw  
**Standard:** All claims treated as false until proven by code path tracing.

---

## 1. EXECUTIVE SUMMARY

| Area | Verdict | Criticality |
|------|---------|-------------|
| PMDG 737 Native HUD Integration | **BROKEN** (deploy L:Var L:AS1001_HUD never registered) | CRITICAL |
| PMDG 777 Native HUD Detection | **MISSING** (no native HUD logic exists, retrofit not implemented) | CRITICAL |
| Boeing 787 Deployment Detection | **BROKEN** (deploy L:Var L:HUD_DEPLOY never registered) | CRITICAL |
| Combiner Glass Clipping | **PARTIALLY IMPLEMENTED** (geometry computed but no FOV/zoom compensation) | HIGH |
| Collimation Correction | **BROKEN** (body-frame m → screen px conversion is incorrect; tracks static eye offset not camera) | HIGH |
| Viewport/FOV Handling | **STUB** (ignores zoom, FOV, multi-monitor) | HIGH |
| Deployment State Machine | **PARTIALLY IMPLEMENTED** (logical framework exists but deploy L:Var tokens never resolved) | CRITICAL |
| A350 Deploy Detection | **BROKEN** (A350-specific L:Vars never registered) | CRITICAL |

---

## 2. Code Path Tracing — Full Pipeline

### 2.1 WASM Init → POST_INSTALL

```
module_init() [main.cpp:61]
  ├── hud_deployment_init()    → sets phase=UNKNOWN, fraction=1.0 ✓
  ├── combiner_geometry_init() → sets default panel rect ✓
  └── g_behavior = 0

gauge_callback_post_install() [module.cpp:104]
  ├── register_simvar("L:HUD_POWER_SWITCH") → g_state.tok_hud_power ✓
  ├── register_simvar("TITLE") → g_state.tok_aircraft_title ✓
  ├── register_runway_vertex_tokens() → 8 runway L:Vars ✓
  ├── register_pitch_ladder_tokens() → 5 pitch L:Vars ✓
  └── lvar_init() → resolves LVAR_* token table ✓

  *** MISSING *** → Deploy L:Var tokens NEVER REGISTERED
  → g_hud.deploy.tok_deploy_lvar = 0 (never assigned)
  → g_hud.deploy.tok_deploy_pct  = 0 (never assigned)
  → Root cause: g_hud is `static` to main.cpp, inaccessible from module.cpp
```

### 2.2 Pre-Update

```
gauge_callback_pre_update() [module.cpp:168]
  └── module_update_read_vars() → reads all SimVars ✓
      → g_state.hud_power_on = (L:HUD_POWER_SWITCH >= 0.5) ✓
```

### 2.3 Project Phase — Deployment Detection **BROKEN**

```
module_update_project() [main.cpp:388]
  ├── hud_deployment_update() [main.cpp:528]
  │   ├── ds->initialised=true ✓
  │   ├── ds->use_deploy_lvar = true (from config) ✓
  │   ├── ds->tok_deploy_lvar == 0 (NEVER RESOLVED from module.cpp) ❌
  │   │   └── deploy_raw stays at 1.0 (default fallback)
  │   ├── ds->tok_deploy_pct == 0 (NEVER RESOLVED) ❌
  │   │   └── pct path skipped
  │   └── ds->phase = HUD_DEPLOY_DEPLOYED (always, since fraction ≈ 1.0) ❌
  │
  ├── combiner_geometry_update() [main.cpp:535]
  │   ├── cg->panel_x/y/w/h from profile ✓
  │   ├── cg->scale_x = screen_w / 1024.0 (assumes panel space)
  │   ├── cg->scale_y = screen_h / 1024.0
  │   ├── *** NO FOV/ZOOM/MULTI-MONITOR COMPENSATION *** ❌
  │   └── cg->valid = true ✓
  │
  ├── collimation_update() [main.cpp:510]
  │   ├── Tracks eye delta in body frame ✓ (but only static eye offset)
  │   ├── Leaky integrator with 0.995 decay ✓
  │   ├── Clamp to max 0.15m ✓
  │   └── cc->active = (correction_mag_m > 0.001) ✓
  │
  └── (remaining computations) ✓
```

### 2.4 Publish Phase — L:Var Emission

```
module_update_publish() [main.cpp:987]
  ├── LVAR_SCREEN_CX = 512.0 (HARDCODED!) ❌
  │   └── Should be win_w * 0.5
  ├── LVAR_SCREEN_CY = 512.0 (HARDCODED!) ❌
  ├── LVAR_COMB_X/Y/W/H from profile ✓
  │
  ├── LVAR_HUD_DEPLOY_PHASE = g_hud.deploy.phase ✓ (but always DEPLOYED)
  ├── LVAR_HUD_DEPLOY_FRACTION = g_hud.deploy.deployment_fraction ✓
  ├── LVAR_HUD_DEPLOY_POWER = g_hud.deploy.power_on ✓
  │
  ├── LVAR_COMB_SCREEN_X/Y/W/H = combiner_geom.screen_* ✓
  ├── LVAR_OPTICAL_CX/CY = combiner_geom.optical_cx/cy ✓
  │
  ├── LVAR_COLL_SCREEN_DX = correction_vector.x * scale_x
  │   *** BUG: correction_vector is body-frame METRES, scale_x is dimensionless *** ❌
  │   *** Should use focal_px * atan(delta_m / distance_m) ***
  ├── LVAR_COLL_SCREEN_DY = same issue ❌
  │
  ├── LVAR_HUD_RENDER_IN_COMBINER = combiner_geom.valid ? 1.0 : 0.0 ✓
  ├── LVAR_HUD_COLLIMATED = collimation_cc.active ? 1.0 : 0.0 ✓
  │
  └── (symbology L:Vars) ✓
```

### 2.5 JS Render Path — VERIFIED

```
hud_overlay.html loads:
  <script src="conformal_renderer.js">    → ONLY active renderer ✓
  (hud_overlay.js exists on disk but is NOT loaded by HTML)

conformal_renderer.js frame():
  ├── fit_canvas() ✓
  ├── read L:C_HUD_Deploy_Phase → skips if < 1.5 ✓
  ├── read L:C_HUD_Deploy_Fraction → modulates alpha ✓
  ├── ctx.save()
  │   ├── ctx.translate(coll_dx, coll_dy)  ← collimation compensation
  │   ├── ctx.clip(combiner_rect)           ← combiner clipping
  │   ├── (all symbology inside clip region) ✓
  │   └── ctx.restore()
  └── requestAnimationFrame(frame)
```

---

## 3. Feature-by-Feature Reality Audit

### 3.1 `ctx.clip`

| File | Line(s) | Classification |
|------|---------|----------------|
| `panel/HUD/conformal_renderer.js` | 1091 | **VERIFIED** — clips to combiner rect before drawing all symbology |
| `panel/HUD/hud_overlay.js` | 233 | **DEAD CODE** — file exists but is NOT loaded by HTML |

### 3.2 `translate()` (Collimation Correction)

| File | Line(s) | Classification |
|------|---------|----------------|
| `panel/HUD/conformal_renderer.js` | 1084 | **PARTIALLY IMPLEMENTED** — translate exists but units are suspect |
| `panel/HUD/hud_overlay.js` | — | **DEAD CODE** — file not loaded at runtime |

### 3.3 Camera Correction

| Component | Classification |
|-----------|----------------|
| `src/hud/collimation.cpp` | **VERIFIED** — CameraDelta tracking logic works correctly |
| `src/main.cpp` project phase | **VERIFIED** — collimation_update() called each frame |
| Camera position tracked | **MISSING** — only static eye offset tracked, not dynamic camera |
| Publish path (m→px conversion) | **BUGGY** — body-frame metres incorrectly converted to screen pixels |

### 3.4 Viewport Correction

| Component | Classification |
|-----------|----------------|
| `src/hud/combiner_geometry.cpp` | **STUB** — assumes panel is always 1024×1024 |
| `src/main.cpp` publish | **STUB** — hardcodes LVAR_SCREEN_CX/CY to 512 |
| `panel/HUD/conformal_renderer.js` | **STUB** — uses canvas dimensions but no zoom/FOV awareness |

### 3.5 FOV Correction

| Component | Classification |
|-----------|----------------|
| Profile-based `hfov_deg`/`vfov_deg` | **VERIFIED** — profiles have FOV values |
| `focal_length_px` from profile | **STUB** — always falls back to hardcoded 520.0 |
| FOV scaling in combiner geometry | **MISSING** — combiner_geometry_update() ignores FOV entirely |
| Zoom handling | **MISSING** — no zoom level tracking whatsoever |

### 3.6 Collimation Correction (Centre)

| Component | Classification |
|-----------|----------------|
| `collimation_update()` logic | **VERIFIED** — tracks deltas, leaky integrator, clamp |
| `collimation_apply()` | **VERIFIED** — adds correction to eye offset |
| Screen-space publish | **BUGGY** — `correction_vector.x * cg->scale_x` is physically wrong |
| Camera-offset → screen pixels | **MISSING** — no proper projection through camera matrix |

### 3.7 Deployment State

| Component | Classification |
|-----------|----------------|
| `HUDDeploymentState` struct | **VERIFIED** — correct fields, phase enum |
| `hud_deployment_init()` | **VERIFIED** — initialises all fields |
| `hud_deployment_update()` | **PARTIALLY IMPLEMENTED** — logic correct BUT deploy tokens never resolved |
| Token registration in module.cpp | **MISSING** — deploy L:Var names never registered as GAUGE_VAR |
| Power L:Var (`L:HUD_POWER_SWITCH`) | **VERIFIED** — registered and working |
| Deploy L:Var (`L:AS1001_HUD`) | **DEAD CODE** — defined in HUDDeployConfig, never registered |
| Deploy L:Var (`L:HUD_DEPLOY`) | **DEAD CODE** — defined for 787, never registered |
| Deploy PCT L:Var (`L:A350_HUD_DEPLOY_PCT`) | **DEAD CODE** — defined for A350, never registered |

### 3.8 HUD Power State

| Component | Classification |
|-----------|----------------|
| `L:HUD_POWER_SWITCH` SimVar read | **VERIFIED** — registered and polled each frame |
| `g_state.hud_power_on` | **VERIFIED** — set correctly each frame |
| Published as LVAR_HUD_DEPLOY_POWER | **VERIFIED** |

### 3.9 `hud_overlay.js` — Status

| Check | Finding |
|-------|---------|
| Loaded by HTML? | **NO** — `panel/HUD/hud_overlay.html` only loads `conformal_renderer.js` |
| Exists on disk? | **YES** — kept for installer/backward compat |
| Contains draw code? | **YES** — has own `frame()`/`draw()` cycle |
| Executes at runtime? | **NO** — not referenced by any HTML or panel config |
| Dual renderer conflict? | **NO** — only one renderer is active |

---

## 4. Broken Link Summary

| # | Pipeline Link | Status | Impact |
|---|--------------|--------|--------|
| 1 | WASM: deploy L:Var name → GAUGE_VAR token | **BROKEN** | PMDG 737/777, 787, A350 deployment detection always reports "deployed" |
| 2 | WASM: body-frame metres → screen pixels for collimation | **BROKEN** | Collimation translate on canvas has physically wrong magnitude |
| 3 | WASM: module_update_publish() → hardcoded 512,512 for screen centre | **BROKEN** | Multi-monitor/ultrawide screen centre offset is wrong |
| 4 | WASM: combiner_geometry_update() ignores FOV/zoom | **MISSING** | Combiner clipping doesn't adjust for zoom/FOV changes |
| 5 | WASM: No camera position tracking for collimation | **MISSING** | Collimation corrects static eye offset instead of dynamic camera movement |
| 6 | WASM: No PMDG 777 native HUD detection or fallback | **MISSING** | 777 always uses Boeing HGS profile, no deploy detection |
| 7 | WASM: 'g_hud' is static to main.cpp | **ARCHITECTURAL** | module.cpp cannot access g_hud.deploy.tok_deploy_lvar to register tokens |
| 8 | JS: ctx.translate() before ctx.clip() | **ORDER ISSUE** | Clip region moves with collimation translate |

---

## 5. Critical Root Cause: Cross-Translation-Unit Token Access

### The Problem

```cpp
// src/main.cpp:161 — g_hud is STATIC to main.cpp
static HUDState g_hud;

// src/main.cpp:528 area — deployment uses g_hud.deploy
hud_deployment_update(&g_hud.deploy, ...);

// src/module.cpp:104-145 — token registration happens here
register_simvar("L:HUD_POWER_SWITCH", &g_state.tok_hud_power);
// But CANNOT access g_hud.deploy.tok_deploy_lvar because it's static!
```

### The Fix

Three options, ordered by preference:

**Option A (Recommended):** Add deploy GAUGE_VAR tokens to `ModuleState` (which IS extern'd):
```cpp
// include/module.h — add to ModuleState
GAUGE_VAR tok_deploy_lvar;
GAUGE_VAR tok_deploy_pct;

// src/module.cpp — register in POST_INSTALL
register_simvar("L:AS1001_HUD", &g_state.tok_deploy_lvar);

// src/hud/hud_deployment.cpp — pass tokens from g_state instead of g_hud
```

**Option B:** Expose g_hud via extern in module.cpp:
```cpp
// include/module.h or separate header
extern HUDState g_hud;
```

**Option C:** Move registration to main.cpp post-install callback (requires MSFS SDK callback infrastructure).

---

## 6. Verification Matrix Summary

| Feature | WASM C++ | L:Var Publish | JS Consume | Canvas Draw | Runtime Verified |
|---------|----------|---------------|------------|-------------|------------------|
| HUD deployment phase | PARTIAL | VERIFIED | VERIFIED | VERIFIED | ❌ (never changes state) |
| Combiner clipping | STUB | VERIFIED | VERIFIED | VERIFIED | ❌ (no FOV/zoom) |
| Collimation correction | VERIFIED (logic) | BUGGY (units) | PARTIAL | PARTIAL | ❌ (wrong units + wrong tracking target) |
| FOV scaling | MISSING | MISSING | MISSING | MISSING | ❌ |
| Viewport handling | STUB | BROKEN | STUB | STUB | ❌ |
| Multi-monitor | MISSING | MISSING | MISSING | MISSING | ❌ |
| Ultrawide support | MISSING | MISSING | MISSING | MISSING | ❌ |
| Deploy L:Var tokens | MISSING | N/A | N/A | N/A | ❌ |
