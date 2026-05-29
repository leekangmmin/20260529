# REALISM GAP REPORT — Conformal HUD Runway Symbology (C_HUD_Runway)

**Report version:** 1.0  
**Date:** 2025-05-29  
**Target benchmark:** Boeing HGS (Collins HGS-4000/4000A), Airbus HUD (Thales/Elbit)  
**Evaluated codebase:** v2.7.0 (commit `196f9a638a770d994c466d86a51d3168813c6d`)

---

## Scoring Summary

| Category | Score (0–100) |
|---|---|
| Architecture & Modularity | **85** |
| Performance Infrastructure | **80** |
| HUD Realism (Optical) | **35** |
| Aircraft Compatibility | **55** |
| Collimation Accuracy | **20** |
| Combiner Glass Handling | **40** |
| Camera / Head Tracking | **15** |
| PMDG Integration | **10** |
| MSFS SDK Compliance | **70** |
| Test Coverage | **90** |
| **OVERALL (Boeing HGS benchmark)** | **42 / 100** |

---

## Evaluation Criteria

### 1. Architecture & Structure — 85/100

#### Implemented (confirmed by code):

| Feature | File(s) | Function(s) | Evidence |
|---|---|---|---|
| WASM lifecycle (init/deinit/update) | `src/main.cpp` | `module_init()`, `module_deinit()`, `module_update_read_vars()`, `module_update_project()`, `module_update_publish()` | Lines 105–175, 240–290, 460–1090 |
| Gauge callbacks (POST_INSTALL, PRE_UPDATE, POST_DRAW) | `src/module.cpp` | `gauge_callback_post_install()`, `gauge_callback_pre_update()`, `gauge_callback_post_draw()` | Full file, three callback definitions |
| Multi-aircraft behavior abstraction | `include/hud/aircraft/ihud_aircraft_behavior.h`, `src/hud/aircraft/boeing_hgs_behavior.cpp`, `src/hud/aircraft/airbus_hud_behavior.cpp` | `IHudAircraftBehavior` virtual interface, `BoeingHGSBehavior`, `AirbusHUDBehavior` | Full interface class; concrete impls 410 lines each |
| Aircraft detection engine | `src/hud/aircraft_detector.cpp` | `aircraft_detect()`, `hud_behavior_create()` | Prefix+substring matching against registry; statically allocated singletons |
| Aircraft profiles database | `src/hud/aircraft_profiles.cpp` | `hud_profile_match()`, `hud_profile_by_index()` | 5 profiles: PMDG 737, PMDG 777, ASOBO 787, WT 787 alt, Default |
| Subsystem heartbeat watchdog | `src/main.cpp` | watchdog logic in `module_update_publish()` | Lines 1340–1390: 9 subsystem heartbeats monitored |
| L:Var token table | `src/lvar_table.cpp` | `lvar_init()`, `lvar_write()` | 200 L:Var token slots |
| Runtime perf instrumentation | `include/module.h` (structs), `src/main.cpp` (calls) | `perf_begin()`, `perf_measure()`, `percentile_compute()` | 17 SubsystemIDs, P50/P95/P99 histograms |
| Frame pacing validation | `include/module.h` (structs) | `PacingState` with anomaly detection | Hitch >50ms, stutter >33ms, circular log of 32 events |
| Binary telemetry export | `include/hud/telemetry.h`, `src/hud/telemetry.cpp` | `telemetry_recorder_start/stop`, compression, replay | `.chtelem` format, ZLIB compression, SHA-256 checksums |

#### Not implemented / Confirmation impossible:

| Feature | Status | Reason |
|---|---|---|
| Heap-free WASM guarantee | **Confirmed** | All allocations are static/global; `-nostdlib`, `-fno-exceptions`, `-fno-rtti` in CMakeLists.txt |
| Modular plugin interface (e.g. WASM plugins) | **Not found** | No dynamic loading mechanism; entire module is monolithic |
| Real-time config reload | **Not found** | No file watcher or hot-reload mechanism exists |

---

### 2. Performance Infrastructure — 80/100

#### Implemented:

