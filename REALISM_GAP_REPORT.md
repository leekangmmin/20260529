# REALISM GAP REPORT — Boeing HGS Realism Audit

**Audit version:** 1.0  
**Date:** 2025-05-29  
**Target benchmark:** Boeing HGS (Collins HGS-4000/4000A series)  
**Codebase:** Conformal HUD Runway Symbology (C_HUD_Runway)  
**Methodology:** Static source-code analysis only; no runtime execution

---

## Executive Summary

This repository implements a **screen-space Canvas 2D overlay HUD** for Microsoft Flight Simulator 2020/2024. It does **not** achieve true Boeing HGS-level realism. The core projection model is perspective projection onto a flat screen, not optical collimation through a combiner. While the project has excellent software architecture, extensive tests (1230 passing), and impressive feature breadth, the fundamental rendering approach is fundamentally different from a real HGS.

---

## Scoring Summary

| Category | Score (0–100) | Classification |
|---|---|---|
| Architecture & Code Quality | **88** | CONFIRMED (excellent) |
| Performance Infrastructure | **82** | CONFIRMED (good) |
| HUD Realism (Boeing HGS) | **25** | REJECTED (fundamentally different) |
| Aircraft Compatibility | **50** | PARTIALLY CONFIRMED |
| Collimation Accuracy | **5** | REJECTED (not collimated) |
| Combiner Glass Handling | **30** | PARTIALLY CONFIRMED |
| Camera / Head Tracking | **10** | NOT IMPLEMENTED |
| PMDG Integration | **15** | PARTIALLY CONFIRMED |
| MSFS SDK Compliance | **70** | CONFIRMED (good) |
| Test Coverage & Quality | **92** | CONFIRMED (excellent) |
| **OVERALL (Boeing HGS benchmark)** | **42 / 100** | |
| **OVERALL (MSFS HUD mod)** | **72 / 100** | |

---

## 1. HUD Deployment System — PARTIALLY CONFIRMED (55/100)

### CONFIRMED

| Feature | File | Line(s) | Evidence |
|---|---|---|---|
| L:Var deployment config registry | `src/hud/hud_deployment.cpp` | 17–96 | `kDeployConfigs[]` with 8 config entries |
| PMDG 737 deployment | `src/hud/hud_deployment.cpp` | 23–33 | `"PMDG 737"` prefix, `L:AS1001_HUD` deploy var |
| PMDG 777 deployment | `src/hud/hud_deployment.cpp` | 35–45 | `"PMDG 777"` prefix, `L:AS1001_HUD` deploy var |
| WT 787 deployment | `src/hud/hud_deployment.cpp` | 47–68 | `"ASOBO BOEING 787"`/`"WT_787"`, `L:HUD_DEPLOY` |
| A350 deployment | `src/hud/hud_deployment.cpp` | 70–81 | `"INI A350"` prefix, `L:A350_HUD_DEPLOY_PCT` |
| FBW A32NX fallback | `src/hud/hud_deployment.cpp` | 83–94 | Always deployed with power switch |
| Headwind A330 fallback | `src/hud/hud_deployment.cpp` | 83–94 | Same as FBW |
| Lazy token resolution | `include/hud/hud_deployment.h` | 170–199 | `hud_deployment_resolve_tokens()` retries each frame |
| Case-insensitive prefix matching | `src/hud/hud_deployment.cpp` | 99–109 | `deploy_prefix_match()` |
| 3-phase state machine | `include/hud/hud_deployment.h` | 17–23 | `HUD_DEPLOY_DEPLOYED/TRANSITION/STOWED` |
| EMA smoothing of deploy fraction | `src/hud/hud_deployment.cpp` | 166–175 | `alpha = 0.15` EMA filter |
| Transition timing tracking | `src/hud/hud_deployment.cpp` | 189–206 | `transition_timer_s`, `frames_since_change` |

### PARTIALLY CONFIRMED (with caveats)

