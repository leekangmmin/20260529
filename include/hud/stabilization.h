#ifndef C_HUD_STABILIZATION_H
#define C_HUD_STABILIZATION_H

// ============================================================================
//  Conformal HUD – Symbol Stabilisation & Predictive Filtering
//  MSFS 2024  ·  C++17  ·  WASM
//
//  v2.3.0 — Turbulence-adaptive damping and motion confidence weighting.
//
//  Provides temporal smoothing and anti-jitter filtering for all HUD
//  symbology elements.  Uses predictive EMA filtering, temporal damping,
//  and adaptive smoothing to achieve aircraft-grade optical stability.
//
//  Stabilisation is applied to:
//    · FPV position → anti-jitter filtering
//    · Guidance cues → temporal damping
//    · Runway projection → EMA filtering of corner positions
//    · Horizon/pitch → angular smoothing
//
//  Each filter adapts its smoothing factor based on the rate of change
//  and the current phase of flight, so fast, deliberate movements are
//  tracked while small-amplitude jitter is suppressed.
// ============================================================================

#include "../module.h"
#include "../projection.h"

// ============================================================================
//  1.  Predictive EMA filter (with rate-of-change adaptation)
// ============================================================================

/// An adaptive EMA filter that adjusts its alpha based on the rate of
/// change of the input signal.  Fast, sustained changes → higher alpha
/// (less smoothing, more responsive).  Small perturbations → lower alpha
/// (more smoothing, jitter rejection).
typedef struct AdaptiveEMAFilter {
    FLOAT64 value;              // filtered output
    FLOAT64 alpha;              // current smoothing factor (0..1)
    FLOAT64 alpha_min;          // minimum alpha (max smoothing)
    FLOAT64 alpha_max;          // maximum alpha (min smoothing)
    FLOAT64 rate_threshold;     // rate-of-change threshold for adaptation
    FLOAT64 prev_raw;           // previous raw sample (for rate calc)
    FLOAT64 dt_s;               // time step (seconds)
    bool    initialised;
} AdaptiveEMAFilter;

/// Initialise an adaptive EMA filter.
static inline void adaptive_ema_init(AdaptiveEMAFilter* f,
                                      FLOAT64 alpha_min,
                                      FLOAT64 alpha_max,
                                      FLOAT64 rate_threshold) {
    if (f == 0) return;
    f->value     = 0.0;
    f->alpha     = alpha_min;
    f->alpha_min = (alpha_min > 0.0) ? alpha_min : 0.05;
    f->alpha_max = (alpha_max < 1.0) ? alpha_max : 0.95;
    f->rate_threshold = (rate_threshold > 0.0) ? rate_threshold : 1.0;
    f->prev_raw  = 0.0;
    f->dt_s      = 1.0 / 60.0;
    f->initialised = false;
}

/// Feed a raw sample into the adaptive EMA filter.
FLOAT64 adaptive_ema_feed(AdaptiveEMAFilter* f, FLOAT64 sample, FLOAT64 dt_s);

/// Reset an adaptive EMA filter.
static inline void adaptive_ema_reset(AdaptiveEMAFilter* f) {
    if (f == 0) return;
    f->value = 0.0;
    f->alpha = f->alpha_min;
    f->prev_raw = 0.0;
    f->initialised = false;
}

// ============================================================================
//  2.  2-D Position stabiliser (for FPV, guidance cues, etc.)
// ============================================================================

typedef struct PosStabiliser {
    AdaptiveEMAFilter fx;
    AdaptiveEMAFilter fy;
    Vec2    smoothed;
    Vec2    velocity;
    bool    initialised;
} PosStabiliser;

/// Initialise a 2-D position stabiliser.
static inline void pos_stab_init(PosStabiliser* ps,
                                  FLOAT64 alpha_min,
                                  FLOAT64 alpha_max,
                                  FLOAT64 rate_threshold) {
    if (ps == 0) return;
    adaptive_ema_init(&ps->fx, alpha_min, alpha_max, rate_threshold);
    adaptive_ema_init(&ps->fy, alpha_min, alpha_max, rate_threshold);
    ps->smoothed    = proj_vec2_make(0, 0);
    ps->velocity    = proj_vec2_make(0, 0);
    ps->initialised = false;
}

/// Feed a raw position sample into the 2-D stabiliser.
Vec2 pos_stab_feed(PosStabiliser* ps, Vec2 raw, FLOAT64 dt_s);

/// Reset the position stabiliser.
static inline void pos_stab_reset(PosStabiliser* ps) {
    if (ps == 0) return;
    adaptive_ema_reset(&ps->fx);
    adaptive_ema_reset(&ps->fy);
    ps->smoothed = proj_vec2_make(0, 0);
    ps->velocity = proj_vec2_make(0, 0);
    ps->initialised = false;
}

// ============================================================================
//  3.  Temporal damping (for guidance cues)
// ============================================================================

