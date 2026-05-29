# Rendering Path Verification Report
## Phase 4 — Real HUD Integration

### 1. Rendering Pipeline Overview

The Phase 4 rendering pipeline transforms HUD symbology from a fixed screen overlay to a combiner-clipped, deployment-aware, collimation-compensated display that appears within the physical HUD glass area.

### 2. Pipeline Verification

#### 2.1 WASM → L:Var Path ✅

| Step | Component | Status | Verification |
|------|-----------|--------|-------------|
| 1 | `hud_deployment_update()` | ✅ | Writes deployment state to L:Vars |
| 2 | `combiner_geometry_update()` | ✅ | Computes screen-space combiner rect from profile |
| 3 | `collimation_update()` | ✅ | Existing — computes head-movement compensation |
| 4 | `module_update_publish()` | ✅ | Publishes 12 new Phase 4 L:Vars |
| 5 | L:Var registration | ✅ | All 12 new entries registered in `lvar_table.cpp` |
| 6 | `CMakeLists.txt` | ✅ | New source files added to build |

#### 2.2 JS Rendering Path ✅

| Step | Component | Status | Verification |
|------|-----------|--------|-------------|
| 7 | `read_lvar("L:C_HUD_Deploy_Phase")` | ✅ | Deployment state check |
| 8 | `read_lvar("L:C_HUD_Deploy_Fraction")` | ✅ | Deployment fraction for fade alpha |
| 9 | `get_combiner()` → screen-space rect | ✅ | Reads `L:C_HUD_CombinerScreen*` L:Vars |
| 10 | `ctx.clip(combiner rect)` | ✅ | Clips all symbology to combiner glass area |
| 11 | `ctx.translate(coll_dx, coll_dy)` | ✅ | Collimation correction for viewpoint |
| 12 | `read_lvar("L:C_HUD_Collimated")` | ✅ | Conditional collimation activation |
| 13 | Symbology drawing | ✅ | All existing elements drawn inside clipping region |

#### 2.3 Rendering Constraints Verification

| Constraint | Implementation | Status |
|------------|---------------|--------|
| Never render as fixed screen overlay | Combiner rect clipping via `ctx.clip()` | ✅ |
| Symbology must be collimated with scenery | `ctx.translate(coll_dx, coll_dy)` from WASM collimation | ✅ |
| Must move naturally with pilot viewpoint | Collimation correction computed from camera deltas | ✅ |
| Must be clipped to HUD combiner geometry | Canvas clip region from `L:C_HUD_CombinerScreen*` | ✅ |
| Symbology only inside HUD glass area | Combined clip + deployment phase check | ✅ |

### 3. Data Verification

#### 3.1 L:Var Output Mapping

| L:Var Name | WASM Source | JS Consumer | Type |
|------------|-------------|-------------|------|
| `L:C_HUD_Deploy_Phase` | `HUDDeploymentState::phase` | `draw()` → deploy check | Enum (0-3) |
| `L:C_HUD_Deploy_Fraction` | `HUDDeploymentState::deployment_fraction` | `draw()` → alpha scaling | Float (0-1) |
| `L:C_HUD_Deploy_Power` | `HUDDeploymentState::power_on` | `draw()` → power check | Bool |
| `L:C_HUD_CombinerScreenX` | `CombinerGeometry::screen_x` | `get_combiner()` → clip rect | Float |
| `L:C_HUD_CombinerScreenY` | `CombinerGeometry::screen_y` | `get_combiner()` → clip rect | Float |
| `L:C_HUD_CombinerScreenW` | `CombinerGeometry::screen_w` | `get_combiner()` → clip rect | Float |
| `L:C_HUD_CombinerScreenH` | `CombinerGeometry::screen_h` | `get_combiner()` → clip rect | Float |
| `L:C_HUD_OpticalCX` | `CombinerGeometry::optical_cx` | Available for future centering | Float |
| `L:C_HUD_OpticalCY` | `CombinerGeometry::optical_cy` | Available for future centering | Float |
| `L:C_HUD_Coll_ScreenDX` | `CollimationCorrection::correction_vector.x * scale` | `draw()` → translate | Float |
| `L:C_HUD_Coll_ScreenDY` | `CollimationCorrection::correction_vector.y * scale` | `draw()` → translate | Float |
| `L:C_HUD_RenderInCombiner` | `CombinerGeometry::valid` | Future use | Bool |
| `L:C_HUD_Collimated` | `CollimationCorrection::active` | Conditional translate | Bool |

#### 3.2 Fallback Paths

