// ============================================================================
//  Conformal HUD – Airbus A350 XWB Flight Path Vector Controller
//  MSFS 2024  ·  C++17  ·  WASM
//
//  v3.0.0 — A350 Certification Layer
//
//  Implementation of the A350 flight path vector controller that sits
//  above the existing AirbusFPVFilter and provides certification-level
//  FPV behaviour:
//
//    · Adaptive filtering with turbulence rejection
//    · Flare stabilization (runway-referenced during flare)
//    · Predictive runway alignment
//    · Crosswind visual compensation
// ============================================================================

#include "../../../include/hud/aircraft/a350_fpv_controller.h"
#include "../../../include/projection.h"

// ============================================================================
//  Internal: Turbulence detection (enhanced for controller)
// ============================================================================

static void controller_detect_turbulence(
    A350FPVTurbulenceState* ts,
    Vec2 raw,
    Vec2 filtered,
    FLOAT64 dt_s)
{
    if (ts == 0) return;

    // Compute frame-to-frame jitter magnitude
    const FLOAT64 jitter_x = proj_fabs(raw.x - filtered.x);
    const FLOAT64 jitter_y = proj_fabs(raw.y - filtered.y);
    const FLOAT64 jitter = (jitter_x + jitter_y) * 0.5;

    // EMA with fast attack, slow decay for envelope following
    if (!ts->initialised) {
        ts->jitter_ema = jitter;
        ts->initialised = true;
    }

    if (jitter > ts->jitter_ema) {
        ts->jitter_ema += (jitter - ts->jitter_ema) * ts->attack_alpha;
    } else {
        ts->jitter_ema += (jitter - ts->jitter_ema) * ts->decay_alpha;
    }

    // Map jitter EMA to turbulence level (0..1)
    const FLOAT64 j = ts->jitter_ema;
    FLOAT64 level = 0.0;

    if (j > ts->jitter_threshold_severe) {
        level = 1.0;
    } else if (j > ts->jitter_threshold_calm) {
        const FLOAT64 range = ts->jitter_threshold_severe - ts->jitter_threshold_calm;
        if (range > 0.01) {
            level = (j - ts->jitter_threshold_calm) / range;
        }
    }

    ts->turbulence_level = proj_clamp(level, 0.0, 1.0);

    // Confidence in turbulence estimate is inversely related to rate of change
    const FLOAT64 change_rate = proj_fabs(ts->turbulence_level - level);
    ts->turbulence_confidence = 1.0 - proj_fmin(change_rate * 2.0, 1.0);
}

// ============================================================================
//  Internal: Flare stabilization
// ============================================================================

static void controller_compute_flare_stab(
    A350FPVFlareStab* fs,
    Vec2 raw_pos,
    Vec2 runway_pos,
    FLOAT64 radio_alt_m,
    FLOAT64 dt_s,
    bool on_ground)
{
    if (fs == 0) return;

    const FLOAT64 flare_activation_m = 50.0 * 0.3048;  // 50 ft in metres

    // Determine if we're in flare
    const bool should_flare = (radio_alt_m < flare_activation_m && radio_alt_m > 0.1 && !on_ground)
                              || (radio_alt_m < 5.0)
                              || on_ground;

    if (should_flare) {
        fs->flare_active = true;
        fs->flare_height_m = radio_alt_m;

        // Compute flare blend: 0 at activation altitude, 1 at touchdown
        if (radio_alt_m < 0.5) {
            fs->flare_blend = 1.0;
        } else {
            fs->flare_blend = 1.0 - (radio_alt_m / flare_activation_m);
            fs->flare_blend = proj_clamp(fs->flare_blend, 0.0, 1.0);
        }

        // Runway reference position: smoothly blend FPV toward runway aim point
        if (fs->initialised) {
            const FLOAT64 blend_rate = fs->flare_stabilization_gain * 0.1;

            // Update runway reference (smoothed runway aim point)
            fs->runway_aim_point.x += (runway_pos.x - fs->runway_aim_point.x) * 0.15;
            fs->runway_aim_point.y += (runway_pos.y - fs->runway_aim_point.y) * 0.15;

            // The FPV is attracted to the runway aim point during flare
            // Stronger attraction closer to the ground
            const FLOAT64 attraction = fs->flare_blend * fs->runway_reference_strength;

            fs->stabilized_pos.x = raw_pos.x + (fs->runway_aim_point.x - raw_pos.x) * attraction;
            fs->stabilized_pos.y = raw_pos.y + (fs->runway_aim_point.y - raw_pos.y) * attraction;
        } else {
            fs->runway_aim_point = runway_pos;
            fs->stabilized_pos = raw_pos;
            fs->initialised = true;
        }
    } else {
        // Not in flare — decay flare state
        if (fs->flare_active) {
            fs->flare_blend *= 0.95;
            if (fs->flare_blend < 0.01) {
                fs->flare_active = false;
                fs->flare_blend = 0.0;
                fs->initialised = false;
            }
        }
    }
}

