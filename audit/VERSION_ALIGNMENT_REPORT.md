# VERSION ALIGNMENT REPORT — Phase 2 Version Consistency

**Generated:** 2026-05-29  
**Repository:** C_HUD_Runway  
**Authoritative Source:** `CMakeLists.txt` → `project(C_HUD_Runway VERSION 2.7.0 ...)`

---

## Before: Version Drift Analysis

| # | File | Old Version | Intended | Delta |
|---|---|---|---|---|
| 1 | `CMakeLists.txt:33` (project VERSION) | 2.7.0 | 2.7.0 | ✅ Correct (authoritative) |
| 2 | `include/module.h:4` (banner) | v2.7.0 | 2.7.0 | ✅ Correct |
| 3 | `src/main.cpp:3` (banner) | v2.6.0 | 2.7.0 | ❌ 1 minor behind |
| 4 | `src/module.cpp:3` (banner) | v2.2.0 | 2.7.0 | ❌ 5 minors behind |
| 5 | `src/lvar_table.cpp:2` (banner) | v2.7.0 | 2.7.0 | ✅ Correct |
| 6 | `installer/__init__.py:16` (__version__) | "2.6.0" | "2.7.0" | ❌ 1 minor behind |
| 7 | `README.md:3` (header) | v2.6.0 | 2.7.0 | ❌ 1 minor behind |
| 8 | `src/main.cpp:877` (LVAR_VERSION runtime) | 2.5 | 2.7 | ❌ Incorrect runtime version |
| 9 | `include/module.h.bak:4` | v2.2.0 | N/A | ❌ Stale backup (DELETED) |
| 10 | `src/lvar_table.cpp.bak:3` | v2.7.0 | N/A | ❌ Stale backup (DELETED) |

---

## After: All Versions Synchronized

| # | File | New Version | Status |
|---|---|---|---|
| 1 | `CMakeLists.txt:33` | 2.7.0 | ✅ Authoritative |
| 2 | `include/module.h:4` | v2.7.0 | ✅ Matches CMake |
| 3 | `src/main.cpp:3` | **v2.7.0** (fixed) | ✅ Now matches |
| 4 | `src/module.cpp:3` | **v2.7.0** (fixed) | ✅ Now matches |
| 5 | `src/lvar_table.cpp:2` | v2.7.0 | ✅ Already correct |
| 6 | `installer/__init__.py:16` | **"2.7.0"** (fixed) | ✅ Now matches |
| 7 | `README.md:3` | **v2.7.0** (fixed) | ✅ Now matches |
| 8 | `src/main.cpp:877` (LVAR_VERSION) | **2.7** (fixed) | ✅ Now matches |
| 9 | `include/module.h.bak` | **DELETED** | ✅ Removed |
| 10 | `src/lvar_table.cpp.bak` | **DELETED** | ✅ Removed |

---

## Changes Applied

| File | Change | Justification |
|---|---|---|
| `src/main.cpp:3` | `v2.6.0` → `v2.7.0` | Align banner with authoritative CMake version |
| `src/module.cpp:3` | `v2.2.0` → `v2.7.0` | Align banner with authoritative CMake version |
| `installer/__init__.py:16` | `"2.6.0"` → `"2.7.0"` | Align installer version with project version |
| `README.md:3` | `v2.6.0` → `v2.7.0` | Align documentation with current version |
| `src/main.cpp:877` | `2.5` → `2.7` | Runtime LVAR_VERSION must match project version |
| `include/module.h.bak` | Deleted | Stale backup |
| `src/lvar_table.cpp.bak` | Deleted | Stale backup |

---

## No Conflicts Remaining

All 10 version declaration points have been reconciled to 2.7.0. The CMake `project(VERSION ...)` directive remains the single source of truth. No runtime behavior was changed — only version strings and banners were updated.
