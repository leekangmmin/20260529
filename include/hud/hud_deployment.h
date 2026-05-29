#ifndef C_HUD_HUD_DEPLOYMENT_H
#define C_HUD_HUD_DEPLOYMENT_H

// ============================================================================
//  Conformal HUD – HUD Deployment/Stow Detection Module
//  MSFS 2024  ·  C++17  ·  WASM
//
//  PHASE 4 — REAL HUD INTEGRATION
//
//  Provides aircraft-specific HUD deployment detection for each supported
//  aircraft family.  The physical HUD combiner glass may be animated
//  (deployed/stowed) via L:Vars or model animations.  This module:
//
//    1. Detects whether the HUD is physically deployed (glass visible).
//    2. Provides deployment confidence (transitioning vs fully deployed).
//    3. Allows the pipeline to skip rendering when the HUD is stowed.
//    4. Reports deployment state for each known aircraft type.
//
//  Supported aircraft:
//    · PMDG 737-700/800   — L:Vars for HUD power + deploy animation
//    · PMDG 777-300ER     — L:Vars for HUD power + deploy animation
//    · WT/Asobo 787-10    — L:Vars/panel state for HUD deployment
//    · iniBuilds A350      — Native HUD with deployment L:Vars
//
//  v3.0.1 — FIX: Lazy token resolution.  Deploy L:Var names in the config
//  are now resolved to GAUGE_VAR tokens at runtime via gauge_get_var_by_name(),
//  so the deployment state machine can actually read the aircraft's HUD
//  animation L:Vars instead of always reporting DEPLOYED.
// ============================================================================

#include "../module.h"

// ============================================================================
//  1.  Deployment phase enumeration
// ============================================================================

/// The physical deployment state of the HUD combiner glass.
typedef enum HUDDeployPhase {
    HUD_DEPLOY_UNKNOWN      = 0,   // State not yet determined
    HUD_DEPLOY_STOWED       = 1,   // HUD glass fully stowed (not visible)
    HUD_DEPLOY_TRANSITION   = 2,   // HUD is deploying or stowing
    HUD_DEPLOY_DEPLOYED     = 3,   // HUD glass fully deployed (visible)
} HUDDeployPhase;

// ============================================================================
//  2.  Deployment state (per aircraft, persistent across frames)
// ============================================================================

/// Complete HUD deployment state for the current aircraft.
typedef struct HUDDeploymentState {
    // --- Current state ---
    HUDDeployPhase  phase;                  // Current deployment phase
    HUDDeployPhase  prev_phase;             // Previous frame phase
    FLOAT64         deployment_fraction;    // 0.0 = stowed … 1.0 = deployed
    bool            power_on;               // HUD power switch state
    bool            electrical_power;       // Aircraft electrical power available

    // --- Detection method ---
    bool            use_power_lvar;         // Use power L:Var for detection
    bool            use_deploy_lvar;        // Use deploy animation L:Var
    bool            use_panel_state;        // Use panel state (787 style)
    bool            use_model_animation;    // Use model animation percentage

    // --- Active config (for lazy token resolution) ---
    const struct HUDDeployConfig* config;   // Currently active deploy config

    // --- L:Var tokens (resolved lazily via config name strings) ---
    GAUGE_VAR       tok_deploy_lvar;        // Deployment animation L:Var
    GAUGE_VAR       tok_deploy_pct;         // Deployment percentage (if available)

    // --- Timing ---
    FLOAT64         transition_timer_s;     // Time in current transition
    int             frames_since_change;    // Frames since last phase change
    FLOAT64         dt_s;                   // Frame delta time

    // --- Debug ---
    const char*     aircraft_id;            // Aircraft ID for debug logging
    bool            initialised;
    bool            valid;
} HUDDeploymentState;

// ============================================================================
//  3.  Per-aircraft deployment configuration
// ============================================================================

/// Configuration for HUD deployment detection on a specific aircraft.
typedef struct HUDDeployConfig {
    const char*     aircraft_prefix;        // Case-insensitive aircraft ID prefix
    bool            has_power_switch;       // True if power switch L:Var exists
    bool            has_deploy_animation;   // True if deploy animation L:Var exists
    const char*     power_lvar_name;        // Power switch L:Var name
    const char*     deploy_lvar_name;       // Deployment animation L:Var name
    const char*     deploy_pct_lvar;        // Deployment percentage L:Var (if available)
    FLOAT64         deploy_threshold;       // Fraction above which HUD is "deployed"
    FLOAT64         stow_threshold;         // Fraction below which HUD is "stowed"
    bool            use_panel_state;        // Use panel state configuration
} HUDDeployConfig;

// ============================================================================
//  4.  Initialisation
// ============================================================================

