# README VALIDATION REPORT

**Generated:** 2026-05-29  
**Scope:** Compare README.md documented file structure against actual repository files.

---

## 1. Documented vs Actual File Structure

### Legend
- ✅ **EXISTS** — File found at the documented location
- ❌ **MISSING** — File documented but not found
- 🔶 **RENAMED/MOVED** — File exists but under different name/location
- ⚠️ **OBSOLETE** — File exists but is a backup or stale copy

---

### 1.1 `include/` Directory

| README Claimed Path | Actual Path | Status | Notes |
|---|---|---|---|
| `include/module.h` | `include/module.h` | ✅ EXISTS | Current v2.7.0 header |
| — | `include/module.h.bak` | ⚠️ OBSOLETE | Backup of v2.2.0 — should be removed |
| `include/hud/telemetry.h` | ❌ NOT FOUND | ❌ MISSING | Claimed in README "v2.6.0" structure |
| `include/hud/perf_monitor.h` | ❌ NOT FOUND | ❌ MISSING | Claimed as NEW in README |
| `include/hud/pacing_validator.h` | ❌ NOT FOUND | ❌ MISSING | Claimed as NEW in README |
| `include/hud/compatibility.h` | ❌ NOT FOUND | ❌ MISSING | Claimed as NEW in README |
| — | `include/hud/aircraft_detector.h` | ✅ EXISTS | Not listed in README structure |
| — | `include/hud/aircraft_profiles.h` | ✅ EXISTS | Not listed in README structure |
| — | `include/hud/airport_database.h` | ✅ EXISTS | Not listed in README structure |
| — | `include/hud/collimation.h` | ✅ EXISTS | Not listed |
| — | `include/hud/confidence.h` | ✅ EXISTS | Not listed |
| — | `include/hud/declutter.h` | ✅ EXISTS | Not listed |
| — | `include/hud/depth_illusion.h` | ✅ EXISTS | Not listed |
| — | `include/hud/evs.h` | ✅ EXISTS | Not listed |
| — | `include/hud/flare.h` | ✅ EXISTS | Not listed |
| — | `include/hud/fpv.h` | ✅ EXISTS | Not listed |
| — | `include/hud/guidance.h` | ✅ EXISTS | Not listed |
| — | `include/hud/rollout.h` | ✅ EXISTS | Not listed |
| — | `include/hud/runway_cache.h` | ✅ EXISTS | Not listed |
| — | `include/hud/runway_projection.h` | ✅ EXISTS | Not listed |
| — | `include/hud/stabilization.h` | ✅ EXISTS | Not listed |
| — | `include/hud/symbology.h` | ✅ EXISTS | Not listed |
| — | `include/hud/verification.h` | ✅ EXISTS | Not listed in README |
| — | `include/hud/visual_response.h` | ✅ EXISTS | Not listed in README |
| — | `include/projection.h` | ✅ EXISTS | Not listed in README |
| — | `include/hud/aircraft/a350_*.h` (9 files) | ✅ EXISTS | Not listed in README |
| — | `include/hud/aircraft/airbus_*.h` | ✅ EXISTS | Not listed |
| — | `include/hud/aircraft/boeing_*.h` | ✅ EXISTS | Not listed |
| — | `include/hud/aircraft/ihud_aircraft_behavior.h` | ✅ EXISTS | Not listed |

### 1.2 `src/` Directory

| README Claimed Path | Actual Path | Status | Notes |
|---|---|---|---|
| `src/main.cpp` | `src/main.cpp` | ✅ EXISTS | |
| `src/lvar_table.cpp` | `src/lvar_table.cpp` | ✅ EXISTS | |
| — | `src/lvar_table.cpp.bak` | ⚠️ OBSOLETE | Backup file |
| `src/hud/perf_monitor.cpp` | ❌ NOT FOUND | ❌ MISSING | Claimed as NEW in README |
| `src/hud/pacing_validator.cpp` | ❌ NOT FOUND | ❌ MISSING | Claimed as NEW in README |
| `src/hud/compatibility.cpp` | ❌ NOT FOUND | ❌ MISSING | Claimed as NEW in README |
| `src/hud/calibration.cpp` | `src/hud/calibration.cpp` | ✅ EXISTS | |
| — | `src/hud/aircraft_detector.cpp` | ✅ EXISTS | Not listed |
| — | `src/hud/aircraft_profiles.cpp` | ✅ EXISTS | Not listed |
| — | (23 more .cpp files) | ✅ EXISTS | Not listed |

### 1.3 `tests/` Directory

| README Claimed Path | Actual Path | Status | Notes |
|---|---|---|---|
| `test_runtime_instrumentation.py` | ✅ | ✅ EXISTS | |
| `test_telemetry_capture.py` | ✅ | ✅ EXISTS | |
| `test_frame_pacing.py` | ✅ | ✅ EXISTS | |
| `test_aircraft_compatibility.py` | ✅ | ✅ EXISTS | |
| `test_optical_validation.py` | ✅ | ✅ EXISTS | |
| `test_long_duration_stability.py` | ✅ | ✅ EXISTS | |
| `test_operational_certification.py` | ✅ | ✅ EXISTS | |

All 7 claimed test files exist ✅. However, there are **43+ additional test files** not documented in the README.

---

## 2. Missing Files Summary

**7 files** claimed in README do not exist in the repository:

| Claimed File | Claimed Purpose |
|---|---|
| `include/hud/telemetry.h` | Binary export, compression, session mgmt |
| `include/hud/perf_monitor.h` | Runtime performance monitoring (NEW) |
| `include/hud/pacing_validator.h` | Frame pacing validation (NEW) |
| `include/hud/compatibility.h` | Aircraft compatibility (NEW) |
| `src/hud/perf_monitor.cpp` | Performance monitoring impl (NEW) |
| `src/hud/pacing_validator.cpp` | Pacing validation impl (NEW) |
| `src/hud/compatibility.cpp` | Compatibility impl (NEW) |

### Impact

All 7 missing files are claimed as "NEW" in the v2.6.0 section of README. The functionality they describe (perf monitoring, pacing, compatibility signatures) is actually implemented **inline in `include/module.h`** via POD structs and static inline functions, not in separate files. The README documents a file structure that doesn't match the actual implementation architecture.

---

## 3. Obsolete/Backup Files

| File | Age | Recommendation |
|---|---|---|
| `include/module.h.bak` | v2.2.0 backup | 🗑️ REMOVE — Obsolete, confuses developers |
| `src/lvar_table.cpp.bak` | v2.7.0 backup | 🗑️ REMOVE — Duplicate of current file |
| `installer/backups/bk_*.zip` (103 files) | Various | 🗑️ REMOVE — Backup artifacts polluting repo |
| `installer/backups/txn_*.json` (50+ files) | Various | 🗑️ REMOVE — Transaction test artifacts |
| `installer/backups/hgs_telemetry_*.json` (80+ files) | Various | 🗑️ REMOVE — Telemetry dump artifacts |
| `*.pyc` throughout | Build artifacts | 🗑️ REMOVE — Should be gitignored |

---

## 4. Obsolete Documentation References

The following README sections contain inaccurate or misleading information:

1. **Project Structure** — Lists 7 files that don't exist (see Section 2)
2. **Test Results** — Claims 884 passing tests but doesn't list all test files
3. **What's New in v2.6.0** — Describes capabilities that cannot be verified from source (perf_monitor, pacing_validator, compatibility as separate modules)
4. **Missing aircraft_profiles.h** from the documented include structure — the profile system is a core component not mentioned
