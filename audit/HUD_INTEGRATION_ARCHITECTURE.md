# HUD Integration Architecture Report
## Phase 4 — Real HUD Integration

### 1. Overview

This document describes the architecture for integrating HUD symbology rendering into the aircraft's physical HUD combiner glass, as opposed to a fixed screen overlay. The architecture consists of three layers:

1. **WASM Backend (C++)** — Computes world-referenced projections, detects HUD deployment state, and publishes combiner geometry to L:Vars.
2. **L:Var Bridge** — Shared state interface between WASM and JS layers.
3. **JS/Canvas Frontend** — Reads L:Vars, clips rendering to combiner area, applies collimation correction for viewpoint compensation, and fades during deployment transitions.

### 2. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    MSFS 2024 Simulator                       │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  WASM C++ Module (C_HUD_Runway.wasm)                  │  │
│  │                                                       │  │
│  │  module_update_project():                             │  │
│  │    ├── hud_deployment_update()  → deployment state    │  │
│  │    ├── combiner_geometry_update() → screen-space rect │  │
│  │    ├── collimation_update() → collimation correction  │  │
│  │    └── (existing projection pipeline)                 │  │
│  │                                                       │  │
│  │  module_update_publish():                             │  │
│  │    └── lvar_write() → L:C_HUD_Deploy_Phase, etc.     │  │
│  └───────────────┬───────────────────────────────────────┘  │
│                  │ L:Vars (SimConnect)                      │
│  ┌───────────────▼───────────────────────────────────────┐  │
│  │  HTML/JS Canvas Overlay                              │  │
│  │                                                       │  │
│  │  conformal_renderer.js / hud_overlay.js:              │  │
│  │    ├── read_lvar("L:C_HUD_Deploy_Phase")              │  │
│  │    ├── read_lvar("L:C_HUD_Deploy_Fraction")           │  │
│  │    ├── get_combiner() → screen-space rect             │  │
│  │    ├── ctx.clip(combiner rect)  → clip to HUD glass   │  │
│  │    ├── ctx.translate(coll_dx, coll_dy) → viewpoint    │  │
│  │    └── draw all symbology                             │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 3. Key Components

#### 3.1 HUD Deployment Detection (`hud_deployment.h/.cpp`)

- **Purpose**: Detect whether the HUD combiner glass is physically deployed or stowed.
- **Mechanism**: Reads aircraft-specific L:Vars per frame, applies EMA smoothing to deployment fraction, determines phase (STOWED/TRANSITION/DEPLOYED).
- **Supported Aircraft**:
  - PMDG 737/777: `L:HUD_POWER_SWITCH` + `L:AS1001_HUD`
  - WT 787: `L:HUD_POWER_SWITCH` + `L:HUD_DEPLOY`
  - iniBuilds A350: `L:A350_HUD_POWER` + `L:A350_HUD_DEPLOY` + `L:A350_HUD_DEPLOY_PCT`
- **Published L:Vars**:
  - `L:C_HUD_Deploy_Phase` (0=unknown, 1=stowed, 2=transition, 3=deployed)
  - `L:C_HUD_Deploy_Fraction` (0.0..1.0)
  - `L:C_HUD_Deploy_Power` (0/1)

#### 3.2 Combiner Geometry Management (`combiner_geometry.h/.cpp`)

- **Purpose**: Translate panel-space combiner rectangles from aircraft profiles into screen-space coordinates.
- **Mechanism**: Applies panel-to-screen scaling based on current viewport dimensions, accounts for profile optical centre offsets.
- **Published L:Vars**:
  - `L:C_HUD_CombinerScreen{X,Y,W,H}` — screen-space combiner rect
  - `L:C_HUD_OpticalCX` / `L:C_HUD_OpticalCY` — optical centre

#### 3.3 JS Combiner Clipping

- **Mechanism**: The JS renderer reads screen-space combiner rect and applies `ctx.clip()` before drawing any symbology.
- **Result**: Symbology is only visible within the HUD combiner glass area, matching the physical HUD display.

#### 3.4 Collimation Correction for Viewpoint

- **Mechanism**: The WASM pipeline's existing `collimation_update()` computes head-movement compensation. This is now published as screen-space deltas via `L:C_HUD_Coll_ScreenDX`/`DY`.
- **JS Application**: `ctx.translate(coll_dx, coll_dy)` before drawing symbology, so symbology appears world-referenced despite pilot head movement.

### 4. Data Flow

```
Frame Start
  │
  ├── module_update_read_vars() → reads SimVars, resolves tokens
  │
  ├── module_update_project():
  │   ├── collimation_update() → computes head-movement compensation
  │   ├── hud_deployment_update() → reads deploy L:Vars, determines phase
  │   ├── combiner_geometry_update() → computes screen-space combiner rect
  │   ├── (existing FPV / guidance / runway / flare / rollout computation)
  │   └── (existing telemetry capture)
  │
  └── module_update_publish():
      ├── lvar_write(LVAR_HUD_DEPLOY_PHASE, ...)
      ├── lvar_write(LVAR_HUD_DEPLOY_FRACTION, ...)
      ├── lvar_write(LVAR_HUD_DEPLOY_POWER, ...)
      ├── lvar_write(LVAR_COMB_SCREEN_X, ...)
      ├── lvar_write(LVAR_COMB_SCREEN_Y, ...)
      ├── lvar_write(LVAR_COMB_SCREEN_W, ...)
      ├── lvar_write(LVAR_COMB_SCREEN_H, ...)
      ├── lvar_write(LVAR_OPTICAL_CX, ...)
      ├── lvar_write(LVAR_OPTICAL_CY, ...)
      ├── lvar_write(LVAR_COLL_SCREEN_DX, ...)
      ├── lvar_write(LVAR_COLL_SCREEN_DY, ...)
      ├── lvar_write(LVAR_HUD_RENDER_IN_COMBINER, ...)
      ├── lvar_write(LVAR_HUD_COLLIMATED, ...)
      └── (existing L:var publishing)
```

### 5. Design Decisions

1. **No performance optimization**: As requested, we avoid optimizing for performance. The deployment state is updated every frame (EMA smoothing prevents jitter).

2. **Minimal changes to existing logic**: The HUD deployment and combiner geometry modules are additive — they do not modify existing flight guidance or projection logic.

3. **Fallback compatibility**: If the new Phase 4 L:Vars are not available (legacy aircraft or incomplete deployment configuration), the JS renderer falls back to the existing `L:C_HUD_HUD_Active` flag.

4. **Canvas clipping over individual element clipping**: We use `ctx.clip()` at the canvas level rather than clipping each symbology element individually, which simplifies the code and ensures consistent behaviour.

5. **Smooth transitions**: During deployment/stow transitions, the `deploy_fraction` is used to fade symbology opacity, providing a smooth visual transition rather than abrupt on/off.