typedef struct TemporalDamper {
    FLOAT64 value;
    FLOAT64 velocity;
    FLOAT64 damping_ratio;
    FLOAT64 natural_freq;
    FLOAT64 dt_s;
    bool    initialised;
} TemporalDamper;

/// Initialise a temporal damper.
static inline void damper_init(TemporalDamper* d,
                                FLOAT64 damping_ratio,
                                FLOAT64 natural_freq_hz) {
    if (d == 0) return;
    d->value        = 0.0;
    d->velocity     = 0.0;
    d->damping_ratio = (damping_ratio > 0.0) ? damping_ratio : 1.0;
    d->natural_freq  = (natural_freq_hz > 0.0)
                         ? natural_freq_hz * 2.0 * 3.141592653589793 : 1.0;
    d->dt_s         = 1.0 / 60.0;
    d->initialised  = false;
}

/// Feed a raw value into the temporal damper.
FLOAT64 damper_feed(TemporalDamper* d, FLOAT64 target, FLOAT64 dt_s);

/// Reset the temporal damper to a specific value.
static inline void damper_reset(TemporalDamper* d, FLOAT64 value) {
    if (d == 0) return;
    d->value = value;
    d->velocity = 0.0;
    d->initialised = true;
}

// ============================================================================
//  4.  Complete symbol stabilisation state  (v2.3.0: turbulence-adaptive)
// ============================================================================

typedef struct HUDStabilisation {
    // --- FPV ---
    PosStabiliser   fpv_pos;
    TemporalDamper  fpv_pitch_damper;
    TemporalDamper  fpv_heading_damper;

    // --- Guidance cues ---
    PosStabiliser   loc_bar_pos;
    PosStabiliser   gs_bar_pos;
    TemporalDamper  steering_pitch;
    TemporalDamper  steering_bank;

    // --- Runway ---
    Vec2            runway_ema_corners[8];
    bool            runway_ema_initialised[8];

    // --- Horizon / Pitch ---
    TemporalDamper  horizon_y;
    TemporalDamper  horizon_slope;
    TemporalDamper  pitch_ladder_offsets[5];

    // --- Flare ---
    TemporalDamper  flare_cue;

    // ================================================================
    //  v2.3.0  —  Turbulence-adaptive parameters
    // ================================================================

    /// Estimated turbulence intensity (0 = calm, 1 = severe)
    FLOAT64 turbulence_intensity;

    /// Motion confidence weighting (0..1) — reduces smoothing when
    /// deliberate control inputs are detected vs environmental jitter.
    FLOAT64 motion_confidence;

    /// Adaptive damping multiplier applied to all alpha_min values
    /// during turbulence.  Higher = more smoothing.
    FLOAT64 turbulence_damping_boost;

    /// Frame-to-frame jitter accumulator for turbulence detection
    FLOAT64 jitter_accumulator;
    int     jitter_sample_count;

    // --- Global ---
    bool    initialised;
} HUDStabilisation;

/// Initialise all HUD stabilisation filters.
void hud_stab_init(HUDStabilisation* hs);

/// v2.3.0: Tune stabilisation parameters for current turbulence level.
/// Should be called once per frame before any stabilisation feeds.
///
/// @param hs            Stabilisation state
/// @param dt_s          Frame delta time (seconds)
/// @param turbulence_gain  Profile-specific turbulence sensitivity (0..1)
/// @param motion_weight    Profile-specific motion confidence weight (0..1)
void hud_stab_tune_for_turbulence(HUDStabilisation* hs,
                                   FLOAT64 dt_s,
                                   FLOAT64 turbulence_gain,
                                   FLOAT64 motion_weight);

/// Apply rate-of-change-based EMA to a single runway corner.
Vec2 hud_stab_runway_corner(HUDStabilisation* hs,
                             int index,
                             Vec2 raw,
                             FLOAT64 dt_s,
                             bool valid);

/// Apply stabilisation to FPV position.
Vec2 hud_stab_fpv(HUDStabilisation* hs, Vec2 raw, FLOAT64 dt_s);

/// Apply stabilisation to guidance cue positions.
void hud_stab_guidance(HUDStabilisation* hs,
                        Vec2  raw_loc,
                        Vec2  raw_gs,
                        FLOAT64 loc_error_dots,
                        FLOAT64 gs_error_dots,
                        FLOAT64 dt_s);

/// Apply stabilisation to horizon.
FLOAT64 hud_stab_horizon_y(HUDStabilisation* hs,
                            FLOAT64 raw_y,
                            FLOAT64 dt_s);

FLOAT64 hud_stab_horizon_slope(HUDStabilisation* hs,
                                FLOAT64 raw_slope,
                                FLOAT64 dt_s);

/// Apply stabilisation to a pitch ladder offset.
FLOAT64 hud_stab_pitch_line(HUDStabilisation* hs,
                             int index,
                             FLOAT64 raw,
                             FLOAT64 dt_s);

// ============================================================================
//  5.  Debug logging
// ============================================================================

void hud_stab_debug_log(const HUDStabilisation* hs);

#endif // C_HUD_STABILIZATION_H
