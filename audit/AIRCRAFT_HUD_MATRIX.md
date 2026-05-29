# Aircraft HUD Integration Matrix
## Phase 5 — Verified Aircraft Compatibility Status

**Date:** 2025-01-XX  
**Methodology:** Code path tracing only. All entries marked "✅" are supported by executable code.  

---

## 1. Full Integration Matrix

| Aircraft | Native HUD | Deployment Detection | Combiner Clipping | Collimation | Additional Symbology | Runtime Verified | Status |
|----------|------------|---------------------|-------------------|-------------|---------------------|------------------|--------|
| PMDG 737-700 | ✅ exists (glass combiner, HGS) | ❌ BROKEN (L:AS1001_HUD never registered) | ⚠️ PARTIAL (no FOV/zoom) | ❌ BROKEN (tracks static eye offset; wrong units) | ✅ published | ❌ | **NON-FUNCTIONAL** |
| PMDG 737-800 | ✅ exists (glass combiner, HGS) | ❌ BROKEN (same as above) | ⚠️ PARTIAL | ❌ BROKEN | ✅ published | ❌ | **NON-FUNCTIONAL** |
| PMDG 777-300ER | ✅ exists (glass combiner, HGS-4000) | ❌ BROKEN (L:AS1001_HUD never registered) | ⚠️ PARTIAL | ❌ BROKEN | ✅ published (incl. speed/alt tapes) | ❌ | **NON-FUNCTIONAL** |
| Asobo 787-10 | ✅ exists (deployable) | ❌ BROKEN (L:HUD_DEPLOY never registered) | ⚠️ PARTIAL | ❌ BROKEN | ✅ published | ❌ | **NON-FUNCTIONAL** |
| WT 787 | ✅ exists (deployable) | ❌ BROKEN (L:HUD_DEPLOY never registered) | ⚠️ PARTIAL | ❌ BROKEN | ✅ published | ❌ | **NON-FUNCTIONAL** |
| FBW A32NX | ❌ no native HUD | ✅ ALWAYS ON (no deploy animation) | ⚠️ PARTIAL | ❌ BROKEN | ✅ published | ❌ | **NON-FUNCTIONAL** |
| Headwind A330 | ❌ no native HUD | ✅ ALWAYS ON | ⚠️ PARTIAL | ❌ BROKEN | ✅ published | ❌ | **NON-FUNCTIONAL** |
| iniBuilds A350 | ✅ exists (deployable) | ❌ BROKEN (L:A350_HUD_DEPLOY/PCT never registered) | ⚠️ PARTIAL | ❌ BROKEN | ✅ published | ❌ | **NON-FUNCTIONAL** |

---

## 2. Detailed Aircraft Analysis

### 2.1 PMDG 737-700 / 737-800

**Native HUD:** ✅ Confirmed. The PMDG 737 includes a full 3D combiner glass model (Collins HGS-4000) that deploys/stows via `L:AS1001_HUD` animation. PMDG's own HUD symbology renders on this glass internally.

**Current Integration:**
- Panel config loads our overlay as a VC panel gauge (panel.cfg: `htmlgauge00 = HUD/hud_overlay.html`)
- Our overlay creates a transparent canvas clipped to the combiner area
- ✅ Profile `profile_pmdg_737` exists with correct combiner rect (150,250 → 724×524)
- ✅ Eye position defined (0.50m forward, 0.0m right, -1.20m down)
- ✅ FOV: 30°×22.5° with Boeing HGS-4000 calibration
- ❌ **C-1**: `L:AS1001_HUD` deploy L:Var is never registered — deployment detection always reports "deployed"
- ❌ No detection of PMDG's internal HUD brightness/standby state
- ✅ Panel clipping ensures symbology only appears within glass area (when rect is correct)

### 2.2 PMDG 777-300ER

**Native HUD:** ✅ Confirmed by `audit/PMDG777_VIRTUAL_HUD_FEASIBILITY.md`. PMDG 777 has physical HUD glass (Collins HGS-4000) with `L:AS1001_HUD` animation. **No retrofit needed.**

