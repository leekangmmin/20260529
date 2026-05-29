# AIRCRAFT COMPATIBILITY MATRIX — C_HUD_Runway

**Benchmark:** Real Boeing HGS / Airbus HUD behaviour  
**Codebase:** Conformal HUD Runway Symbology v2.7.0  
**Analysis method:** Static source-code only

---

## Compatibility Summary

| Aircraft | Detection | Profile | Behaviors | HUD Deployment | Integration Type | Status |
|---|---|---|---|---|---|---|
| **PMDG 737-800** | ✅ CONFIRMED | ✅ PMDG 737 | ✅ Boeing HGS | ✅ L:AS1001_HUD | Overlay | BETA |
| **PMDG 737-700** | ✅ CONFIRMED | ✅ PMDG 737 | ✅ Boeing HGS | ✅ L:AS1001_HUD | Overlay | BETA |
| **PMDG 777-300ER** | ✅ CONFIRMED | ✅ PMDG 777 | ✅ Boeing HGS | ✅ L:AS1001_HUD | Overlay | BETA |
| **ASOBO 787-10** | ✅ CONFIRMED | ✅ ASOBO 787 | ✅ Boeing HGS | ✅ L:HUD_DEPLOY | Overlay | BETA |
| **WT 787-10** | ✅ CONFIRMED | ✅ WT 787 | ✅ Boeing HGS | ✅ L:HUD_DEPLOY | Overlay | BETA |
| **iniBuilds A350** | ✅ CONFIRMED | ❌ NONE | ✅ Airbus HUD | ✅ L:A350_HUD_DEPLOY | Overlay | ALPHA |
| **FBW A32NX** | ✅ CONFIRMED | ✅ Default | ❌ **WRONG (Boeing HGS)** | ✅ L:HUD_POWER_SWITCH | Overlay | BROKEN |
| **Headwind A330** | ✅ CONFIRMED | ✅ Default | ❌ **WRONG (Boeing HGS)** | ✅ L:HUD_POWER_SWITCH | Overlay | BROKEN |

---

## Detailed Aircraft-by-Aircraft Analysis

### 1. PMDG 737-800 / 737-700

| Aspect | File | Lines | Finding |
|---|---|---|---|
| Detection | `hud/aircraft_detector.cpp` | 44 | `"PMDG 737"` → `BOEING_HGS` |
| Profile | `hud/aircraft_profiles.cpp` | 29–71 | Full profile with `hFOV=30°, vFOV=22.5°, eye=(0.50, 0, -1.20)` |
| Behavior | `hud/aircraft/boeing_hgs_behavior.cpp` | Full | Full Boeing behavior implementation |
| Deployment | `hud/hud_deployment.cpp` | 23–33 | `L:AS1001_HUD` deploy var, `deploy_threshold=0.85` |
| Symbology | `aircraft_profiles.cpp` | 44–49 | FPV, horizon, pitch, runway, LOC, GS, drift, centerline, ILS crosshair |

**Issues:**
- `L:AS1001_HUD` is a guessed variable name — not confirmed from PMDG SDK documentation
- PMDG 737 internally models the HGS as a separate avionics system with its own power bus — this project does not use PMDG's internal HGS data
- The profile FOV (30°×22.5°) is used for FOV metadata only, not for physical projection calibration

### 2. PMDG 777-300ER

| Aspect | File | Lines | Finding |
|---|---|---|---|
| Detection | `hud/aircraft_detector.cpp` | 45 | `"PMDG 777"` → `BOEING_HGS` |
| Profile | `hud/aircraft_profiles.cpp` | 73–122 | `hFOV=33°, vFOV=24°, eye=(0.60, 0, -1.30)` |
| Behavior | `hud/aircraft/boeing_hgs_behavior.cpp` | Full | Same Boeing behavior |
| Deployment | `hud/hud_deployment.cpp` | 35–45 | Same as 737 — `L:AS1001_HUD` |
| Symbology | `aircraft_profiles.cpp` | 91–96 | Includes speed scale + altitude scale |

**Issues:**
- PMDG 777 actually has a fully modelled HGS in the virtual cockpit that functions independently — this overlay will conflict visually  
- Speed and altitude tapes are **enabled in profile** but **not rendered** — no Canvas code to draw them was found in `conformal_renderer.js`
- Same variable name concern as PMDG 737

### 3. ASOBO / WT 787-10

| Aspect | File | Lines | Finding |
|---|---|---|---|
| Detection | `hud/aircraft_detector.cpp` | 47–48 | Both `"ASOBO BOEING 787"` and `"WT_787"` → `BOEING_HGS` |
| Profile | `hud/aircraft_profiles.cpp` | 124–199 | `hFOV=36°, vFOV=26°, eye=(0.40, 0, -1.10)` |
| Deployment | `hud/hud_deployment.cpp` | 47–68 | `L:HUD_DEPLOY` with `use_panel_state=true` |
| Panel state | `hud/hud_deployment.cpp` | 57 | `use_panel_state=true` but **no reading code** |