/// Initialise the HUD deployment state structure.
///
/// @param ds    [out] Deployment state to initialise
static inline void hud_deployment_init(HUDDeploymentState* ds) {
    if (ds == 0) return;
    ds->phase                = HUD_DEPLOY_UNKNOWN;
    ds->prev_phase           = HUD_DEPLOY_UNKNOWN;
    ds->deployment_fraction  = 1.0;         // Assume deployed until proven otherwise
    ds->power_on             = true;
    ds->electrical_power     = true;

    ds->use_power_lvar       = false;
    ds->use_deploy_lvar      = false;
    ds->use_panel_state      = false;
    ds->use_model_animation  = false;

    ds->config               = 0;

    ds->tok_deploy_lvar      = 0;
    ds->tok_deploy_pct       = 0;

    ds->transition_timer_s   = 0.0;
    ds->frames_since_change  = 0;
    ds->dt_s                 = 1.0 / 60.0;

    ds->aircraft_id          = 0;
    ds->initialised          = false;
    ds->valid                = false;
}

// ============================================================================
//  5.  Configuration lookup
// ============================================================================

/// Get the deployment configuration for a given aircraft ID.
///
/// @param aircraft_id   Aircraft title string (e.g. "PMDG 737-800")
/// @return              Pointer to static config, or 0 if unknown.
const HUDDeployConfig* hud_deploy_config_for_aircraft(const char* aircraft_id);

// ============================================================================
//  6.  Per-frame update
// ============================================================================

/// Update HUD deployment state for the current frame.
///
/// Should be called once per frame from the project phase.
///
/// @param ds             [in/out] Deployment state
/// @param aircraft_id    Current aircraft ID string
/// @param power_switch   Current HUD power switch value (0 or 1)
/// @param dt_s           Frame delta time (seconds)
/// @param frame_counter  Current frame counter
void hud_deployment_update(HUDDeploymentState* ds,
                            const char*         aircraft_id,
                            FLOAT64             power_switch,
                            FLOAT64             dt_s,
                            int                 frame_counter);

// ============================================================================
//  7.  Query helpers
// ============================================================================

/// Check if the HUD is fully deployed and ready for rendering.
///
/// @param ds   Deployment state
/// @return     True if HUD glass is deployed and power is on.
static inline bool hud_is_deployed(const HUDDeploymentState* ds) {
    if (ds == 0 || !ds->initialised) return true;  // Default to deployed
    return (ds->phase == HUD_DEPLOY_DEPLOYED && ds->power_on);
}

/// Check if the HUD is stowed and should NOT render.
///
/// @param ds   Deployment state
/// @return     True if HUD glass is stowed or power is off.
static inline bool hud_is_stowed(const HUDDeploymentState* ds) {
    if (ds == 0 || !ds->initialised) return false;  // Default to not stowed
    return (ds->phase == HUD_DEPLOY_STOWED || !ds->power_on);
}

/// Get the deployment fraction for use in fade animations.
///
/// @param ds   Deployment state
/// @return     0.0 = fully stowed, 1.0 = fully deployed
static inline FLOAT64 hud_deployment_fraction(const HUDDeploymentState* ds) {
    if (ds == 0) return 1.0;
    return ds->deployment_fraction;
}

// ============================================================================
//  8.  Debug logging
// ============================================================================

/// Log the current deployment state.
///
/// @param ds   Deployment state to log
void hud_deployment_debug_log(const HUDDeploymentState* ds);

// ============================================================================
//  9.  Lazy token resolution helper
// ============================================================================

/// Resolve deploy L:Var tokens from the active config using MSFS's
/// gauge_get_var_by_name().  This avoids the cross-TU visibility problem
/// that prevented module.cpp from registering these tokens in POST_INSTALL.
///
/// Call this every frame until all tokens are non-zero.
///
/// @param ds   [in/out] Deployment state with config already set
static inline void hud_deployment_resolve_tokens(HUDDeploymentState* ds) {
    if (ds == 0 || ds->config == 0) return;

    // Resolve deploy animation L:Var
    if (ds->tok_deploy_lvar == 0 && ds->config->deploy_lvar_name != 0) {
        ds->tok_deploy_lvar = gauge_get_var_by_name(
            ds->config->deploy_lvar_name, "number");
        if (ds->tok_deploy_lvar != 0) {
            MSFS_Log("[C_HUD] Deploy token resolved: '%s' -> %p",
                     ds->config->deploy_lvar_name,
                     (void*)(size_t)ds->tok_deploy_lvar);
        }
    }

    // Resolve deploy percentage L:Var (A350-specific)
    if (ds->tok_deploy_pct == 0 && ds->config->deploy_pct_lvar != 0) {
        ds->tok_deploy_pct = gauge_get_var_by_name(
            ds->config->deploy_pct_lvar, "number");
        if (ds->tok_deploy_pct != 0) {
            MSFS_Log("[C_HUD] Deploy PCT token resolved: '%s' -> %p",
                     ds->config->deploy_pct_lvar,
                     (void*)(size_t)ds->tok_deploy_pct);
        }
    }
}

#endif // C_HUD_HUD_DEPLOYMENT_H