// ============================================================================
//  Internal: Predictive runway alignment
// ============================================================================

static void controller_predictive_align(
    A350FPVPredictiveAlign* pa,
    Vec2 raw_pos,
    Vec2 runway_pos,
    FLOAT64 dt_s,
    FLOAT64 crosswind_ms,
    FLOAT64 groundspeed_ms,
    bool flare_active)
{
    if (pa == 0) return;

    // Crosswind component for compensation
    pa->crosswind_component_ms = crosswind_ms;

    // Compute crosswind visual compensation offset
    // During approach and flare, crosswind causes the FPV to visually
    // drift from the runway centerline. We compensate by shifting the
    // FPV laterally to visually "attach" to the runway.
    if (flare_active || groundspeed_ms > 30.0) {
        // Crosswind compensation: ~0.5 px per knot of crosswind (scaled)
        const FLOAT64 crosswind_kt = crosswind_ms * 1.94384;
        const FLOAT64 comp_px = crosswind_kt * 0.35 * 0.6;  // 60% compensation

        pa->crosswind_compensation.x = comp_px;
        pa->crosswind_compensation.y = 0.0;

        // Alignment angle estimate (how much the aircraft is crabbing)
        pa->alignment_angle_deg = crosswind_ms / proj_fmax(groundspeed_ms, 1.0);
        pa->alignment_angle_deg = proj_fabs(pa->alignment_angle_deg * 57.2958);
        pa->alignment_angle_deg = proj_fmin(pa->alignment_angle_deg, 15.0);

        // Alignment quality is higher when crosswind is steady
        pa->alignment_quality = 1.0 - proj_fmin(proj_fabs(crosswind_ms) / 15.0, 0.7);
        pa->alignment_quality = proj_clamp(pa->alignment_quality, 0.3, 1.0);

        // Predicted touchdown position - blend between raw FPV and runway
        if (runway_pos.x != 0.0 || runway_pos.y != 0.0) {
            pa->predicted_touchdown_pos.x = raw_pos.x * 0.3 + runway_pos.x * 0.7;
            pa->predicted_touchdown_pos.y = raw_pos.y * 0.3 + runway_pos.y * 0.7;
        }

        pa->valid = true;
    } else {
        pa->crosswind_compensation = proj_vec3_make(0, 0, 0);
        pa->alignment_angle_deg = 0.0;
        pa->alignment_quality = 0.0;
        pa->valid = false;
    }
}

// ============================================================================
//  Core computation
// ============================================================================