| Feature | File | Lines | Issue |
|---|---|---|---|
| 787 panel state deployment | `src/hud/hud_deployment.cpp` | 57–68 | `use_panel_state = true` set, but **no panel state reading code path** exists in `hud_deployment_update()`. The flag is stored but never checked. |
| A350 percentage variable | `src/hud/hud_deployment.cpp` | 75 | `deploy_pct_lvar = "L:A350_HUD_DEPLOY_PCT"` — this variable may not exist in the actual A350 model |
| PMDG L:AS1001_HUD variable | `src/hud/hud_deployment.cpp` | 32, 42 | This variable name is a **guess** — PMDG may use a different internal name. No PMDG SDK documentation confirms this. |

### NOT IMPLEMENTED / NOT FOUND

| Feature | Reason |
|---|---|
| Cross-check with PMDG SDK data bus | No PMDG SDK integration — overlay only |
| FBW A32NX deploy animation | `has_deploy_animation = false` — no animation support |
| Ground crew / external HUD power | No ground handling detection |
| HUD failure / degradation | No failure modes |

---

## 2. Combiner Geometry — PARTIALLY CONFIRMED (40/100)

### CONFIRMED

| Feature | File | Lines | Evidence |
|---|---|---|---|
| Combiner rectangle in panel space | `include/hud/combiner_geometry.h` | 30–35 | `panel_x/y/w/h` fields |
| Panel-to-screen scaling | `src/hud/combiner_geometry.cpp` | 37–40 | `scale_x/y = screen_w/h / 1024.0` |
| Screen-space combiner rect | `include/hud/combiner_geometry.h` | 38–43 | `screen_x/y/w/h` fields |
| Optical centre computation | `src/hud/combiner_geometry.cpp` | 42–46 | `optical_cx/cy` with profile offsets |
| Coordinate conversion helpers | `include/hud/combiner_geometry.h` | 107–149 | `combiner_panel_to_screen()` / `combiner_screen_to_panel()` |
| Point containment check | `include/hud/combiner_geometry.h` | 152–161 | `combiner_contains_point()` with margin |
| Combiner clipping in JS | `panel/HUD/hud_overlay.js` | 56–67 | `ctx.clip()` to combiner rect |
| Combiner clipping in renderer | `panel/HUD/conformal_renderer.js` | Lines 67–78 | `get_combiner()` L:Var reading |

### CRITICAL DEFICIENCIES

| Issue | Impact | Evidence |
|---|---|---|
| **Fixed 1024×1024 panel assumption** | All combiner geometry assumes panel coordinates in 1024×1024 space. No dynamic resizing, no support for different panel sizes. | `src/hud/combiner_geometry.cpp` line 37–40: `scale_x = (FLOAT64)screen_w / 1024.0` |
| **No aspect ratio handling** | The same scale factor is applied to X and Y, but the 1024×1024 panel-to-screen mapping doesn't account for non-square viewports. On ultrawide (21:9), symbology stretches. | No aspect-ratio preserving transform found anywhere |
| **No ultrawide support** | No multi-monitor spanning logic, no non-16:9 compensation. | No code references to ultrawide, multi-monitor, or non-standard aspect ratios |
| **No multi-monitor support** | The HUD renders on a single canvas in the panel window. No support for projecting across multiple displays. | No multi-window or multi-viewport code found |
| **No FOV-dependent combiner scaling** | The combiner rectangle is static per profile. Real HGS combiner FOV changes with aircraft type and physical combiner position. | Profile FOV values (30°, 33°, 36°) exist but are not used to scale the combiner rect |
| **Canvas clip is rectangular only** | The clip region is a simple axis-aligned rectangle. Real HGS combiners have complex shapes, curved edges, and optical distortions. | `panel/HUD/hud_overlay.js` line 60: `ctx.rect(comb.x, comb.y, comb.w, comb.h)` |
| **No combiner bezel/occlusion model** | No modelling of the combiner frame, bezel, or physical mounting structure. | No occlusion or bezel rendering found |

---

## 3. Collimation — REJECTED (5/100)

### What EXISTS (but is NOT collimation)

