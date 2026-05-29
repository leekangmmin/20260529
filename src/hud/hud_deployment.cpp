// ============================================================================
//  Conformal HUD – HUD Deployment/Stow Detection Implementation
//  MSFS 2024  ·  C++17  ·  WASM
//
//  PHASE 4 — REAL HUD INTEGRATION
//
//  Implements HUD deployment detection for supported aircraft:
//    · PMDG 737 — Uses L:HUD_POWER_SWITCH + deploy animation L:Var
//    · PMDG 777 — Uses L:HUD_POWER_SWITCH + deploy animation L:Var
//    · WT 787  — Uses panel state / deploy animation L:Var
//    · A350    — Uses native HUD deployment L:Var
//
//  v3.0.1 — FIX: Lazy token resolution so deploy L:Vars (L:AS1001_HUD,
//  L:HUD_DEPLOY, L:A350_HUD_DEPLOY, L:A350_HUD_DEPLOY_PCT) are actually
//  resolved to GAUGE_VAR tokens and readable by the state machine.
// ============================================================================

#include "hud/hud_deployment.h"

// ============================================================================
//  1.  Known deployment configurations (matching aircraft_detector.cpp)
// ============================================================================

/// Registry of known deployment configurations.
static const HUDDeployConfig kDeployConfigs[] = {
    // --- PMDG 737 — Uses HUD_POWER_SWITCH + deploy animation ---
    {
        .aircraft_prefix       = "PMDG 737",
        .has_power_switch      = true,
        .has_deploy_animation  = true,
        .power_lvar_name       = "L:HUD_POWER_SWITCH",
        .deploy_lvar_name      = "L:AS1001_HUD",
        .deploy_pct_lvar       = 0,
        .deploy_threshold      = 0.85,
        .stow_threshold        = 0.15,
        .use_panel_state       = false,
    },
    // --- PMDG 777 — Uses HUD_POWER_SWITCH + deploy animation ---
    {
        .aircraft_prefix       = "PMDG 777",
        .has_power_switch      = true,
        .has_deploy_animation  = true,
        .power_lvar_name       = "L:HUD_POWER_SWITCH",
        .deploy_lvar_name      = "L:AS1001_HUD",
        .deploy_pct_lvar       = 0,
        .deploy_threshold      = 0.85,
        .stow_threshold        = 0.15,
        .use_panel_state       = false,
    },
    // --- WT / Asobo 787 — Panel state based deployment ---
    {
        .aircraft_prefix       = "ASOBO BOEING 787",
        .has_power_switch      = true,
        .has_deploy_animation  = true,
        .power_lvar_name       = "L:HUD_POWER_SWITCH",
        .deploy_lvar_name      = "L:HUD_DEPLOY",
        .deploy_pct_lvar       = 0,
        .deploy_threshold      = 0.75,
        .stow_threshold        = 0.25,
        .use_panel_state       = true,
    },
    // --- WT_787 alternative prefix ---
    {
        .aircraft_prefix       = "WT_787",
        .has_power_switch      = true,
        .has_deploy_animation  = true,
        .power_lvar_name       = "L:HUD_POWER_SWITCH",
        .deploy_lvar_name      = "L:HUD_DEPLOY",
        .deploy_pct_lvar       = 0,
        .deploy_threshold      = 0.75,
        .stow_threshold        = 0.25,
        .use_panel_state       = true,
    },
    // --- iniBuilds A350 — Native HUD with deployment L:Var ---
    {
        .aircraft_prefix       = "INI A350",
        .has_power_switch      = true,
        .has_deploy_animation  = true,
        .power_lvar_name       = "L:A350_HUD_POWER",
        .deploy_lvar_name      = "L:A350_HUD_DEPLOY",
        .deploy_pct_lvar       = "L:A350_HUD_DEPLOY_PCT",
        .deploy_threshold      = 0.80,
        .stow_threshold        = 0.20,
        .use_panel_state       = false,
    },
    // --- FBW — Generic HUD fallback (always deployed) ---
    {
        .aircraft_prefix       = "FBW",
        .has_power_switch      = true,
        .has_deploy_animation  = false,
        .power_lvar_name       = "L:HUD_POWER_SWITCH",
        .deploy_lvar_name       = 0,
        .deploy_pct_lvar       = 0,
        .deploy_threshold      = 0.5,
        .stow_threshold        = 0.5,
        .use_panel_state       = false,
    },
    // --- HEADWIND A330 ---
    {
        .aircraft_prefix       = "HEADWIND A330",
        .has_power_switch      = true,
        .has_deploy_animation  = false,
        .power_lvar_name       = "L:HUD_POWER_SWITCH",
        .deploy_lvar_name       = 0,
        .deploy_pct_lvar       = 0,
        .deploy_threshold      = 0.5,
        .stow_threshold        = 0.5,
        .use_panel_state       = false,
    },
    // --- INI A330 — Uses HUD_POWER_SWITCH + deploy animation ---
    {
        .aircraft_prefix       = "INI A330",
        .has_power_switch      = true,
        .has_deploy_animation  = false,
        .power_lvar_name       = "L:HUD_POWER_SWITCH",
        .deploy_lvar_name       = 0,
        .deploy_pct_lvar       = 0,
        .deploy_threshold      = 0.5,
        .stow_threshold        = 0.5,
        .use_panel_state       = false,
    },
    // --- Sentinel ---
    { 0, false, false, 0, 0, 0, 0.5, 0.5, false },
};

