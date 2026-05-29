# C_HUD_Runway — Conformal HUD Runway Guidance System

**v3.4.0 — ROLLOUT/CAT-III/EVS ENHANCEMENT**

A WASM gauge module that implements a true conformal Boeing HGS-style HUD for
MSFS aircraft with native HUDs.

## Overview

### Phase 1 — Real WASM Runtime Instrumentation
- High-resolution timing instrumentation (`perf_begin`/`perf_end`) for every subsystem
- Rolling timing histograms with P50/P95/P99 percentile computation
- Per-subsystem execution time measurement (FPV, Guidance, Runway, Flare, etc.)
- L:var publish cost measurement
- SimVar read latency measurement
- JS bridge latency measurement
- Projection cost model validation
- Stabilization cost analysis
- Telemetry recording overhead measurement
- Optical rendering overhead tracking
- Subsystem cost overlays for the HUD debug view
- Runtime profiling HUD data export via L:vars

### Phase 2 — Real MSFS Telemetry Capture
- Binary telemetry export format (`.chtelem` files)
- ZLIB compression for telemetry data (typical 2:1 ratio)
- Live telemetry streaming export
- Replay session management (save/load/compare)
- Deterministic frame checksumming
- Frame-by-frame telemetry integrity validation
- Session metadata tagging (aircraft, flight, date, scenario)

### Phase 3 — Real Frame Pacing Validation
- Timing anomaly detection (hitches > 50ms, stutters > 33ms)
- Frame hitch recovery with stabilization reset logic
- Pause/unpause transition handling
- Temporal continuity metric (0..1)
- Circular anomaly event log (32 events)
- Rolling frame-time statistics (min, max, mean, stddev)
- Consecutive stable frame counting

### Phase 4 — Live Aircraft Compatibility Certification
- Compatibility signature database for 8 aircraft types:
  - PMDG 737-800/700
  - PMDG 777-300ER
  - ASOBO 787-10 / WT 787-10
  - iniBuilds A350
  - FBW A32NX
  - Headwind A330-900
- Aircraft-version detection (major/minor)
- Integration self-repair capability
- Automatic fallback mode for unknown aircraft
- Optical center verification per aircraft
- Eye offset correction profiles

### Phase 5 — Real Optical Validation
- Shimmer detection (high-frequency oscillation > 2px)
- Visual fatigue tracking (build-up over time, decay in darkness)
- Phosphor persistence smearing detection
- Optical stability scoring (0..1 combined metric)
- Runway attachment stability verification
- CAT III readability assessment

### Phase 6 — Long-Duration Stability Testing
- Memory growth monitoring (linear regression leak detection)
- Timing drift detection (execution time trends over hours)
- Telemetry corruption detection with SHA-256 checksums
- Subsystem stall monitoring (configurable threshold)
- Endurance simulation (multi-hour flights, pause/resume cycles)
- Aircraft switching endurance

### Phase 7 — Operational Certification Mode
- Automated validation runs across 8 certification scenarios:
  - CAT III fog approach (weight 20%)
  - Crosswind landing (15%)
  - Night operation (10%)
  - Turbulence recovery (10%)
  - Wet runway rollout (10%)
  - Rejected landing / go-around (10%)
  - Long-haul stability test (15%)
  - Aircraft switching (10%)
- Scenario scoring engine with weighted aggregation
- Aircraft certification levels (CRITICAL/HIGH/MEDIUM/LOW/FAIL)
- Replay-based regression detection (2% tolerance)
- Release readiness determination
- Compatibility matrix generation
- Runtime performance report generation
- Human-readable certification summary reports

### Project Structure

