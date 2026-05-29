# README CORRECTIONS — Phase 2 Documentation Audit

**Generated:** 2026-05-29  
**Repository:** C_HUD_Runway  
**Methodology:** Compare every claim in `README.md` against actual repository contents.

---

## Correction 1 — Version Header

| | Content |
|---|---|
| **OLD** | `**v2.6.0 — RUNTIME INSTRUMENTATION & OPERATIONAL CERTIFICATION**` |
| **NEW** | `**v2.7.0 — ROLLOUT/CAT-III/EVS ENHANCEMENT**` |
| **REASON** | CMakeLists.txt (authoritative source) declares `project(C_HUD_Runway VERSION 2.7.0 ...)`. The v2.7.0 tagline matches `include/module.h` banner. |

---

## Correction 2 — Project Structure / Nonexistent Files

The README lists several files in the project structure diagram that do not exist in the repository:

| File in README | Status | Action |
|---|---|---|
| `include/hud/perf_monitor.h` | ❌ Does not exist | Remove from diagram |
| `include/hud/pacing_validator.h` | ❌ Does not exist | Remove from diagram |
| `include/hud/compatibility.h` | ❌ Does not exist | Remove from diagram |
| `src/hud/perf_monitor.cpp` | ❌ Does not exist | Remove from diagram |
| `src/hud/pacing_validator.cpp` | ❌ Does not exist | Remove from diagram |
| `src/hud/compatibility.cpp` | ❌ Does not exist | Remove from diagram |

Additionally, the README omits several directories and files that DO exist:

| File/Directory | Status | Action |
|---|---|---|
| `include/hud/aircraft/` (dir with 10+ headers) | ❌ Missing | Add to diagram |
| `src/hud/aircraft/` (dir with 10+ sources) | ❌ Missing | Add to diagram |
| `include/hud/verification.h` | ❌ Missing | Add to diagram |
| `include/hud/telemetry.h` | ❌ Listed as `telemetry.h` without subpath | Clarify |

### OLD Structure (incorrect references):

```text
├── include/
│   ├── module.h                # v2.6.0: Timing histograms, perf state, pacing,
│   │                           #          compatibility sigs, optical stability,
│   │                           #          certification mode L:vars
│   └── hud/
│       ├── telemetry.h         # Binary export, compression, session mgmt
│       ├── perf_monitor.h      # Runtime performance monitoring (NEW)
│       ├── pacing_validator.h  # Frame pacing validation (NEW)
│       └── compatibility.h     # Aircraft compatibility (NEW)
├── src/
│   ├── main.cpp                # v2.6.0: Instrumented update pipeline
│   ├── lvar_table.cpp          # New L:vars for perf, pacing, compat, cert
│   └── hud/
│       ├── calibration.cpp     # New debug overlay toggles
│       ├── perf_monitor.cpp    # Performance monitoring impl (NEW)
│       ├── pacing_validator.cpp# Pacing validation impl (NEW)
│       └── compatibility.cpp   # Compatibility impl (NEW)
└── tests/
    ├── test_runtime_instrumentation.py   # 72 tests (NEW)
    ├── test_telemetry_capture.py         # 32 tests (NEW)
    ├── test_frame_pacing.py             # 24 tests (NEW)
    ├── test_aircraft_compatibility.py   # 28 tests (NEW)
    ├── test_optical_validation.py       # 26 tests (NEW)
    ├── test_long_duration_stability.py  # 20 tests (NEW)
    └── test_operational_certification.py# 34 tests (NEW)
```

### NEW Structure (correct):

```text
├── include/
│   ├── module.h                # v2.7.0: Core types, timing histograms, perf state,
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
│       │   ├── airbus_fpv.h              # Airbus FPV filter
│       │   └── airbus_hud_behavior.h     # Airbus HUD behavior
│       ├── aircraft_detector.h           # Automatic aircraft detection
│       ├── aircraft_profiles.h           # Aircraft HUD profile database
│       ├── telemetry.h                   # Binary export, compression, session mgmt
│       ├── verification.h               # Debug overlay types
│       ├── advanced_symbology.h          # Advanced symbology
│       ├── airport_database.h            # Airport/runway database
│       ├── calibration.h                 # Calibration (in module.h)
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
│   ├── main.cpp                # v2.7.0: WASM lifecycle + update pipeline
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

---

## Correction 3 — Test Counts

| Phase | OLD | NEW | REASON |
|---|---|---|---|
| Phase 1 — Runtime Instrumentation | 72 tests | 48 tests | Actual function count |
| Phase 2 — Telemetry Capture | 32 tests | 19 tests | Actual function count |
| Phase 3 — Frame Pacing | 24 tests | 32 tests | Actual function count |
| Phase 4 — Aircraft Compatibility | 28 tests | 35 tests | Actual function count |
| Phase 5 — Optical Validation | 26 tests | 24 tests | Actual function count |
| Phase 6 — Long-Duration Stability | 20 tests | 23 tests | Actual function count |
| Phase 7 — Operational Certification | 34 tests | 33 tests | Actual function count |
| Existing v2.5.x tests | 648 tests | 1016 tests | 44 test files, 1230 total - 214 new = 1016 |
| **Total** | **884 tests** | **1230 tests** | Actual function count across all 44 test files |

---

## Correction 4 — "What's New" Section

The README's "What's New in v2.6.0" section describes features that are not new in v2.6.0. Given that the current version is v2.7.0, the section title should be updated and the content should be clarified as cumulative rather than version-exclusive.

| OLD | NEW | REASON |
|---|---|---|
| `## What's New in v2.6.0` | `## Overview` | Current version is v2.7.0; features listed span multiple versions |

---

## Correction 5 — Module Description

| OLD | NEW | REASON |
|---|---|---|
| `A WASM gauge module that implements a true conformal Boeing HGS-style HUD for MSFS aircraft with native HUDs. This release transitions from algorithmic validation to real runtime instrumentation and operational certification.` | `A WASM gauge module that implements a true conformal Boeing HGS-style HUD for MSFS aircraft with native HUDs.` | The "transitions from..." text refers to v2.6.0 specifically; keep description version-agnostic. |

---

## Summary of Changes

| # | README Location | Type | Severity |
|---|---|---|---|
| 1 | Title header (version number) | Outdated | High |
| 2 | Project structure diagram (6 nonexistent files) | Incorrect | High |
| 3 | Project structure diagram (missing directories) | Incomplete | Medium |
| 4 | Test counts per phase | Incorrect | High |
| 5 | Total test count | Incorrect | High |
| 6 | "What's New" section title | Outdated | Medium |
| 7 | Module description | Outdated | Low |
