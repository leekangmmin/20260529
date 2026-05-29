# DEAD CODE AUDIT REPORT

**Generated:** 2026-05-29  
**Scope:** All source files, backup files, build artifacts, and unused compiled files

---

## 1. Backup Files (Stale/Obsolete)

### 1.1 C++ Header Backup

| File | Status | Reason |
|---|---|---|
| `include/module.h.bak` | 🗑️ **DEAD** | v2.2.0 backup of module.h. Current module.h is v2.7.0. The .bak file contains declarations (`calib_init`, `debug_init`, `optics_init`, `weather_compute_params`, `lvar_init`) that are MISSING from the current `include/module.h`, making it a misleading reference. Should be removed. |

### 1.2 C++ Source Backup

| File | Status | Reason |
|---|---|---|
| `src/lvar_table.cpp.bak` | 🗑️ **DEAD** | Backup copy of lvar_table.cpp. Contains a duplicate `lvar_init()` definition. Current lvar_table.cpp also defines `lvar_init()`. Potential linker conflict if accidentally both get compiled. Should be removed. |

### 1.3 Installer Backup Zips

| Count | Pattern | Status | Reason |
|---|---|---|---|
| 103 files | `installer/backups/bk_*.zip` | 🗑️ **DEAD** | Backup zip files from installer patching operations, e.g., `bk_1780011810_pmdg-737-800.zip`. These are user-data artifacts that should not be in the repository. |
| 50+ files | `installer/backups/txn_*.json` | 🗑️ **DEAD** | Transaction test artifacts, e.g., `txn_1780011810_test.json`. |
| 80+ files | `installer/backups/hgs_telemetry_*.json` | 🗑️ **DEAD** | Telemetry dump files from testing sessions, e.g., `hgs_telemetry_20260529_090132.json`. |
| 1 file | `installer/backups/healer_state.json` | 🗑️ **DEAD** | Healer state snapshot. |
| 1 file | `installer/backups/backup_manifest.json` | 🗑️ **DEAD** | Backup manifest. |

**Total: ~240 files** — All should be removed from repository and gitignored.

---

## 2. Compiled Python Cache Files

| Location | Count | Status | Reason |
|---|---|---|---|
| `installer/__pycache__/*.cpython-314.pyc` | 12 files | 🗑️ **DEAD** | Python bytecode cache. Should be gitignored. |
| `tests/__pycache__/*.cpython-314-pytest-9.0.3.pyc` | 40+ files | 🗑️ **DEAD** | Pytest bytecode cache. Should be gitignored. |
| `.pytest_cache/` | Entire directory | 🗑️ **DEAD** | Pytest cache. Should be gitignored. |
| `tests/.pytest_cache/` | Entire directory | 🗑️ **DEAD** | Pytest cache (duplicate). Should be gitignored. |

---

## 3. Missing Source Files (Referenced in README but Not Present)

These files are documented as part of the project but do not exist:

| Claimed File | Documentation Source | Impact |
|---|---|---|
| `include/hud/telemetry.h` | README.md | Telemetry functionality is inline in module.h |
| `include/hud/perf_monitor.h` | README.md | Perf monitoring is inline in module.h |
| `include/hud/pacing_validator.h` | README.md | Pacing functionality is in module.h |
| `include/hud/compatibility.h` | README.md | Compatibility types are in module.h |
| `src/hud/perf_monitor.cpp` | README.md | No separate implementation file |
| `src/hud/pacing_validator.cpp` | README.md | No separate implementation file |
| `src/hud/compatibility.cpp` | README.md | No separate implementation file |

These are not "dead" in the traditional sense — the functionality exists, but it was integrated into `module.h` rather than kept in separate files as the README claims.

---

## 4. Orphaned Functionality Analysis

### 4.1 Functions Declared in Backup Only

The following functions are **called** from `src/main.cpp` but **only declared** in `include/module.h.bak` (the backup file), NOT in the current `include/module.h`:

| Function | Called in | Declared in current module.h? |
|---|---|---|
| `calib_init` | `src/main.cpp:184` | ❌ MISSING (only in .bak) |
| `debug_init` | `src/main.cpp:185` | ❌ MISSING (only in .bak) |
| `optics_init` | `src/main.cpp:186` | ❌ MISSING (only in .bak) |
| `weather_compute_params` | `src/main.cpp:276,278` | ❌ MISSING (only in .bak) |
| `lvar_init` | `src/module.cpp:149` | ❌ Declaration MISSING but **defined** in `src/lvar_table.cpp` |

