#ifndef C_HUD_AIRCRAFT_DETECTOR_H
#define C_HUD_AIRCRAFT_DETECTOR_H

// ============================================================================
//  Conformal HUD – Automatic Aircraft Detection Engine
//  MSFS 2024  ·  C++17  ·  WASM
//
//  PHASE 3 — AUTOMATIC AIRCRAFT DETECTION
//
//  Detects the active aircraft by matching the TITLE SimVar against
//  known aircraft identifiers and returns the appropriate:
//    · HudAircraftCategory (Boeing HGS, Airbus HUD, etc.)
//    · Calibration profile index
//    · Optical profile selection
//    · Flare law type
//    · Rollout law type
//
//  Detection is done via prefix matching (case-insensitive) against
//  a static registry of known aircraft types.
//
//  Supported aircraft:
//    · PMDG 737-800 / 737-700        → Boeing HGS
//    · PMDG 777-300ER                 → Boeing HGS
//    · WT 787 / Asobo 787-10         → Boeing HGS
//    · iniBuilds A350                 → Airbus HUD
//    · FBW A32NX                      → Generic (fallback)
//    · HEADWIND A330-900              → Generic (fallback)
//    · Everything else                → Generic safe mode
// ============================================================================

#include "aircraft/ihud_aircraft_behavior.h"
#include "aircraft_profiles.h"

// ============================================================================
//  1.  Detection result
// ============================================================================

/// Result of automatic aircraft detection.
struct AircraftDetectionResult {
    HudAircraftCategory category;       // Primary behavior category
    const HUDProfile*   profile;        // Matched HUD profile (or default)
    const char*         detected_id;    // Canonical aircraft ID string
    bool                supported;      // True if aircraft is HUD-supported
    bool                detected;       // True if a known aircraft was matched
};

// ============================================================================
//  2.  Detection API
// ============================================================================

/// Detect the aircraft category and profile from the MSFS TITLE string.
///
/// @param aircraft_id   Aircraft title string (e.g. "PMDG 737-800")
/// @return              Detection result with category, profile, and support status
AircraftDetectionResult aircraft_detect(const char* aircraft_id);

/// Get a human-readable name for an aircraft category.
///
/// @param category   Aircraft category
/// @return           Static string describing the category
const char* aircraft_category_name(HudAircraftCategory category);

/// Check if a detected aircraft should enter safe mode.
///
/// Safe mode means minimal HUD functionality with no aircraft-specific
/// tuning — just basic runway projection and FPV.
///
/// @param result   Detection result
/// @return         True if safe mode should be activated
static inline bool aircraft_should_use_safe_mode(const AircraftDetectionResult& result) {
    return !result.supported || result.category == HudAircraftCategory::UNKNOWN;
}

#endif // C_HUD_AIRCRAFT_DETECTOR_H
