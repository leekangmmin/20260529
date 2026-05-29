# PACING VALIDATION — Phase 3, Task 4

**Date:** 2026-05-29  
**Scope:** Verify that frame pacing state is actively updated every frame.

---

## 1. Structures Audited

| Field | Location | Previously Updated? | Now Updated? |
|---|---|---|---|
| `PacingState` | `include/module.h` | ✅ Declared, initialised | ✅ Updated every frame |
| `pacing_init()` | `include/module.h` line 907 | ✅ Called in `module_init()` | ✅ Unchanged |
| `pacing_update()` | NEW — `include/module.h` section 4b | N/A | ✅ Called every frame |

## 2. What `pacing_update()` Does

```c
static inline void pacing_update(PacingState* ps, FLOAT64 dt_s, 
                                  int frame_index, FLOAT64 timestamp_s)
```

Updates per frame:
- **`dt_history[]`** — Rolling window of last 60 frame intervals (circular buffer)
- **`dt_sample_count`** — Capped at 60
- **`dt_min` / `dt_max`** — Running min/max
- **`dt_mean` / `dt_stddev`** — Running mean and standard deviation
- **Anomaly detection** — Compares `dt_ms` against `hitch_threshold_ms` (50ms) and `stutter_threshold_ms` (33ms mean over 10+ frames)
- **`anomalies[]`** — Circular log of last 32 anomalies (HITCH or STUTTER type)
- **`continuity_metric`** — 0..1, increments by +0.01 per stable frame, drops by -0.2 on anomaly
- **`consecutive_stable_frames`** — Count reset on anomaly
- **`in_recovery` / `recovery_frames`** — Recovery tracking

## 3. Integration Point

Called in `module_update_project()` (main.cpp) after FPS/jitter computation and before pause detection. This ensures `dt_s` is available from the frame delta timing block.

## 4. Test Evidence

All 32 tests in `tests/test_frame_pacing.py` pass, including:
- `test_record_normal_frame` — validates basic state update
- `test_dt_history_limited` — validates rolling window cap
- `test_hitch_detection` — validates anomaly detection
- `test_continuity_drops_on_hitch` — validates continuity metric behavior
- `test_recovery_after_hitch` — validates recovery tracking

## 5. Success Criteria

| Criterion | Status |
|---|---|
| Frame pacing state updates every frame | ✅ |
| `dt_history` receives real frame intervals | ✅ |
| `continuity_metric` updates correctly | ✅ |
| `consecutive_stable_frames` updates | ✅ |
| Anomaly detection functions | ✅ |