**Classification:** These are NOT dead code but **orphaned declarations** — the function implementations may have been lost during the transition from module.h.bak (v2.2.0) to module.h (v2.7.0). They are currently **compile blockers** (see AUDIT_VERIFICATION.md).

### 4.2 Functions Defined but No Longer Called

Using static analysis based on search patterns:

| Function | Defined in | Called from | Status |
|---|---|---|---|
| `hud_profiles_init_all()` | `aircraft_profiles.cpp` | `module.cpp:109` | ✅ ACTIVE |
| `hud_profile_match()` | `aircraft_profiles.cpp` | `aircraft_detector.cpp` | ✅ ACTIVE |
| `hud_behavior_create()` | `aircraft_detector.cpp` | `main.cpp` (ensure_behavior) | ✅ ACTIVE |
| `hud_detect_category()` | `aircraft_detector.cpp` | Not called in any .cpp file | 🔶 **POSSIBLY DEAD** — declared and defined but no internal caller found. Might be used externally. |

---

## 5. Unreferenced Compiled Sources

All `.cpp` files listed in `CMakeLists.txt` GAUGE_SOURCES have corresponding headers and are compiled. No compiled source files are completely unreferenced.

However, these A350-specific files may be partially dead since the A350 is classified as AIRBUS_HUD but:

| File | Status | Notes |
|---|---|---|
| `src/hud/aircraft/a350_autoland.cpp` | ⚠️ **POSSIBLY DEAD** | Only used if A350-specific behavior is invoked |
| `src/hud/aircraft/a350_cat3.cpp` | ⚠️ **POSSIBLY DEAD** | Same — A350-specific |
| `src/hud/aircraft/a350_flare_law.cpp` | ⚠️ **POSSIBLY DEAD** | AirbusHUDBehavior may or may not use these |
| `src/hud/aircraft/a350_fpv_controller.cpp` | ⚠️ **POSSIBLY DEAD** | Same |
| `src/hud/aircraft/a350_horizon.cpp` | ⚠️ **POSSIBLY DEAD** | Same |
| `src/hud/aircraft/a350_landing_energy.cpp` | ⚠️ **POSSIBLY DEAD** | Same |
| `src/hud/aircraft/a350_profile.cpp` | ⚠️ **POSSIBLY DEAD** | Same |
| `src/hud/aircraft/a350_rollout.cpp` | ⚠️ **POSSIBLY DEAD** | Same |
| `src/hud/aircraft/a350_runway_augmentation.cpp` | ⚠️ **POSSIBLY DEAD** | Same |
| `src/hud/aircraft/a350_symbology.cpp` | ⚠️ **POSSIBLY DEAD** | Same |
| `src/hud/aircraft/airbus_fpv.cpp` | ⚠️ **POSSIBLY DEAD** | Same |

**Verdict:** These are all compiled into the WASM binary but their code paths may never be reached if `AirbusHUDBehavior` doesn't call them. Full verification requires tracing the `AirbusHUDBehavior` implementation, which is out of scope for this dead-code audit. Marked as **UNVERIFIED**.

---

## 6. Unused Header Files

All `.h` files in `include/` and `include/hud/` are referenced by at least one `.cpp` file. No completely orphaned headers found.

---

## 7. Summary

| Category | Count | Disposition |
|---|---|---|
| Backup header (.bak) | 1 | 🗑️ Remove |
| Backup source (.bak) | 1 | 🗑️ Remove |
| Backup zip files | ~103 | 🗑️ Remove |
| Transaction artifacts | ~50 | 🗑️ Remove |
| Telemetry dumps | ~80 | 🗑️ Remove |
| Python cache files | ~52 | 🗑️ Remove |
| Missing claimed files | 7 | 📝 Update README |
| Possibly dead A350 modules | 11 | 🔶 UNVERIFIED |
| Orphaned function declarations | 5 | 🔴 ACTIVE COMPILE BLOCKER (not dead, but missing) |

**Total removable artifacts: ~288 files**
