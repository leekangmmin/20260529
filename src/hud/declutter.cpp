// ============================================================================
//  Conformal HUD – Symbol Priority & Declutter System Implementation
//  MSFS 2024  ·  C++17  ·  WASM
//
//  v2.4.0 — Dynamic symbol prioritisation and declutter.
//
//  Ensures the HUD never feels visually overloaded by managing symbol
//  visibility based on flight phase and ambient conditions.
// ============================================================================

#include "../../include/hud/declutter.h"
#include "../../include/projection.h"

// ============================================================================
//  1.  Helper: base priority table
// ============================================================================

/// Define the base priority for each symbol type in each flight phase.
/// Higher = more important, harder to suppress.
static void declutter_build_priority_table(DeclutterState* ds) {
    if (ds == 0) return;

    // Initialise all to default NORMAL
    for (int p = 0; p < 5; ++p) {
        for (int s = 0; s < SYM_TYPE_COUNT; ++s) {
            ds->phase_base_priorities[p][s] = (FLOAT64)SYM_PRIO_NORMAL;
        }
    }

    // --- CRUISE phase ---
    // All standard symbology visible
    ds->phase_base_priorities[PHASE_CRUISE][SYM_TYPE_FPV]            = (FLOAT64)SYM_PRIO_CRITICAL;
    ds->phase_base_priorities[PHASE_CRUISE][SYM_TYPE_HORIZON]        = (FLOAT64)SYM_PRIO_HIGH;
    ds->phase_base_priorities[PHASE_CRUISE][SYM_TYPE_PITCH_LADDER]   = (FLOAT64)SYM_PRIO_HIGH;
    ds->phase_base_priorities[PHASE_CRUISE][SYM_TYPE_DRIFT_CUE]      = (FLOAT64)SYM_PRIO_NORMAL;
    ds->phase_base_priorities[PHASE_CRUISE][SYM_TYPE_ACCEL_CARET]    = (FLOAT64)SYM_PRIO_NORMAL;
    ds->phase_base_priorities[PHASE_CRUISE][SYM_TYPE_ENERGY_TREND]   = (FLOAT64)SYM_PRIO_LOW;
    ds->phase_base_priorities[PHASE_CRUISE][SYM_TYPE_SPEED_TAPE]     = (FLOAT64)SYM_PRIO_HIGH;
    ds->phase_base_priorities[PHASE_CRUISE][SYM_TYPE_ALTITUDE_TAPE]  = (FLOAT64)SYM_PRIO_HIGH;
    ds->phase_base_priorities[PHASE_CRUISE][SYM_TYPE_HEADING_SCALE]  = (FLOAT64)SYM_PRIO_NORMAL;

    // --- APPROACH phase ---
    // Runway, FPV, and guidance cues are critical
    ds->phase_base_priorities[PHASE_APPROACH][SYM_TYPE_FPV]            = (FLOAT64)SYM_PRIO_CRITICAL;
    ds->phase_base_priorities[PHASE_APPROACH][SYM_TYPE_RUNWAY_BOX]     = (FLOAT64)SYM_PRIO_CRITICAL;
    ds->phase_base_priorities[PHASE_APPROACH][SYM_TYPE_LOCALIZER_BAR]  = (FLOAT64)SYM_PRIO_CRITICAL;
    ds->phase_base_priorities[PHASE_APPROACH][SYM_TYPE_GLIDESLOPE_BAR] = (FLOAT64)SYM_PRIO_CRITICAL;
    ds->phase_base_priorities[PHASE_APPROACH][SYM_TYPE_HORIZON]        = (FLOAT64)SYM_PRIO_HIGH;
    ds->phase_base_priorities[PHASE_APPROACH][SYM_TYPE_PITCH_LADDER]   = (FLOAT64)SYM_PRIO_HIGH;
    ds->phase_base_priorities[PHASE_APPROACH][SYM_TYPE_DRIFT_CUE]      = (FLOAT64)SYM_PRIO_NORMAL;
    ds->phase_base_priorities[PHASE_APPROACH][SYM_TYPE_CENTERLINE]     = (FLOAT64)SYM_PRIO_HIGH;
    ds->phase_base_priorities[PHASE_APPROACH][SYM_TYPE_ILS_CROSSHAIR]  = (FLOAT64)SYM_PRIO_NORMAL;
    ds->phase_base_priorities[PHASE_APPROACH][SYM_TYPE_TOUCHDOWN_ZONE] = (FLOAT64)SYM_PRIO_HIGH;
    ds->phase_base_priorities[PHASE_APPROACH][SYM_TYPE_TD_PREDICTOR]   = (FLOAT64)SYM_PRIO_NORMAL;
    ds->phase_base_priorities[PHASE_APPROACH][SYM_TYPE_ACCEL_CARET]    = (FLOAT64)SYM_PRIO_NORMAL;
    ds->phase_base_priorities[PHASE_APPROACH][SYM_TYPE_ENERGY_TREND]   = (FLOAT64)SYM_PRIO_LOW;
    ds->phase_base_priorities[PHASE_APPROACH][SYM_TYPE_VELOCITY_TREND] = (FLOAT64)SYM_PRIO_LOW;
    // Suppress non-essential during approach
    ds->phase_base_priorities[PHASE_APPROACH][SYM_TYPE_HEADING_SCALE]  = (FLOAT64)SYM_PRIO_BACKGROUND;

    // --- FLARE phase ---
    // Flare cue is critical, non-essential symbols are suppressed
    ds->phase_base_priorities[PHASE_FLARE][SYM_TYPE_FLARE_CUE]        = (FLOAT64)SYM_PRIO_CRITICAL;
    ds->phase_base_priorities[PHASE_FLARE][SYM_TYPE_FPV]              = (FLOAT64)SYM_PRIO_HIGH;
    ds->phase_base_priorities[PHASE_FLARE][SYM_TYPE_RUNWAY_BOX]       = (FLOAT64)SYM_PRIO_HIGH;
    ds->phase_base_priorities[PHASE_FLARE][SYM_TYPE_TOUCHDOWN_ZONE]   = (FLOAT64)SYM_PRIO_HIGH;
    ds->phase_base_priorities[PHASE_FLARE][SYM_TYPE_HORIZON]          = (FLOAT64)SYM_PRIO_NORMAL;
    ds->phase_base_priorities[PHASE_FLARE][SYM_TYPE_PITCH_LADDER]     = (FLOAT64)SYM_PRIO_LOW;
    ds->phase_base_priorities[PHASE_FLARE][SYM_TYPE_FLARE_BRACKET]    = (FLOAT64)SYM_PRIO_HIGH;
    // Suppress non-essential during flare
    ds->phase_base_priorities[PHASE_FLARE][SYM_TYPE_LOCALIZER_BAR]    = (FLOAT64)SYM_PRIO_LOW;
    ds->phase_base_priorities[PHASE_FLARE][SYM_TYPE_GLIDESLOPE_BAR]   = (FLOAT64)SYM_PRIO_LOW;
    ds->phase_base_priorities[PHASE_FLARE][SYM_TYPE_ACCEL_CARET]      = (FLOAT64)SYM_PRIO_BACKGROUND;
    ds->phase_base_priorities[PHASE_FLARE][SYM_TYPE_ENERGY_TREND]     = (FLOAT64)SYM_PRIO_BACKGROUND;
    ds->phase_base_priorities[PHASE_FLARE][SYM_TYPE_DRIFT_CUE]        = (FLOAT64)SYM_PRIO_BACKGROUND;
    ds->phase_base_priorities[PHASE_FLARE][SYM_TYPE_ILS_CROSSHAIR]    = (FLOAT64)SYM_PRIO_BACKGROUND;
    ds->phase_base_priorities[PHASE_FLARE][SYM_TYPE_VELOCITY_TREND]   = (FLOAT64)SYM_PRIO_BACKGROUND;
    ds->phase_base_priorities[PHASE_FLARE][SYM_TYPE_TD_PREDICTOR]     = (FLOAT64)SYM_PRIO_BACKGROUND;

    // --- ROLLOUT phase ---
    // Centerline and rollout guidance are critical
    ds->phase_base_priorities[PHASE_ROLLOUT][SYM_TYPE_ROLLOUT_CENTER]  = (FLOAT64)SYM_PRIO_CRITICAL;
    ds->phase_base_priorities[PHASE_ROLLOUT][SYM_TYPE_ROLLOUT_DECEL]   = (FLOAT64)SYM_PRIO_HIGH;
    ds->phase_base_priorities[PHASE_ROLLOUT][SYM_TYPE_FPV]             = (FLOAT64)SYM_PRIO_HIGH;
    ds->phase_base_priorities[PHASE_ROLLOUT][SYM_TYPE_RUNWAY_BOX]      = (FLOAT64)SYM_PRIO_HIGH;
    ds->phase_base_priorities[PHASE_ROLLOUT][SYM_TYPE_CENTERLINE]      = (FLOAT64)SYM_PRIO_HIGH;
    ds->phase_base_priorities[PHASE_ROLLOUT][SYM_TYPE_HORIZON]         = (FLOAT64)SYM_PRIO_NORMAL;
    // Suppress non-essential during rollout
    ds->phase_base_priorities[PHASE_ROLLOUT][SYM_TYPE_PITCH_LADDER]    = (FLOAT64)SYM_PRIO_LOW;
    ds->phase_base_priorities[PHASE_ROLLOUT][SYM_TYPE_LOCALIZER_BAR]   = (FLOAT64)SYM_PRIO_BACKGROUND;
    ds->phase_base_priorities[PHASE_ROLLOUT][SYM_TYPE_GLIDESLOPE_BAR]  = (FLOAT64)SYM_PRIO_BACKGROUND;
    ds->phase_base_priorities[PHASE_ROLLOUT][SYM_TYPE_FLARE_CUE]       = (FLOAT64)SYM_PRIO_BACKGROUND;
    ds->phase_base_priorities[PHASE_ROLLOUT][SYM_TYPE_TOUCHDOWN_ZONE]  = (FLOAT64)SYM_PRIO_BACKGROUND;
    ds->phase_base_priorities[PHASE_ROLLOUT][SYM_TYPE_FLARE_BRACKET]   = (FLOAT64)SYM_PRIO_BACKGROUND;
    ds->phase_base_priorities[PHASE_ROLLOUT][SYM_TYPE_ACCEL_CARET]     = (FLOAT64)SYM_PRIO_BACKGROUND;
    ds->phase_base_priorities[PHASE_ROLLOUT][SYM_TYPE_ENERGY_TREND]    = (FLOAT64)SYM_PRIO_BACKGROUND;
    ds->phase_base_priorities[PHASE_ROLLOUT][SYM_TYPE_DRIFT_CUE]       = (FLOAT64)SYM_PRIO_BACKGROUND;
    ds->phase_base_priorities[PHASE_ROLLOUT][SYM_TYPE_ILS_CROSSHAIR]   = (FLOAT64)SYM_PRIO_BACKGROUND;
    ds->phase_base_priorities[PHASE_ROLLOUT][SYM_TYPE_TD_PREDICTOR]    = (FLOAT64)SYM_PRIO_BACKGROUND;
    ds->phase_base_priorities[PHASE_ROLLOUT][SYM_TYPE_VELOCITY_TREND]  = (FLOAT64)SYM_PRIO_BACKGROUND;

    // --- TAXI phase ---
    // Minimal symbology
    ds->phase_base_priorities[PHASE_TAXI][SYM_TYPE_FPV]                = (FLOAT64)SYM_PRIO_NORMAL;
    ds->phase_base_priorities[PHASE_TAXI][SYM_TYPE_HORIZON]            = (FLOAT64)SYM_PRIO_LOW;
    ds->phase_base_priorities[PHASE_TAXI][SYM_TYPE_RUNWAY_BOX]         = (FLOAT64)SYM_PRIO_HIGH;
    ds->phase_base_priorities[PHASE_TAXI][SYM_TYPE_CENTERLINE]         = (FLOAT64)SYM_PRIO_NORMAL;
    // Suppress everything else
    for (int s = 0; s < SYM_TYPE_COUNT; ++s) {
        if (ds->phase_base_priorities[PHASE_TAXI][s] >= (FLOAT64)SYM_PRIO_NORMAL) {
            continue;
        }
        ds->phase_base_priorities[PHASE_TAXI][s] = (FLOAT64)SYM_PRIO_BACKGROUND;
    }
}

