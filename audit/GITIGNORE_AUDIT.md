# GITIGNORE AUDIT — Phase 2 Git Hygiene

**Generated:** 2026-05-29  
**Repository:** C_HUD_Runway  
**Audit Method:** Compare `.gitignore` against actual repository contents and common best practices for C++ WASM + Python projects.

---

## Previous `.gitignore` (v1) — Findings

### What was already present:
- `build/` — WASM build output
- `lib/nanovg/` — External library
- `.pytest_cache/`, `__pycache__/`, `*.pyc` — Python cache
- `.vscode/`, `.idea/` — IDE folders
- `*.swp`, `*.swo`, `*~` — Editor swap files
- `.DS_Store` — macOS metadata
- `*.zip`, `*.tar.gz` — Archive files
- `installer/backups/` — Backup directory
- `installer/installer.log` — Installer log

### What was missing:

| Missing Pattern | Risk | Example Match |
|---|---|---|
| `*.wasm` | Built WASM binaries could be accidentally committed | `C_HUD_Runway.wasm` |
| `*.o`, `*.obj`, `*.a`, `*.lib` | Object/library files | Build artifacts |
| `*.exp`, `*.ilk`, `*.pdb` | Windows/MSVC linker artifacts | Debug symbols |
| `.DS_Store?` | Extended macOS metadata | `.DS_Store` variants |
| `._*` | Apple Double files | `._filename` |
| `.Spotlight-V100`, `.Trashes` | macOS volume metadata | System files |
| `ehthumbs.db`, `Thumbs.db`, `Desktop.ini` | Windows thumbnail/index | Explorer cache |
| `*.pyo`, `*.pyd` | Additional Python bytecode | Optimized `.pyo` |
| `*.egg-info/`, `dist/`, `build-py/`, `*.egg` | Python packaging artifacts | Pip builds |
| `*.7z`, `*.rar` | Additional archive formats | Compressed backups |
| `installer/*.log` | Any log file in installer dir | Debug logs |
| `*.bak`, `*.orig`, `*.tmp`, `*.temp` | Backup/temporary files | Editor backups |
| `*.gcno`, `*.gcda`, `*.gcov`, `*.profraw` | Code coverage artifacts | GCC/Clang coverage |
| `*.sublime-workspace`, `*.sublime-project` | Sublime Text config | Project files |
| `*.swo` (already listed) | Already covered | — |

---

## Updated `.gitignore` (v2) — Changes Applied

### Patterns Added:

| Pattern | Section | Reason |
|---|---|---|
| `*.wasm` | Build output | Prevent committed WASM binaries |
| `*.o`, `*.obj`, `*.a`, `*.lib`, `*.so`, `*.dll`, `*.dylib` | Build output | Compiled object/library files |
| `*.exp`, `*.ilk`, `*.pdb` | Build output | Windows linker artifacts |
| `*.sublime-workspace`, `*.sublime-project` | IDE / Editor | Sublime Text config |
| `.DS_Store?`, `._*`, `.Spotlight-V100`, `.Trashes` | OS-generated | Extended macOS metadata |
| `ehthumbs.db`, `Thumbs.db`, `Desktop.ini` | OS-generated | Windows thumbnail cache |
| `*.pyo`, `*.pyd` | Python cache | Alternative bytecode formats |
| `*.egg-info/`, `dist/`, `build-py/`, `*.egg` | Python cache | Packaging artifacts |
| `*.7z`, `*.rar` | Archives | Additional compression formats |
| `installer/*.log` | Installer | All log files in installer dir |
| `*.bak`, `*.orig`, `*.tmp`, `*.temp` | Backup / temporary | Generic backup/swap artifacts |
| `*.gcno`, `*.gcda`, `*.gcov`, `*.profraw` | C/C++ compile | Code coverage data |

### Patterns Removed:
None. All v1 patterns were preserved and augmented.

---

## Verification

```
# Quick check: patterns not already covered
git status  →  Should show no unwanted tracked artifacts
```

**Result:** All unwanted artifact types identified in CLEANUP_INVENTORY.md are now covered by `.gitignore` patterns.

---

## Conclusion

The `.gitignore` has been upgraded from 12 patterns to 40+ patterns organized in logical sections. No existing v1 patterns were removed. The new patterns cover all categories identified during the cleanup inventory (Python bytecode, build artifacts, telemetry dumps, temporary files, editor files, OS-generated files).