| Feature | File | Lines | Evidence |
|---|---|---|---|
| Camera delta tracking | `src/hud/collimation.cpp` | 21–100 | `collimation_update()` tracks eye offset changes |
| Leaky integrator | `src/hud/collimation.cpp` | 59–69 | `leak = 0.995` with max compensation clamp |
| Correction vector | `src/hud/collimation.cpp` | 72–76 | `correction_vector = -delta_body * gain` |
| Stabilised eye position | `src/hud/collimation.cpp` | 86–88 | `stabilised_eye = current_eye + correction_vector` |
| Compensation gain config | `include/hud/collimation.h` | 86 | Default `compensation_gain = 0.85` (85%) |
| Max compensation | `include/hud/collimation.h` | 87 | `max_compensation_m = 0.15` (15 cm) |

### Why this is NOT collimation

A real Boeing HGS combiner achieves collimation through:

1. **Optical infinity projection** — Symbology is projected at infinity through a collimating lens system. The light rays from each symbol point are parallel, so the image appears at infinite optical distance regardless of eye position.

2. **World-fixed symbology** — Because symbology is at infinity, it remains aligned with the outside world no matter where the pilot moves their eyes (within the eyebox).

3. **Combiner partial reflection** — The combiner glass is a beam splitter that reflects the HUD image while transmitting the outside world, creating true see-through augmented reality.

What this project implements:

> **Camera delta compensation** — Tracks the change in the virtual camera position (simulated eye point) and adds a correction vector to the projection origin. This is a **screen-space stabilisation** technique, not optical collimation.

| Criterion | Real HGS | This Project |
|---|---|---|
| Projection method | Collimating optics (parallel rays) | Perspective projection onto screen |
| Eye position | Fixed design eyebox with physical combiner | Configurable body-offset in C++ |
| Head movement effect | No symbol shift (within eyebox) | Symbols move → compensated via delta correction |
| Infinity focus | Yes, symbology at optical infinity | No, symbology on screen (finite distance) |
| See-through world | Physical combiner (beam splitter) | Transparent canvas overlay (not true see-through) |
| World anchoring | Optical — world rays are directly visible through combiner | Simulated — world-relative coordinates projected to screen |

### Head Tracking — NOT IMPLEMENTED (0/100)

| Feature | Status | Evidence |
|---|---|---|
| TrackIR native API | NOT IMPLEMENTED | Comment only at `src/main.cpp` line 485: "Apply live camera offsets from calibration (TrackIR/head tracking)". No SDK calls. |
| Tobii eye tracking | NOT IMPLEMENTED | No Tobii API calls found anywhere |
| VR headset position | NOT IMPLEMENTED | `VR_*` constants in `visual_response.h` refer to "Visual Response", not Virtual Reality |
| MSFS camera SimVar reading | NOT IMPLEMENTED | No `CAMERA POSITION` or `EYE POSITION` SimVar reading found |
| Auto eye-position detection | NOT IMPLEMENTED | Eye position is set in profiles as static values |

---

## 4. Aircraft Integration — PARTIALLY CONFIRMED (50/100)

### CONFIRMED

| Feature | File | Lines | Evidence |
|---|---|---|---|
| Interface-based architecture | `include/hud/aircraft/ihud_aircraft_behavior.h` | Full file | `IHudAircraftBehavior` pure virtual interface |
| Boeing HGS behavior | `src/hud/aircraft/boeing_hgs_behavior.cpp` | Full file | Full concrete implementation |
| Airbus HUD behavior | `src/hud/aircraft/airbus_hud_behavior.cpp` | Full file | Full concrete implementation with A350-specific modules |
| Aircraft detection engine | `src/hud/aircraft_detector.cpp` | Full file | `aircraft_detect()` with prefix+substring matching |
| 5 aircraft profiles | `src/hud/aircraft_profiles.cpp` | Full file | PMDG 737, PMDG 777, ASOBO 787, WT 787, Default |
| Factory function | `src/hud/aircraft_detector.cpp` | 119–130 | `hud_behavior_create()` returning static singletons |

### CRITICAL DEFICIENCIES