| Feature | File | Evidence |
|---|---|---|
| Per-subsystem microsecond timing | `src/main.cpp` lines 260–285, `include/module.h` SubsystemHistogram | perf_begin/perf_measure/perf_end wrappers around each subsystem block |
| Rolling P50/P95/P99 percentiles | `include/module.h` SubsystemHistogram, percentile_compute | 1024-sample rolling window, 32-bin histogram |
| Frame hitch/stutter detection | `include/module.h` PacingState | >50ms hitch, >33ms stutter thresholds |
| Pause/unpause handling | `include/module.h` PacingAnomalyType ANOMALY_PAUSE | Detection + stabilization reset |
| Memory leak detection (linear regression) | `include/module.h` OpticalStabilityMetrics + long-duration tests | Test infrastructure exists in tests/ |

#### Gaps:

| Gap | Severity | Evidence |
|---|---|---|
| No GPU-side timing (WASM → Canvas latency) | **Medium** | JS bridge latency is tracked (`SUBSYS_JS_BRIDGE`) but no actual measurement mechanism found |
| No draw-call count optimization | **Low** | No batching or draw-call reduction logic visible |
| No L:Var write coalescing | **Medium** | `lvar_write()` is called per-symbol per-frame; 100+ L:Var writes per frame |
| No WASM→JS transfer size metrics | **Medium** | L:Var values are doubles; no compression for bulk transfer |

---

### 3. HUD Realism (Boeing HGS Benchmark) — 35/100

#### A. Actually implemented features (with code evidence):

| Feature | File | Function(s) | Notes |
|---|---|---|---|
| FPV (Flight Path Vector) | `src/hud/fpv.cpp` | `fpv_compute()`, `fpv_project_to_hud()` | Computes velocity vector from groundspeed/VS/heading |
| Horizon line | `panel/HUD/conformal_renderer.js` | `draw_horizon()` | Lines 339–385: pitch-dependent Y, bank rotation |
| Pitch ladder | `panel/HUD/conformal_renderer.js` | `draw_pitch_ladder()` | Lines 387–422: ±5°, ±10°, ±15° lines |
| Runway outline box | `panel/HUD/conformal_renderer.js` | `draw_runway()` | Lines 271–337: 4-vertex quad from projected L:Vars |
| ILS crosshair (loc/GS) | `panel/HUD/conformal_renderer.js` | `draw_guidance()` | Lines 473–516 |
| Drift cue (diamond) | `panel/HUD/conformal_renderer.js` | `draw_drift_cue()` | Lines 518–531 |
| Flare cue | `panel/HUD/conformal_renderer.js` | `draw_flare()` | Lines 533–587: circle rises from TD point |
| Rollout guidance | `panel/HUD/conformal_renderer.js` | `draw_rollout()` | Lines 592–661: centerline/command/deviation |
| CAT III / LAND annunciations | `panel/HUD/conformal_renderer.js` | `draw_cat_annunciations()` | Lines 709–787: priority sorted text lines |
| Phosphor persistence effect | `src/hud/optical.cpp` (via visual_response.cpp) | `visual_response_compute()` | EMA-based brightness with configurable decay |
| Bloom intensity | `src/hud/visual_response.cpp` | `visual_response_compute()` | brightness-dependant bloom |
| Edge fade (combiner vignette) | `panel/HUD/conformal_renderer.js` | `draw_runway()` etc use `get_combiner()` clipping | Canvas clip to combiner rect |
| Weather-adaptive opacity/linewidth | `src/main.cpp` | `weather_compute_params()` → L:C_HUD_WeatherLineW, L:C_HUD_WeatherAlpha | Visibility-based |
| Depth illusion (parallax from head movement) | `src/hud/depth_illusion.cpp` | `depth_illusion_compute()` | Uses camera delta for parallax offsets on runway corners |

#### B. Features that APPEAR implemented but are NOT functional:

