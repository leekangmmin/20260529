# OPTICAL STABILITY VALIDATION — Phase 3, Task 5

**Date:** 2026-05-29  
**Scope:** Verify that optical stability metrics are actively updated every frame.

---

## 1. Structures Audited

| Field | Location | Previously Updated? | Now Updated? |
|---|---|---|---|
| `OpticalStabilityMetrics` | `include/module.h` | ✅ Declared, initialised | ✅ Updated every frame |
| `optic_stability_init()` | `include/module.h` line 930 | ✅ Called in `module_init()` | ✅ Unchanged |
| `optic_stability_update()` | NEW — `include/module.h` section 4b | N/A | ✅ Called every frame |

## 2. What `optic_stability_update()` Does

```c
static inline void optic_stability_update(
    OpticalStabilityMetrics* osm,
    FLOAT64 element_x, FLOAT64 element_y,
    FLOAT64 dt_s, FLOAT64 brightness)
```

Updates per frame:
- **`shimmer_accumulator`** — Accumulates absolute element position values (X + Y) as a proxy for high-frequency oscillation. Decayed by 50% every 60 samples.
- **`shimmer_sample_count`** — Tracks samples in window for averaging
- **`current_fatigue`** — 0..1 fatigue level. Increases with brightness × dt, decays when brightness < 0.3.
- **`optical_stability_score`** — 0..1 combined score. Penalised by shimmer excess and fatigue > 0.7.

## 3. Integration Point

Called in `module_update_project()` (main.cpp) after FPS/jitter computation and pacing update. Uses current FPV screen position as the element input for shimmer detection.

## 4. Test Evidence

All 24 tests in `tests/test_optical_validation.py` pass, including:
- `test_no_shimmer_for_stable_position` — validates baseline
- `test_shimmer_detected_for_oscillation` — validates shimmer detection
- `test_fatigue_increases_over_time` — validates fatigue tracking
- `test_perfect_stable_optics` — validates stability scoring
- `test_shimmer_reduces_score` — validates score penalisation
- `test_score_range` — validates score clamped to 0..1

## 5. Success Criteria

| Criterion | Status |
|---|---|
| Optical stability metrics update every frame | ✅ |
| Uses existing fields only | ✅ |
| No new metrics added | ✅ |
| No new structures added | ✅ |
| Score updates correctly under shimmer/fatigue | ✅ |