void a350_fpv_controller_compute(
    A350FlightPathVectorController* ctrl,
    Vec2            raw_pos,
    Vec2            runway_pos,
    FLOAT64         dt_s,
    int             phase,
    FLOAT64         crosswind_ms,
    FLOAT64         radio_alt_m,
    FLOAT64         groundspeed_ms,
    bool            on_ground)
{
    if (ctrl == 0) return;

    ctrl->valid = false;
    ctrl->raw_screen_pos = raw_pos;

    // ================================================================
    //  Step 1: Set FPV phase for phase-aware base filtering
    // ================================================================
    airbus_fpv_set_phase(&ctrl->base_filter, phase);

    // ================================================================
    //  Step 2: Run base Airbus FPV filter
    // ================================================================
    Vec2 base_filtered = airbus_fpv_feed(&ctrl->base_filter, raw_pos, dt_s);
    ctrl->filtered_screen_pos = base_filtered;

    // If base filter didn't produce valid output, use raw
    if (base_filtered.x < -9000.0 || base_filtered.y < -9000.0) {
        base_filtered = raw_pos;
        ctrl->filtered_screen_pos = raw_pos;
    }

    // ================================================================
    //  Step 3: Detect turbulence and adapt
    // ================================================================
    controller_detect_turbulence(&ctrl->turbulence, raw_pos, base_filtered, dt_s);

    // Apply turbulence rejection: blend between filtered and extra-smoothed
    // based on turbulence level
    Vec2 post_turbulence = base_filtered;
    if (ctrl->turbulence.turbulence_level > 0.05) {
        // Extra EMA smoothing proportional to turbulence
        const FLOAT64 extra_alpha = 0.1 * (1.0 - ctrl->turbulence.turbulence_level * 0.5);
        const FLOAT64 extra_alpha_clamped = proj_clamp(extra_alpha, 0.02, 0.15);

        post_turbulence.x = post_turbulence.x * (1.0 - extra_alpha_clamped) +
                            base_filtered.x * extra_alpha_clamped;
        post_turbulence.y = post_turbulence.y * (1.0 - extra_alpha_clamped) +
                            base_filtered.y * extra_alpha_clamped;
    }

    // ================================================================
    //  Step 4: Crosswind visual compensation
    // ================================================================
    Vec2 with_crosswind = post_turbulence;
    if (ctrl->crosswind_compensation && (phase >= 1 /* APPROACH */)) {
        controller_predictive_align(
            &ctrl->predictive_align,
            post_turbulence,
            runway_pos,
            dt_s,
            crosswind_ms,
            groundspeed_ms,
            (phase == 2 || radio_alt_m < 50.0 * 0.3048));

        // Apply crosswind compensation
        with_crosswind.x += ctrl->predictive_align.crosswind_compensation.x;
        ctrl->debug_crosswind_px = ctrl->predictive_align.crosswind_compensation.x;
    }

    // ================================================================
    //  Step 5: Flare stabilization — runway-referenced FPV
    // ================================================================
    Vec2 flare_adjusted = with_crosswind;
    if (ctrl->runway_referenced_flare) {
        controller_compute_flare_stab(
            &ctrl->flare_stab,
            with_crosswind,
            runway_pos,
            radio_alt_m,
            dt_s,
            on_ground);

        if (ctrl->flare_stab.flare_active) {
            // Blend between crosswind-compensated and flare-stabilized
            const FLOAT64 blend = ctrl->flare_stab.flare_blend;
            flare_adjusted.x = with_crosswind.x * (1.0 - blend) +
                               ctrl->flare_stab.stabilized_pos.x * blend;
            flare_adjusted.y = with_crosswind.y * (1.0 - blend) +
                               ctrl->flare_stab.stabilized_pos.y * blend;
            ctrl->debug_flare_blend = blend;
        } else {
            ctrl->debug_flare_blend = 0.0;
        }
    }
    ctrl->flare_adjusted_pos = flare_adjusted;

    // ================================================================
    //  Step 6: Compute final stability score
    // ================================================================
    {
        // Stability is highest when:
        //   - turbulence is low
        //   - FPV is on screen and valid
        //   - flare transition is smooth (not oscillating)
        FLOAT64 turb_stability = 1.0 - ctrl->turbulence.turbulence_level;

        // Jitter-based stability
        FLOAT64 jitter_stability = 1.0;
        if (ctrl->turbulence.jitter_ema > 0.1) {
            jitter_stability = 1.0 / (1.0 + ctrl->turbulence.jitter_ema * 0.5);
        }

        // Flare smoothness
        FLOAT64 flare_smoothness = 1.0;
        if (ctrl->flare_stab.flare_active) {
            // During flare, stability is high when blend is smooth
            flare_smoothness = 0.8 + ctrl->flare_stab.flare_blend * 0.2;
        }

        ctrl->stability_score = (turb_stability * 0.4 +
                                  jitter_stability * 0.3 +
                                  flare_smoothness * 0.3);
        ctrl->stability_score = proj_clamp(ctrl->stability_score, 0.0, 1.0);

        // FPV quality blends stability with on-screen validity
        ctrl->fpv_quality = ctrl->stability_score * 0.7 + 0.3;
        ctrl->fpv_quality = proj_clamp(ctrl->fpv_quality, 0.0, 1.0);
    }

    // ================================================================
    //  Step 7: Final output
    // ================================================================
    ctrl->final_screen_pos = flare_adjusted;
    ctrl->on_screen = true;
    ctrl->valid = true;

    // Debug
    ctrl->debug_jitter = ctrl->turbulence.jitter_ema;
    ctrl->debug_turbulence = ctrl->turbulence.turbulence_level;
    ctrl->debug_stability = ctrl->stability_score;
}

// ============================================================================
//  Debug logging
// ============================================================================

void a350_fpv_controller_debug_log(const A350FlightPathVectorController* ctrl) {
    if (ctrl == 0) {
        MSFS_Log("[C_HUD_A350_FPV_CTRL] A350FlightPathVectorController: NULL");
        return;
    }

    MSFS_Log("[C_HUD_A350_FPV_CTRL] STAB=%.2f QUAL=%.2f TURB=%.2f "
             "FLARE=%.2f CROSS=%.2fpx ON=%d VALID=%d",
             ctrl->stability_score, ctrl->fpv_quality,
             ctrl->debug_turbulence,
             ctrl->debug_flare_blend, ctrl->debug_crosswind_px,
             (int)ctrl->on_screen, (int)ctrl->valid);
}
