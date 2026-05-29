#ifndef C_HUD_DECLUTTER_H
#define C_HUD_DECLUTTER_H

// ============================================================================
//  Conformal HUD – Symbol Priority & Declutter System
//  MSFS 2024  ·  C++17  ·  WASM
//
//  v2.4.0 — Dynamic symbol prioritisation and declutter.
//
//  Manages the visibility and emphasis of HUD symbology based on the
//  current phase of flight.  The HUD should never feel visually
//  overloaded — elements that are not essential for the current phase
//  are dimmed or suppressed entirely.
//
//  Priority scheme:
//    · Approach: runway outline + FPV have highest priority
//    · Flare: flare cue has highest priority
//    · Rollout: centerline + rollout guidance have highest priority
//    · Low visibility: critical symbols are enhanced, non-essentials
//      suppressed to reduce clutter
//
//  Declutter operates on a priority scoring system. Each symbol type
//  is assigned a base priority, which is modulated by the flight phase
//  and ambient conditions.  Symbols below a threshold are dimmed or
//  hidden.
// ============================================================================

#include "../module.h"

// ============================================================================
//  1.  Symbol priority classes
// ============================================================================

/// Priority class for each symbol type.
typedef enum SymPriority {
    // --- Critical (never suppressed) ---
    SYM_PRIO_CRITICAL    = 100,

    // --- High priority (suppressed only in extreme clutter) ---
    SYM_PRIO_HIGH        = 80,

    // --- Normal priority ---
    SYM_PRIO_NORMAL      = 60,

    // --- Low priority (dimmed in busy phases) ---
    SYM_PRIO_LOW         = 40,

    // --- Background (suppressed in all but cruise) ---
    SYM_PRIO_BACKGROUND   = 20,
} SymPriority;

// ============================================================================
//  2.  Symbol type identifiers
// ============================================================================

typedef enum SymType {
    SYM_TYPE_FPV              = 0,
    SYM_TYPE_HORIZON          = 1,
    SYM_TYPE_PITCH_LADDER     = 2,
    SYM_TYPE_RUNWAY_BOX       = 3,
    SYM_TYPE_LOCALIZER_BAR    = 4,
    SYM_TYPE_GLIDESLOPE_BAR   = 5,
    SYM_TYPE_DRIFT_CUE        = 6,
    SYM_TYPE_CENTERLINE       = 7,
    SYM_TYPE_ILS_CROSSHAIR    = 8,
    SYM_TYPE_FLARE_CUE        = 9,
    SYM_TYPE_TOUCHDOWN_ZONE   = 10,
    SYM_TYPE_ACCEL_CARET      = 11,
    SYM_TYPE_ENERGY_TREND     = 12,
    SYM_TYPE_FLARE_BRACKET    = 13,
    SYM_TYPE_TD_PREDICTOR     = 14,
    SYM_TYPE_VELOCITY_TREND   = 15,
    SYM_TYPE_ROLLOUT_CENTER   = 16,
    SYM_TYPE_ROLLOUT_DECEL    = 17,
    SYM_TYPE_SPEED_TAPE       = 18,
    SYM_TYPE_ALTITUDE_TAPE    = 19,
    SYM_TYPE_HEADING_SCALE    = 20,

    SYM_TYPE_COUNT            = 21,
} SymType;

// ============================================================================
//  3.  Flight phase identifiers
// ============================================================================

typedef enum FlightPhase {
    PHASE_CRUISE     = 0,
    PHASE_APPROACH   = 1,
    PHASE_FLARE      = 2,
    PHASE_ROLLOUT    = 3,
    PHASE_TAXI       = 4,
} FlightPhase;

// ============================================================================
//  4.  Declutter state
// ============================================================================

/// Per-symbol priority state.
typedef struct SymPriorityState {
    FLOAT64 base_priority;          // base priority value
    FLOAT64 phase_modifier;         // phase-based priority modifier (0..1)
    FLOAT64 visibility_modifier;    // visibility-based modifier (0..1)
    FLOAT64 alpha;                  // final alpha (0 = hidden, 1 = full)
    FLOAT64 dimming_factor;         // dimming factor (0..1)
    bool    suppressed;             // true if symbol should be hidden
} SymPriorityState;

/// Declutter system state.
typedef struct DeclutterState {
    // --- Current flight phase ---
    FlightPhase current_phase;

    // --- Per-symbol priority state ---
    SymPriorityState symbols[SYM_TYPE_COUNT];

    // --- Phase-specific priority overrides ---
    // These arrays define the base priority for each symbol in each phase
    FLOAT64 phase_base_priorities[5][SYM_TYPE_COUNT];

    // --- Low visibility mode ---
    bool    low_visibility;         // true when visibility is degraded
    FLOAT64 visibility_factor;      // 0..1, visibility condition

    // --- Overall declutter ---
    FLOAT64 global_dimming;         // global dimming factor (0..1)
    int     visible_symbol_count;   // number of non-suppressed symbols
    bool    active;                 // true when declutter is active

    // --- Debug ---
    bool    debug_force_all;        // force all symbols visible (debug)
} DeclutterState;

// ============================================================================
//  5.  Initialisation
// ============================================================================

/// Initialise the declutter system.
///
/// @param ds  [out] Declutter state
void declutter_init(DeclutterState* ds);

// ============================================================================
//  6.  Declutter computation
// ============================================================================

/// Compute symbol priorities for the current frame.
///
/// @param ds              [in/out] Declutter state
/// @param phase           Current flight phase
/// @param low_visibility  True if low visibility conditions
/// @param visibility_m    Current visibility (metres)
void declutter_compute(DeclutterState* ds,
                        FlightPhase     phase,
                        bool            low_visibility,
                        FLOAT64         visibility_m);

/// Get the effective alpha for a symbol type.
///
/// @param ds   Declutter state
/// @param type Symbol type
/// @return     Alpha value (0 = hidden, 1 = full)
static inline FLOAT64 declutter_get_alpha(const DeclutterState* ds, SymType type) {
    if (ds == 0 || type < 0 || type >= SYM_TYPE_COUNT) return 1.0;
    if (ds->debug_force_all) return 1.0;
    return ds->symbols[type].alpha;
}

/// Check if a symbol type is suppressed.
///
/// @param ds   Declutter state
/// @param type Symbol type
/// @return     true if symbol should be hidden
static inline bool declutter_is_suppressed(const DeclutterState* ds, SymType type) {
    if (ds == 0 || type < 0 || type >= SYM_TYPE_COUNT) return false;
    if (ds->debug_force_all) return false;
    return ds->symbols[type].suppressed;
}

/// Get the dimming factor for a symbol type.
///
/// @param ds   Declutter state
/// @param type Symbol type
/// @return     Dimming factor (0 = fully dimmed, 1 = full brightness)
static inline FLOAT64 declutter_get_dim(const DeclutterState* ds, SymType type) {
    if (ds == 0 || type < 0 || type >= SYM_TYPE_COUNT) return 1.0;
    return ds->symbols[type].dimming_factor;
}

// ============================================================================
//  7.  Debug logging
// ============================================================================

/// Log declutter state for debugging.
void declutter_debug_log(const DeclutterState* ds);

#endif // C_HUD_DECLUTTER_H
