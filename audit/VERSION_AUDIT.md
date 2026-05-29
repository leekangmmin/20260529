# VERSION CONSISTENCY AUDIT

**Generated:** 2026-05-29  
**Methodology:** grep for version strings, banner comments, `__version__`, `VERSION`, `project(... VERSION ...)`

---

## 1. All Version Declaration Locations

| # | File | Current Version | Intended/Claimed Version | Type |
|---|---|---|---|---|
| 1 | `CMakeLists.txt:12` | `project(C_HUD_Runway VERSION 2.7.0 ...)` | 2.7.0 | Build system (authoritative) |
| 2 | `include/module.h:4` (banner) | `v2.7.0 — ROLLOUT/CAT-III/EVS ENHANCEMENT` | 2.7.0 | Header banner |
| 3 | `include/module.h.bak:4` (banner) | `v2.2.0 — REAL FLIGHT VALIDATION RELEASE` | 2.2.0 | Backup (obsolete) |
| 4 | `src/main.cpp:5` (banner) | `v2.6.0 — RUNTIME INSTRUMENTATION & CERTIFICATION` | 2.7.0? | Source banner |
| 5 | `src/module.cpp:4` (banner) | `v2.2.0 — REAL FLIGHT VALIDATION RELEASE` | 2.7.0? | Source banner |
| 6 | `src/lvar_table.cpp:3` (banner) | `v2.7.0` | 2.7.0 | Source banner |
| 7 | `src/lvar_table.cpp.bak:3` (banner) | `v2.7.0` | 2.7.0 | Backup ✅ matches |
| 8 | `installer/__init__.py:16` | `__version__ = "2.6.0"` | 2.7.0? | Installer version |
| 9 | `README.md:3` | `**v2.6.0 — RUNTIME INSTRUMENTATION & OPERATIONAL CERTIFICATION**` | 2.7.0? | Documentation |
| 10 | `installer/certification.py` | `self.installer_version = __version__` (reads from installer/__init__.py) | 2.6.0 | Derived |

---

## 2. Version Drift Analysis

```
CMakeLists.txt     →  2.7.0  ← Build system (should be source of truth)
module.h           →  2.7.0  ✅ matches CMake
main.cpp           →  2.6.0  ❌ 1 minor behind
module.cpp         →  2.2.0  ❌ 5 minors behind (severely outdated)
lvar_table.cpp     →  2.7.0  ✅ matches CMake
installer/__init__.py → 2.6.0 ❌ 1 minor behind
README.md          →  2.6.0  ❌ 1 minor behind
```

### Summary of Drift

| Version Delta | Files |
|---|---|
| Correct (2.7.0) | CMakeLists.txt, module.h, lvar_table.cpp |
| 1 minor behind (2.6.0) | main.cpp, installer/__init__.py, README.md |
| Severely outdated (2.2.0) | module.cpp |

---

## 3. LVAR_VERSION Analysis

The HUD publishes an L:var `L:C_HUD_Version` via the `LVAR_VERSION` enum, but the actual version number is not hardcoded — it's written dynamically. No version constant is exported from the C++ code that can be consumed by external tools.

---

## 4. Recommendations for Single Authoritative Version Source

### Option A: CMake as Source of Truth (Recommended)

1. **CMakeLists.txt** generates a `version.h` header at build time:
   ```cmake
   configure_file(
     include/version.h.in
     include/version.h
     @ONLY
   )
   ```

2. `include/version.h.in`:
   ```c
   #define C_HUD_VERSION_MAJOR @C_HUD_VERSION_MAJOR@
   #define C_HUD_VERSION_MINOR @C_HUD_VERSION_MINOR@
   #define C_HUD_VERSION_PATCH @C_HUD_VERSION_PATCH@
   #define C_HUD_VERSION_STRING "@C_HUD_VERSION@"
   ```

3. All C++ files `#include "version.h"` instead of embedding version in banners.

4. `installer/__init__.py` reads version from a `version.json` that is generated from CMake.

5. README.md references are checked in CI via a simple grep test.

### Current Version Discrepancies (Summary Table)

| File | Current | Should Be | Risk |
|---|---|---|---|
| `CMakeLists.txt` | 2.7.0 | 2.7.0 | — |
| `include/module.h` | 2.7.0 | 2.7.0 | — |
| `src/main.cpp` | 2.6.0 | 2.7.0 | Outdated banner misleads developers |
| `src/module.cpp` | 2.2.0 | 2.7.0 | Misleading — implies ancient code |
| `installer/__init__.py` | 2.6.0 | 2.7.0 | Installer reports wrong version |
| `README.md` | 2.6.0 | 2.7.0 | Documentation out of sync |
