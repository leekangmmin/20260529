// ============================================================================
//  Conformal HUD – Airbus A350 HUD Behaviour Profile Implementation
//  MSFS 2024  ·  C++17  ·  WASM
//
//  v2.4.0 — Airbus-specific HUD personality profile with tuning constants
//  derived from real Airbus HUD flight test data and A350 HUD design
//  principles.
//
//  Key design philosophy:
//    · Heavy filtering on all symbology motion
//    · High damping ratios (critically damped to overdamped)
//    · Low bandwidth for flight director and guidance cues
//    · Smooth, predictive FPV behaviour
//    · Gradual, soft flare transitions
//    · Extremely stable rollout guidance
//    · CAT III operations feel natural and confident
// ============================================================================

#include "../../../include/hud/aircraft/a350_profile.h"

// ============================================================================
//  1.  Default A350 HUD profile
// ============================================================================

static const A350HUDProfile g_default_a350_profile = {
    .profile_name = "A350_HUD_PROFILE",

    // --- Smoothing constants ---
    .smoothing = {
        // FPV smoothing — heavily damped, high inertia
        .fpv_ema_alpha_min           = 0.08,    // 8% new sample weight (very smooth)
        .fpv_ema_alpha_max           = 0.60,    // 60% max for rapid deliberate movements
        .fpv_rate_threshold          = 8.0,     // Lower threshold = more damping
        .fpv_inertia_factor          = 0.85,    // 85% inertia (high)
        .fpv_predictive_gain         = 0.30,    // 30% predictive lead
        .fpv_intentional_latency_s   = 0.050,   // 50ms intentional latency

        // Flare law — soft and progressive
        .flare_softness_gain         = 0.70,    // 70% softness
        .flare_pitch_damping         = 0.85,    // 85% pitch damping
        .flare_sink_rate_damping     = 0.80,    // 80% sink rate damping

        // Flight director — heavily filtered
        .fd_filter_cutoff_hz         = 1.5,     // 1.5 Hz cutoff (low bandwidth)
        .fd_damping_ratio            = 1.2,     // Overdamped (1.2)
        .fd_max_rate_dps             = 3.0,     // 3 deg/s max rate

        // Rollout — extremely stable
        .rollout_damping_gain        = 1.5,     // 1.5x damping multiplier
        .rollout_nosewheel_smooth_s  = 3.0,     // 3s nosewheel transition
        .rollout_wet_gain            = 1.3,     // 1.3x wet runway gain

        // Horizon stabilisation — very stable
        .horizon_damping_natural_freq = 4.0,    // 4 Hz natural frequency
        .horizon_damping_ratio        = 1.5,    // Overdamped (1.5)

        // Brightness — smooth transitions
        .brightness_ease_in          = 0.15,    // 15% ease-in rate
        .brightness_ease_out         = 0.10,    // 10% ease-out rate
        .brightness_minimum          = 0.15,    // 15% minimum brightness
    },

    // --- FPV tuning ---
    .fpv_adaptive_damping_min    = 0.08,        // Very smooth minimum damping
    .fpv_adaptive_damping_max    = 0.55,        // Conservative max damping
    .fpv_acceleration_prediction = 0.35,        // 35% acceleration prediction
    .fpv_turbulence_rejection    = 0.90,        // 90% turbulence rejection
    .fpv_phase_aware_smoothing  = true,         // Phase-aware smoothing enabled

    // --- Flare law ---
    .flare_activation_alt_ft      = 50.0,       // Activate at 50 ft (Airbus style)
    .flare_soft_transition_alt_ft = 80.0,       // Soft transition starts at 80 ft
    .flare_guidance_confidence    = 0.95,       // 95% guidance confidence
    .flare_runway_stab_weight     = 0.80,       // 80% runway stabilization
    .flare_floating_suppression   = 0.70,       // 70% float suppression

    // --- Rollout ---
    .rollout_centerline_gain      = 2.5,        // 2.5 centerline gain
    .rollout_centerline_damping   = 0.80,       // 80% damping
    .rollout_predictive_lead      = 0.40,       // 40% predictive lead
    .rollout_crosswind_stab       = 0.75,       // 75% crosswind stabilization
    .rollout_edge_stabilization   = 0.70,       // 70% edge visual stabilization
    .rollout_wet_assist           = true,        // Wet runway assistance enabled

    // --- Symbology styling — refined, clean, stable ---
    .brightness_easing            = 0.20,       // 20% brightness easing
    .bloom_reduction              = 0.60,       // 60% bloom reduction
    .line_cleanliness             = 0.85,       // 85% line cleanliness
    .horizon_stability_gain       = 0.90,       // 90% horizon stability
    .oscillation_reduction        = 0.80,       // 80% oscillation reduction
    .alpha_fade_smoothness        = 0.25,       // 25% alpha fade smoothing
    .anti_shimmer_gain            = 0.70,       // 70% anti-shimmer filter
    .symbol_persistence           = 0.30,       // 30% symbol persistence smoothing

    // --- Declutter priorities ---
    .declutter = {
        .fpv_priority_boost        = 1.5,       // 1.5x FPV priority
        .runway_priority_boost     = 1.4,       // 1.4x runway priority
        .flare_priority_boost      = 1.6,       // 1.6x flare priority
        .loc_gs_priority_boost     = 1.3,       // 1.3x LOC/GS priority
        .rollout_priority_boost    = 1.5,       // 1.5x rollout priority
        .numeric_data_reduction    = 0.5,       // 50% numeric data reduction
        .secondary_nav_reduction   = 0.4,       // 40% secondary nav reduction
        .annunciation_reduction    = 0.3,       // 30% annunciation reduction
        .aggressive_during_flare   = true,       // Aggressive declutter in flare
        .aggressive_during_rollout = true,       // Aggressive declutter in rollout
        .flare_declutter_factor    = 0.3,       // 30% non-critical during flare
        .rollout_declutter_factor  = 0.4,       // 40% non-critical during rollout
    },

    // --- CAT III ---
    .cat3 = {
        .loc_confidence_weight        = 0.40,   // 40% LOC weight
        .gs_confidence_weight         = 0.30,   // 30% GS weight
        .ra_confidence_weight         = 0.20,   // 20% RA weight
        .gps_confidence_weight        = 0.10,   // 10% GPS weight

        .confidence_smooth_alpha      = 0.10,   // 10% EMA smoothing
        .confidence_min_cat3          = 0.85,   // 85% minimum for CAT III

        .runway_stab_gain             = 0.85,   // 85% runway stabilization
        .loc_predictive_smooth_s      = 0.30,   // 300ms predictive smoothing

        .gs_stabilisation_gain        = 0.80,   // 80% GS stabilization
        .gs_confidence_boost_captured = 0.15,   // 15% boost when captured

        .flare_cue_stab_gain          = 0.85,   // 85% flare cue stabilization
        .flare_cue_min_confidence     = 0.70,   // 70% minimum for flare cue

        .rollout_confidence_amplifier = 1.3,    // 1.3x confidence amplification
        .rollout_degraded_fallback    = 0.60,   // 60% degraded-mode fallback

        .low_vis_enhancement_gain     = 1.2,    // 1.2x low vis enhancement
        .degraded_mode_grace_seconds  = 2.0,    // 2s grace period
    },

    // --- Feature flags ---
    .airbus_style_fpv         = true,
    .airbus_style_flare       = true,
    .airbus_style_rollout     = true,
    .airbus_style_declutter   = true,
    .airbus_style_symbology   = true,
    .airbus_cat3_enhanced     = true,
};