**Issues:**
- Panel state deployment is **declared but not implemented** — the flag is never checked in `hud_deployment_update()`
- 787 profile has the largest FOV (36°×26°) which is appropriate for the 787's larger combiner
- Two separate profile entries with identical data (ASOBO and WT variants)

### 4. iniBuilds A350

| Aspect | File | Lines | Finding |
|---|---|---|---|
| Detection | `hud/aircraft_detector.cpp` | 40–43 | Multiple prefix/substring matches |
| Profile | `hud/aircraft_profiles.cpp` | NONE | No dedicated A350 profile — falls to default |
| Behavior | `hud/aircraft/airbus_hud_behavior.cpp` | Full | Full Airbus behavior with A350-specific modules |
| Deployment | `hud/hud_deployment.cpp` | 70–81 | `L:A350_HUD_DEPLOY` with percentage var |

**Issues:**
- A350 has **no dedicated profile** in `aircraft_profiles.cpp` — it uses the default `profile_default`
- 13 A350-specific modules exist in `src/hud/aircraft/a350_*.cpp` but no profile connects them to the A350 HGS geometry
- The Airbus behavior loads its tuning from `A350HUDProfile` (via `a350_get_default_profile()`) not from the standard `HUDProfile` system — **two separate profile systems**
- Detection includes substring match on "A330" which may misclassify other aircraft

### 5. FBW A32NX

| Aspect | File | Lines | Finding |
|---|---|---|---|
| Detection | `hud/aircraft_detector.cpp` | 49 | `"FBW A32NX"` → `BOEING_HGS` |
| Profile | `hud/aircraft_profiles.cpp` | NONE | Falls to default |
| Deployment | `hud/hud_deployment.cpp` | 83–94 | `has_deploy_animation=false`, always deployed |

**CRITICAL ISSUE:**
- **FBW A32NX is an Airbus A320neo, not a Boeing.** It is classified as `BOEING_HGS` which applies Boeing-specific behaviours (different flare law, FPV filtering philosophy, declutter logic) to an Airbus aircraft.
- The A320 does not have a production HUD. This project is adding a HUD to an aircraft that never had one.

### 6. Headwind A330

| Aspect | Finding |
|---|---|
| Detection | `"HEADWIND A330"` → `BOEING_HGS` |
| Issue | Same misclassification as FBW A32NX — Airbus aircraft treated as Boeing |

---

## Aircraft Detection Code Path

```
TITLE SimVar
    → aircraft_detect() [aircraft_detector.cpp:74-120]
        → Prefix match against kAircraftRegistry[]
            → PMDG 737 → BOEING_HGS
            → PMDG 777 → BOEING_HGS
            → ASOBO BOEING 787 → BOEING_HGS
            → WT_787 → BOEING_HGS
            → INI A350 → AIRBUS_HUD
            → FBW A32NX → BOEING_HGS (WRONG)
            → HEADWIND A330 → BOEING_HGS (WRONG)
        → Fallback substring match
            → Contains "A350"/"A330"/"A32NX" → AIRBUS_HUD
            → Contains "737"/"777"/"787"/"PMDG"/"BOEING" → BOEING_HGS
    → hud_behavior_create() returns singleton behavior
        → BOEING_HGS → &g_boeing_behavior
        → AIRBUS_HUD → &g_airbus_behavior
    → hud_profile_match(aircraft_id) returns profile
        → Falls to default if no match
```

---

## Missing Aircraft Support

| Aircraft | Would it work? | Reason |
|---|---|---|
| Fenix A320 | ❌ NO | Not detected, no profile |
| PMDG 737-600 | ⚠️ PARTIAL | Detected (contains "737") but no specific profile |
| JustFlight BAE 146 | ❌ NO | Not detected |
| Aerosoft CRJ | ❌ NO | Not detected |
| Captain Sim 767 | ❌ NO | Not detected |
| FlyJSim 737 | ❌ NO | Not detected |
| Cessna Citation Longitude | ✅ WOULD DETECT | Contains "BOEING" → wrong classification |
| MilViz C-310 | ❌ NO | Not detected |

---

## Recommendations

1. **Create a dedicated A350 profile** in `aircraft_profiles.cpp` with proper combiner geometry and tuning
2. **Fix FBW A32NX classification** — create an `AIRBUS_FLYBYWIRE` category or use `AIRBUS_HUD` behavior  
3. **Fix Headwind A330** — same as FBW  
4. **Add panel state reading** for 787 deployment  
5. **Add Fenix A320 support** — popular aircraft, easy grammar-based detection  
6. **Remove overly broad substring matches** — "BOEING" matches general aviation aircraft without HUDs  
7. **Add hardware detection fallbacks** — detect by panel.cfg presence rather than title string alone  

*Report generated from static source-code analysis.*