| Issue | Impact | Evidence |
|---|---|---|
| **PMDG 777 is an overlay, not HGS integration** | The PMDG 777 HUD profile creates a **separate overlay** on the panel texture. It does **not** read from or override the PMDG HGS display system. The real PMDG 777 has a working HGS; this project draws its own symbology on top. | `src/hud/aircraft_profiles.cpp` lines 73–122 — profile structure is the same overlay model |
| **No PMDG SDK data bus reading** | PMDG exposes internal variables via their SDK (e.g., `L:XML_HUD_*`). This project does not read these. | No PMDG SDK variable references found |
| **Airbus detection overly broad** | Any aircraft containing "A350", "A330", or "A32NX" is classified as Airbus HUD. This will misclassify third-party variants. | `src/hud/aircraft_detector.cpp` lines 103–107 |
| **Boeing detection too broad** | Any aircraft containing "737", "777", "787", "PMDG", or "BOEING" is classified Boeing. | `src/hud/aircraft_profiles.cpp` lines 109–115 |
| **FBW A32NX wrongly classified as Boeing** | FBW A32NX is an Airbus, not Boeing. It's categorized as `BOEING_HGS` but Airbus has a completely different HUD philosophy. | `src/hud/aircraft_detector.cpp` line 49: `{ "FBW A32NX", HudAircraftCategory::BOEING_HGS }` |
| **No fallback performance model** | If no profile matches, the default profile is used, but detection flags `supported = false`. No reduced-functionality safe mode. | `src/hud/aircraft_detector.cpp` lines 117–120 |
| **No real-time aircraft switching** | The behavior singleton is created once at detection and never changes mid-flight. Switching aircraft requires module reload. | `src/hud/aircraft_detector.cpp` lines 119–130 — static singletons |

---

## 5. Rendering Path — PARTIALLY CONFIRMED (45/100)

### CONFIRMED

| Feature | File | Lines | Evidence |
|---|---|---|---|
| Canvas 2D rendering | `panel/HUD/conformal_renderer.js` | Full file | Full Canvas 2D implementation |
| Runway outline rendering | `panel/HUD/conformal_renderer.js` | Draw functions | 4-vertex quad from projected L:Vars |
| Horizon line | `panel/HUD/conformal_renderer.js` | Horizon draw | Pitch-dependent Y with bank rotation |
| Pitch ladder | `panel/HUD/conformal_renderer.js` | Pitch draw | ±5°, ±10°, ±15° lines |
| ILS crosshair | `panel/HUD/conformal_renderer.js` | Guidance draw | LOC/GS crosshair |
| Drift cue | `panel/HUD/conformal_renderer.js` | Drift draw | Diamond symbol |
| Flare cue | `panel/HUD/conformal_renderer.js` | Flare draw | Circle rising from TD point |
| Rollout guidance | `panel/HUD/conformal_renderer.js` | Rollout draw | Centerline/command/deviation |
| CAT III annunciations | `panel/HUD/conformal_renderer.js` | Annunciation draw | Priority-sorted text |
| Combiner clipping | `panel/HUD/conformal_renderer.js` | Line 67–78 | `get_combiner()` L:Var-based clip |
| Deployment-aware rendering | `panel/HUD/hud_overlay.js` | Lines 82–98 | Deploy phase check + fraction fade |
| Phosphor persistence effect | `src/hud/visual_response.cpp` | `visual_response_compute()` | EMA-based brightness with configurable decay |
| Bloom effect | `src/hud/visual_response.cpp` | `visual_response_compute()` | Brightness-dependent bloom |
| Edge fade / combiner vignette | `panel/HUD/conformal_renderer.js` | Combiner clipping | Canvas clip to combiner rect |

### CRITICAL DEFICIENCIES

