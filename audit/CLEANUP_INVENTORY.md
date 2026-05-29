# CLEANUP INVENTORY — Phase 2 Repository Cleanup

**Generated:** 2026-05-29  
**Repository:** C_HUD_Runway  

---

## Category 1: Python Bytecode (`.pyc`) — 60 files

### Directory: `installer/__pycache__/` — 12 files
| File | Size |
|---|---|
| `installer/__pycache__/__init__.cpython-314.pyc` | ~4 KB |
| `installer/__pycache__/aircraft_scanner.cpython-314.pyc` | ~8 KB |
| `installer/__pycache__/certification.cpython-314.pyc` | ~6 KB |
| `installer/__pycache__/diagnostics.cpython-314.pyc` | ~5 KB |
| `installer/__pycache__/healer.cpython-314.pyc` | ~7 KB |
| `installer/__pycache__/installer.cpython-314.pyc` | ~10 KB |
| `installer/__pycache__/msfs_detector.cpython-314.pyc` | ~4 KB |
| `installer/__pycache__/patch_engine.cpython-314.pyc` | ~8 KB |
| `installer/__pycache__/repair_wizard.cpython-314.pyc` | ~6 KB |
| `installer/__pycache__/safety.cpython-314.pyc` | ~5 KB |
| `installer/__pycache__/signature_verifier.cpython-314.pyc` | ~4 KB |
| `installer/__pycache__/updater.cpython-314.pyc` | ~5 KB |
| **Subtotal** | **~72 KB** |

### Directory: `tests/__pycache__/` — 48 files
| Pattern | Count | Est. Size Each | Est. Total |
|---|---|---|---|
| `.cpython-314-pytest-9.0.3.pyc` | 44 | ~4 KB avg | ~176 KB |
| `.cpython-314.pyc` | 4 | ~4 KB avg | ~16 KB |
| **Subtotal** | **48** | | **~192 KB** |

---

## Category 2: `__pycache__` Directories — 2 directories

| Directory | Est. Content Size |
|---|---|
| `installer/__pycache__/` | ~72 KB |
| `tests/__pycache__/` | ~192 KB |
| **Subtotal** | **~264 KB** |

---

## Category 3: `.pytest_cache` Directories — 2 directories

| Directory | Est. Content Size |
|---|---|
| `.pytest_cache/` | ~1 KB |
| `tests/.pytest_cache/` | ~1 KB |
| **Subtotal** | **~2 KB** |

---

## Category 4: Telemetry Dump Files — 83 files

All located in `installer/backups/` — JSON telemetry exports from test runs.

| Pattern | Count | Est. Size Each | Est. Total |
|---|---|---|---|
| `hgs_telemetry_20260529_*.json` | 83 | ~2-8 KB each | ~400 KB |
| **Subtotal** | **83** | | **~400 KB** |

---

## Category 5: Temporary Transaction Files — 128 files

All located in `installer/backups/` — JSON transaction test artifacts.

| Pattern | Count | Est. Size Each | Est. Total |
|---|---|---|---|
| `txn_17800*_test.json` | 128 | ~1 KB each | ~128 KB |
| **Subtotal** | **128** | | **~128 KB** |

---

## Category 6: Stale Backup ZIP Files — 111 files

All located in `installer/backups/` — duplicate PMDG 737-800 backup archives.

| Pattern | Count | Est. Size Each | Est. Total |
|---|---|---|---|
| `bk_*_pmdg-737-800.zip` | 111 | ~500 KB each | ~55.5 MB |
| **Subtotal** | **111** | | **~55.5 MB** |

---

## Category 7: Stale Backup Artifacts — 4 files

| File | Est. Size | Reason |
|---|---|---|
| `installer/backups/backup_manifest.json` | ~4 KB | Stale backup manifest |
| `installer/backups/healer_state.json` | ~2 KB | Stale healer state |
| `include/module.h.bak` | ~17 KB | Obsolete backup header (v2.2.0) |
| `src/lvar_table.cpp.bak` | ~12 KB | Obsolete backup source |
| **Subtotal** | **~35 KB** | |

---

## Category 8: Empty Build Placeholder

| File | Est. Size | Reason |
|---|---|---|
| `build/.gitkeep` | 0 B | Not needed (build/ already in .gitignore) |
| **Subtotal** | **0 B** | |

---

## Summary

| Category | Count | Est. Size |
|---|---|---|
| 1. Python bytecode (`.pyc`) | 60 | ~264 KB |
| 2. `__pycache__` directories | 2 | ~264 KB (includes .pyc) |
| 3. `.pytest_cache` directories | 2 | ~2 KB |
| 4. Telemetry dump files | 83 | ~400 KB |
| 5. Temporary transaction files | 128 | ~128 KB |
| 6. Stale backup ZIP files | 111 | ~55.5 MB |
| 7. Stale backup artifacts | 4 | ~35 KB |
| 8. Empty build placeholder | 1 | 0 B |
| **Total** | **~391 items** | **~56.3 MB** |

---

## Files NOT deleted

All source code (`src/`, `include/`, `CMakeLists.txt`), documentation (`audit/`, `README.md`), test files (`tests/*.py`), installer source (`installer/*.py`), build configuration, and aircraft profiles are preserved.