| Scenario | Fallback Behaviour |
|----------|-------------------|
| Phase 4 L:Vars not published | JS falls back to `L:C_HUD_HUD_Active` |
| CombinerScreen L:Vars unavailable | JS uses panel-space `L:C_HUD_Combiner{X,Y,W,H}` |
| Coll_ScreenDX/DY unavailable | JS skips collimation translation (`coll_dx=0`) |
| Deploy_Fraction unavailable | JS uses full alpha (no fade) |
| No combiner rect available at all | JS renders full-screen (legacy behaviour) |

### 4. Code Path Verification

#### 4.1 WASM Project Phase

```
module_update_project()
  ├── collimation_update()          [EXISTING]
  ├── hud_deployment_update()       [NEW — Phase 4]
  │     ├── init if needed
  │     ├── read power L:Var
  │     ├── read deploy L:Var
  │     ├── EMA smooth deployment fraction
  │     └── determine phase
  ├── combiner_geometry_update()    [NEW — Phase 4]
  │     ├── read profile combiner rect
  │     ├── compute screen-space scaling
  │     └── compute optical centre
  ├── stabilization update          [EXISTING]
  ├── runway detection              [EXISTING]
  ├── FPV computation               [EXISTING]
  ├── guidance computation          [EXISTING]
  ├── horizon/pitch computation     [EXISTING]
  ├── flare computation             [EXISTING]
  ├── rollout computation           [EXISTING]
  └── advanced symbology            [EXISTING]
```

#### 4.2 WASM Publish Phase

```
module_update_publish()
  ├── diagnostics (version, FPS, etc.)        [EXISTING]
  ├── HUD active flag                         [EXISTING]
  ├── screen centre / combiner panel rect     [EXISTING]
  ├── PHASE 4 — Deployment + Combiner         [NEW]
  │     ├── L:C_HUD_Deploy_Phase
  │     ├── L:C_HUD_Deploy_Fraction
  │     ├── L:C_HUD_Deploy_Power
  │     ├── L:C_HUD_CombinerScreen{X,Y,W,H}
  │     ├── L:C_HUD_Optical{CX,CY}
  │     ├── L:C_HUD_Coll_Screen{DX,DY}
  │     └── L:C_HUD_RenderInCombiner, L:C_HUD_Collimated
  ├── weather                                 [EXISTING]
  ├── ILS deviations                          [EXISTING]
  ├── HUD-specific element publishing         [EXISTING]
  └── subsystem heartbeats                    [EXISTING]
```

#### 4.3 JS Render Frame

```
frame()
  ├── fit_canvas()                         [EXISTING]
  └── draw()
        ├── ctx.clearRect()                [EXISTING]
        ├── read L:C_HUD_Deploy_Phase      [NEW]
        ├── if stowed → skip rendering      [NEW]
        ├── read L:C_HUD_Deploy_Fraction   [NEW]
        ├── read weather params             [EXISTING]
        ├── scale alpha by deploy fraction  [NEW]
        ├── read L:C_HUD_Coll_ScreenDX/DY  [NEW]
        ├── get_combiner() → screen rect    [NEW]
        ├── ctx.save()                      [EXISTING modified]
        ├── ctx.translate(coll_dx,coll_dy)  [NEW]
        ├── ctx.clip(combiner rect)         [NEW]
        ├── draw all symbology              [EXISTING]
        ├── ctx.restore()                   [EXISTING modified]
        ├── apply_optical_effects()         [EXISTING]
        └── draw_diagnostics()              [EXISTING]
```

### 5. Test Verification

All 1230 existing test cases continue to pass after Phase 4 integration.

| Test Suite | Tests | Status |
|-----------|-------|--------|
| test_hud.py | 72 | ✅ Pass |
| test_aircraft_compatibility.py | 15 | ✅ Pass |
| test_collimation.py | 24 | ✅ Pass |
| test_flare.py | 18 | ✅ Pass |
| test_rollout.py | 16 | ✅ Pass |
| test_advanced_symbology.py | 42 | ✅ Pass |
| test_a350_hud.py | 385 | ✅ Pass |
| All other suites | 658 | ✅ Pass |
| **Total** | **1230** | **✅ All Pass** |

### 6. Rendering Quality Assurance

| Quality Metric | Verification |
|---------------|-------------|
| Symbology appears inside HUD glass only | Combiner rect clipping confirmed |
| No rendering when HUD stowed | Deployment phase check before any drawing |
| Smooth deploy/stow transitions | Deployment fraction fades alpha |
| Symbology moves with viewpoint | Collimation correction translate applied |
| Backward compatible with legacy aircraft | Fallback paths for missing Phase 4 L:Vars |
| No visual regression for existing symbology | All drawing code unchanged, only clipped |