```
├── include/
│   ├── module.h                # v3.4.0: Core types, timing histograms, perf state,
│   │                           #          pacing validation, compatibility sigs,
│   │                           #          optical stability, certification L:vars
│   ├── projection.h            # Projection math utilities
│   └── hud/
│       ├── aircraft/
│       │   ├── ihud_aircraft_behavior.h  # Unified behavior interface
│       │   ├── boeing_hgs_behavior.h     # Boeing HGS behavior
│       │   ├── airbus_hud_behavior.h     # Airbus HUD behavior
│       │   ├── a350_profile.h            # A350 HUD behaviour profile
│       │   ├── a350_flare_law.h          # Airbus flare law
│       │   ├── a350_rollout.h            # Airbus rollout augmentation
│       │   ├── a350_cat3.h               # Airbus CAT III augmentation
│       │   ├── a350_symbology.h          # Airbus symbology styling
│       │   ├── a350_fpv_controller.h     # A350 FPV controller
│       │   ├── a350_horizon.h            # A350 horizon stabilization
│       │   ├── a350_autoland.h           # A350 autoland HUD layer
│       │   ├── a350_landing_energy.h     # A350 landing energy model
│       │   ├── a350_runway_augmentation.h# A350 runway augmentation
│       │   └── airbus_fpv.h              # Airbus FPV filter
│       ├── aircraft_detector.h           # Automatic aircraft detection
│       ├── aircraft_profiles.h           # Aircraft HUD profile database
│       ├── telemetry.h                   # Binary export, compression, session mgmt
│       ├── verification.h               # Debug overlay types
│       ├── advanced_symbology.h          # Advanced symbology
│       ├── airport_database.h            # Airport/runway database
│       ├── collimation.h                 # Semi-collimated rendering
│       ├── confidence.h                  # Confidence-based rendering
│       ├── declutter.h                   # Declutter system
│       ├── depth_illusion.h              # Optical depth effects
│       ├── evs.h                         # Enhanced Vision System
│       ├── flare.h                       # Flare guidance
│       ├── fpv.h                         # Flight Path Vector
│       ├── guidance.h                    # ILS guidance
│       ├── rollout.h                     # Rollout guidance
│       ├── runway_cache.h                # Runway geometry cache
│       ├── runway_projection.h           # Runway corner computation
│       ├── stabilization.h               # Symbol stabilisation filters
│       └── visual_response.h             # Visual response effects
├── src/
│   ├── main.cpp                # v3.4.0: WASM lifecycle + update pipeline
│   ├── module.cpp              # Gauge callbacks
│   ├── lvar_table.cpp          # L:Var token table
│   └── hud/
│       ├── aircraft/
│       │   ├── boeing_hgs_behavior.cpp   # Boeing HGS behavior
│       │   ├── airbus_hud_behavior.cpp   # Airbus HUD behavior
│       │   ├── a350_profile.cpp          # A350 HUD behaviour profile
│       │   ├── airbus_fpv.cpp            # Airbus FPV filter
│       │   ├── a350_flare_law.cpp        # Airbus flare law
│       │   ├── a350_rollout.cpp          # Airbus rollout augmentation
│       │   ├── a350_cat3.cpp             # Airbus CAT III augmentation
│       │   ├── a350_symbology.cpp        # Airbus symbology styling
│       │   ├── a350_fpv_controller.cpp   # A350 FPV controller
│       │   ├── a350_horizon.cpp          # A350 horizon stabilization
│       │   ├── a350_autoland.cpp         # A350 autoland HUD layer
│       │   ├── a350_landing_energy.cpp   # A350 landing energy model
│       │   └── a350_runway_augmentation.cpp # A350 runway augmentation
│       ├── aircraft_detector.cpp         # Automatic aircraft detection
│       ├── aircraft_profiles.cpp         # Aircraft profile database
│       ├── telemetry.cpp                 # Flight data recording & replay
│       ├── advanced_symbology.cpp        # Advanced symbology
│       ├── airport_database.cpp          # Airport/runway database
│       ├── calibration.cpp               # Calibration system
│       ├── collimation.cpp               # Semi-collimated rendering
│       ├── confidence.cpp                # Confidence-based rendering
│       ├── declutter.cpp                 # Declutter system
│       ├── depth_illusion.cpp            # Optical depth effects
│       ├── evs.cpp                       # Enhanced Vision System
│       ├── flare.cpp                     # Flare guidance
│       ├── fpv.cpp                       # Flight Path Vector
│       ├── guidance.cpp                  # ILS guidance
│       ├── rollout.cpp                   # Rollout guidance
│       ├── runway_cache.cpp              # Runway geometry cache
│       ├── runway_projection.cpp         # Runway corner computation
│       ├── stabilization.cpp             # Symbol stabilisation filters
│       └── visual_response.cpp           # Visual response effects
└── tests/
    ├── test_a350_hud.py                  # A350-specific tests
    ├── test_aircraft_compatibility.py    # 35 tests (Phase 4)
    ├── test_frame_pacing.py              # 32 tests (Phase 3)
    ├── test_long_duration_stability.py   # 23 tests (Phase 6)
    ├── test_operational_certification.py # 33 tests (Phase 7)
    ├── test_optical_validation.py        # 24 tests (Phase 5)
    ├── test_runtime_instrumentation.py   # 48 tests (Phase 1)
    ├── test_telemetry_capture.py         # 19 tests (Phase 2)
    └── ... (36 additional test files)
```

## Test Results

**1230 passing tests** (44 test files):
- 48 tests — WASM Runtime Instrumentation (Phase 1)
- 19 tests — Telemetry Capture & Export (Phase 2)
- 32 tests — Frame Pacing Validation (Phase 3)
- 35 tests — Aircraft Compatibility (Phase 4)
- 24 tests — Optical Validation (Phase 5)
- 23 tests — Long-Duration Stability (Phase 6)
- 33 tests — Operational Certification (Phase 7)
- 1016 tests — Additional tests covering all subsystems

Run: `python3 -m pytest tests/ -v`
