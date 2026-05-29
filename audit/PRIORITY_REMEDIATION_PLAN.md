# PRIORITY REMEDIATION PLAN

**Generated:** 2026-05-29  
**Source:** Synthesis of all 7 audit reports

---

## 1. Executive Summary

Based on thorough source-code evidence review, the repository has **3–5 actual compile blockers**, **11 documentation false claims**, **~288 dead/obsolete files**, and **structural inconsistencies** across 4 independent aircraft registries. All classifications below are based exclusively on source-code evidence (not on external reports or assumptions).

---

## 2. VERIFIED Issues

### 🔴 CRITICAL — Compile Blockers

| # | Issue | Evidence | Files Affected |
|---|---|---|---|
| CB-1 | `calib_init` declaration missing from current `include/module.h` | Called at `main.cpp:184`. Only in `module.h.bak:553`. | main.cpp, include/module.h |
| CB-2 | `debug_init` declaration missing from current `include/module.h` | Called at `main.cpp:185`. Only in `module.h.bak:579`. | main.cpp, include/module.h |
| CB-3 | `optics_init` declaration missing from current `include/module.h` | Called at `main.cpp:186`. Only in `module.h.bak:592`. | main.cpp, include/module.h |
| CB-4 | `weather_compute_params` declaration missing from current `include/module.h` | Called at `main.cpp:276,278`. Only in `module.h.bak:533`. | main.cpp, include/module.h |
| CB-5 | `lvar_init` declaration missing from current `include/module.h` | Called at `module.cpp:149`. Declared in `module.h.bak:492`. **Defined** in `lvar_table.cpp`. | module.cpp, include/module.h |

### 🔴 HIGH — Integrity Issues

| # | Issue | Evidence |
|---|---|---|
| HI-1 | README claims 7 files that don't exist | `telemetry.h`, `perf_monitor.h`, `pacing_validator.h`, `compatibility.h`, `perf_monitor.cpp`, `pacing_validator.cpp`, `compatibility.cpp` |
| HI-2 | module.cpp allowlist missing PMDG 777-300ER and iniBuilds A350 | C++ allowlist at `module.cpp:20-28` doesn't include these, but detector and profiles do |
| HI-3 | module.cpp allowlist includes ASOBO BOEING 747-8I with no profile or detector support | 747-8I only in allowlist, nowhere else |
| HI-4 | Version drift — 5 files report wrong version | See VERSION_AUDIT.md |
| HI-5 | certification.py scores are simulated, not measured | Test pass rate is always 0.95+ regardless of actual results |

### 🟡 MEDIUM — Consistency Issues

| # | Issue | Evidence |
|---|---|---|
| CI-1 | Category mismatch — FBW A32NX and HEADWIND A330-900 classified as BOEING_HGS | These are Airbus aircraft mapped to Boeing behavior |
| CI-2 | `hud_detect_category()` function possibly dead | Defined in `aircraft_detector.cpp`, no internal callers found |
| CI-3 | Missing `.gitignore` for backups, pycache, and artifacts | ~288 removable files in repo |

### ⚪ INFORMATIONAL

| # | Issue | Evidence |
|---|---|---|
| I-1 | `include/hud/verification.h` claims `debug_init` is "defined in module.h" | False — not in current module.h |
| I-2 | aircraft_profiles.h `C_HUD_NUM_PROFILES = 6` matches actual array length | ✅ Verified correct |

---

## 3. FALSE POSITIVES

Claims from external reports that could NOT be verified by source code:

| Claim | Reason for FALSE POSITIVE |
|---|---|
| "Missing telemetry implementation" | Telemetry types ARE defined in `include/module.h` (sections 2e-2h). The functionality was consolidated into module.h, not extracted into separate files. |
| "pacing_validator files missing" | Frame pacing types (PacingState, PacingAnomalyEvent, etc.) ARE defined inline in `include/module.h:366-427`. The README claimed separate files that were never created because the implementation was kept in the main header. |
| "Dead code — unused A350 modules" | Cannot confirm without full runtime call graph analysis. These files are compiled but may be reached through AirbusHUDBehavior. **UNVERIFIED**. |
| "Broken compatibility between module.cpp and aircraft_detector.cpp" | They serve different purposes: module.cpp is a HUD power allowlist (gate), detector.cpp is a behavioral classifier. The mismatch is a design concern but NOT a bug per se. |
| `hud_detect_category()` is functionally unused in current call paths but is a public API | It's exported for external consumers. Not truly dead. |

---

## 4. UNVERIFIED Claims

Claims for which insufficient source-code evidence exists:

| Claim | Why UNVERIFIED |
|---|---|
| "The project compiles successfully" | No CI artifacts, no build script output in repo, no `.wasm` binary present. Cannot confirm. |
| "884 passing tests" | README claim. `.pytest_cache` has stale data but no actual run results. |
| "A350-specific modules are reachable" | AirbusHUDBehavior implementation was not fully traced. These may or may not call the A350 module functions. |
| "Installer works correctly" | No integration test evidence in the repo. The installer Python code exists but its runtime behavior cannot be verified. |
| "All SimVar tokens resolve at runtime" | WASM runtime resolution depends on MSFS SDK which is not present. |
| "pytest suite is currently passing" | Cannot verify without running the tests in the current environment. |

