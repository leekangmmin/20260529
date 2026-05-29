# RUNTIME TIMING AUDIT — Phase 3, Task 1

**Date:** 2026-05-29  
**Scope:** Verify that WASM runtime timing instrumentation is functional and receives real data.

---

## 1. Structures Audited

| Structure | Location | Status |
|---|---|---|
| `PerfState` | `include/module.h` lines 779-808 | ✅ Declared, initialised in `module_init()` |
| `SubsystemHistogram` | `include/module.h` | ✅ Declared |
| `TimingSample` | `include/module.h` | ✅ Declared |
| `perf_state_init()` | `include/module.h` line 872 | ✅ Static inline, called in `main.cpp` init |

## 2. Functions Added This Phase

| Function | Location | Purpose |
|---|---|---|
| `histogram_record()` | `include/module.h` section 4b | Core function that populates histograms with timing data |
| `perf_begin()` | `include/module.h` section 4b | Marks frame start, stores timestamp |
| `perf_end()` | `include/module.h` section 4b | Marks frame end, records total frame time |
| `perf_measure()` | `include/module.h` section 4b | Records per-subsystem timing measurement |

## 3. Pipeline Instrument Points

| Pipeline Stage | Timing Call | Location in main.cpp |
|---|---|---|
| **ReadVars** | `perf_begin()` at start, `perf_measure(SUBSYS_SIMVAR_READ)` at end | `module_update_read_vars()` |
| **Project** | `perf_measure()` for each subsystem (FPV, Guidance, RunwayProj, Flare, Rollout, Collimation, EVS, Stabilization, AdvSymbology, Confidence, Declutter, Optical, Telemetry), `perf_end()` | `module_update_project()` |
| **Publish** | `perf_measure(SUBSYS_SYM_PUBLISH)` | `module_update_publish()` |

## 4. Success Criteria

| Criterion | Status |
|---|---|
| Histograms receive real timing data | ✅ `histogram_record()` is called for every frame per subsystem |
| No dynamic allocation | ✅ All buffers are static arrays (`samples[1024]`, `bins[32]`) |
| WASM-safe | ✅ Uses only `__builtin_*` math, no libc or heap |
| Existing structures preserved | ✅ All original fields untouched, new code only adds callsites |