| Claimed Feature | File | Reality | Evidence |
|---|---|---|---|
| Semi-collimated rendering | `include/hud/collimation.h`, `src/hud/collimation.cpp` | **Camera delta compensation ONLY** — tracks eye offset changes and computes a correction vector. This is NOT true collimation (which requires optical infinity projection through a combiner). The correction is applied as a body-frame offset, not a world-aligned collimation. | `collimation_update()` computes `correction_vector = -delta_body * gain` and adds it to eye offset. No ray-to-infinity math, no collimation matrix, no world-aligned projection plane. |
| True conformal runway projection | `src/hud/runway_projection.cpp`, `panel/HUD/conformal_renderer.js` | **Screen-space coordinate projection** — runway corners are projected from world to screen using focal length + attitude matrix, then drawn as 2D canvas coordinates. This is perspective projection, not true conformal/collimated rendering. | Runway is drawn at screen positions from L:C_HUD_RunwayV{n}_{X,Y}. When head moves, these positions shift (via collimation compensation). True conformal HUD would keep runway fixed relative to the world while symbology overlays shift with head. |
| Combiner glass clipping | `panel/HUD/hud_overlay.js` lines 56–67, `panel/HUD/conformal_renderer.js` | **Canvas clip rect implementation** — `ctx.clip()` applied from L:C_HUD_CombinerScreenX/Y/W/H. This clips symbology to a rectangle. A real combiner glass is not a simple rectangle; it has complex shapes, variable transmission, and chromatic effects. | `get_combiner()` returns simple rect. No shape mask, no variable opacity profile, no double-sided rendering. |
| EVS (Enhanced Vision System) | `src/hud/evs.cpp` | **Simulated EVS** — contrast boost and fog penetration computed from visibility. Not connected to any actual MSFS camera/IR sensor. | `evs_compute()` only adjusts contrast and brightness parameters. No sensor data ingestion. |
| Night vision / IR capability | `include/hud/evs.h` | No actual NVG/IR rendering path | Only contrast/brightness adjustments |

#### C. Features that exist ONLY in design (no executable code):

| Feature | Header/Declaration | Implementation Status |
|---|---|---|
| `L:AS1001_HUD` for PMDG deploy animation | `src/hud/hud_deployment.cpp` line 32 | Declared in config, token lazily resolved. **Verification needed**: PMDG 737/777 may not expose `L:AS1001_HUD`; actual variable name differs per PMDG version. |
| 787 panel-state based deployment | `src/hud/hud_deployment.cpp` lines 55–58 | `use_panel_state = true` but no panel state reading code path found in `hud_deployment_update()` |
| `L:AS1001_HUD` deploy percentage | `src/hud/hud_deployment.cpp` | `deploy_pct_lvar` is NULL for all Boeing configs; only A350 has percentage L:Var |
| TrackIR / Tobii native API | `src/main.cpp` line 485 comment | Comment only: "Apply live camera offsets from calibration (TrackIR/head tracking)". No actual TrackIR SDK calls or Tobii API integration. Calibration values are manual. |
| VR-specific rendering | `src/hud/visual_response.cpp` | Constants named `VR_*` refer to "Visual Response", not Virtual Reality. No stereo rendering, no HMD position tracking. |
| PMDG 777 native HGS integration | `include/hud/aircraft_profiles.h` + `src/hud/aircraft_profiles.cpp` | Profile exists for PMDG 777 but as a **separate overlay**, not integrated with PMDG's real HGS. The project creates a virtual HUD on the panel texture; it does not read from or override the PMDG HGS display. |

#### D. Features REQUIRED for real Boeing HGS equivalence:

