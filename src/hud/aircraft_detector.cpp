// ============================================================================
//  Conformal HUD – Automatic Aircraft Detection Engine
//  MSFS 2024  ·  C++17  ·  WASM
//
//  PHASE 3 — AUTOMATIC AIRCRAFT DETECTION
//
//  Detects the active aircraft by matching the TITLE SimVar against
//  known aircraft identifiers and returns the appropriate behavior
//  category and HUD profile.
//
//  NOTE: All behavior instances are statically allocated singletons
//  because this is a freestanding WASM environment (-nostdlib) with
//  no heap allocator.
// ============================================================================

#include "hud/aircraft_detector.h"
#include "hud/aircraft_profiles.h"
#include "hud/aircraft/boeing_hgs_behavior.h"
#include "hud/aircraft/airbus_hud_behavior.h"

// ============================================================================
//  1.  Known aircraft registry
// ============================================================================

/// An entry in the aircraft detection registry.
struct AircraftRegistryEntry {
    const char*         id_prefix;      // Case-insensitive prefix to match
    HudAircraftCategory category;       // Behavior category
};

/// Static registry of known aircraft.
/// Order matters: more specific prefixes should come first.
static const AircraftRegistryEntry kAircraftRegistry[] = {
    // --- Airbus A350 variants ---
    { "INI A350",       HudAircraftCategory::AIRBUS_HUD },
    { "INIBUILDS A350", HudAircraftCategory::AIRBUS_HUD },
    { "AIRBUS A350",    HudAircraftCategory::AIRBUS_HUD },
    { "A350",           HudAircraftCategory::AIRBUS_HUD },
    { "AIRBUS A330",    HudAircraftCategory::AIRBUS_HUD },
    { "INI A330",       HudAircraftCategory::AIRBUS_HUD },  // fallback to Boeing
    { "HEADWIND A330",  HudAircraftCategory::AIRBUS_HUD },

    // --- Fenix ---
    { "FENIX A320",   HudAircraftCategory::AIRBUS_HUD },
    // --- Boeing PMDG ---
    // --- PMDG 737 MAX ---
    { "PMDG 737 MAX", HudAircraftCategory::BOEING_HGS },
    { "PMDG 737",       HudAircraftCategory::BOEING_HGS },
    { "PMDG 777",       HudAircraftCategory::BOEING_HGS },

    // --- Boeing/Asobo 787 ---
    { "ASOBO BOEING 787", HudAircraftCategory::BOEING_HGS },
    { "WT_787",         HudAircraftCategory::BOEING_HGS },

    // --- FBW ---
    { "FBW",            HudAircraftCategory::AIRBUS_HUD },
    { "FBW A32NX",      HudAircraftCategory::AIRBUS_HUD },

    // --- Sentinel ---
    { 0,                HudAircraftCategory::UNKNOWN },
};

// ============================================================================
//  2.  Case-insensitive prefix matching
// ============================================================================

/// Check if `str` starts with `prefix` (case-insensitive ASCII).
static bool string_starts_with_ignore_case(const char* str, const char* prefix) {
    if (str == 0 || prefix == 0) return false;

    while (*prefix) {
        char sc = *str;
        char pc = *prefix;

        // Convert to lowercase for comparison
        if (sc >= 'A' && sc <= 'Z') sc += 32;
        if (pc >= 'A' && pc <= 'Z') pc += 32;

        if (sc != pc) return false;

        ++str;
        ++prefix;
    }
    return true;
}

// ============================================================================
//  3.  Substring presence check
// ============================================================================

/// Check if `str` contains `substr` (case-insensitive ASCII).
static bool string_contains_ignore_case(const char* str, const char* substr) {
    if (str == 0 || substr == 0 || *substr == '\0') return false;

    while (*str) {
        const char* s = str;
        const char* t = substr;

        while (*t) {
            char sc = *s;
            char tc = *t;
            if (sc >= 'A' && sc <= 'Z') sc += 32;
            if (tc >= 'A' && tc <= 'Z') tc += 32;
            if (sc != tc) break;
            ++s; ++t;
        }

        if (*t == '\0') return true;  // Full substring matched
        ++str;
    }
    return false;
}

// ============================================================================
//  4.  Detection implementation
// ============================================================================

AircraftDetectionResult aircraft_detect(const char* aircraft_id) {
    AircraftDetectionResult result;
    result.category     = HudAircraftCategory::UNKNOWN;
    result.profile      = hud_profile_match(aircraft_id);
    result.detected_id  = aircraft_id;
    result.supported    = true;
    result.detected     = false;

    if (aircraft_id == 0 || aircraft_id[0] == '\0') {
        result.profile   = hud_profile_default();
        result.supported = true;
        return result;
    }

    // Try prefix matching against registry
    for (int i = 0; kAircraftRegistry[i].id_prefix != 0; ++i) {
        if (string_starts_with_ignore_case(aircraft_id,
                                            kAircraftRegistry[i].id_prefix)) {
            result.category = kAircraftRegistry[i].category;
            result.detected = true;
            break;
        }
    }

    // Fall back to substring matching for common patterns
    if (!result.detected) {
        if (string_contains_ignore_case(aircraft_id, "A350") ||
            string_contains_ignore_case(aircraft_id, "A330") ||
            string_contains_ignore_case(aircraft_id, "A32NX")) {
            result.category = HudAircraftCategory::AIRBUS_HUD;
            result.detected = true;
        } else if (string_contains_ignore_case(aircraft_id, "737") ||
                   string_contains_ignore_case(aircraft_id, "777") ||
                   string_contains_ignore_case(aircraft_id, "787") ||
                   string_contains_ignore_case(aircraft_id, "PMDG") ||
                   string_contains_ignore_case(aircraft_id, "BOEING")) {
            result.category = HudAircraftCategory::BOEING_HGS;
            result.detected = true;
        }
    }

    // If still not detected, treat as generic/safe
    if (!result.detected) {
        result.category  = HudAircraftCategory::BOEING_HGS;  // Default to Boeing
        result.supported = false;
    }

    // Ensure profile is always set
    if (result.profile == 0) {
        result.profile = hud_profile_default();
    }

    return result;
}

// ============================================================================
//  5.  Category name helper
// ============================================================================

const char* aircraft_category_name(HudAircraftCategory category) {
    switch (category) {
        case HudAircraftCategory::BOEING_HGS: return "Boeing HGS";
        case HudAircraftCategory::AIRBUS_HUD: return "Airbus HUD";
        default: return "Unknown / Generic";
    }
}

// ============================================================================
//  6.  Statically-allocated behavior singletons
//
//  In this freestanding WASM environment (-nostdlib), there is no heap
//  allocator.  We pre-allocate one instance of each behavior type as
//  a global.  The factory returns a pointer to the appropriate one.
// ============================================================================

/// Pre-allocated Boeing HGS behavior singleton.
static BoeingHGSBehavior g_boeing_behavior;

/// Pre-allocated Airbus HUD behavior singleton.
static AirbusHUDBehavior g_airbus_behavior;

// ============================================================================
//  7.  Factory implementation
// ============================================================================

IHudAircraftBehavior* hud_behavior_create(const char* aircraft_id) {
    AircraftDetectionResult det = aircraft_detect(aircraft_id);

    switch (det.category) {
        case HudAircraftCategory::BOEING_HGS:
            return &g_boeing_behavior;

        case HudAircraftCategory::AIRBUS_HUD:
            return &g_airbus_behavior;

        default:
            // For unsupported aircraft, use the Boeing fallback
            return &g_boeing_behavior;
    }
}
