# HUD Deployment Detection Report
## Phase 4 — Real HUD Integration

### 1. Deployment Detection Architecture

The HUD deployment detection system (`hud_deployment.h` / `hud_deployment.cpp`) tracks the physical state of the HUD combiner glass for each supported aircraft.

### 2. Detection States

```
HUD_DEPLOY_UNKNOWN    (0) → Initial state before first frame
HUD_DEPLOY_STOWED     (1) → HUD glass fully stowed, not visible to pilot
HUD_DEPLOY_TRANSITION (2) → HUD glass in motion (deploying or stowing)
HUD_DEPLOY_DEPLOYED   (3) → HUD glass fully deployed, symbology visible
```

### 3. State Machine

```
                  ┌─────────────────┐
                  │   UNKNOWN (0)   │
                  └────────┬────────┘
                           │
                           ▼
                  ┌─────────────────┐
         ┌───────│   DEPLOYED (3)  │◄───────┐
         │       │  (fraction≥0.85)│        │
         │       └────────┬────────┘        │
         │                │                 │
         │                ▼                 │
         │       ┌─────────────────┐        │
         │       │ TRANSITION (2)  │────────┘  fraction rises above 0.85
         │       │ (0.15<f<0.85)  │────────┐  fraction drops below 0.15
         │       └────────┬────────┘        │
         │                │                 │
         │                ▼                 │
         │       ┌─────────────────┐        │
         └───────│   STOWED (1)    │────────┘
                 │  (fraction≤0.15)│
                 └─────────────────┘
```

### 4. Deployment Detection by Aircraft

#### 4.1 PMDG 737-700/800

- **Power Detection**: `L:HUD_POWER_SWITCH` — reads 0/1 value
- **Deploy Detection**: `L:AS1001_HUD` — HUD animation L:Var from PMDG
- **Deploy Threshold**: fraction ≥ 0.85 = DEPLOYED
- **Stow Threshold**: fraction ≤ 0.15 = STOWED
- **Transition Handling**: EMA smoothing with α = 0.15
- **Edge Cases**: If `L:AS1001_HUD` is unavailable, defaults to DEPLOYED (safe mode)

#### 4.2 PMDG 777-300ER

- **Power Detection**: `L:HUD_POWER_SWITCH` — reads 0/1 value
- **Deploy Detection**: `L:AS1001_HUD` — same as PMDG 737 (shared HGS system)
- **Deploy Threshold**: fraction ≥ 0.85
- **Stow Threshold**: fraction ≤ 0.15
- **Notes**: Identical detection method to PMDG 737. No special handling required.

#### 4.3 WT/Asobo 787-10

- **Power Detection**: `L:HUD_POWER_SWITCH`
- **Deploy Detection**: `L:HUD_DEPLOY` — panel state L:Var
- **Deploy Threshold**: fraction ≥ 0.75 (lower due to different animation curve)
- **Stow Threshold**: fraction ≤ 0.25
- **Panel State**: Uses panel state configuration (`use_panel_state = true`)

#### 4.4 iniBuilds A350

- **Power Detection**: `L:A350_HUD_POWER` — dedicated A350 HUD power L:Var
- **Deploy Detection**: `L:A350_HUD_DEPLOY` + `L:A350_HUD_DEPLOY_PCT` (percentage)
- **Deploy Threshold**: fraction ≥ 0.80
- **Stow Threshold**: fraction ≤ 0.20
- **Percentage L:Var**: `L:A350_HUD_DEPLOY_PCT` gives 0-100, normalized to 0-1

#### 4.5 Fallback Aircraft (FBW A32NX, HEADWIND A330)

- **Power Detection**: `L:HUD_POWER_SWITCH` (generic)
- **Deploy Detection**: None — always treated as DEPLOYED when power is on
- **Notes**: These aircraft don't have animated HUD combiner models, so deployment is always assumed

### 5. Edge Cases Handled

| Edge Case | Handling |
|-----------|----------|
| L:Var unavailable at init | Defaults to DEPLOYED until resolved |
| NaN values from SimConnect | Ignored (EMA holds previous value) |
| Sim pause during deploy | Transition timer freezes, resumes on unpause |
| Power failure during deploy | Immediate transition to STOWED |
| Aircraft change mid-flight | Re-initialised on next frame with new aircraft ID |
| Unknown aircraft ID | Uses DEPLOYED fallback (safe rendering) |

### 6. Performance Impact

- **CPU**: One EMA update per frame (~10 instructions)
- **Memory**: `HUDDeploymentState` structure (~120 bytes)
- **L:Var Writes**: 3 L:Var writes per frame
- **No heap allocation**: All state is statically allocated

### 7. Debugging

The `hud_deployment_debug_log()` function logs deployment state every 600 frames during transitions:

```
[C_HUD] Deploy: phase=TRANSITION  fraction=0.72  timer=3.1s
[C_HUD] Deploy phase: 2 -> 3  (fraction=0.87)
```