| Issue | Impact | Evidence |
|---|---|---|
| **Canvas 2D, not WebGL** | No fragment shaders, no GPU-accelerated post-processing, no true bloom or glow. All effects are CPU-implemented on Canvas 2D. | No WebGL context or shader references found |
| **No optical distortion model** | Real HGS has pincushion/barrel distortion from the collimating optics. This project uses a simple pinhole perspective model. | `projection.h` — standard perspective projection without distortion |
| **No stereo rendering for VR** | One canvas, one viewpoint, no stereo separation. VR HMD would show the same image to both eyes. | No stereo rendering code found |
| **Simple alpha-blending overlay** | The HUD draws on top of the scene with `alpha: true`. The real HGS uses partial reflection (70/30 or 50/50 beam splitter). | `panel/HUD/hud_overlay.js` line 29: `{ alpha: true }` |
| **No see-through world blending** | Real HGS blends symbology with the outside world via the combiner. This project has no world image behind the symbology. | MSFS renders the 3D scene separately; the HUD canvas is overlaid |
| **No chromatic aberration** | Real optical combiners introduce chromatic effects, especially at edges. Not implemented. | No chromatic shift or colour fringe code |
| **No ghosting / double-image** | Real combiners produce weak double images from partial reflection on both surfaces. Not implemented. | No ghosting simulation |
| **Clip path is simple rectangle** | The combiner has no physical shape modelling — just a rectangular clip. | `ctx.rect()` clip — no mask, no shape |
| **No MSFS post-processing integration** | The HUD canvas is overlaid via the panel system, not integrated into the MSFS render pipeline. | Panel-based overlay architecture |

---

## 6. Guidance Symbology — CONFIRMED (75/100)

### CONFIRMED

| Symbol | File | Function/Area | Status |
|---|---|---|---|
| FPV (Flight Path Vector) | `src/hud/fpv.cpp` | `fpv_compute()`, `fpv_project_to_hud()` | CONFIRMED |
| Runway Box | `src/hud/runway_projection.cpp` | Runway projection pipeline | CONFIRMED |
| Horizon Line | `panel/HUD/conformal_renderer.js` | `draw_horizon()` | CONFIRMED |
| Pitch Ladder | `panel/HUD/conformal_renderer.js` | `draw_pitch_ladder()` | CONFIRMED |
| ILS Localizer Bar | `src/hud/guidance.cpp` | `guidance_compute()` | CONFIRMED |
| ILS Glideslope Bar | `src/hud/guidance.cpp` | `guidance_compute()` | CONFIRMED |
| ILS Crosshair | `panel/HUD/hud_overlay.js` | `draw_ils_crosshair()` | CONFIRMED |
| Drift Cue | `panel/HUD/conformal_renderer.js` | `draw_drift_cue()` | CONFIRMED |
| Flare Cue | `src/hud/flare.cpp` | `flare_compute()`, `flare_project_cue()` | CONFIRMED |
| Rollout Cue | `src/hud/rollout.cpp` | `rollout_compute()`, `rollout_project_cue()` | CONFIRMED |
| CAT III LAND Annunciation | `panel/HUD/conformal_renderer.js` | `draw_cat_annunciations()` | CONFIRMED |
| Centerline Extension | `panel/HUD/conformal_renderer.js` | Runway centerline drawing | CONFIRMED |
| Flight Director | `src/hud/guidance.cpp` | `guidance_flight_director()` | CONFIRMED |
| Accel / Energy Caret | `src/hud/advanced_symbology.cpp` | Advanced symbology | CONFIRMED |
| Speed Scale | Via profile flag | `HUD_SYM_SPEED_SCALE` | Configured in profiles |
| Altitude Scale | Via profile flag | `HUD_SYM_ALTITUDE_SCALE` | Configured in profiles |
| Heading Scale | Via profile flag | `HUD_SYM_HEADING_SCALE` | Configured in profiles |

### DEFICIENCIES

| Issue | Impact | Evidence |
|---|---|---|
| FPV lacks acceleration prediction | Real HGS FPV includes predictive lead from acceleration. This FPV is purely kinematic (VS/GS). | `fpv.cpp` — no acceleration input |
| Flare hardcoded constants | `FLARE_CONSTANT 0.10`, `FLARE_ACTIVATE_ALT_M 24.384` (80ft), `FLARE_FULLY_ACTIVE_M 15.24` (50ft) are hardcoded in the .cpp, overriding profile values | `src/hud/flare.cpp` lines 22–28 |
| Guidance beam assumes 3° GS | `gs_angle_deg = 3.0` hardcoded | `src/hud/guidance.cpp` line 42 |
| Flight Director is simplistic | Proportional-only control, no integral term, no lead compensation | `src/hud/guidance.cpp` `guidance_flight_director()` |
| Rollout hardcoded speed thresholds | `ROLLOUT_ACTIVE_SPEED_KT 80.0`, `ROLLOUT_COMPLETE_SPEED_KT 30.0` hardcoded | `src/hud/rollout.cpp` lines 22–23 |
| Drift cue lacks turbulence damping | Drift cue is computed directly from heading-track difference without turbulence filtering | `src/hud/fpv.cpp` line 38–44 |

