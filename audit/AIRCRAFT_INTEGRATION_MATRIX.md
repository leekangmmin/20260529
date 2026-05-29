# Aircraft-Specific HUD Integration Matrix
## Phase 4 — Real HUD Integration

### 1. Supported Aircraft Overview

| Aircraft | Category | HUD Type | Deployment Detection | Combiner Defined | Symbology Set | PMDG 777 Virtual HUD |
|----------|----------|----------|-------------------|-----------------|---------------|----------------------|
| PMDG 737-800 | Boeing HGS | Physical HGS | ✅ L:Vars | ✅ Profile | Full | N/A (native) |
| PMDG 737-700 | Boeing HGS | Physical HGS | ✅ L:Vars | ✅ Profile | Full | N/A (native) |
| PMDG 777-300ER | Boeing HGS | Physical HGS | ✅ L:Vars | ✅ Profile | Extended | Investigated (see §4) |
| WT/Asobo 787-10 | Boeing HGS | Physical HGS | ✅ L:Vars | ✅ Profile | Full + Tapes | N/A (native) |
| iniBuilds A350 | Airbus HUD | Native HUD | ✅ L:Vars | ✅ Profile | Full | N/A (native) |
| FBW A32NX | Generic | Generic | ✅ Fallback | ✅ Default | Minimal | N/A |
| HEADWIND A330 | Generic | Generic | ✅ Fallback | ✅ Default | Minimal | N/A |

### 2. Deployment Detection Methods

| Aircraft | Power L:Var | Deploy L:Var | Deploy % L:Var | Threshold | Method |
|----------|-------------|--------------|----------------|-----------|--------|
| PMDG 737-800 | `L:HUD_POWER_SWITCH` | `L:AS1001_HUD` | None | 0.85 | Animation tracking |
| PMDG 737-700 | `L:HUD_POWER_SWITCH` | `L:AS1001_HUD` | None | 0.85 | Animation tracking |
| PMDG 777-300ER | `L:HUD_POWER_SWITCH` | `L:AS1001_HUD` | None | 0.85 | Animation tracking |
| WT/Asobo 787-10 | `L:HUD_POWER_SWITCH` | `L:HUD_DEPLOY` | None | 0.75 | Panel state |
| iniBuilds A350 | `L:A350_HUD_POWER` | `L:A350_HUD_DEPLOY` | `L:A350_HUD_DEPLOY_PCT` | 0.80 | Animation + percentage |
| FBW A32NX | `L:HUD_POWER_SWITCH` | None | None | 0.50 | Power only (always deployed) |
| HEADWIND A330 | `L:HUD_POWER_SWITCH` | None | None | 0.50 | Power only (always deployed) |

### 3. Combiner Geometry Definitions

| Aircraft | Panel X | Panel Y | Width | Height | Optical CX | Optical CY | FOV (H×V) |
|----------|---------|---------|-------|--------|------------|------------|------------|
| PMDG 737 | 150 | 250 | 724 | 524 | 512 + offset | 512 + offset | 30° × 22.5° |
| PMDG 777 | 140 | 240 | 744 | 544 | 512 + 2.0 | 512 - 1.0 | 33° × 24° |
| WT 787 | 100 | 200 | 824 | 624 | 512 - 1.0 | 512 + 1.0 | 36° × 26° |
| A350 | 130 | 220 | 764 | 584 | 512 | 512 | 32° × 24° |
| Default | 150 | 250 | 724 | 524 | 512 | 512 | 30° × 22.5° |

### 4. PMDG 777 Virtual HUD Feasibility

**Current Status**: The PMDG 777-300ER uses the same physical HGS system as the PMDG 737. The HUD in the 777 is a native physical HUD, not virtual.

**Feasibility Assessment**:
- **Feasible**: ✅ Yes — the PMDG 777 has a physical HUD combiner that can display symbology
- **Model files**: `SimObjects/Airplanes/PMDG 777-300ER/model/` contains the HUD glass model
- **Panel integration**: The existing `panel.cfg` integration with C_HUD_Runway works for 777
- **Deployment logic**: Uses same `L:HUD_POWER_SWITCH` and `L:AS1001_HUD` L:Vars as the 737
- **Profile**: Already defined in `aircraft_profiles.cpp` with 33°×24° FOV
- **Combiner geometry**: (140, 240) → (744×544) — slightly larger than 737

**Recommendation**: No separate "virtual HUD" installation is needed. The PMDG 777 already has a physical HUD model that integrates with the existing C_HUD_Runway pipeline. The Phase 4 deployment detection and combiner clipping will work automatically for the 777 through the PMDG HGS detection path.

### 5. Required L:Var New Entries (Phase 4)

| L:Var Name | Type | Range | Description |
|------------|------|-------|-------------|
| `L:C_HUD_Deploy_Phase` | Integer | 0-3 | HUD deployment phase |
| `L:C_HUD_Deploy_Fraction` | Float | 0.0-1.0 | Deployment progress |
| `L:C_HUD_Deploy_Power` | Boolean | 0/1 | HUD electrical power |
| `L:C_HUD_CombinerScreenX` | Float | Screen | Combiner left (screen px) |
| `L:C_HUD_CombinerScreenY` | Float | Screen | Combiner top (screen px) |
| `L:C_HUD_CombinerScreenW` | Float | Screen | Combiner width (screen px) |
| `L:C_HUD_CombinerScreenH` | Float | Screen | Combiner height (screen px) |
| `L:C_HUD_OpticalCX` | Float | Screen | Optical centre X (screen px) |
| `L:C_HUD_OpticalCY` | Float | Screen | Optical centre Y (screen px) |
| `L:C_HUD_Coll_ScreenDX` | Float | Pixels | Collimation delta X |
| `L:C_HUD_Coll_ScreenDY` | Float | Pixels | Collimation delta Y |
| `L:C_HUD_RenderInCombiner` | Boolean | 0/1 | Clipping to combiner active |
| `L:C_HUD_Collimated` | Boolean | 0/1 | Collimation correction active |