// ============================================================================
//  2.  Case-insensitive prefix matching
// ============================================================================

/// Check if `str` starts with `prefix` (case-insensitive ASCII).
static bool deploy_prefix_match(const char* str, const char* prefix) {
    if (str == 0 || prefix == 0) return false;
    while (*prefix) {
        char sc = *str;
        char pc = *prefix;
        if (sc >= 'A' && sc <= 'Z') sc += 32;
        if (pc >= 'A' && pc <= 'Z') pc += 32;
        if (sc != pc) return false;
        ++str; ++prefix;
    }
    return true;
}

// ============================================================================
//  3.  Configuration lookup
// ============================================================================

const HUDDeployConfig* hud_deploy_config_for_aircraft(const char* aircraft_id) {
    if (aircraft_id == 0 || aircraft_id[0] == '\0') return 0;

    for (int i = 0; kDeployConfigs[i].aircraft_prefix != 0; ++i) {
        if (deploy_prefix_match(aircraft_id, kDeployConfigs[i].aircraft_prefix)) {
            return &kDeployConfigs[i];
        }
    }
    return 0;
}

// ============================================================================
//  4.  Per-frame update
// ============================================================================

void hud_deployment_update(HUDDeploymentState* ds,
                            const char*         aircraft_id,
                            FLOAT64             power_switch,
                            FLOAT64             dt_s,
                            int                 frame_counter) {
    if (ds == 0) return;

    // First-time initialisation
    if (!ds->initialised) {
        hud_deployment_init(ds);
        ds->aircraft_id = aircraft_id;
        ds->dt_s = dt_s;

        // Look up aircraft-specific config
        const HUDDeployConfig* cfg = hud_deploy_config_for_aircraft(aircraft_id);
        ds->config = cfg;

        if (cfg != 0) {
            ds->use_power_lvar  = cfg->has_power_switch;
            ds->use_deploy_lvar = cfg->has_deploy_animation;
            ds->use_panel_state = cfg->use_panel_state;

            // Default to deployed while tokens are unresolved
            ds->deployment_fraction = 1.0;
            ds->phase = HUD_DEPLOY_DEPLOYED;

            // Try to resolve tokens immediately
            hud_deployment_resolve_tokens(ds);

            MSFS_Log("[C_HUD] Deploy init: aircraft='%s'  power_lvar=%d  deploy_lvar=%d  "
                     "deploy_var='%s'  pct_var='%s'",
                     aircraft_id ? aircraft_id : "(null)",
                     (int)ds->use_power_lvar,
                     (int)ds->use_deploy_lvar,
                     cfg->deploy_lvar_name ? cfg->deploy_lvar_name : "(none)",
                     cfg->deploy_pct_lvar ? cfg->deploy_pct_lvar : "(none)");
        } else {
            // Unknown aircraft — assume always deployed
            ds->use_power_lvar = true;
            ds->deployment_fraction = 1.0;
            ds->phase = HUD_DEPLOY_DEPLOYED;

            MSFS_Log("[C_HUD] Deploy init: aircraft='%s'  (unknown, assuming deployed)",
                     aircraft_id ? aircraft_id : "(null)");
        }

        ds->initialised = true;
        ds->valid = true;
    }

    // Store previous phase
    ds->prev_phase = ds->phase;
    ds->dt_s = dt_s;

    // --- Lazy token resolution (retry every frame until resolved) ---
    if (ds->config != 0 && ds->use_deploy_lvar &&
        (ds->tok_deploy_lvar == 0 ||
         (ds->config->deploy_pct_lvar != 0 && ds->tok_deploy_pct == 0))) {
        hud_deployment_resolve_tokens(ds);
    }

    // Read electrical power state (default to true)
    ds->electrical_power = true;

    // Read power switch
    ds->power_on = (power_switch >= 0.5);

    // Track deployment fraction
    FLOAT64 deploy_raw = 1.0;

    // Read deployment animation L:Var (if token is resolved)
    if (ds->use_deploy_lvar && ds->tok_deploy_lvar != 0) {
        const FLOAT64 raw = module_read_f64(ds->tok_deploy_lvar);
        if (raw == raw) {  // NaN check
            deploy_raw = raw;

        }
    }

    // If there's a percentage L:Var, use that for more precise tracking
    if (ds->tok_deploy_pct != 0) {
        const FLOAT64 pct = module_read_f64(ds->tok_deploy_pct);
        if (pct == pct && pct >= 0.0 && pct <= 100.0) {
            deploy_raw = pct / 100.0;
        }
    }

    // Smooth the deployment fraction to avoid jitter
    {
        const FLOAT64 alpha = 0.15;  // EMA smoothing
        ds->deployment_fraction = ds->deployment_fraction * (1.0 - alpha)
                                  + deploy_raw * alpha;
        if (ds->deployment_fraction < 0.0) ds->deployment_fraction = 0.0;
        if (ds->deployment_fraction > 1.0) ds->deployment_fraction = 1.0;
    }

    // Determine phase from deployment fraction using config thresholds
    const HUDDeployPhase prev = ds->phase;
    const FLOAT64 deploy_thresh = (ds->config != 0) ? ds->config->deploy_threshold : 0.85;
    const FLOAT64 stow_thresh   = (ds->config != 0) ? ds->config->stow_threshold   : 0.15;

    if (!ds->power_on) {
        ds->phase = HUD_DEPLOY_STOWED;
    } else if (ds->deployment_fraction >= deploy_thresh) {
        ds->phase = HUD_DEPLOY_DEPLOYED;
    } else if (ds->deployment_fraction <= stow_thresh) {
        ds->phase = HUD_DEPLOY_STOWED;
    } else {
        ds->phase = HUD_DEPLOY_TRANSITION;
    }

    // Track transition timing
    if (ds->phase != prev) {
        ds->transition_timer_s = 0.0;
        ds->frames_since_change = 0;
        MSFS_Log("[C_HUD] Deploy phase: %d -> %d  (fraction=%.3f  power=%d  "
                 "deploy_thresh=%.2f  stow_thresh=%.2f)",
                 (int)prev, (int)ds->phase, ds->deployment_fraction,
                 (int)ds->power_on, deploy_thresh, stow_thresh);
    } else {
        ds->transition_timer_s += dt_s;
        ds->frames_since_change++;
    }

    // Periodic debug logging (every 10 seconds in transition)
    if (ds->phase == HUD_DEPLOY_TRANSITION &&
        (frame_counter % 600) == 0) {
        MSFS_Log("[C_HUD] Deploy: phase=TRANSITION  fraction=%.3f  timer=%.1fs",
                 ds->deployment_fraction, ds->transition_timer_s);
    }
}

// ============================================================================
//  5.  Debug logging
// ============================================================================

void hud_deployment_debug_log(const HUDDeploymentState* ds) {
    if (ds == 0 || !ds->valid) return;

    const char* phase_str = "UNKNOWN";
    switch (ds->phase) {
        case HUD_DEPLOY_STOWED:     phase_str = "STOWED";     break;
        case HUD_DEPLOY_TRANSITION: phase_str = "TRANSITION"; break;
        case HUD_DEPLOY_DEPLOYED:   phase_str = "DEPLOYED";   break;
        default:                    phase_str = "UNKNOWN";    break;
    }

    MSFS_Log("[C_HUD] Deploy: phase=%s  fraction=%.3f  power=%d  "
             "timer=%.1fs  frames=%d  tok_lvar=%p  tok_pct=%p",
             phase_str,
             ds->deployment_fraction,
             (int)ds->power_on,
             ds->transition_timer_s,
             ds->frames_since_change,
             (void*)(size_t)ds->tok_deploy_lvar,
             (void*)(size_t)ds->tok_deploy_pct);
}