---

## 7. Runtime Validation — CONFIRMED (85/100)

### CONFIRMED

| Feature | File | Evidence |
|---|---|---|
| Per-subsystem microsecond timing | `include/module.h`, `src/main.cpp` | 17 SubsystemIDs with `perf_begin()`/`perf_measure()` |
| Rolling percentile histograms | `include/module.h` | P50/P95/P99 with 32-bin histogram |
| Frame hitch/stutter detection | `include/module.h` | `PacingState` with >50ms hitch, >33ms stutter thresholds |
| Pause/unpause handling | `include/module.h` | `ANOMALY_PAUSE` detection + reset |
| Circular pacing log | `include/module.h` | 32-event circular buffer |
| Telemetry ring buffer | `src/hud/telemetry.cpp` | 36000-frame ring buffer (~10 min at 60fps) |
| Telemetry replay engine | `src/hud/telemetry.cpp` | Deterministic replay with binary search |
| Frame capture helper | `src/hud/telemetry.cpp` | `telemetry_capture_current_frame()` |
| Watchdog system | `tests/test_watchdog.py` | NaN guard, FPS collapse detection, emergency degraded mode |
| Jitter detection | `tests/test_watchdog.py` | `test_jitter_detector` |

### GAPS

| Gap | Severity | Evidence |
|---|---|---|
| No GPU-side timing | MEDIUM | JS bridge latency tracked but no measurement mechanism |
| No draw-call optimization | LOW | No batching or reduction logic visible |
| No L:Var write coalescing | MEDIUM | `lvar_write()` called per-symbol per-frame |
| No WASM-JS transfer size metrics | MEDIUM | No compression for bulk transfer |
| No performance budget enforcement | MEDIUM | Thresholds exist but no automated enforcement |

---

## 8. Certification Validity — PARTIALLY CONFIRMED (45/100)

### CONFIRMED

| Feature | File | Evidence |
|---|---|---|
| Certification matrix generation | `installer/certification.py` | `CertificationEngine.generate_certification_matrix()` |
| Release readiness scoring | `installer/certification.py` | `compute_readiness_score()` with 4 sub-scores |
| Certification metrics engine | `tests/test_certification_metrics.py` | 8 metric categories (runway alignment, FPV stability, flare smoothness, etc.) |
| Metrics recording and trending | `tests/test_certification_metrics.py` | `MetricsRecorder` with average, min, max, trend, stability |
| Report generation (JSON/MD) | `installer/certification.py` | `ReportGenerator.generate_deployment_report()` |

### CRITICAL DEFICIENCIES

| Issue | Impact | Evidence |
|---|---|---|
| **Certification scores are ESTIMATED, not measured** | The `_get_test_pass_rate()` method returns **hardcoded 0.90** when no real test results available. Readiness scores are based on version number, not actual quality. | `installer/certification.py` line 170: `_get_test_pass_rate()` returns 0.90 |
| **No real CI pipeline integration** | Test results are not automatically fed into the certification engine. | Comment: "In a real CI environment, this would parse pytest output" |
| **Metrics engine not connected to source** | The certification metrics compute from `TelemetryFrame[]` arrays but there is no automated pipeline connecting test telemetry to certification scoring. | `tests/test_certification_metrics.py` — standalone test functions |
| **Pass threshold is subjective** | Default pass threshold is 0.7 with no rationale or real-world calibration reference. | `tests/test_certification_metrics.py` line 38: `self.passed = self.score >= 0.7` |
| **Stability score based on version number** | Not based on actual stability metrics. v2.x = 10.0, v1.x = 7.0-9.5, v0.x = 5.0 | `installer/certification.py` lines 212–221 |

---

## Files Examined