**Profile Differences from 737:**
- Wider FOV: 33°×24° (vs 30°×22.5° for 737)
- Combiner: (140,240) → 744×544 (slightly larger than 737's 724×524)
- Eye position: 0.60m forward, -1.30m down (slightly further forward and higher)
- ✅ Speed tape and altitude tape support (`has_speed_tape=true`, `has_altitude_tape=true`)

**Same critical issue as 737:** ❌ L:AS1001_HUD never registered.

### 2.3 Asobo / WT Boeing 787-10

**Native HUD:** ✅ Confirmed. 787 includes deployable HUD panel stowable via cockpit switch.

**Key Issues:**
- ❌ **C-1**: `L:HUD_DEPLOY` is defined in deploy config but never registered as GAUGE_VAR
- ❌ No detection of 787 motor animation state
- ✅ Profile has largest FOV (36°×26°)
- ✅ `has_787_style_power = true`
- **787-specific risks:** The 787 HUD may use different animation than L:AS1001_HUD, requiring separate testing

### 2.4 iniBuilds A350

**Native HUD:** ✅ Confirmed. A350 includes native HUD with dedicated L:Vars.

**Key Issues:**
- ❌ **C-1**: `L:A350_HUD_POWER`, `L:A350_HUD_DEPLOY`, `L:A350_HUD_DEPLOY_PCT` never registered
- ❌ Airbus behavior (`AirbusHUDBehavior`) exists but may not be properly integrated
- ❌ No profile-specific combiner rect (uses default 150,250,724,524)

### 2.5 FBW A32NX / Headwind A330

**Native HUD:** ❌ Neither aircraft includes a real HUD combiner glass. Our overlay renders directly on screen space.

**Issue:** Without a real glass combiner, the "HUD" is functionally a floating overlay. The combiner clipping (which expects a physical glass area) clips to an arbitrary panel rect instead of actual glass geometry. The deployment detection correctly shows always-on since these have no deploy animation.

---

## 3. Deployment Detection Detail

### 3.1 Current Registration Status

```cpp
// module.cpp — what IS registered:
register_simvar("L:HUD_POWER_SWITCH", &g_state.tok_hud_power);  // ✅ Works for all

// module.cpp — what is MISSING:
register_simvar("L:AS1001_HUD", ???);       // PMDG 737/777 → cannot access g_hud.deploy.tok_deploy_lvar
register_simvar("L:HUD_DEPLOY", ???);       // 787 → same problem
register_simvar("L:A350_HUD_DEPLOY", ???);  // A350 → same problem
register_simvar("L:A350_HUD_DEPLOY_PCT", ???); // A350 → same problem
register_simvar("L:A350_HUD_POWER", ???);   // A350 → separate power L:Var
```

### 3.2 Root Cause

`g_hud` is declared `static` in `main.cpp` (line 161). The token registration in `module.cpp` cannot access `g_hud.deploy.tok_deploy_lvar` because it's in a different translation unit and not exposed.

**Fix:** Move the deploy token storage from `HUDDeploymentState` (part of `static HUDState g_hud`) to `ModuleState g_state` (which IS extern'd in `include/module.h`).

### 3.3 What Currently Happens

```
hud_deployment_update(ds, power_switch, dt_s, frame_counter)
  ├── ds->use_deploy_lvar = true
  ├── ds->tok_deploy_lvar == 0    ← ALWAYS TRUE, never registered
  │   └── deploy_raw stays at 1.0 (the initialised default)
  ├── ds->deployment_fraction = 0.997 * fraction + 0.003 * 1.0 ≈ 1.0
  └── ds->phase = HUD_DEPLOY_DEPLOYED    ← ALWAYS TRUE
```

---

## 4. Submission Summary

| Aircraft | Has Working Power Detection? | Has Working Deploy Detection? | Will HUD Disappear When Stowed? |
|----------|----------------------------|-----------------------------|----------------------------------|
| PMDG 737-700/800 | ✅ Yes (L:HUD_POWER_SWITCH) | ❌ No | **No — always visible** |
| PMDG 777-300ER | ✅ Yes | ❌ No | **No — always visible** |
| Asobo 787-10 | ✅ Yes | ❌ No | **No — always visible** |
| WT 787 | ✅ Yes | ❌ No | **No — always visible** |
| FBW A32NX | ✅ Yes | ✅ N/A (no animation) | **Always visible (no glass)** |
| Headwind A330 | ✅ Yes | ✅ N/A | **Always visible (no glass)** |
| iniBuilds A350 | ❌ No (wrong power L:Var) | ❌ No | **No — always visible** |

---

## 5. Collimation Status Per Aircraft

| Aircraft | Camera Position Tracked? | Body→Screen Conversion | JS Apply | Works? |
|----------|-------------------------|------------------------|----------|--------|
| ALL | ❌ No (tracks static eye offset) | ❌ Buggy (metres×scale) | ⚠️ Yes (wrong magnitude) | **No** |

All aircraft share the same collimation implementation via `BoeingHGSBehavior` or `AirbusHUDBehavior`. Neither tracks actual dynamic camera position; both use the static profile eye offset. The screen-space conversion is also wrong for all (see COLLIMATION_VERIFICATION.md).

---

## 6. "Runtime Verified" Status

All entries are currently **NOT runtime verified** because:

1. **Deploy L:Var tokens not registered** → deployment detection never activates
2. **Collimation unit conversion wrong** → screen-space compensation has incorrect magnitude
3. **No in-sim automated testing** — all 1230 unit tests mock SimVar data
4. **FOV/zoom not tracked** → combiner clipping doesn't match HUD glass at non-default zoom

After fixes C-1, C-2, C-3, H-1, H-2 from the remediation plan, runtime verification should be possible.

---

## 7. Priority Matrix

| Aircraft | Priority | Reason |
|----------|----------|--------|
| PMDG 737-800 | **P0** | Primary target — largest user base, real glass exists |
| PMDG 737-700 | **P0** | Same as 737-800 |
| Asobo 787-10 | **P0** | Real glass, base sim aircraft |
| PMDG 777-300ER | **P1** | Same fix as 737 (same L:Var), plus speed/alt tapes |
| WT 787 | **P1** | After Asobo 787 verified |
| iniBuilds A350 | **P2** | Complex — different behavior class, different L:Vars |
| FBW A32NX | **P3** | No glass — overlay only |
| Headwind A330 | **P3** | No glass — overlay only |
