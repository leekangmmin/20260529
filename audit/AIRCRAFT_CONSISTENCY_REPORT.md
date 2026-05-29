# AIRCRAFT CONSISTENCY REPORT — Phase 2 Allowlist Audit

**Generated:** 2026-05-29  
**Repository:** C_HUD_Runway  
**Files Audited:**
- `src/module.cpp` — `hud_allowed_aircraft[]` allowlist
- `src/hud/aircraft_detector.cpp` — `kAircraftRegistry[]` detection registry
- `src/hud/aircraft_profiles.cpp` — `HUDProfile` database

---

## Compatibility Matrix

| Aircraft | Allowlist (`module.cpp`) | Detector (`aircraft_detector.cpp`) | Profile (`aircraft_profiles.cpp`) |
|---|---|---|---|
| PMDG 737-800 | ✅ Listed | ✅ Detected (BOEING_HGS) | ✅ `profile_pmdg_737` |
| PMDG 737-700 | ✅ Listed | ✅ Detected (BOEING_HGS) [via "PMDG 737"] | ✅ `profile_pmdg_737` |
| **PMDG 777-300ER** | ❌ **MISSING** | ✅ Detected (BOEING_HGS) [via "PMDG 777"] | ✅ `profile_pmdg_777` |
| ASOBO BOEING 787-10 | ✅ Listed | ✅ Detected (BOEING_HGS) | ✅ `profile_wt_787` |
| WT_787_10 | ✅ Listed | ✅ Detected (BOEING_HGS) | ✅ `profile_wt_787_alt` |
| FBW A32NX | ✅ Listed | ✅ Detected (BOEING_HGS) | ⚠️ Default profile (no specific profile) |
| HEADWIND A330-900 | ✅ Listed | ✅ Detected (BOEING_HGS) [via "HEADWIND A330"] | ⚠️ Default profile |
| ASOBO BOEING 747-8I | ✅ Listed | ❌ **NOT DETECTED** | ❌ **NO PROFILE** |
| **iniBuilds A350** | ❌ **MISSING** | ✅ Detected (AIRBUS_HUD) | ✅ A350 profile system |
| **Airbus A350 (any)** | ❌ **MISSING** | ✅ Detected (AIRBUS_HUD) | ✅ A350 profile system |

---

## Mismatches Identified

### 🔴 MISMATCH 1 — PMDG 777-300ER: Detected but Blocked

**Status:** CRITICAL  
**Detector:** Matches prefix `"PMDG 777"` → `BOEING_HGS`  
**Profile:** `profile_pmdg_777` exists with full tuning  
**Allowlist:** ❌ NOT present in `hud_allowed_aircraft[]`  
**Consequence:** `aircraft_supports_hud()` returns `false` for PMDG 777  
**Fix:** Add `"PMDG 777-300ER"` to allowlist

### 🔴 MISMATCH 2 — A350 Variants: Detected but Blocked

**Status:** CRITICAL  
**Detector:** Matches prefixes `"INI A350"`, `"INIBUILDS A350"`, `"AIRBUS A350"`, `"A350"` → `AIRBUS_HUD`  
**Profile:** A350-specific profile system exists (`a350_profile.cpp`, etc.)  
**Allowlist:** ❌ NOT present in `hud_allowed_aircraft[]`  
**Consequence:** `aircraft_supports_hud()` returns `false` for all A350 variants  
**Fix:** Add `"INI A350"` to allowlist

### 🟡 MISMATCH 3 — ASOBO BOEING 747-8I: Allowed but Undetectable

**Status:** LOW (no user impact, falls through to Boeing default)  
**Allowlist:** ✅ Listed as `"ASOBO BOEING 747-8I"`  
**Detector:** ❌ Not in registry — falls to substring match `"BOEING"` → `BOEING_HGS`  
**Profile:** ❌ No specific profile — uses default  
**Note:** Works correctly via fallback, but could be improved with explicit entry

### 🟢 CONSISTENT — PMDG 737-800/700

All three systems agree. No action needed.

### 🟢 CONSISTENT — Boeing 787 variants

All three systems agree. No action needed.

### 🟢 CONSISTENT — FBW A32NX

All three systems agree. No action needed (uses default profile, which is reasonable for fallback).

### 🟢 CONSISTENT — HEADWIND A330-900

All three systems agree. No action needed.

---

## Fixes Applied

Following the rule "Implement ONLY obvious consistency fixes":

| # | File | Change | Reason |
|---|---|---|---|
| 1 | `src/module.cpp` | Added `"PMDG 777-300ER"` to allowlist | PMDG 777 is detected and has a profile, but was blocked |
| 2 | `src/module.cpp` | Added `"INI A350"` to allowlist | A350 is detected and has profiles, but was blocked |

These are the only two obvious consistency fixes — both aircraft are fully detected by the detector system and have complete profile data, but were inadvertently blocked by the allowlist.

---

## Verification After Fixes

After applying the changes:
- PMDG 777-300ER → Detected → Allowed → Profiled ✅
- INI A350 → Detected → Allowed → Profiled ✅
- All other aircraft remain in their original state ✅
- No new aircraft profiles were created
- No aircraft detection logic was modified
- No flight logic was changed