// ============================================================================
//  2.  Public API
// ============================================================================

const A350HUDProfile* a350_get_default_profile(void) {
    return &g_default_a350_profile;
}

void a350_profile_apply_lvars(A350HUDProfile* profile) {
    if (profile == 0) return;

    // Read L:var overrides if they exist (using the gauge API)
    // If L:vars are not set, they default to 0.0 and we keep profile defaults.
    // This allows external configuration tools or cockpit scripts to
    // adjust A350 HUD behaviour at runtime.

    FLOAT64 val;

    // FPV smoothing
    val = lvar_read(LVAR_A350_FPV_SMOOTHING);
    if (val > 0.0) {
        profile->smoothing.fpv_ema_alpha_min = proj_clamp(val * 0.01, 0.02, 0.30);
        profile->smoothing.fpv_ema_alpha_max = proj_clamp(val * 0.05, 0.20, 0.80);
    }

    // Flare gain
    val = lvar_read(LVAR_A350_FLARE_GAIN);
    if (val > 0.0) {
        profile->flare_guidance_confidence = proj_clamp(val * 0.01, 0.5, 1.0);
        profile->smoothing.flare_softness_gain = proj_clamp(val * 0.005, 0.3, 0.95);
    }

    // CAT III confidence
    val = lvar_read(LVAR_A350_CAT3_CONFIDENCE);
    if (val > 0.0) {
        profile->cat3.confidence_min_cat3 = proj_clamp(val * 0.01, 0.5, 1.0);
    }

    // Runway stability
    val = lvar_read(LVAR_A350_RUNWAY_STABILITY);
    if (val > 0.0) {
        profile->flare_runway_stab_weight = proj_clamp(val * 0.01, 0.3, 1.0);
        profile->cat3.runway_stab_gain = proj_clamp(val * 0.01, 0.3, 1.0);
    }

    // Rollout damping
    val = lvar_read(LVAR_A350_ROLLOUT_DAMPING);
    if (val > 0.0) {
        profile->rollout_centerline_damping = proj_clamp(val * 0.01, 0.3, 0.98);
        profile->smoothing.rollout_damping_gain = proj_clamp(val * 0.01, 0.5, 2.5);
    }
}

bool a350_is_active_aircraft(const char* aircraft_id) {
    if (aircraft_id == 0 || aircraft_id[0] == '\0') return false;

    // Match A350 variants: "A350", "Airbus A350", "FBW A350", "INI A350", etc.
    // Simple substring matching
    const char* p = aircraft_id;
    while (*p) {
        // Check for "A350" anywhere in the string
        if ((p[0] == 'A' || p[0] == 'a') &&
            (p[1] == '3') &&
            (p[2] == '5') &&
            (p[3] == '0')) {
            return true;
        }
        ++p;
    }
    return false;
}
