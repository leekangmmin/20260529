# BOEING HGS COMPARISON — Capability Matrix

**Reference:** Collins Aerospace HGS-4000 / HGS-4000A Head-Up Guidance System  
**Comparison target:** Conformal HUD Runway Symbology (C_HUD_Runway) v2.7.0  
**Date:** 2025-05-29

---

## 1. Physical Architecture Comparison

| Aspect | Boeing HGS (Real) | This Project | Gap |
|---|---|---|---|
| **Projection technology** | Collimating refractive/reflective optics projecting at optical infinity | Canvas 2D perspective projection onto flat screen | **Fundamental** — different physics |
| **Combiner glass** | 70/30 or 50/50 beam-splitter combiner with anti-reflective coating, shaped glass | Canvas `<canvas>` element with `alpha: true` compositing over MSFS viewport | **Fundamental** — no physical combiner |
| **Display source** | CRT (HGS-4000) or LCD (HGS-4000A) with 800×600 or higher resolution monochrome green image source | Canvas 2D on the user's monitor at their monitor resolution | Different display technology |
| **Field of view** | 30°×24° (HGS-4000 standard), 30°×20° (737), 33°×24° (777) | 30°×22.5° (737), 33°×24° (777), 36°×26° (787) — profile values but projection model doesn't use them for physical FOV | **Gap** — FOV values are decorative; actual screen FOV depends on user's monitor size/distance |
| **Eye position** | Fixed design eye position (D.E.P.) with ±2-inch box tolerance | Configurable `eye_position` body offset but no MSFS camera integration | **Gap** — static values, not tracked |
| **Brightness** | Auto/manual brightness, 10,000+ ft-Lamberts for sunlight readability | Brightness computed from ambient luminance, output via L:Var | **Partial** — simulated but not physically accurate |
| **Failure modes** | Redundant channels (dual HGS), self-test, failure flag | L:Var reporting only — no hardware redundancy model | **Gap** — no failure simulation |

## 2. Symbology Comparison

| Symbol | Boeing HGS | This Project | Gap |
|---|---|---|---|
| **Flight Path Vector (FPV)** | Circle showing true inertial path, acceleration prediction (lead) | Circle computed from GS/VS/heading, **no acceleration prediction** | **Minor** — missing predictive lead |
| **Horizon Line** | Single line with bank indication, world-referenced, collimated | Single line with bank, world-referenced, screen-projected | **Equivalent** |
| **Pitch Ladder** | Conformal pitch bars at 5° intervals, 10°, 15°, ±90°; banks with aircraft; world-anchored | Conformal pitch bars at 5°, 10°, 15°; banks with aircraft; screen-projected | **Equivalent** |
| **Runway Box** | Conformal trapezoid drawn from runway geometry, world-anchored, collimated | 4-vertex projected quad from runway lat/lon/alt, screen-projected | **Equivalent** in concept |
| **ILS Localizer** | Single bar or double bars, conformal to runway position, ±2.5 dots full scale | Single bar, conformal, ±1 dot full scale | **Minor** — scale difference |
| **ILS Glideslope** | Single bar, conformal to touchdown, ±0.7° full scale (CAT I) or ±0.35° (CAT III) | Single bar using 0.16 dots/degree sensitivity | **Minor** |
| **Drift Cue** | Diamond showing wind correction angle / drift | Diamond drawn from heading-track difference | **Equivalent** |
| **Flare Cue** | Circle rising from TD aim point, exponential sink-rate reduction | Circle rising from TD point with `-k*sqrt(h-h_td)` model | **Equivalent** in concept |
| **Rollout Cue** | Centerline tracking bar with predictive steering | Centerline tracking with adaptive damping, braking advisory | **Equivalent** |
| **Speed Tape** | Vertical tape with numeric, bug, trend arrow | Configured per profile but rendering **not confirmed** | **PRESENT IN PROFILE, NOT IN RENDERER** |
| **Altitude Tape** | Vertical tape with numeric, bug, VSI trend | Configured per profile but rendering **not confirmed** | **PRESENT IN PROFILE, NOT IN RENDERER** |
| **Heading Scale** | Compass arc at top of HUD, conformal | Configured per profile but rendering **not confirmed** | **PRESENT IN PROFILE, NOT IN RENDERER** |
| **Radio Altitude** | Digital readout below 2500 ft | Read via SimVar but display **not confirmed** | **NOT CONFIRMED** |
| **Decision Height** | Set by pilot, annunciated at DH | Present in CAT III annunciations but integration **not confirmed** | **PARTIAL** |
| **Flight Director** | Crosshair or cue showing pitch/roll commands | Computed in `guidance_flight_director()` but display **not confirmed** in renderer | **PARTIAL** |

## 3. Guidance Modes

| Mode | Boeing HGS | This Project | Gap |
|---|---|---|---|
| **Takeoff** | Takeoff guidance, Vr callout, centerline tracking | Not implemented | **NOT IMPLEMENTED** |
| **Climb** | Flight path vector, pitch steering | Basic FPV only | **NOT IMPLEMENTED** |
| **Cruise/Enroute** | FPV, heading, altitude, speed | Basic FPV only | **NOT IMPLEMENTED** |
| **Approach (CAT I)** | ILS bars, FPV, cross-check with PFD | ILS bars, FPV, guidance projection | **CONFIRMED** |
| **Approach (CAT II)** | As CAT I plus RA callouts, DH annunciation | CAT II annunciation, RA display | **PARTIAL** |
| **Approach (CAT IIIA)** | Autoland capable, dual channel, LAND 3, FLARE, ROLLOUT, NO DH | CAT III/IIIA/IIIB annunciation, FLARE/ROLLOUT cues, NO DH | **CONFIRMED** (annunciation only) |
| **Approach (CAT IIIB)** | Autoland capable, rollout guidance, fail-operational | As above + rollout guidance with confidence weighting | **PARTIAL** (no autoland integration) |
| **Flare** | Automatic flare guidance (dual channel for CAT III) | Flare cue with `-k*sqrt(h)` algorithm | **CONFIRMED** in concept |
| **Rollout** | Centerline tracking with nosewheel steering guidance | Rollout guidance with predictive steering | **CONFIRMED** in concept |
| **Go-Around** | FPV guidance, pitch command, TOGA callout | Not implemented | **NOT IMPLEMENTED** |
| **Taxi** | Airport surface map (some HGS variants) | Not implemented | **NOT IMPLEMENTED** |