---

## 5. Actual Compile Blockers

Based on source code analysis, these ARE compile blockers for the WASM target:

| Rank | Function | File | Missing From | Severity |
|---|---|---|---|---|
| 1 | `calib_init(HUDSettings*)` | main.cpp:184 | current module.h | 🔴 **BLOCKER** — called, no declaration |
| 2 | `debug_init(DebugOverlay*)` | main.cpp:185 | current module.h | 🔴 **BLOCKER** — called, no declaration |
| 3 | `optics_init(OpticalState*)` | main.cpp:186 | current module.h | 🔴 **BLOCKER** — called, no declaration |
| 4 | `weather_compute_params(FLOAT64, WeatherState*)` | main.cpp:276,278 | current module.h | 🔴 **BLOCKER** — called, no declaration |
| 5 | `lvar_init(void)` | module.cpp:149 | current module.h (declaration) | 🟡 **SOFT BLOCKER** — defined in lvar_table.cpp, declaration missing from module.h |

**Note:** While these functions are declared in `module.h.bak`, compiler doesn't read `.bak` files. The build will fail with "implicit function declaration" errors (or link errors in C++).

---

## 6. Actual Runtime Blockers

No runtime blockers can be confirmed from source analysis alone. However, these are POTENTIAL runtime issues:

| Issue | Potential Impact |
|---|---|
| If `calib_init` is not called, calibration state is zero-initialized | HUDSettings fields will be 0.0 instead of sensible defaults. May cause division-by-zero or NaN in projection math. |
| If `debug_init` is not called | Debug overlay flags remain false (safe default). Low impact. |
| If `optics_init` is not called | OpticalState fields will be 0.0 instead of sensible defaults. Phosphor buffer uninitialized. |
| If `weather_compute_params` is not called | WeatherState will remain invalid. Line width and opacity are never set. |
| HUD may show no symbology due to missing weather parameters | Runway lines may be invisible. |

---

## 7. Recommended Fix Order

### Phase 1 — Fix Compile Blockers (IMMEDIATE)

| Step | Action | Risk |
|---|---|---|
| 1 | Copy `calib_init`, `debug_init`, `optics_init`, `weather_compute_params` static inline definitions from `include/module.h.bak` into current `include/module.h` before the `#endif` guard | Low — these are simple initializer functions |
| 2 | Add `void lvar_init(void);` declaration to current `include/module.h` | Low — matches existing definition in `lvar_table.cpp` |
| 3 | Remove `include/module.h.bak` and `src/lvar_table.cpp.bak` | Low — obsolete backups |
| 4 | Attempt compilation | Medium — may reveal additional issues |

### Phase 2 — Fix Integrity Issues (HIGH)

| Step | Action | Risk |
|---|---|---|
| 5 | Create `.gitignore` for `*.bak`, `*.pyc`, `__pycache__/`, `.pytest_cache/`, `installer/backups/` | Low |
| 6 | Clean all ~288 dead/obsolete files from repo | Low |
| 7 | Update README.md to reflect actual file structure (remove 7 phantom files) | Low — documentation only |
| 8 | Add PMDG 777-300ER and iniBuilds A350 to `module.cpp` allowlist | Low — adds missing entries |
| 9 | Remove ASOBO BOEING 747-8I from `module.cpp` allowlist or add proper support | Medium — could break existing users |
| 10 | Update version banners: `main.cpp` → 2.7.0, `module.cpp` → 2.7.0, `installer/__init__.py` → 2.7.0, `README.md` → 2.7.0 | Low |

### Phase 3 — Structural Improvements (MEDIUM)

| Step | Action | Risk |
|---|---|---|
| 11 | Implement single aircraft registry (see COMPATIBILITY_MATRIX.md Section 3) | Medium — requires coordination |
| 12 | Replace Python `compat_map` with auto-generated version from C++ | Medium |
| 13 | Fix category misclassification (A32NX, A330 → AIRBUS_HUD) | Medium — changes behavior |
| 14 | Make certification scoring real (integrate pytest) | Low-Medium |

### Phase 4 — Verification (ONGOING)

| Step | Action |
|---|---|
| 15 | Run `pytest tests/ -v` after each phase |
| 16 | Verify WASM compilation with `cmake --build build` |
| 17 | Regenerate all audit documents |
| 18 | Add CI pipeline to prevent regression |

---

## 8. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Compile blocker fix introduces regressions | Low | Medium | Copy .bak functions verbatim, verify with tests |
| Missing declarations mask deeper issues | Medium | High | After adding declarations, verify all callee functions exist |
| category fix (A32NX → AIRBUS_HUD) changes runtime behavior | Medium | Medium | Test with FBW A32NX users |
| Remove 747-8I from allowlist breaks existing users | Low | Low (no profile exists) | Add proper support instead of removing |
| Cleanup removes wanted telemetry data | Low | Low | Data is from May 29, 2026 — test artifacts |

---

## 9. Evidence Sources

All conclusions in this document are based on:
- Direct grep searches of the entire codebase
- File-by-file comparison of README claims vs actual files
- Cross-reference of all function declarations and calls
- Version string comparison across 10+ files
- Analysis of ~3500 lines of Python certification code
- Inspection of ~240 backup/build artifact files