// ============================================================================
//  2.  Initialisation
// ============================================================================

void declutter_init(DeclutterState* ds) {
    if (ds == 0) return;

    ds->current_phase = PHASE_CRUISE;

    for (int i = 0; i < SYM_TYPE_COUNT; ++i) {
        ds->symbols[i].base_priority       = (FLOAT64)SYM_PRIO_NORMAL;
        ds->symbols[i].phase_modifier      = 1.0;
        ds->symbols[i].visibility_modifier = 1.0;
        ds->symbols[i].alpha               = 1.0;
        ds->symbols[i].dimming_factor      = 1.0;
        ds->symbols[i].suppressed          = false;
    }

    declutter_build_priority_table(ds);

    ds->low_visibility      = false;
    ds->visibility_factor   = 1.0;
    ds->global_dimming      = 1.0;
    ds->visible_symbol_count = SYM_TYPE_COUNT;
    ds->active              = false;
    ds->debug_force_all     = false;
}

// ============================================================================
//  3.  Declutter computation
// ============================================================================

void declutter_compute(DeclutterState* ds,
                        FlightPhase     phase,
                        bool            low_visibility,
                        FLOAT64         visibility_m) {
    if (ds == 0) return;

    ds->current_phase = phase;

    // Normalise visibility factor (200m = worst, 10km+ = best)
    const FLOAT64 vis = proj_clamp(visibility_m, 200.0, 10000.0);
    ds->visibility_factor = (vis - 200.0) / (10000.0 - 200.0);
    ds->low_visibility = low_visibility;

    const int p = (int)phase;

    // --- Compute per-symbol priority ---
    int visible_count = 0;
    for (int s = 0; s < SYM_TYPE_COUNT; ++s) {
        const FLOAT64 base_prio = ds->phase_base_priorities[p][s];

        // Phase modifier: symbols aligned with current phase get a boost
        FLOAT64 phase_mod = 1.0;
        if (s == SYM_TYPE_FLARE_CUE && phase == PHASE_FLARE) {
            phase_mod = 1.5;  // Boost flare cue during flare
        } else if (s == SYM_TYPE_ROLLOUT_CENTER && phase == PHASE_ROLLOUT) {
            phase_mod = 1.5;  // Boost rollout centerline during rollout
        } else if (s == SYM_TYPE_FPV && (phase == PHASE_APPROACH || phase == PHASE_FLARE)) {
            phase_mod = 1.3;  // Boost FPV during landing
        } else if (s == SYM_TYPE_RUNWAY_BOX && phase == PHASE_APPROACH) {
            phase_mod = 1.2;
        }

        // Visibility modifier: in low vis, boost critical elements
        FLOAT64 vis_mod = 1.0;
        if (low_visibility) {
            if (base_prio >= (FLOAT64)SYM_PRIO_HIGH) {
                vis_mod = 1.2;  // Boost high-priority elements in low vis
            } else if (base_prio <= (FLOAT64)SYM_PRIO_LOW) {
                vis_mod = 0.6;  // Suppress low-priority elements in low vis
            }
        }

        // Store modifiers
        ds->symbols[s].phase_modifier = proj_clamp(phase_mod, 0.0, 2.0);
        ds->symbols[s].visibility_modifier = proj_clamp(vis_mod, 0.0, 2.0);

        // Compute effective alpha
        const FLOAT64 effective_priority = base_prio * phase_mod * vis_mod;

        if (effective_priority >= (FLOAT64)SYM_PRIO_CRITICAL) {
            ds->symbols[s].alpha = 1.0;
            ds->symbols[s].dimming_factor = 1.0;
            ds->symbols[s].suppressed = false;
        } else if (effective_priority >= (FLOAT64)SYM_PRIO_HIGH) {
            ds->symbols[s].alpha = 0.9;
            ds->symbols[s].dimming_factor = 0.9;
            ds->symbols[s].suppressed = false;
        } else if (effective_priority >= (FLOAT64)SYM_PRIO_NORMAL) {
            ds->symbols[s].alpha = 0.7;
            ds->symbols[s].dimming_factor = 0.8;
            ds->symbols[s].suppressed = false;
        } else if (effective_priority >= (FLOAT64)SYM_PRIO_LOW) {
            ds->symbols[s].alpha = 0.4;
            ds->symbols[s].dimming_factor = 0.6;
            ds->symbols[s].suppressed = false;
        } else {
            // Background → suppressed (hidden)
            ds->symbols[s].alpha = 0.0;
            ds->symbols[s].dimming_factor = 0.0;
            ds->symbols[s].suppressed = true;
        }

        if (!ds->symbols[s].suppressed) {
            ++visible_count;
        }
    }

    ds->visible_symbol_count = visible_count;
    ds->active = (ds->visible_symbol_count < SYM_TYPE_COUNT);
}

// ============================================================================
//  4.  Debug logging
// ============================================================================

void declutter_debug_log(const DeclutterState* ds) {
    if (ds == 0) {
        MSFS_Log("[C_HUD_DCL] DeclutterState: NULL");
        return;
    }

    const char* phase_str = "?";
    switch (ds->current_phase) {
        case PHASE_CRUISE:   phase_str = "CRUISE";   break;
        case PHASE_APPROACH: phase_str = "APPROACH"; break;
        case PHASE_FLARE:    phase_str = "FLARE";    break;
        case PHASE_ROLLOUT:  phase_str = "ROLLOUT";  break;
        case PHASE_TAXI:     phase_str = "TAXI";     break;
    }

    MSFS_Log("[C_HUD_DCL] PHASE=%s  VIS=%s  LOVIS=%d  "
             "VISIBLE=%d/%d  GLOBAL_DIM=%.2f",
             phase_str,
             ds->visibility_factor > 0.7 ? "GOOD" :
             ds->visibility_factor > 0.3 ? "MOD" : "POOR",
             (int)ds->low_visibility,
             ds->visible_symbol_count, SYM_TYPE_COUNT,
             ds->global_dimming);
}