## 4. Optical Realism

| Effect | Boeing HGS | This Project | Gap |
|---|---|---|---|
| **Collimation** | True optical infinity | Screen-space delta compensation | **CRITICAL** |
| **Phosphor persistence** | P43/P53 phosphor with ~0.1-1ms decay; long-persistence P39 for flicker reduction | EMA-based brightness decay configured per profile (35-45ms) | **PARTIAL** — simulated, not physically accurate |
| **Bloom** | CRT flood gun bloom on bright symbols | Brightness-dependent bloom from visual_response.cpp | **PARTIAL** |
| **Scan line** | 525/625 line CRT raster, visible at close range | Not implemented | **NOT IMPLEMENTED** |
| **Combiner ghosting** | Weak double-image from partial reflection on both combiner surfaces | Not implemented | **NOT IMPLEMENTED** |
| **Chromatic aberration** | Glass dispersion at edges | Not implemented | **NOT IMPLEMENTED** |
| **Veiling glare** | Scattered light in combiner from bright sunlight | Not implemented | **NOT IMPLEMENTED** |
| **Edge vignette** | Gradual brightness falloff at combiner edges | Simple rectangular clip + optional edge fade factor | **PARTIAL** |
| **Reticle blemish** | Minor fixed-pattern noise from CRT mask | Not implemented | **NOT IMPLEMENTED** |

## 5. Aircraft Integration

| Aircraft | Real HGS Support | This Project Support | Gap |
|---|---|---|---|
| **Boeing 737 NG (PMDG)** | Optional factory HGS (Collins HGS-4000), integrated with FMS and PFD | Separate overlay using profile for PMDG 737, reads L:Vars from aircraft | **OVERLAY ONLY** — no real integration |
| **Boeing 777 (PMDG)** | Standard HGS as primary flight display (Collins HGS-4000A), full integration | Separate overlay using profile for PMDG 777 | **OVERLAY ONLY** |
| **Boeing 787 (WT/Asobo)** | HGS integrated into cockpit design (as primary flight reference) | Separate overlay using profile for WT 787 | **OVERLAY ONLY** |
| **Airbus A350 (iniBuilds)** | Thales/Elbit HUD (different from Boeing HGS philosophy) | Separate Airbus overlay with A350-specific modules | **OVERLAY ONLY** |
| **Airbus A32NX (FBW)** | No real HUD (HUD not standard on A320) | Boeing-style overlay, incorrectly classified | **WRONG CLASSIFICATION** — Airbus classified as Boeing |

## 6. Certification

| Aspect | Boeing HGS | This Project | Gap |
|---|---|---|---|
| **Certification standard** | DO-178C DAL-C (software), TSO-C197 (HGS), FAA/EASA certified | No certification — community mod for MSFS | **Fundamental** — different domains |
| **Integrity monitoring** | Dual-channel cross-check, continuous BIT, failure flag to ARINC 429 | Confidence scoring system, watchdog subsystem, NaN guards | **PARTIAL** — simulation only |
| **Failure condition classification** | Minor to Catastrophic per CS-25/FAR 25 with required dispatch conditions | No failure classification — emergency degraded mode only | **MINIMAL** |
| **Flight test validation** | Hundreds of flight test hours per aircraft type | No real flight test — MSFS simulation only | **NOT APPLICABLE** |

## 7. Key Architectural Decisions Preventing HGS Equivalence

1. **Canvas 2D screen projection** — The fundamental rendering model is perspective projection of 3D points onto a flat 2D canvas. The real HGS uses collimating optics. To achieve HGS equivalence, the project would need to either: (a) integrate with an MSFS depth-aware rendering pipeline, or (b) implement a full ray-tracing collimation model. Both are extremely hard within the WASM+Canvas constraints.

2. **No physical combiner model** — The combiner in this project is a clip rectangle. A real combiner is a carefully designed beam-splitter with specific optical properties (reflectivity gradient, thickness, curvature, anti-reflective coating).

3. **WASM sandbox limiting** — The WASM module runs in MSFS's CoherentGT sandbox with no access to: GPU shaders, native VR/XR APIs, TrackIR/Tobii SDKs, MSFS internal camera position, or OS window management.

4. **Panel-based overlay** — The HUD draws on a panel texture (`.htm` + JS) that renders as a viewport overlay. This is fundamentally different from how MSFS renders the 3D scene. The HUD cannot be injected into the MSFS render pipeline.

---

**Bottom Line:** This project is an excellent MSFS HUD mod with impressive features, but it is not and cannot become a true Boeing HGS without a complete rewrite of the rendering pipeline, MSFS SDK changes, and fundamentally different hardware interaction. It achieves approximately **25%** of the Boeing HGS visual/guidance experience and **0%** of the physical/optical HGS behaviour.

*Report generated from static source-code analysis.*