| Required Feature | Boeing HGS Reference | Current Gap | Priority | Difficulty |
|---|---|---|---|---|
| **True optical collimation** | HGS uses collimating optics to project symbology at infinity. Symbology is world-fixed, not screen-fixed. | Current "collimation" is camera-delta compensation in body frame. No infinite-focus projection. No world-aligned clipping. | **CRITICAL** | **Very Hard** (requires rewriting projection pipeline) |
| **Combiner glass physical model** | Real combiner uses partial reflection (70/30 or 50/50 beam splitter), AR coating, shaped glass with variable thickness | Current: simple clip rectangle. Missing: reflectivity gradient, chromatic shift, ghosting, veiling glare, see-through world blending | **HIGH** | **Hard** (requires fragment shader or advanced Canvas compositing) |
| **Head/Eye position tracking** | HGS uses the aircraft's design eye position fixed relative to the combiner. Real crew adjust seat/eye. | Current: manual `eye_offset_*` calibration parameters. No automatic detection. | **HIGH** | **Medium** (MSFS camera position SimVar available) |
| **TrackIR / Tobii native API** | Not applicable (military HGS doesn't use consumer head tracking) | **For MSFS**: TrackIR and Tobii provide head position data via SimVars or window messages | **HIGH** | **Medium** (read CAMERA POSITION SimVar + apply) |
| **VR stereo rendering** | N/A | No stereo separation, no per-eye projection, no HMD position integration | **MEDIUM** | **Hard** (requires full stereo pipeline) |
| **PMDG HGS data bus integration** | PMDG 777 models the real HGS with actual PFD/HUD symbology computed by PMDG SDK | Current system is an independent overlay. To integrate, must read PMDG's internal L:Vars or use PMDG SDK for symbology | **MEDIUM** | **Very Hard** (PMDG SDK is proprietary, may not expose HGS data) |
| **Real HUD declutter logic** | Boeing HGS declutters symbology based on flight phase, engine power, failures, warnings | Current: `declutter_compute()` is a stub that checks visibility and phase. No failure-mode declutter, no warning integration. | **MEDIUM** | **Medium** |
| **HUD failure/warning flags** | HGS has BIT (Built-In Test), failure flags, miscompare detection | No failure injection, no BIT simulation, no cross-check logic | **LOW** | **Medium** |
| **Runway centerline extension** | HGS shows extended centerline with appropriate perspective | Current: runway box only. Centerline is labelled as available (`HUD_SYM_CENTERLINE`) but no drawing code confirmed. | **MEDIUM** | **Low** (2-3 canvas lines) |
| **Speed tape / altitude tape** | Boeing HGS shows speed and altitude tapes on left/right edges | Profiles for 777/787 declare `has_speed_tape`/`has_altitude_tape` but no rendering code in JS | **MEDIUM** | **Medium** |
| **ILS frequency-based runway selection** | HGS auto-selects runway based on tuned ILS frequency | Current: NAV1 frequency read (`g_state.nav1_freq_mhz`) but runway matching logic not verified | **MEDIUM** | **Low** |
| **Approach path indicator (VASI/PAPI)** | HUD shows PAPI lights or approach path indicator | Not implemented | **LOW** | **Low** |
| **Real HGS font / symbology styling** | Boeing HGS uses specific stroke widths, font sizes, and placement rules | Current: generic green monochrome Canvas drawing | **LOW** | **Medium** |

---

### 4. Aircraft Compatibility — 55/100

#### Implemented:

| Aircraft | Profile | Behavior Class | Detection | Evidence |
|---|---|---|---|---|
| PMDG 737-800/700 | `profile_pmdg_737` | `BoeingHGSBehavior` | Prefix "PMDG 737" | `src/hud/aircraft_profiles.cpp` lines 65–78, `src/hud/aircraft_detector.cpp` line 43 |
| PMDG 777-300ER | `profile_pmdg_777` | `BoeingHGSBehavior` | Prefix "PMDG 777" | `src/hud/aircraft_profiles.cpp` lines 86–143, `src/hud/aircraft_detector.cpp` line 44 |
| ASOBO 787-10 | `profile_wt_787` | `BoeingHGSBehavior` | Prefix "ASOBO BOEING 787" | `src/hud/aircraft_profiles.cpp` lines 150–207 |
| WT 787-10 | `profile_wt_787_alt` | `BoeingHGSBehavior` | Prefix "WT_787" | `src/hud/aircraft_profiles.cpp` lines 214–271 |
| iniBuilds A350 | (part of Airbus behavior) | `AirbusHUDBehavior` | Prefix "INI A350", substring "A350" | `src/hud/aircraft_detector.cpp` lines 36–40 |
| FBW A32NX | (default profile) | `BoeingHGSBehavior` (fallback) | Substring "A32NX" | `src/hud/aircraft_detector.cpp` lines 56–58 |
| Headwind A330 | (default profile) | `BoeingHGSBehavior` (fallback) | Substring "A330" | `src/hud/aircraft_detector.cpp` lines 40–41, 56–58 |

#### Gaps:

| Gap | Details | Evidence |
|---|---|---|
| **No PMDG HGS override path** | The project creates an independent overlay. For PMDG 777 (which has real HGS), the user would see two HUDs: the PMDG native + this overlay. No detection or suppression of native HUD. | No code references to reading PMDG HUD state or suppressing PMDG HGS rendering. |
| **iniBuilds A350 incomplete** | `include/hud/aircraft/airbus_hud_behavior.h` header not found (wc reports error). Header file missing from repository. | `wc -l include/hud/aircraft/airbus_hud_behavior.h` → file not found |
| **A350-specific modules may be dead code** | 11 A350-specific source files exist (fpv_controller, horizon, autoland, landing_energy, runway_augmentation) but may not be called from the pipeline | `airbus_hud_behavior.cpp` only calls generic `fpv_compute()` not A350-specific controllers |
| **No PMDG 747-8 support** | Listed in `module.cpp` allowlist but no profile | `src/module.cpp` line 23: "ASOBO BOEING 747-8I" |
| **No compatibility fallback for unknown aircraft** | Unrecognized aircraft get default profile + Boeing behavior, but there's a `suppressed` flag that is never checked in rendering pipeline | `aircraft_detect()` sets `supported=false` but behavior returns Boeing singleton |

---

### 5. Collimation Accuracy — 20/100

#### Current implementation:

| Aspect | Implementation | Analysis |
|---|---|---|
| Camera delta tracking | `collimation_update()` in `src/hud/collimation.cpp` | Tracks body-frame eye offset delta with leaky integrator (α=0.995). Corrects eye offset by `-delta_body * gain` where gain=0.85. Max compensation 0.15m. |
| Stabilized eye position | `collimation_apply()` in `include/hud/collimation.h` | Adds correction vector to raw eye offset |
| Compensation mechanism | Body-frame vector adjustment | This is **not collimation** — it's a low-pass filter on eye position. True collimation requires world-aligned projection. |

#### Why this is NOT true collimation:

Real Boeing HGS collimation:
1. Symbology is projected through a lens system that creates collimated (parallel) light rays
2. The symbology appears at optical infinity regardless of eye position
3. As the pilot moves their head, symbology stays fixed relative to the outside world
4. The combiner glass reflects the collimated image while allowing outside light to pass through

Current implementation:
1. Tracks how much the virtual camera has moved
2. Applies an inverse offset to the projection origin
3. This keeps symbology in the same screen position despite camera movement
4. **But** it doesn't create world-fixed symbology — it creates screen-fixed symbology with a correction term

**Critical gap**: When the camera moves laterally, the runway box should shift in screen space (parallax from eye movement). The current implementation tries to cancel this shift, which is the OPPOSITE of what real collimation does. In a real HGS, the runway IS world-fixed and the HUD symbology world-fixed — there should be NO shift with head movement. The current code ADDS an inverse shift to compensate, but since the base projection already shifts with head movement (because it's a perspective projection from the camera position), the compensation may over-correct or under-correct.

---

### 6. Combiner Glass Handling — 40/100

#### Implemented:

| Feature | File | Evidence |
|---|---|---|
| Combiner rectangle (panel space) | `include/hud/aircraft_profiles.h` `HUDCombinerRect` | Declared with x, y, width, height per profile |
| Combiner rect → screen space scaling | `src/hud/combiner_geometry.cpp` `combiner_geometry_update()` | Full implementation: scales 1024x1024 panel rect to viewport |
| Combiner clipping in JS | `panel/HUD/hud_overlay.js` `get_combiner()` + `ctx.clip()` | Canvas clip to combiner rect |
| Combiner L:Var publishing | `src/main.cpp` lines 1038–1041 | LVAR_COMB_SCREEN_{X,Y,W,H} published every frame |
| Optical center computation | `src/hud/combiner_geometry.cpp` | `optical_cx/cy` = combiner center + profile offset |
| Panel↔Screen coordinate conversion | `include/hud/combiner_geometry.h` | `combiner_panel_to_screen()`, `combiner_screen_to_panel()` inline helpers |
| Combiner containment test | `include/hud/combiner_geometry.h` | `combiner_contains_point()` with margin |
| Screen rect query | `include/hud/combiner_geometry.h` | `combiner_screen_rect()` |
| Geometry validation | `src/hud/combiner_geometry.cpp` | `combiner_geometry_validate()` dimension/sanity checks |

#### Gaps:

| Gap | Description | Impact |
|---|---|---|
| **Rectangular only** | Real combiner glass has curved/beveled edges, cutouts for the airframe structure | Visual realism |
| **No variable transparency** | Real combiner has 70/30 or 50/50 beam splitter coating with reflectivity gradient | Optical realism |
| **No chromatic effects** | No thin-film interference, no anti-reflective coating spectrum shift | Optical realism |
| **No ghosting** | Real combiners produce secondary reflections (ghost images) | Optical realism |
| **No veiling glare** | Bright outside scenes wash out HUD symbology; not simulated | Optical realism |
| **No dual-surface rendering** | Real combiner has front and back surface reflections | Optical realism |
| **No sun position / glare modeling** | Sun angle affects HUD readability | Optical realism |

---

### 7. Camera / Head Tracking — 15/100

#### Implemented:

| Feature | Evidence |
|---|---|
| Calibration eye offset (manual) | `HUDSettings` struct: `eye_offset_forward_m`, `eye_offset_right_m`, `eye_offset_down_m` |
| Live camera offset comment | `src/main.cpp` line 485: comment only |
| Camera delta tracking | `src/hud/collimation.cpp` full implementation |

#### Gaps:

| Gap | Details | Priority |
|---|---|---|
| **No TrackIR API** | No TrackIR SDK calls, no TrackIR SimVar reading | **CRITICAL** |
| **No Tobii API** | No Tobii eye tracker integration | **CRITICAL** |
| **No MSFS camera SimVar reading** | MSFS exposes `CAMERA POSITION` SimVars but they are not read | **HIGH** |
| **No VR HMD position** | `VR_*` constants in `visual_response.cpp` are about Visual Response, not Virtual Reality. No stereo rendering, no HMD tracking | **HIGH** |
| **No automatic eye position** | The design eye point is from the profile; no dynamic adjustment for pilot seat position | **MEDIUM** |

---

### 8. PMDG Integration — 10/100

#### Claimed vs Reality:

| Claim | Reality | Evidence |
|---|---|---|
| PMDG 777 HUD support | Profile exists but as **independent overlay** — NOT integrated with PMDG's real HGS | PMDG 777-300ER has a fully modeled HGS (Collins HGS-4000A). This project draws on top of it. Users will see BOTH HUDs. |
| PMDG 737 HUD support | Same as above — overlay, not integrated | PMDG 737 has optional HUD modeled; this is an overlay |
| L:AS1001_HUD deployment | Variable name assumed but never verified against PMDG SDK documentation | `src/hud/hud_deployment.cpp` line 32: `"L:AS1001_HUD"`. PMDG may use different L:Var names per aircraft version. |

#### Required for real integration:

| Requirement | Difficulty | Notes |
|---|---|---|
| Detect PMDG native HUD state (on/off/mode) | **Hard** | Need PMDG SDK or reverse-engineered L:Vars |
| Read PMDG HGS symbology data | **Very Hard** | PMDG doesn't expose HUD symbology via L:Vars directly |
| Suppress PMDG HUD when C_HUD active | **Hard** | Would require modifying panel.cfg or using model animation overrides |
| Dual-mode: Use PMDG HGS for primary, C_HUD for augmentation | **Very Hard** | Requires synchronizing both systems |

---

### 9. MSFS SDK Compliance — 70/100

#### Strengths:

| Area | Evidence |
|---|---|
| WASM module format (.wasm) | `CMakeLists.txt` clang → wasm32-unknown-unknown toolchain |
| Gauge API (MSFS/Legacy/gauges.h) | `src/module.cpp` uses PANEL_SERVICE_POST_INSTALL, PRE_UPDATE, POST_DRAW properly |
| L:Var publishing | `lvar_write()` via MSFS legacy gauge API |
| SimVar reading | `gauge_get_var_by_name()` for all tokens |
| sGaugeDrawData usage | `module_update_project()` receives `sGaugeDrawData* dd` for winWidth/winHeight |

#### Weaknesses:

| Area | Issue | Impact |
|---|---|---|
| MSFS 2024 compatibility | Some APIs may have changed; the project uses MSFS 0.23+ SDK | **Medium** — test with MSFS 2024 |
| WASM memory limit | `--initial-memory=16777216` (16MB), `--max-memory=67108864` (64MB) | **Low** — sufficient for current code |
| No HTML/JS gauge API usage | Uses `htmlgauge00` in panel.cfg but doesn't use `CoherentGetSimVar`/`CoherentCall` properly | **Medium** — the JS overlay reads L:Vars via `SimVar.GetSimVarValue()` which works but has higher latency than `gauge_get_var_by_name()` |

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| L:AS1001_HUD token never resolves (PMDG doesn't expose this L:Var) | **High** | HUD always reports DEPLOYED even when physically stowed | Verify against actual PMDG aircraft; add fallback to L:HUD_POWER_SWITCH only |
| A350 header missing breaks A350 build | **Medium** | Airbus HUD behavior may not compile | `include/hud/aircraft/airbus_hud_behavior.h` missing from repository |
| Collimation over-correction causes symbology swim | **Medium** | Leaky integrator (α=0.995) accumulates error over long flights | Needs real-flight testing with TrackIR |
| Performance cliff with all L:Vars enabled | **Low-Medium** | 200+ L:Var writes per frame may exceed MSFS L:Var update budget | Profile and limit writes to visible symbols only (Phase 5) |
| Dual HUD rendering with PMDG aircraft | **High** | User sees both PMDG HGS and C_HUD overlay simultaneously | Needs PMDG HUD detection + automatic suppression |
| Combiner clipping incompatible with ultrawide/FOV | **Medium** | Combiner rect hardcoded to 1024x1024 panel space; scales linearly | Dynamic viewport detection needed |

---

## Prioritized Roadmap

### Phase A — Critical Fixes (0–3 months)

| # | Task | Difficulty | Priority |
|---|---|---|---|
| A1 | Fix missing `airbus_hud_behavior.h` header | **Low** | **Critical** |
| A2 | Add MSFS camera position SimVar reading for head tracking | **Medium** | **Critical** |
| A3 | Verify and fix L:AS1001_HUD → actual PMDG deployment L:Var mapping | **Medium** | **Critical** |
| A4 | Add PMDG native HUD detection (to prevent dual rendering) | **Hard** | **High** |
| A5 | Implement proper combiner clipping in JS (bezier/curved mask, not just rect) | **Medium** | **High** |

### Phase B — Optical Realism (3–6 months)

| # | Task | Difficulty | Priority |
|---|---|---|---|
| B1 | Implement true world-aligned collimation (reproject symbology to world-space, not screen-space) | **Very Hard** | **Critical** |
| B2 | Add combiner glass transparency gradient (vignette, not just clip) | **Medium** | **High** |
| B3 | Implement HUD brightness auto-control (ambient light sensor SimVar) | **Medium** | **High** |
| B4 | Add phosphor persistence rendering (trail effect on moving symbols) | **Medium** | **Medium** |
| B5 | Implement veiling glare simulation (bright backgrounds wash out HUD) | **Hard** | **Medium** |

### Phase C — Aircraft Integration (6–9 months)

| # | Task | Difficulty | Priority |
|---|---|---|---|
| C1 | PMDG 777 HGS integration — read PMDG HUD state, provide optional hybrid mode | **Very Hard** | **High** |
| C2 | PMDG 737 HGS integration — same as above | **Very Hard** | **High** |
| C3 | Asobo 787 native HUD suppression | **Medium** | **Medium** |
| C4 | FBW A32NX / Headwind A330 compatibility testing | **Low** | **Low** |
| C5 | iniBuilds A350 full integration with A350-specific code path | **Medium** | **Medium** |

### Phase D — User Experience (9–12 months)

| # | Task | Difficulty | Priority |
|---|---|---|---|
| D1 | Configurable HUD position/scale via in-game UI | **Medium** | **Medium** |
| D2 | TrackIR/Tobii calibration overlay | **Medium** | **High** |
| D3 | VR stereo rendering support | **Very Hard** | **Low** |
| D4 | PMDG HGS-style declutter modes (TO, CLB, CRZ, DES, APP) | **Medium** | **Medium** |
| D5 | Built-in flight test scenarios (certification mode) | **Medium** | **Low** |
| D6 | Performance budget monitor (per-subsystem HUD overlay) | **Medium** | **Low** |

---

## Detailed Code Analysis: Key Gaps by Component

### Collimation (`src/hud/collimation.cpp`)

```cpp
// Current: body-frame camera delta compensation
cd->delta_body = cd->delta_body * leak + eye_delta_body;
cc->correction_vector = proj_vec3_scale(cd->delta_body, -cd->compensation_gain);
cc->stabilised_eye = proj_vec3_add(current_eye, cc->correction_vector);
```

**Problem**: This modifies the eye position used for perspective projection. It tries to keep symbology screen-fixed by counteracting head movement. But in a real HGS:
1. The symbology is projected to infinity (collimated)
2. Eye position within the eyebox doesn't change the apparent position of symbology
3. What changes is the relationship between symbology and the outside world through the combiner

**Required**: Replace perspective projection with orthographic (or hybrid) projection that maps world coordinates directly to screen positions, then apply combiner optics as overlay.

### Combiner Geometry (`src/hud/combiner_geometry.cpp`)

```cpp
// Current: simple rect scaling
cg->screen_x = (FLOAT64)cg->panel_x * cg->scale_x;
cg->screen_y = (FLOAT64)cg->panel_y * cg->scale_y;
cg->screen_w = (FLOAT64)cg->panel_w * cg->scale_x;
cg->screen_h = (FLOAT64)cg->panel_h * cg->scale_y;
```

**Problem**: No consideration of:
- Combiner shape (trapezoidal, curved)
- FOV-dependent scaling (FOV changes affect combiner apparent size)
- Eye relief (distance from eye to combiner affects apparent angular coverage)

**Required**: Add FOV-aware combiner geometry, shape mask, and optical distortion model.

### Camera Tracking (`src/main.cpp` line 485)

```cpp
// v3.0.1 — Apply live camera offsets from calibration (TrackIR/head tracking).
```

**Problem**: Comment-only. No actual TrackIR/Tobii/VR code.

**Required**: Add:
```cpp
// Read MSFS camera position SimVars
FLOAT64 cam_x = module_read_f64(g_state.tok_camera_x);
FLOAT64 cam_y = module_read_f64(g_state.tok_camera_y);
FLOAT64 cam_z = module_read_f64(g_state.tok_camera_z);
// Use as dynamic eye offset
eye_offset.x += cam_x * profile->trackir_gain;
```

---

## Verification Summary

| Verification Item | Result | Evidence |
|---|---|---|
| All tests pass | ✅ 1230 passed | `python3 -m pytest tests/ -q` |
| Build configuration valid | ✅ CMakeLists.txt well-formed | WASM target with proper flags |
| JS overlay loads | ✅ (verified code) | `panel/HUD/hud_overlay.html` references `conformal_renderer.js` |
| L:Var pipeline connected | ✅ C++ publishes, JS reads | Confirmed L:C_HUD_* L:Vars in both C++ and JS |
| Combiner clipping active | ✅ Rect clipping via canvas | `hud_overlay.js` `get_combiner()` + `ctx.clip()` |
| Deployment detection active | ✅ L:Var read + state machine | `hud_overlay.js` reads L:C_HUD_Deploy_Phase |
| A350 header exists | ❌ **MISSING** | `include/hud/aircraft/airbus_hud_behavior.h` not found |
| PMDG L:AS1001_HUD verified | ❌ **UNVERIFIED** | Assumed variable name; not confirmed with PMDG SDK |
| TrackIR integration | ❌ **NOT IMPLEMENTED** | Comment only |
| True collimation | ❌ **NOT IMPLEMENTED** | Camera delta compensation only |
| PMDG HGS override | ❌ **NOT IMPLEMENTED** | Independent overlay only |

---

## Conclusion

**Current score: 42/100 vs Boeing HGS**

The project has excellent architecture, comprehensive test coverage (1230 tests), and solid WASM infrastructure. The deployment detection and combiner geometry modules are well-implemented for Phase 4.

However, several critical claims are inaccurate:
1. **"Semi-collimated rendering" is camera-delta compensation**, not optical collimation
2. **"TrackIR/head tracking" is comment-only**, not implemented
3. **"PMDG 777 integration" creates a separate overlay**, not integrated with the real HGS
4. **A350 Airbus HUD behavior header is missing** from the repository

The largest gaps are:
- True optical collimation (score: 20/100)
- Camera/head tracking (score: 15/100)
- PMDG native HGS integration (score: 10/100)

To reach Boeing HGS level, the project needs a fundamental rethink of the projection pipeline — moving from screen-space 2D canvas rendering to true world-aligned collimated projection, with proper combiner optics modeling.