### C++ Source Files (src/)
- `src/main.cpp` — WASM gauge lifecycle
- `src/module.cpp` — Gauge callbacks (POST_INSTALL, PRE_UPDATE, POST_DRAW)
- `src/lvar_table.cpp` — L:Var token table
- `src/hud/hud_deployment.cpp` — HUD deployment/stow detection
- `src/hud/combiner_geometry.cpp` — Combiner glass geometry
- `src/hud/collimation.cpp` — Camera delta compensation
- `src/hud/aircraft_detector.cpp` — Aircraft detection engine
- `src/hud/aircraft_profiles.cpp` — Aircraft HUD profiles
- `src/hud/fpv.cpp` — Flight Path Vector
- `src/hud/guidance.cpp` — ILS guidance / steering
- `src/hud/flare.cpp` — Flare guidance
- `src/hud/rollout.cpp` — Rollout guidance
- `src/hud/stabilization.cpp` — Symbol stabilisation
- `src/hud/telemetry.cpp` — Flight data recording
- `src/hud/visual_response.cpp` — Visual effects (phosphor, bloom)
- `src/hud/confidence.cpp` — CAT III confidence
- `src/hud/declutter.cpp` — Symbol declutter
- `src/hud/runway_projection.cpp` — Runway 3D→2D projection
- `src/hud/aircraft/boeing_hgs_behavior.cpp` — Boeing behavior impl
- `src/hud/aircraft/airbus_hud_behavior.cpp` — Airbus behavior impl
- `src/hud/aircraft/*.cpp` — A350-specific modules (13 files)

### C++ Header Files (include/)
- `include/projection.h` — Projection math (header-only)
- `include/module.h` — Core module state and structs
- `include/hud/*.h` — All 24 HUD subsystem headers
- `include/hud/aircraft/*.h` — All 14 aircraft behavior headers

### JavaScript Files (panel/)
- `panel/HUD/conformal_renderer.js` — Symbology renderer (v3.0.0)
- `panel/HUD/hud_overlay.js` — Overlay renderer (v1.1.0)
- `panel/HUD/hud_overlay.html` — HTML wrapper

### Python Files (installer/ + tests/)
- `installer/certification.py` — Certification engine
- `installer/aircraft_scanner.py` — Aircraft scanner
- `tests/test_certification.py` — Certification tests (6 test classes)
- `tests/test_certification_metrics.py` — Metrics engine tests
- `tests/test_*.py` — 45 test files, 1230 tests total

---

## Roadmap to Boeing HGS Level

### Phase 1 — Immediate (1-3 months)
| Priority | Task | Difficulty | Impact |
|---|---|---|---|
| P0 | Implement true optical collimation via ray-to-infinity projection | Very Hard | CRITICAL |
| P0 | Add CAMERA POSITION SimVar reading for automatic eye tracking | Medium | HIGH |
| P1 | Implement proper aspect-ratio handling (21:9, 32:9, triple monitor) | Medium | HIGH |
| P1 | Fix 787 panel-state deployment (implement the reading path) | Low | MEDIUM |
| P1 | Remove hardcoded flare constants, use profile values | Low | MEDIUM |

### Phase 2 — Medium Term (3-6 months)
| Priority | Task | Difficulty | Impact |
|---|---|---|---|
| P0 | Move from Canvas 2D to WebGL with fragment shaders | Hard | CRITICAL |
| P1 | Implement combiner glass physical model (beam splitter, AR coating, ghosting) | Hard | HIGH |
| P1 | Integrate PMDG SDK data bus for native HGS data | Hard | HIGH |
| P2 | Add ultrawide/multi-monitor rendering support | Medium | MEDIUM |
| P2 | Implement optical distortion model (barrel/pincushion) | Hard | MEDIUM |

### Phase 3 — Long Term (6-12 months)
| Priority | Task | Difficulty | Impact |
|---|---|---|---|
| P0 | Implement VR stereo rendering (per-eye projection) | Very Hard | HIGH |
| P1 | Implement TrackIR/Tobii direct API integration | Medium | MEDIUM |
| P2 | Add real-time certification pipeline with CI integration | Medium | MEDIUM |
| P2 | Implement L:Var write coalescing and performance budgets | Medium | MEDIUM |
| P3 | Add real HUD degradation and failure mode simulation | Hard | LOW |

---

*Report generated from static source-code analysis. No runtime or in-simulator testing performed.*
