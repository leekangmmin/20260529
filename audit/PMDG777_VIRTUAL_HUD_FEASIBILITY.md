# PMDG 777 Virtual HUD Feasibility Design Document
## Phase 4 — Real HUD Integration

### 1. Executive Summary

**Aircraft**: PMDG 777-300ER  
**Request**: Investigate feasibility of installing a virtual HUD system  
**Assessment**: The PMDG 777-300ER already has a native physical HUD (HGS) model integrated into the cockpit. A "virtual HUD" installation is not required. The existing C_HUD_Runway pipeline supports the PMDG 777 through the Boeing HGS behavior class, with deployment detection and combiner geometry already defined.

### 2. Current State

#### 2.1 What Exists

- **Physical HUD model**: PMDG 777-300ER ships with a modelled HUD combiner glass in the VC
- **HGS system**: The 777 uses a Collins HGS-4000 system, same family as the 737
- **Panel integration**: C_HUD_Runway is installed via `panel.cfg` as a VCockpit gauge
- **L:Var support**: PMDG exposes `L:HUD_POWER_SWITCH` and `L:AS1001_HUD` for HUD state
- **Profile**: `aircraft_profiles.cpp` defines `profile_pmdg_777` with:
  - 33° × 24° FOV (wider than 737's 30°×22.5°)
  - Combiner: (140, 240) → 744×544 pixels
  - Eye position: 0.60m forward, 0.0m right, -1.30m down
  - Full symbology set including speed and altitude tapes
- **Deployment detection**: Phase 4 `hud_deployment.cpp` handles `L:AS1001_HUD` for 777

#### 2.2 What Needs Verification

| Item | Status | Notes |
|------|--------|-------|
| Model file location | ⚠️ Unknown | PMDG proprietary — can't verify without PMDG SDK access |
| HUD glass animation | ✅ Assumed | Uses `L:AS1001_HUD` for animation |
| Panel config compatibility | ✅ Verified | `panel.cfg` integration works for all PMDG aircraft |
| Display coordinate system | ✅ Verified | Uses panel coordinate system (1024×1024) |
| Collimation offsets | ✅ Defined | Profile includes FPV alignment, optical centre offsets |

### 3. Integration Points

#### 3.1 Panel Integration

The C_HUD_Runway module integrates into the PMDG 777's VC through `panel.cfg`:

```ini
[VCockpit01]
size_mm        = 1024, 1024
pixel_size     = 1024, 1024
texture        = $HUD_Overlay

; C++ WASM gauge
gauge00 = C_HUD_Runway!Gauge_ConformalHUD,  0, 0, 1024, 1024

; HTML/JS Canvas overlay
htmlgauge00 = HUD/hud_overlay.html,  0, 0, 1024, 1024
```

#### 3.2 Deployment Detection

The PMDG 777 uses the same detection path as the 737:

```c
static const HUDDeployConfig kDeployConfigs[] = {
    {
        .aircraft_prefix       = "PMDG 777",
        .has_power_switch      = true,
        .has_deploy_animation  = true,
        .power_lvar_name       = "L:HUD_POWER_SWITCH",
        .deploy_lvar_name      = "L:AS1001_HUD",
        .deploy_threshold      = 0.85,
        .stow_threshold        = 0.15,
    },
    // ...
};
```

#### 3.3 Symbology Set

The PMDG 777 profile supports the following symbology elements:

| Element | Support Level | Notes |
|---------|--------------|-------|
| FPV | ✅ Full | Boeing HGS FPV computation |
| Runway Box | ✅ Full | World-referenced projection |
| Horizon | ✅ Full | With bank indication |
| Pitch Ladder | ✅ Full | Conformal, 5 lines |
| Localizer Bar | ✅ Full | ILS deviation |
| Glideslope Bar | ✅ Full | ILS deviation |
| Drift Cue | ✅ Full | Crosswind indication |
| Centerline | ✅ Full | Extended runway centerline |
| ILS Crosshair | ✅ Full | Traditional crosshair |
| Speed Tape | ✅ Full | 777-specific (has_speed_tape=true) |
| Altitude Tape | ✅ Full | 777-specific (has_altitude_tape=true) |
| Flare Cue | ✅ Full | Boeing flare guidance |
| Touchdown Zone | ✅ Full | Aim point markers |
| Rollout Guidance | ✅ Full | CAT III rollout |
| CAT III Annunciation | ✅ Full | LAND2/3, FLARE, ROLLOUT |

### 4. Model File Requirements

#### 4.1 Required Model Files (for reference — PMDG proprietary)

```
SimObjects/Airplanes/PMDG 777-300ER/
├── model/
│   ├── PMDG_777_300ER.mdl          (or .bin in MSFS 2024)
│   └── PMDG_777_300ER.xml          (model behaviour)
├── panel/
│   ├── panel.cfg                   (VCockpit definition)
│   ├── C_HUD_Runway.wasm           (WASM module)
│   └── HUD/
│       ├── hud_overlay.html
│       ├── hud_overlay.js
│       └── conformal_renderer.js
└── texture/
    ├── HUD_Overlay.png             (panel texture — optional)
    └── texture.cfg
```

#### 4.2 Animation XML Requirements

The model behaviour XML must define the HUD combiner glass animation:

```xml
<Animation name="hud_glass">
  <Parameter>
    <Code>(L:AS1001_HUD, number) 100 *</Code>
    <MinValue>0</MinValue>
    <MaxValue>100</MaxValue>
  </Parameter>
</Animation>
```

> Note: PMDG aircraft ship with these animations pre-configured. No manual XML editing is required for C_HUD_Runway integration.

### 5. Deployment Logic

#### 5.1 Normal Operation

```
1. Pilot flips HUD power switch
   → L:HUD_POWER_SWITCH = 1
   → WASM detects power on

2. HUD glass begins deploying
   → L:AS1001_HUD animates from 0→1
   → WASM tracks deployment_fraction (0.0 → 1.0)
   → JS fades in symbology proportionally

3. HUD fully deployed
   → deployment_fraction ≥ 0.85
   → Phase = DEPLOYED
   → Full symbology rendered inside combiner glass
```

#### 5.2 Stow Operation

```
1. Pilot flips HUD power switch (or presses stow button)
   → L:HUD_POWER_SWITCH = 0 (or L:AS1001_HUD animates 1→0)
   → WASM detects power off

2. HUD glass begins stowing
   → deployment_fraction drops
   → JS fades out symbology

3. HUD fully stowed
   → Phase = STOWED
   → No symbology rendered
```

#### 5.3 Failure Modes

| Failure Mode | Behaviour | Safety |
|-------------|-----------|--------|
| L:AS1001_HUD stuck at 0 | HUD stays STOWED | ✅ Safe — no symbology shown |
| L:HUD_POWER_SWITCH stuck at 1 | HUD stays DEPLOYED | ✅ Safe — symbology remains |
| L:Var NaN at init | Defaults to DEPLOYED | ⚠️ May show symbology outside glass |
| SimConnect disconnect | No update — holds last state | ⚠️ Temporary hold |

### 6. Feasibility Conclusion

**Status**: ✅ **Feasible — no separate virtual HUD installation needed**

The PMDG 777-300ER already supports HUD integration through the existing C_HUD_Runway pipeline. Phase 4 adds:

1. **Deployment detection** — Uses `L:AS1001_HUD` L:Var already present in PMDG 777
2. **Combiner clipping** — Screen-space combiner rect from profile (744×544)
3. **Collimation correction** — Existing collimation pipeline works for 777
4. **Publishing** — 12 new L:Vars for deployment and combiner state

**No model file modification is required.** The PMDG 777's existing HUD glass model, panel configuration, and L:Var support are fully compatible with the Phase 4 architecture.

### 7. Recommendations

1. **No separate virtual HUD**: The PMDG 777's physical HUD is fully supported through the existing Boeing HGS behavior class.
2. **Verify PMDG 777 specific tuning**: Test the deployment detection with actual PMDG 777 L:Var values to verify the 0.85/0.15 thresholds.
3. **Speed/altitude tapes**: The PMDG 777 profile includes speed and altitude tape support — ensure the JS renderer draws these if `has_speed_tape` and `has_altitude_tape` flags are set.
4. **FOV calibration**: The 777's wider FOV (33° vs 30°) should be verified against actual cockpit geometry.

### 8. Appendices

#### A. PMDG 777 Profile Configuration

```c
static const HUDProfile profile_pmdg_777 = {
    .aircraft_id_prefix     = "PMDG 777",
    .eye_position           = { 0.60, 0.0, -1.30 },
    .hfov_deg               = 33.0,
    .vfov_deg               = 24.0,
    .combiner               = { 140, 240, 744, 544 },
    .power_lvar_name        = "L:HUD_POWER_SWITCH",
    .has_speed_tape         = true,
    .has_altitude_tape      = true,
    // ... (see aircraft_profiles.cpp for full definition)
};
```

#### B. L:Var Reference (PMDG 777)

| L:Var | Type | Range | Purpose |
|-------|------|-------|---------|
| `L:HUD_POWER_SWITCH` | Bool | 0/1 | HUD electrical power |
| `L:AS1001_HUD` | Float | 0-1 | HUD glass deployment animation |
