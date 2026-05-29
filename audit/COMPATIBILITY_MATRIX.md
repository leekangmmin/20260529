# AIRCRAFT SUPPORT CONSISTENCY — COMPATIBILITY MATRIX

**Generated:** 2026-05-29  
**Sources compared:** module.cpp allowlist, aircraft_detector.cpp registry, aircraft_profiles.cpp profiles, installer/aircraft_scanner.py

---

## 1. Complete Compatibility Matrix

| Aircraft | module.cpp (allowlist) | aircraft_detector.cpp (registry) | aircraft_profiles.cpp (profiles) | installer/aircraft_scanner.py |
|---|---|---|---|---|
| **PMDG 737-800** | ✅ | ✅ → BOEING_HGS | profile_pmdg_737 | ✅ AircraftType.PMDG_737_800 |
| **PMDG 737-700** | ✅ | ✅ (matches "PMDG 737" prefix) | profile_pmdg_737 (same profile) | ✅ AircraftType.PMDG_737_700 |
| **PMDG 777-300ER** | ❌ **NOT LISTED** | ✅ → BOEING_HGS | profile_pmdg_777 | ✅ AircraftType.PMDG_777_300ER |
| **FBW A32NX** | ✅ | ✅ → BOEING_HGS | ❌ **NO PROFILE** (falls to default) | ✅ AircraftType.FBW_A32NX |
| **HEADWIND A330-900** | ✅ | ✅ → BOEING_HGS | ❌ **NO PROFILE** (falls to default) | ✅ AircraftType.HEADWIND_A330_900 |
| **ASOBO BOEING 747-8I** | ✅ | ❌ **NOT IN REGISTRY** | ❌ **NO PROFILE** | ❌ **NOT IN SCANNER** |
| **ASOBO BOEING 787-10** | ✅ | ✅ → BOEING_HGS | profile_wt_787 (prefix match "ASOBO BOEING 787") | ✅ AircraftType.ASOBO_787_10 |
| **WT_787_10** | ✅ | ✅ → BOEING_HGS | profile_wt_787_alt (prefix match "WT_787") | ✅ AircraftType.WT_787_10 |
| **iniBuilds A350** | ❌ **NOT LISTED** | ✅ → AIRBUS_HUD | profile_a350 | ✅ AircraftType.INIBUILDS_A350 |
| **FBW A32NX** (detector matches) | ✅ | ✅ → BOEING_HGS | ❌ **NO PROFILE** | ✅ AircraftType.FBW_A32NX |

---

## 2. Identified Mismatches

### 2.1 Missing from module.cpp Allowlist (but supported elsewhere)

- **PMDG 777-300ER** — present in detector, profiles, and installer but NOT in module.cpp's `hud_allowed_aircraft[]`
- **iniBuilds A350** — present in detector, profiles, and installer but NOT in module.cpp's `hud_allowed_aircraft[]`

### 2.2 Present in module.cpp Allowlist (but unsupported elsewhere)

- **ASOBO BOEING 747-8I** — only in module.cpp allowlist. Not in aircraft detector registry, no profile, not in installer scanner.

### 2.3 Category Assignment Mismatches

| Aircraft | detector.cpp category | Appropriate? | Issue |
|---|---|---|---|
| HEADWIND A330-900 | BOEING_HGS (via registry) | Airbus aircraft mapped to Boeing | ⚠️ **MISCLASSIFICATION** — A330 is an Airbus, should be AIRBUS_HUD |
| FBW A32NX | BOEING_HGS | Airbus A320 mapped to Boeing | ⚠️ **MISCLASSIFICATION** — A320 is an Airbus |
| INI A330 | BOEING_HGS (fallback) | Mapped as Boeing fallback | ⚠️ **MISCLASSIFICATION** |

### 2.4 Profile Count vs Claim

- `aircraft_profiles.h` defines `C_HUD_NUM_PROFILES = 6`
- Actual profiles: PMDG737, PMDG777, WT787, WT787_alt, A350, Default = 6 ✅
- But only 4 of these 6 have dedicated aircraft profiles (Default is a catch-all, A350 only has an A350 profile but some A350 modules seem incomplete)
- FBW A32NX and HEADWIND A330-900 fall through to default profile

### 2.5 Detection Logic Issues

In `aircraft_detector.cpp`, the registry explicitly lists "INI A330" → BOEING_HGS (as fallback). However, the substring fallback logic would match "A330" → AIRBUS_HUD. This creates **inconsistent detection** depending on which branch matches first. Since registry matching happens first, "INI A330" would go BOEING_HGS, but "HEADWIND A330" would also match the registry → BOEING_HGS.

---

## 3. Recommended Single Source of Truth Architecture

The current architecture has **4 independent aircraft registries**:

```
module.cpp          → hud_allowed_aircraft[] (hardcoded allowlist)
aircraft_detector.cpp → kAircraftRegistry[] (detection registry)
aircraft_profiles.cpp → static profiles (tuning data)
aircraft_scanner.py  → AircraftType enum + patterns (installer)
```

### Proposed architecture

Replace the 4 independent sources with a single **aircraft_registry.h** / **aircraft_registry.cpp** pair that both C++ and Python can derive from:

```
┌─────────────────────────────────────────────────┐
│           SINGLE SOURCE OF TRUTH                 │
│  include/hud/aircraft_registry.h                 │
│                                                   │
│  struct AircraftEntry {                           │
│    const char* id_prefix;        // "PMDG 737"    │
│    HudAircraftCategory category; // BOEING_HGS    │
│    HudAircraftStyle style;       // HGS style     │
│    int profile_index;            // 0..N          │
│    bool allowlisted;             // HUD allowed   │
│    const char* scanner_pattern;  // regex pattern │
│  };                                                │
│                                                   │
│  const AircraftEntry kAircraftRegistry[] = {      │
│    { "PMDG 737", BOEING_HGS, ..., true, "pmdg.*737" },  │
│    { "PMDG 777", BOEING_HGS, ..., true, "pmdg.*777" },  │
│    ...                                              │
│  };                                                 │
└─────────────────────────────────────────────────┘
```

The Python installer can parse the same registry via a JSON export or a dedicated Python binding. This ensures:

- Adding a new aircraft requires only **one** change
- No mismatches between allowlist, detector, profiles, and installer
- Category assignment is consistent
- All consumers automatically stay in sync
