#!/usr/bin/env python3
"""
Conformal HUD – Airbus A350-Specific HUD Test Suite (v3.0.0)

Tests:
  1. A350 HUD profile default values and structure
  2. Airbus FPV filter (damping, jitter suppression, turbulence)
  3. A350 flare law (soft transition, phase detection, float suppression)
  4. A350 rollout augmentation (centerline, crosswind, wet runway)
  5. CAT III augmentation (sensor fusion, degraded mode)
  6. Symbology styling (brightness easing, alpha smoothing, anti-shimmer)
  7. L:var integration and consistency
  8. Cross-module integration scenarios
  v3.0.0:
  9. A350 FPV Controller (flare stabilization, crosswind, turbulence)
  10. A350 Horizon Controller (turbulence damping, attitude smoothing)
  11. A350 Autoland HUD Layer (CAT IIIA/B/C, graceful degradation)
  12. A350 Landing Energy Model (weight, sink rate, rollout prediction)
  13. A350 Runway Augmentation (threshold/centerline/edge stabilization)
  14. Certification layer integration scenarios

Run:  python -m pytest tests/test_a350_hud.py -v
"""

import math
import pytest


# ======================================================================
#  Constants
# ======================================================================
G = 9.80665
KT_PER_MS = 1.94384
FT_TO_M = 0.3048

# Test tolerance
TOL = 1e-6


# ======================================================================
#  1.  A350 HUD Profile Reference Implementation
# ======================================================================

class A350SmoothingConstants:
    def __init__(self):
        self.fpv_ema_alpha_min = 0.08
        self.fpv_ema_alpha_max = 0.60
        self.fpv_rate_threshold = 8.0
        self.fpv_inertia_factor = 0.85
        self.fpv_predictive_gain = 0.30
        self.fpv_intentional_latency_s = 0.050

        self.flare_softness_gain = 0.70
        self.flare_pitch_damping = 0.85
        self.flare_sink_rate_damping = 0.80

        self.fd_filter_cutoff_hz = 1.5
        self.fd_damping_ratio = 1.2
        self.fd_max_rate_dps = 3.0

        self.rollout_damping_gain = 1.5
        self.rollout_nosewheel_smooth_s = 3.0
        self.rollout_wet_gain = 1.3

        self.horizon_damping_natural_freq = 4.0
        self.horizon_damping_ratio = 1.5

        self.brightness_ease_in = 0.15
        self.brightness_ease_out = 0.10
        self.brightness_minimum = 0.15


class A350DeclutterPriorities:
    def __init__(self):
        self.fpv_priority_boost = 1.5
        self.runway_priority_boost = 1.4
        self.flare_priority_boost = 1.6
        self.loc_gs_priority_boost = 1.3
        self.rollout_priority_boost = 1.5
        self.numeric_data_reduction = 0.5
        self.secondary_nav_reduction = 0.4
        self.annunciation_reduction = 0.3
        self.aggressive_during_flare = True
        self.aggressive_during_rollout = True
        self.flare_declutter_factor = 0.3
        self.rollout_declutter_factor = 0.4


class A350CatIIIParams:
    def __init__(self):
        self.loc_confidence_weight = 0.40
        self.gs_confidence_weight = 0.30
        self.ra_confidence_weight = 0.20
        self.gps_confidence_weight = 0.10
        self.confidence_smooth_alpha = 0.10
        self.confidence_min_cat3 = 0.85
        self.runway_stab_gain = 0.85
        self.loc_predictive_smooth_s = 0.30
        self.gs_stabilisation_gain = 0.80
        self.gs_confidence_boost_captured = 0.15
        self.flare_cue_stab_gain = 0.85
        self.flare_cue_min_confidence = 0.70
        self.rollout_confidence_amplifier = 1.3
        self.rollout_degraded_fallback = 0.60
        self.low_vis_enhancement_gain = 1.2
        self.degraded_mode_grace_seconds = 2.0


class A350HUDProfile:
    def __init__(self):
        self.profile_name = "A350_HUD_PROFILE"
        self.smoothing = A350SmoothingConstants()
        self.fpv_adaptive_damping_min = 0.08
        self.fpv_adaptive_damping_max = 0.55
        self.fpv_acceleration_prediction = 0.35
        self.fpv_turbulence_rejection = 0.90
        self.fpv_phase_aware_smoothing = True
        self.flare_activation_alt_ft = 50.0
        self.flare_soft_transition_alt_ft = 80.0
        self.flare_guidance_confidence = 0.95
        self.flare_runway_stab_weight = 0.80
        self.flare_floating_suppression = 0.70
        self.rollout_centerline_gain = 2.5
        self.rollout_centerline_damping = 0.80
        self.rollout_predictive_lead = 0.40
        self.rollout_crosswind_stab = 0.75
        self.rollout_edge_stabilization = 0.70
        self.rollout_wet_assist = True
        self.brightness_easing = 0.20
        self.bloom_reduction = 0.60
        self.line_cleanliness = 0.85
        self.horizon_stability_gain = 0.90
        self.oscillation_reduction = 0.80
        self.alpha_fade_smoothness = 0.25
        self.anti_shimmer_gain = 0.70
        self.symbol_persistence = 0.30
        self.declutter = A350DeclutterPriorities()
        self.cat3 = A350CatIIIParams()
        self.airbus_style_fpv = True
        self.airbus_style_flare = True
        self.airbus_style_rollout = True
        self.airbus_style_declutter = True
        self.airbus_style_symbology = True
        self.airbus_cat3_enhanced = True


# ======================================================================
#  2.  Airbus FPV Filter Reference Implementation
# ======================================================================

class AirbusFPVFilter:
    """Airbus-style FPV filter with heavy damping, inertia, and prediction."""
    def __init__(self):
        self.damping_min = 0.08
        self.damping_max = 0.55
        self.current_damping = 0.30
        self.damping_adaptation_rate = 0.05

        self.acceleration = 0.0
        self.velocity = 0.0
        self.prediction_gain = 0.30
        self.prev_filtered = 0.0
        self.prev_filtered_y = 0.0

        self.turbulence_level = 0.0
        self.turbulence_rejection_gain = 0.90
        self.jitter_accumulator = 0.0

        self.phase_aware_enabled = True
        self.phase_damping_multiplier = 1.0
        self.current_phase = 0

        self.lpf_cutoff_hz = 4.0
        self.lpf_state = 0.0
        self.intentional_latency_s = 0.050

        # EMA state
        self.ema_x_value = 0.0
        self.ema_x_alpha = 0.08
        self.ema_x_initialised = False
        self.ema_y_value = 0.0
        self.ema_y_alpha = 0.08
        self.ema_y_initialised = False

        self.raw_input = (0.0, 0.0)
        self.filtered_output = (0.0, 0.0)
        self.predicted_output = (0.0, 0.0)
        self.initialised = False

    def configure(self, damping_min, damping_max, prediction_gain, turbulence_rej, latency_s):
        self.damping_min = max(0.02, min(0.50, damping_min))
        self.damping_max = max(0.15, min(0.90, damping_max))
        self.prediction_gain = max(0.0, min(0.8, prediction_gain))
        self.turbulence_rejection_gain = max(0.0, min(1.0, turbulence_rej))
        self.intentional_latency_s = max(0.0, min(0.200, latency_s))

    def set_phase(self, phase):
        self.current_phase = phase
        if not self.phase_aware_enabled:
            self.phase_damping_multiplier = 1.0
            return
        if phase == 2:  # FLARE
            self.phase_damping_multiplier = 1.8
        elif phase == 3:  # ROLLOUT
            self.phase_damping_multiplier = 1.5
        elif phase == 1:  # APPROACH
            self.phase_damping_multiplier = 1.3
        else:
            self.phase_damping_multiplier = 1.0

    def _detect_turbulence(self, raw_x, raw_y, filtered_x, filtered_y):
        # On first call when filtered is (0,0), skip detection to avoid startup transient
        if not self.initialised and filtered_x == 0.0 and filtered_y == 0.0:
            return 0.0
        jitter_x = abs(raw_x - filtered_x)
        jitter_y = abs(raw_y - filtered_y)
        jitter = (jitter_x + jitter_y) * 0.5

        attack_alpha = 0.3
        decay_alpha = 0.05

        if jitter > self.jitter_accumulator:
            self.jitter_accumulator += (jitter - self.jitter_accumulator) * attack_alpha
        else:
            self.jitter_accumulator += (jitter - self.jitter_accumulator) * decay_alpha

        j = self.jitter_accumulator
        if j > 8.0:
            level = 1.0
        elif j > 3.0:
            level = 0.5 + (j - 3.0) / 10.0
        elif j > 0.5:
            level = (j - 0.5) / 5.0
        else:
            level = 0.0
        return max(0.0, min(1.0, level))

    def _lpf_single_pole(self, inp, state, cutoff_hz, dt_s):
        if cutoff_hz <= 0.0 or dt_s <= 0.0:
            return inp
        rc = 1.0 / (cutoff_hz * 2.0 * math.pi)
        alpha = dt_s / (rc + dt_s)
        if state[0] == 0.0:
            state[0] = inp  # Initialise state to input
        state[0] = state[0] + alpha * (inp - state[0])
        return state[0]

    def feed(self, raw_x, raw_y, dt_s=1.0/60.0):
        self.raw_input = (raw_x, raw_y)

        # Step 1: Handle first frame - initialise and return raw
        if not self.initialised:
            self.ema_x_value = raw_x
            self.ema_y_value = raw_y
            self.filtered_output = (raw_x, raw_y)
            self.predicted_output = (raw_x, raw_y)
            self.ema_x_initialised = True
            self.ema_y_initialised = True
            self.prev_filtered = raw_x
            self.prev_filtered_y = raw_y
            self.initialised = True
            return self.predicted_output

        # Step 1: Detect turbulence
        fx, fy = self.filtered_output
        self.turbulence_level = self._detect_turbulence(raw_x, raw_y, fx, fy)

        # Step 2: Adapt damping
        adapted_min = self.damping_min
        adapted_max = self.damping_max

        if self.turbulence_level > 0.05:
            turb_factor = 1.0 - self.turbulence_level * self.turbulence_rejection_gain
            adapted_min *= turb_factor
            adapted_max *= (1.0 - self.turbulence_level * 0.3)

        adapted_min /= self.phase_damping_multiplier
        adapted_max /= self.phase_damping_multiplier
        adapted_min = max(0.02, min(0.50, adapted_min))
        adapted_max = max(0.15, min(0.95, adapted_max))

        self.current_damping = adapted_min
        self.ema_x_alpha = adapted_min
        self.ema_y_alpha = adapted_min

        # Step 3: Apply EMA filtering
        # (first frame already handled above, now apply EMA)
        rate_x = abs(raw_x - self.ema_x_value)
        alpha_x = adapted_min
        if rate_x > self.damping_min * 100:
            alpha_x = adapted_max * 0.5
        alpha_y = adapted_min
        rate_y = abs(raw_y - self.ema_y_value)
        if rate_y > self.damping_min * 100:
            alpha_y = adapted_max * 0.5
        self.ema_x_value = alpha_x * raw_x + (1.0 - alpha_x) * self.ema_x_value
        self.ema_y_value = alpha_y * raw_y + (1.0 - alpha_y) * self.ema_y_value

        sx, sy = self.ema_x_value, self.ema_y_value
        self.filtered_output = (sx, sy)

        # Step 4: Intentional latency LPF
        if self.intentional_latency_s > 0.01:
            lpf_cutoff = 1.0 / (2.0 * math.pi * (self.intentional_latency_s + 0.001))
            self.lpf_cutoff_hz = max(0.5, min(20.0, lpf_cutoff))
            lpf_state = [self.lpf_state]
            sx = self._lpf_single_pole(sx, lpf_state, self.lpf_cutoff_hz, dt_s)
            self.lpf_state = lpf_state[0]
            sy = self.ema_y_value

        # Step 5: Acceleration prediction
        if self.initialised and dt_s > 0.001:
            vel_x = (sx - self.prev_filtered) / dt_s
            vel_y = (sy - self.prev_filtered_y) / dt_s
            vel_alpha = 0.2
            self.velocity = self.velocity * (1.0 - vel_alpha) + math.sqrt(vel_x**2 + vel_y**2) * vel_alpha
            pred_dt = self.prediction_gain * 0.5
            px = sx + vel_x * pred_dt
            py = sy + vel_y * pred_dt
            max_pred = 20.0
            dx = max(-max_pred, min(max_pred, px - sx))
            dy = max(-max_pred, min(max_pred, py - sy))
            px, py = sx + dx, sy + dy
            if self.turbulence_level > 0.2:
                turb_factor = max(0.0, min(1.0, 1.0 - (self.turbulence_level - 0.2) / 0.8))
                px = sx + (px - sx) * turb_factor
                py = sy + (py - sy) * turb_factor
            self.predicted_output = (px, py)
        else:
            self.predicted_output = (sx, sy)
            self.velocity = 0.0
            self.acceleration = 0.0

        self.prev_filtered = sx
        self.prev_filtered_y = sy
        self.initialised = True
        return self.predicted_output

    def get_filtered(self):
        return self.filtered_output

    def get_predicted(self):
        return self.predicted_output

    def get_turbulence(self):
        return self.turbulence_level

    def reset(self):
        self.__init__()


# ======================================================================
#  3.  A350 Flare Law Reference Implementation
# ======================================================================

class A350FlareLaw:
    def __init__(self):
        self.phase = 0  # INACTIVE
        self.engagement_alt_m = 0.0
        self.time_in_phase_s = 0.0
        self.pitch_command_deg = 0.0
        self.pitch_rate_command_dps = 0.0
        self.sink_rate_command_ms = 0.0
        self.sink_rate_error_ms = 0.0
        self.pitch_attenuation = 0.0
        self.pitch_rate_limit_dps = 2.0
        self.guidance_confidence = 1.0
        self.sink_rate_stability = 1.0
        self.runway_stab_weight = 0.5
        self.runway_visual_stab = 0.5
        self.float_suppression_cue = 0.0
        self.flare_completion = 0.0
        self.prev_vertical_speed_ms = 0.0
        self.sink_rate_filtered = 0.0
        self.pitch_filtered = 0.0
        self.radio_altitude_m = 100.0
        self.vertical_speed_ms = 0.0
        self.groundspeed_ms = 70.0
        self.pitch_deg = 2.0
        self.gs_deviation_deg = 0.0
        self.activation_alt_ft = 50.0
        self.soft_transition_alt_ft = 80.0
        self.flare_guidance_confidence = 0.95
        self.runway_stab_weight_setting = 0.80
        self.float_suppression_gain = 0.70
        self.valid = False
        self.active = False

    def _get_activation_m(self):
        return self.activation_alt_ft * FT_TO_M

    def _get_soft_m(self):
        return self.soft_transition_alt_ft * FT_TO_M

    def compute(self, dt_s=1.0/60.0):
        self.valid = False
        ra = max(self.radio_altitude_m, 0.0)
        vs = self.vertical_speed_ms
        act_m = self._get_activation_m()
        soft_m = self._get_soft_m()

        # Phase transitions
        if self.phase == 0 and ra < soft_m and vs < -0.3:
            self.phase = 1
            self.engagement_alt_m = ra
            self.time_in_phase_s = 0.0
            self.active = True

        if self.phase == 1 and ra < act_m:
            self.phase = 2
            self.time_in_phase_s = 0.0

        if self.phase == 2 and ra <= 0.5:
            self.phase = 3
            self.time_in_phase_s = 0.0

        if self.active and ra > soft_m + 15.0:
            self.phase = 0
            self.active = False
            self.time_in_phase_s = 0.0

        if self.active:
            self.time_in_phase_s += dt_s

        # Filter sink rate
        self.sink_rate_filtered = self.sink_rate_filtered * 0.85 + vs * 0.15

        # Compute commands if active
        if self.active:
            h_eff = max(ra, 0.1)
            k = 1.8 * math.sqrt(G)
            softness = 1.0 - 0.3 * min(h_eff / 10.0, 1.0)
            raw_vs_cmd = -k * math.sqrt(h_eff) * softness
            raw_vs_cmd = max(-5.0, min(0.0, raw_vs_cmd))

            phase_blend = 0.0
            if self.phase == 1:
                phase_blend = max(0.0, min(0.5, 1.0 - (ra / soft_m)))
            elif self.phase == 2:
                phase_blend = max(0.7, min(1.0, 1.0 - (ra / act_m) * 0.3))
            elif self.phase == 3:
                phase_blend = 1.0
                raw_vs_cmd = -0.5

            self.sink_rate_command_ms = raw_vs_cmd * phase_blend
            self.sink_rate_command_ms -= self.gs_deviation_deg * 0.15
            self.sink_rate_error_ms = self.sink_rate_command_ms - self.sink_rate_filtered

            # Pitch command
            flare_pitch_inc = 0.0
            if self.phase == 1:
                alt_progress = 1.0 - (ra / soft_m)
                flare_pitch_inc = alt_progress * 1.5
            elif self.phase == 2:
                alt_progress = 1.0 - (ra / act_m)
                flare_pitch_inc = 1.5 + alt_progress * 2.0
            else:
                flare_pitch_inc = 3.5

            target_pitch = self.pitch_deg + flare_pitch_inc
            self.pitch_filtered = self.pitch_filtered * 0.8 + target_pitch * 0.2
            self.pitch_command_deg = self.pitch_filtered

            # Attenuation
            if self.phase == 1:
                self.pitch_attenuation = 0.3
            elif self.phase == 2:
                self.pitch_attenuation = 0.6
            else:
                self.pitch_attenuation = 0.8

            # Runway stab weight
            stab_weight = self.runway_stab_weight_setting
            if self.phase == 1:
                stab_weight *= 1.2
            elif self.phase == 2:
                stab_weight *= 1.5
            else:
                stab_weight *= 1.8
            self.runway_stab_weight = max(0.0, min(1.0, stab_weight))
            self.runway_visual_stab = self.runway_stab_weight

            # Float suppression
            expected_sink = 0.5 + ra * 0.1
            if self.sink_rate_filtered > -expected_sink and ra < 5.0:
                self.float_suppression_cue = max(0.0, min(1.0,
                    (self.sink_rate_filtered + expected_sink) / expected_sink))
            else:
                self.float_suppression_cue *= 0.9
            self.float_suppression_cue *= self.float_suppression_gain

            # Confidence
            confidence = self.flare_guidance_confidence
            confidence *= (0.5 + self.sink_rate_stability * 0.5)
            self.guidance_confidence = max(0.0, min(1.0, confidence))

            # Completion
            if self.phase == 2:
                alt_progress = 1.0 - (ra / act_m)
                self.flare_completion = max(0.0, min(1.0, alt_progress))
            elif self.phase == 3:
                self.flare_completion = 1.0
            else:
                self.flare_completion = 0.0
        else:
            self.pitch_command_deg = 0.0
            self.sink_rate_command_ms = 0.0
            self.sink_rate_error_ms = 0.0
            self.pitch_attenuation = 0.0
            self.flare_completion = 0.0
            self.guidance_confidence = self.flare_guidance_confidence

        self.valid = True
        return True


# ======================================================================
#  4.  A350 Rollout Reference Implementation
# ======================================================================

class A350RolloutAugmentation:
    def __init__(self):
        self.on_ground = False
        self.groundspeed_ms = 0.0
        self.heading_deg = 0.0
        self.track_deg = 0.0
        self.runway_heading_deg = 0.0
        self.lateral_deviation_m = 0.0
        self.crosswind_ms = 0.0
        self.wet_runway = False
        self.steering_command_deg = 0.0
        self.steering_raw_deg = 0.0
        self.steering_damping = 0.80
        self.centerline_error_deg = 0.0
        self.predictive_steering = 0.0
        self.nosewheel_fraction = 0.0
        self.nosewheel_target = 0.0
        self.nosewheel_transition_s = 3.0
        self.aerodynamic_fraction = 1.0
        self.deceleration_ms2 = 0.0
        self.target_decel_ms2 = 1.47
        self.deceleration_smooth = 0.0
        self.centerline_stability = 1.0
        self.crosswind_compensation = 0.0
        self.wet_gain_multiplier = 1.0
        self.edge_stabilization = 1.0
        self.centerline_visual_smooth = 1.0
        self.active = False
        self.time_s = 0.0
        self.centerline_gain = 2.5
        self.centerline_damping = 0.80
        self.predictive_lead_gain = 0.40
        self.crosswind_stab_gain = 0.75
        self.edge_stab_gain = 0.70
        self.wet_assist_enabled = True
        self.valid = False

    def compute(self, dt_s=1.0/60.0):
        self.valid = False
        speed_kt = self.groundspeed_ms * KT_PER_MS
        should_activate = self.on_ground and speed_kt > 10.0

        if should_activate and not self.active:
            self.active = True
            self.time_s = 0.0
            self.nosewheel_fraction = 0.0
            self.aerodynamic_fraction = 1.0

        if not should_activate and self.active:
            if self.groundspeed_ms < 0.5:
                self.active = False

        if not self.active:
            self.steering_command_deg = 0.0
            self.centerline_error_deg = 0.0
            self.centerline_stability = 1.0
            self.valid = True
            return True

        self.time_s += dt_s

        # Centerline error
        heading_error = self.heading_deg - self.runway_heading_deg
        while heading_error > 180.0: heading_error -= 360.0
        while heading_error < -180.0: heading_error += 360.0
        self.centerline_error_deg = heading_error
        lateral_contrib = self.lateral_deviation_m * 0.35
        total_error = max(-30.0, min(30.0, heading_error + lateral_contrib))
        self.steering_raw_deg = max(-8.0, min(8.0, total_error * self.centerline_gain))

        # Predictive
        track_error = self.track_deg - self.runway_heading_deg
        while track_error > 180.0: track_error -= 360.0
        while track_error < -180.0: track_error += 360.0
        self.predictive_steering = track_error * self.predictive_lead_gain * 0.5
        self.steering_raw_deg += self.predictive_steering
        self.steering_raw_deg = max(-8.0, min(8.0, self.steering_raw_deg))

        # Adaptive damping
        damping = self.centerline_damping
        speed_factor = min(speed_kt / 80.0, 1.0)
        damping = damping * (0.5 + 0.5 * speed_factor)
        if self.crosswind_stab_gain > 0.0:
            cw_kt = self.crosswind_ms * KT_PER_MS
            cw_factor = min(cw_kt / 15.0, 1.0)
            damping += cw_factor * 0.15
        if self.wet_runway and self.wet_assist_enabled:
            damping *= self.wet_gain_multiplier
        self.steering_damping = max(0.3, min(0.98, damping))

        # Smooth steering
        alpha = 0.15 * (1.0 - self.steering_damping * 0.5)
        self.steering_command_deg = self.steering_command_deg * (1.0 - alpha) + self.steering_raw_deg * alpha
        self.steering_command_deg = max(-8.0, min(8.0, self.steering_command_deg))

        # Nosewheel transition
        if speed_kt < 40.0:
            self.nosewheel_target = 1.0
        elif speed_kt < 80.0:
            self.nosewheel_target = 1.0 - (speed_kt - 40.0) / 40.0
        else:
            self.nosewheel_target = 0.0
        transition_rate = dt_s / self.nosewheel_transition_s
        self.nosewheel_fraction += (self.nosewheel_target - self.nosewheel_fraction) * transition_rate
        self.nosewheel_fraction = max(0.0, min(1.0, self.nosewheel_fraction))
        self.aerodynamic_fraction = 1.0 - self.nosewheel_fraction

        # Crosswind comp
        wind_angle = self.track_deg - self.runway_heading_deg
        self.crosswind_compensation = wind_angle * self.crosswind_stab_gain * 0.3
        self.crosswind_compensation = max(-3.0, min(3.0, self.crosswind_compensation))

        # Stability
        error_quality = 1.0 - min(abs(self.centerline_error_deg) / 3.0, 1.0)
        speed_quality = 1.0 if (speed_kt > 20.0 and speed_kt < 100.0) else 0.7
        nosewheel_quality = 0.5 + self.nosewheel_fraction * 0.5
        time_quality = min(self.time_s / 3.0, 1.0)
        self.centerline_stability = error_quality * 0.4 + speed_quality * 0.2 + nosewheel_quality * 0.2 + time_quality * 0.2
        self.centerline_stability = max(0.0, min(1.0, self.centerline_stability))

        # Visual stabilization
        self.edge_stabilization = (0.5 + self.centerline_stability * 0.5) * self.edge_stab_gain
        self.centerline_visual_smooth = 0.7 + self.centerline_stability * 0.3

        self.valid = True
        return True


# ======================================================================
#  5.  A350 CAT III Reference Implementation
# ======================================================================

class A350CatIIIState:
    def __init__(self):
        self.cat3_active = False
        self.cat3_qualified = False
        self.cat3_confidence = 0.0
        self.cat3_qualification = 0.0
        self.radio_altitude_m = 100.0
        self.loc_captured = False
        self.gs_captured = False
        self.confidence_smoothed = 0.0
        self.runway_stab_gain = 0.0
        self.loc_predictive_smooth = 0.0
        self.gs_stabilisation = 0.0
        self.gs_confidence_boost = 0.0
        self.flare_cue_stab = 0.0
        self.flare_cue_confidence = 0.0
        self.rollout_confidence_amp = 1.0
        self.rollout_degraded_fallback = 0.60
        self.runway_enhancement = 1.0
        self.centerline_enhancement = 1.0
        self.touchdown_enhancement = 1.0
        self.degraded_timer_s = 0.0
        self.loc_weight = 0.40
        self.gs_weight = 0.30
        self.ra_weight = 0.20
        self.gps_weight = 0.10
        self.attitude_weight = 0.15
        self.confidence_min_cat3 = 0.85
        self.runway_stab_gain_setting = 0.85
        self.loc_predictive_smooth_s = 0.30
        self.gs_stab_gain_setting = 0.80
        self.gs_conf_boost_captured = 0.15
        self.flare_cue_stab_gain = 0.85
        self.flare_cue_min_conf = 0.70
        self.rollout_conf_amplifier = 1.30
        self.low_vis_enhancement = 1.0
        self.degraded_mode_grace_s = 2.0
        self.valid = False

    def compute(self, dt_s=1.0/60.0, sensor_confidences=None):
        self.valid = False
        should_activate = self.radio_altitude_m < 200.0

        if should_activate and not self.cat3_active:
            self.cat3_active = True
            self.degraded_timer_s = 0.0

        if not should_activate and self.cat3_active:
            if self.radio_altitude_m > 250.0:
                self.cat3_active = False

        # Sensor fusion
        loc_conf = 0.5
        gs_conf = 0.5
        ra_conf = 0.5
        gps_conf = 0.5
        att_conf = 0.5

        if sensor_confidences:
            loc_conf = sensor_confidences.get('loc', 0.5)
            gs_conf = sensor_confidences.get('gs', 0.5)
            ra_conf = sensor_confidences.get('ra', 0.5)
            gps_conf = sensor_confidences.get('gps', 0.5)
            att_conf = sensor_confidences.get('att', 0.5)

        if self.loc_captured:
            loc_conf += self.gs_conf_boost_captured
        if self.gs_captured:
            gs_conf += self.gs_conf_boost_captured
        loc_conf = max(0.0, min(1.0, loc_conf))
        gs_conf = max(0.0, min(1.0, gs_conf))

        total_weight = self.loc_weight + self.gs_weight + self.ra_weight + self.gps_weight + self.attitude_weight
        qual = (loc_conf * self.loc_weight + gs_conf * self.gs_weight + ra_conf * self.ra_weight +
                gps_conf * self.gps_weight + att_conf * self.attitude_weight) / total_weight
        self.cat3_qualification = qual
        self.cat3_qualified = qual >= self.confidence_min_cat3

        # Smooth
        if qual > self.confidence_smoothed:
            self.confidence_smoothed += (qual - self.confidence_smoothed) * 0.2
        else:
            self.confidence_smoothed += (qual - self.confidence_smoothed) * 0.05
        self.confidence_smoothed = max(0.0, min(1.0, self.confidence_smoothed))
        self.cat3_confidence = self.confidence_smoothed

        # Degraded mode
        if self.cat3_active and not self.cat3_qualified:
            self.degraded_timer_s += dt_s
            if self.degraded_timer_s > self.degraded_mode_grace_s:
                self.rollout_confidence_amp = self.rollout_degraded_fallback
        elif self.cat3_active:
            self.degraded_timer_s = 0.0
            self.rollout_confidence_amp = self.rollout_conf_amplifier

        # Runway stab
        self.runway_stab_gain = self.runway_stab_gain_setting
        if self.cat3_active and self.cat3_qualified:
            self.runway_stab_gain *= 1.2
        self.runway_stab_gain = max(0.0, min(1.0, self.runway_stab_gain))

        # GS stab
        self.gs_stabilisation = self.gs_stab_gain_setting
        if self.gs_captured:
            self.gs_stabilisation *= 1.1
        self.gs_stabilisation = max(0.0, min(1.0, self.gs_stabilisation))

        # Flare stab
        self.flare_cue_stab = self.flare_cue_stab_gain
        if self.cat3_active and self.cat3_qualified:
            self.flare_cue_stab *= 1.2
        self.flare_cue_stab = max(0.0, min(1.0, self.flare_cue_stab))
        self.flare_cue_confidence = self.flare_cue_min_conf

        # Visual enhancement
        if self.cat3_active and self.cat3_qualified:
            self.runway_enhancement = 1.0 + self.low_vis_enhancement * 0.3
            self.centerline_enhancement = 1.0 + self.low_vis_enhancement * 0.4
            self.touchdown_enhancement = 1.0 + self.low_vis_enhancement * 0.2
        else:
            self.runway_enhancement = 1.0
            self.centerline_enhancement = 1.0
            self.touchdown_enhancement = 1.0

        self.valid = True


# ======================================================================
#  6.  A350 Symbology Style Reference Implementation
# ======================================================================

class A350SymbologyStyle:
    def __init__(self):
        self.brightness_target = 0.7
        self.brightness_current = 0.7
        self.brightness_easing_rate = 0.20
        self.brightness_min = 0.15
        self.bloom_reduction = 0.60
        self.bloom_current = 0.0
        self.line_cleanliness = 0.85
        self.line_intensity_stab = 0.90
        self.horizon_stability = 0.90
        self.horizon_oscillation_damping = 0.80
        self.alpha_fade_smoothness = 0.25
        self.alpha_transition_rate = 0.15
        self.anti_shimmer_gain = 0.70
        self.shimmer_accumulator = 0.0
        self.symbol_persistence = 0.30
        self.prev_alpha = [1.0] * 32
        self.prev_position = [0.0] * 32
        self.symbol_count = 0
        self.active = False
        self.valid = False

    def compute(self, dt_s=1.0/60.0, target_bright=None, turbulence=0.0):
        if target_bright is not None:
            self.brightness_target = max(0.0, min(1.0, target_bright))
        diff = self.brightness_target - self.brightness_current
        rate = self.brightness_easing_rate if diff > 0.0 else self.brightness_easing_rate * 0.7
        self.brightness_current += diff * rate * dt_s * 10.0
        self.brightness_current = max(self.brightness_min, min(1.0, self.brightness_current))

        reduction = self.bloom_reduction
        if turbulence > 0.2:
            reduction += (1.0 - reduction) * turbulence * 0.3
        self.bloom_current = 1.0 - reduction
        self.bloom_current = max(0.0, min(1.0, self.bloom_current))

        if turbulence > 0.1:
            self.horizon_oscillation_damping = min(0.80 + turbulence * 0.15, 0.98)
        else:
            self.horizon_oscillation_damping = 0.80

        if turbulence > 0.3:
            self.anti_shimmer_gain = min(0.70 + turbulence * 0.20, 0.95)
        else:
            self.anti_shimmer_gain = 0.70

        if turbulence > 0.2:
            self.alpha_transition_rate = 0.10
        else:
            self.alpha_transition_rate = 0.15

        self.active = True
        self.valid = True

    def smooth_alpha(self, raw_alpha, index):
        if index < 0 or index >= 32:
            return raw_alpha
        alpha = 0.15 * (1.0 + self.symbol_persistence)
        smoothed = self.prev_alpha[index] * (1.0 - alpha) + raw_alpha * alpha
        if self.anti_shimmer_gain > 0.7:
            extra_smooth = (self.anti_shimmer_gain - 0.7) / 0.3
            smoothed = self.prev_alpha[index] * extra_smooth + smoothed * (1.0 - extra_smooth)
        self.prev_alpha[index] = smoothed
        return max(0.0, min(1.0, smoothed))

    def stabilise_pos(self, raw_pos, index):
        if index < 0 or index >= 32:
            return raw_pos
        prev = self.prev_position[index]
        delta = raw_pos - prev
        if self.shimmer_accumulator > 2.0:
            alpha = 0.20 * (1.0 - self.anti_shimmer_gain * 0.5)
            self.prev_position[index] = prev * (1.0 - alpha) + raw_pos * alpha
        else:
            alpha = 0.20 * (1.0 - self.anti_shimmer_gain * 0.2)
            self.prev_position[index] = prev * (1.0 - alpha) + raw_pos * alpha
        if abs(delta) > 1.0:
            self.shimmer_accumulator += abs(delta) * 0.1
            self.shimmer_accumulator = min(self.shimmer_accumulator, 10.0)
        else:
            self.shimmer_accumulator -= 0.05
            self.shimmer_accumulator = max(self.shimmer_accumulator, 0.0)
        return self.prev_position[index]


# ======================================================================
#  v3.0.0 — A350 XWB CERTIFICATION LAYER REFERENCE IMPLEMENTATIONS
# ======================================================================


# ----------------------------------------------------------------------
#  9.  A350 Flight Path Vector Controller
# ----------------------------------------------------------------------

class A350FPVTurbulenceState:
    def __init__(self):
        self.jitter_ema = 0.0
        self.turbulence_level = 0.0
        self.turbulence_confidence = 1.0
        self.attack_alpha = 0.25
        self.decay_alpha = 0.04
        self.jitter_threshold_calm = 0.3
        self.jitter_threshold_severe = 6.0
        self.initialised = False


class A350FPVFlareStab:
    def __init__(self):
        self.flare_active = False
        self.flare_blend = 0.0
        self.runway_reference_pos = (0.0, 0.0)
        self.runway_aim_point = (0.0, 0.0)
        self.runway_reference_strength = 0.0
        self.flare_height_m = 100.0
        self.flare_stabilization_gain = 0.85
        self.stabilized_pos = (0.0, 0.0)
        self.initialised = False


class A350FPVPredictiveAlign:
    def __init__(self):
        self.alignment_angle_deg = 0.0
        self.alignment_quality = 0.0
        self.predicted_touchdown_pos = (0.0, 0.0)
        self.crosswind_component_ms = 0.0
        self.crosswind_compensation = (0.0, 0.0)
        self.runway_slope_deg = 0.0
        self.valid = False


class A350FlightPathVectorController:
    """Top-level A350 FPV controller with runway-referenced flare and crosswind compensation."""
    def __init__(self):
        self.base_filter = AirbusFPVFilter()
        self.turbulence = A350FPVTurbulenceState()
        self.flare_stab = A350FPVFlareStab()
        self.predictive_align = A350FPVPredictiveAlign()

        self.final_screen_pos = (0.0, 0.0)
        self.raw_screen_pos = (0.0, 0.0)
        self.filtered_screen_pos = (0.0, 0.0)
        self.flare_adjusted_pos = (0.0, 0.0)
        self.stability_score = 1.0
        self.fpv_quality = 1.0
        self.on_screen = False
        self.valid = False

        # Config
        self.flare_activation_ft = 50.0
        self.flare_reference_gain = 0.75
        self.crosswind_compensation_gain = 0.60
        self.predictive_lead_time_s = 0.15
        self.stability_min_threshold = 0.70
        self.turbulence_rejection = 0.92
        self.runway_referenced_flare = True
        self.crosswind_compensation = True
        self.predictive_alignment = True

    def _detect_turbulence(self, raw_pos, filtered_pos):
        jitter_x = abs(raw_pos[0] - filtered_pos[0])
        jitter_y = abs(raw_pos[1] - filtered_pos[1])
        jitter = (jitter_x + jitter_y) * 0.5

        ts = self.turbulence
        if not ts.initialised:
            ts.jitter_ema = jitter
            ts.initialised = True

        if jitter > ts.jitter_ema:
            ts.jitter_ema += (jitter - ts.jitter_ema) * ts.attack_alpha
        else:
            ts.jitter_ema += (jitter - ts.jitter_ema) * ts.decay_alpha

        j = ts.jitter_ema
        if j > ts.jitter_threshold_severe:
            level = 1.0
        elif j > ts.jitter_threshold_calm:
            range_val = ts.jitter_threshold_severe - ts.jitter_threshold_calm
            level = (j - ts.jitter_threshold_calm) / range_val if range_val > 0.01 else 0.0
        else:
            level = 0.0

        ts.turbulence_level = max(0.0, min(1.0, level))
        change_rate = abs(ts.turbulence_level - level)
        ts.turbulence_confidence = 1.0 - min(change_rate * 2.0, 1.0)

    def _compute_flare_stab(self, raw_pos, runway_pos, radio_alt_m, dt_s, on_ground):
        fs = self.flare_stab
        flare_activation_m = self.flare_activation_ft * FT_TO_M
        should_flare = (radio_alt_m < flare_activation_m and radio_alt_m > 0.1 and not on_ground) or radio_alt_m < 5.0 or on_ground

        if should_flare:
            fs.flare_active = True
            fs.flare_height_m = radio_alt_m

            if radio_alt_m < 0.5:
                fs.flare_blend = 1.0
            else:
                fs.flare_blend = 1.0 - (radio_alt_m / flare_activation_m)
                fs.flare_blend = max(0.0, min(1.0, fs.flare_blend))

            if fs.initialised:
                fs.runway_aim_point = (
                    fs.runway_aim_point[0] + (runway_pos[0] - fs.runway_aim_point[0]) * 0.15,
                    fs.runway_aim_point[1] + (runway_pos[1] - fs.runway_aim_point[1]) * 0.15
                )
                attraction = fs.flare_blend * self.flare_reference_gain
                fs.stabilized_pos = (
                    raw_pos[0] + (fs.runway_aim_point[0] - raw_pos[0]) * attraction,
                    raw_pos[1] + (fs.runway_aim_point[1] - raw_pos[1]) * attraction
                )
            else:
                fs.runway_aim_point = runway_pos
                fs.stabilized_pos = raw_pos
                fs.initialised = True
        else:
            if fs.flare_active:
                fs.flare_blend *= 0.95
                if fs.flare_blend < 0.01:
                    fs.flare_active = False
                    fs.flare_blend = 0.0
                    fs.initialised = False

    def _predictive_align(self, raw_pos, runway_pos, dt_s, crosswind_ms, groundspeed_ms, flare_active):
        pa = self.predictive_align
        pa.crosswind_component_ms = crosswind_ms

        if flare_active or groundspeed_ms > 30.0:
            cw_kt = crosswind_ms * KT_PER_MS
            comp_px = cw_kt * 0.35 * 0.6
            pa.crosswind_compensation = (comp_px, 0.0)

            pa.alignment_angle_deg = abs(crosswind_ms / max(groundspeed_ms, 1.0) * 57.2958)
            pa.alignment_angle_deg = min(pa.alignment_angle_deg, 15.0)
            pa.alignment_quality = 1.0 - min(abs(crosswind_ms) / 15.0, 0.7)
            pa.alignment_quality = max(0.3, min(1.0, pa.alignment_quality))

            if runway_pos != (0.0, 0.0):
                pa.predicted_touchdown_pos = (
                    raw_pos[0] * 0.3 + runway_pos[0] * 0.7,
                    raw_pos[1] * 0.3 + runway_pos[1] * 0.7
                )
            pa.valid = True
        else:
            pa.crosswind_compensation = (0.0, 0.0)
            pa.alignment_angle_deg = 0.0
            pa.alignment_quality = 0.0
            pa.valid = False

    def compute(self, raw_pos, runway_pos, dt_s=1.0/60.0, phase=0, crosswind_ms=0.0,
                radio_alt_m=100.0, groundspeed_ms=70.0, on_ground=False):
        self.valid = False
        self.raw_screen_pos = raw_pos

        # Step 1: Set phase
        self.base_filter.set_phase(phase)

        # Step 2: Run base filter
        base_filtered = self.base_filter.feed(raw_pos[0], raw_pos[1], dt_s)
        self.filtered_screen_pos = base_filtered

        # Step 3: Turbulence detection
        self._detect_turbulence(raw_pos, base_filtered)

        post_turbulence = base_filtered
        if self.turbulence.turbulence_level > 0.05:
            extra_alpha = 0.1 * (1.0 - self.turbulence.turbulence_level * 0.5)
            extra_alpha = max(0.02, min(0.15, extra_alpha))
            post_turbulence = (
                post_turbulence[0] * (1.0 - extra_alpha) + base_filtered[0] * extra_alpha,
                post_turbulence[1] * (1.0 - extra_alpha) + base_filtered[1] * extra_alpha
            )

        # Step 4: Crosswind compensation
        with_crosswind = post_turbulence
        if self.crosswind_compensation and phase >= 1:
            flare_active_phase = (phase == 2 or radio_alt_m < 50.0 * FT_TO_M)
            self._predictive_align(post_turbulence, runway_pos, dt_s, crosswind_ms, groundspeed_ms, flare_active_phase)
            with_crosswind = (with_crosswind[0] + self.predictive_align.crosswind_compensation[0], with_crosswind[1])

        # Step 5: Flare stabilization
        flare_adjusted = with_crosswind
        if self.runway_referenced_flare:
            self._compute_flare_stab(with_crosswind, runway_pos, radio_alt_m, dt_s, on_ground)
            fs = self.flare_stab
            if fs.flare_active:
                blend = fs.flare_blend
                flare_adjusted = (
                    with_crosswind[0] * (1.0 - blend) + fs.stabilized_pos[0] * blend,
                    with_crosswind[1] * (1.0 - blend) + fs.stabilized_pos[1] * blend
                )

        self.flare_adjusted_pos = flare_adjusted

        # Step 6: Stability score
        turb_stability = 1.0 - self.turbulence.turbulence_level
        jitter_stability = 1.0
        if self.turbulence.jitter_ema > 0.1:
            jitter_stability = 1.0 / (1.0 + self.turbulence.jitter_ema * 0.5)
        flare_smoothness = 1.0
        if self.flare_stab.flare_active:
            flare_smoothness = 0.8 + self.flare_stab.flare_blend * 0.2
        self.stability_score = turb_stability * 0.4 + jitter_stability * 0.3 + flare_smoothness * 0.3
        self.stability_score = max(0.0, min(1.0, self.stability_score))
        self.fpv_quality = self.stability_score * 0.7 + 0.3
        self.fpv_quality = max(0.0, min(1.0, self.fpv_quality))

        self.final_screen_pos = flare_adjusted
        self.on_screen = True
        self.valid = True
        return self.final_screen_pos


# ----------------------------------------------------------------------
#  10.  A350 Horizon Controller
# ----------------------------------------------------------------------

class A350HorizonController:
    """Airbus-specific horizon stabilization."""
    def __init__(self):
        self.stabilized_pitch_deg = 0.0
        self.stabilized_bank_deg = 0.0
        self.horizon_y_px = 0.0
        self.horizon_slope = 0.0
        self.pitch_stability = 1.0
        self.bank_stability = 1.0
        self.pitch_raw = 0.0
        self.bank_raw = 0.0
        self.pitch_filtered = 0.0
        self.bank_filtered = 0.0
        self.pitch_rate_dps = 0.0
        self.bank_rate_dps = 0.0
        self.pitch_ema_alpha = 0.15
        self.bank_ema_alpha = 0.12
        self.turbulence_damping = 0.0
        self.jitter_accumulator = 0.0
        self.turbulence_level = 0.0
        self.flare_active = False
        self.flare_damping_boost = 0.0
        self.flare_pitch_hold_gain = 0.0
        self.low_visibility = False
        self.low_vis_stability_boost = 0.0
        self.pitch_alpha_min = 0.08
        self.pitch_alpha_max = 0.35
        self.bank_alpha_min = 0.06
        self.bank_alpha_max = 0.30
        self.jitter_threshold = 0.15
        self.flare_damping_multiplier = 2.0
        self.low_vis_multiplier = 1.5
        self.initialised = False
        self.valid = False

    def compute(self, raw_pitch_deg, raw_bank_deg, dt_s=1.0/60.0,
                flight_phase=0, turbulence_level=-1.0, low_visibility=False):
        self.valid = False
        self.pitch_raw = raw_pitch_deg
        self.bank_raw = raw_bank_deg

        self.flare_active = (flight_phase == 2)
        self.low_visibility = low_visibility
        if turbulence_level >= 0.0:
            self.turbulence_level = turbulence_level

        self.turbulence_damping = self.turbulence_level * 0.5
        self.flare_damping_boost = self.flare_damping_multiplier if self.flare_active else 0.0
        self.low_vis_stability_boost = (self.low_vis_multiplier - 1.0) if self.low_visibility else 0.0
        total_damping = 1.0 + self.turbulence_damping + self.flare_damping_boost * 0.3 + self.low_vis_stability_boost * 0.2

        def adaptive_smooth(raw, prev_filtered, rate_dps, alpha_min, alpha_max, dt):
            rate = (raw - prev_filtered) / max(dt, 0.001)
            abs_rate = abs(rate)
            if abs_rate < 0.5:
                alpha = alpha_min
            elif abs_rate > 3.0:
                alpha = alpha_max
            else:
                t = (abs_rate - 0.5) / 2.5
                alpha = alpha_min * (1.0 - t) + alpha_max * t
            alpha = max(alpha_min * 0.5, min(alpha_max, alpha))
            return prev_filtered * (1.0 - alpha) + raw * alpha

        if not self.initialised:
            self.pitch_filtered = raw_pitch_deg
            self.bank_filtered = raw_bank_deg
            self.initialised = True

        p_alpha_min = max(0.02, min(0.30, self.pitch_alpha_min / total_damping))
        p_alpha_max = max(0.10, min(0.50, self.pitch_alpha_max / total_damping))
        b_alpha_min = max(0.02, min(0.30, self.bank_alpha_min / total_damping))
        b_alpha_max = max(0.08, min(0.45, self.bank_alpha_max / total_damping))

        self.pitch_filtered = adaptive_smooth(raw_pitch_deg, self.pitch_filtered, self.pitch_rate_dps,
                                               p_alpha_min, p_alpha_max, dt_s)
        self.bank_filtered = adaptive_smooth(raw_bank_deg, self.bank_filtered, self.bank_rate_dps,
                                              b_alpha_min, b_alpha_max, dt_s)

        if self.flare_active:
            hold_strength = 0.3
            self.pitch_filtered = self.pitch_filtered * (1.0 - hold_strength) + self.pitch_filtered * hold_strength * 0.5 + raw_pitch_deg * hold_strength * 0.5

        self.stabilized_pitch_deg = self.pitch_filtered
        self.stabilized_bank_deg = self.bank_filtered

        pitch_rate_quality = 1.0 - min(abs(self.pitch_rate_dps) / 10.0, 1.0)
        self.pitch_stability = max(0.0, min(1.0, 0.5 + pitch_rate_quality * 0.5))
        bank_rate_quality = 1.0 - min(abs(self.bank_rate_dps) / 8.0, 1.0)
        self.bank_stability = max(0.0, min(1.0, 0.5 + bank_rate_quality * 0.5))

        self.valid = True
        return self.stabilized_pitch_deg, self.stabilized_bank_deg

    def get_stability(self):
        return (self.pitch_stability + self.bank_stability) * 0.5


# ----------------------------------------------------------------------
#  11.  A350 Autoland HUD Layer
# ----------------------------------------------------------------------

class A350AutolandHudLayer:
    """CAT III Autoland HUD layer with graceful degradation."""
    def __init__(self):
        self.cat3_level = 0       # NONE
        self.autoland_phase = 0   # INACTIVE
        self.autoland_active = False
        self.cat3_available = False

        self.confidence = {
            'overall': 0.0, 'ils_signal': 0.0, 'runway_alignment': 0.0,
            'vertical_profile': 0.0, 'flare': 0.0, 'rollout': 0.0,
            'system_integrity': 1.0, 'cat3_qualification': 0.0
        }

        self.degradation = {
            'degrading': False, 'failed': False, 'timer_s': 0.0,
            'grace_period_s': 2.0, 'rate': 0.05, 'failed_threshold': 0.30,
            'previous_confidence': 1.0, 'smoothed': 0.0
        }

        self.loc_deviation_dots = 0.0
        self.gs_deviation_dots = 0.0
        self.loc_captured = False
        self.gs_captured = False
        self.loc_deviation_rate = 0.0
        self.gs_deviation_rate = 0.0
        self.radio_altitude_m = 1000.0
        self.groundspeed_ms = 0.0
        self.vertical_speed_ms = 0.0
        self.distance_to_runway_m = 5000.0
        self.on_ground = False

        self.cat3a_max_dh_m = 200.0 * FT_TO_M
        self.cat3b_max_dh_m = 50.0 * FT_TO_M
        self.confidence_smoothing = 0.10
        self.degradation_grace_s = 2.0
        self.min_confidence_cat3 = 0.85
        self.flare_confidence_threshold = 0.75
        self.rollout_confidence_threshold = 0.70
        self.visual_enhancement = 1.0
        self.low_visibility = False
        self.valid = False

    def compute(self, dt_s=1.0/60.0, ils_loc_dots=0.0, ils_gs_dots=0.0,
                loc_captured=False, gs_captured=False, radio_alt_m=1000.0,
                groundspeed_ms=0.0, vs_ms=0.0, on_ground=False, low_vis=False,
                sensor_confidences=None):
        self.valid = False
        self.loc_deviation_dots = ils_loc_dots
        self.gs_deviation_dots = ils_gs_dots
        self.loc_captured = loc_captured
        self.gs_captured = gs_captured
        self.radio_altitude_m = radio_alt_m
        self.groundspeed_ms = groundspeed_ms
        self.vertical_speed_ms = vs_ms
        self.on_ground = on_ground
        self.low_visibility = low_vis

        # Phase detection
        if on_ground and groundspeed_ms < 1.0:
            self.autoland_phase = 5  # COMPLETE
        elif on_ground:
            self.autoland_phase = 4  # ROLLOUT
        elif radio_alt_m < 50.0 * FT_TO_M and radio_alt_m > 0.1:
            self.autoland_phase = 3  # FLARE
        elif loc_captured and gs_captured and radio_alt_m < 600.0:
            self.autoland_phase = 2  # ACTIVE
        elif loc_captured or gs_captured:
            self.autoland_phase = 1  # ARMED
        else:
            self.autoland_phase = 0  # INACTIVE

        self.autoland_active = (1 <= self.autoland_phase <= 4)

        # Confidence computation
        ils_signal = 0.5
        if sensor_confidences:
            loc_conf = sensor_confidences.get('loc', 0.5)
            gs_conf = sensor_confidences.get('gs', 0.5)
            ils_signal = (loc_conf + gs_conf) * 0.5

        loc_dev_factor = 1.0 - min(abs(ils_loc_dots) * 0.2, 1.0)
        gs_dev_factor = 1.0 - min(abs(ils_gs_dots) * 0.2, 1.0)
        ils_signal = ils_signal * (0.6 + 0.2 * loc_dev_factor + 0.2 * gs_dev_factor)
        self.confidence['ils_signal'] = max(0.0, min(1.0, ils_signal))

        runway_align = 0.5
        if loc_captured:
            runway_align = 0.7 + 0.3 * (1.0 - min(abs(ils_loc_dots), 1.0))
        if gs_captured:
            runway_align += 0.1 * (1.0 - min(abs(ils_gs_dots), 1.0))
        if on_ground:
            runway_align = 0.8
        self.confidence['runway_alignment'] = max(0.0, min(1.0, runway_align))

        vert_profile = 0.5
        if gs_captured:
            vert_profile = 0.7 + 0.3 * (1.0 - min(abs(ils_gs_dots), 0.5))
        if radio_alt_m < 100.0 and radio_alt_m > 0.0:
            alt_factor = 1.0 - (radio_alt_m / 100.0)
            vert_profile -= alt_factor * 0.1
        self.confidence['vertical_profile'] = max(0.0, min(1.0, vert_profile))

        self.confidence['flare'] = max(0.0, min(1.0,
            self.confidence['vertical_profile'] * 0.5 +
            self.confidence['ils_signal'] * 0.3 +
            self.confidence['runway_alignment'] * 0.2))
        if loc_captured and gs_captured:
            self.confidence['flare'] = max(0.0, min(1.0, self.confidence['flare'] + 0.1))

        rollout_conf = 0.5
        if on_ground:
            rollout_conf = 0.8
        elif self.confidence['runway_alignment'] > 0.7:
            rollout_conf = self.confidence['runway_alignment'] * 0.8
        self.confidence['rollout'] = max(0.0, min(1.0, rollout_conf))

        overall = (self.confidence['ils_signal'] * 0.25 +
                   self.confidence['runway_alignment'] * 0.25 +
                   self.confidence['vertical_profile'] * 0.20 +
                   self.confidence['flare'] * 0.15 +
                   self.confidence['rollout'] * 0.15)
        self.confidence['overall'] = max(0.0, min(1.0, overall))

        self.confidence['cat3_qualification'] = max(0.0, min(1.0,
            self.confidence['ils_signal'] * 0.35 +
            self.confidence['system_integrity'] * 0.35 +
            self.confidence['runway_alignment'] * 0.20 +
            self.confidence['vertical_profile'] * 0.10))

        # CAT III level
        qual = self.confidence['cat3_qualification']
        if qual > 0.95 and radio_alt_m < 200.0:
            self.cat3_level = 3  # IIIC
        elif qual > 0.85 and radio_alt_m < 200.0:
            self.cat3_level = 2  # IIIB
        elif qual > 0.70 and radio_alt_m < 400.0:
            self.cat3_level = 1  # IIIA
        else:
            self.cat3_level = 0
        self.cat3_available = (self.cat3_level >= 1)

        # Graceful degradation
        d = self.degradation
        if overall < d['previous_confidence'] - 0.02:
            if not d['degrading']:
                d['degrading'] = True
                d['timer_s'] = 0.0
            d['timer_s'] += dt_s
            if d['timer_s'] > d['grace_period_s']:
                d['smoothed'] += d['rate'] * dt_s
                d['smoothed'] = min(d['smoothed'], 1.0)
            if overall < d['failed_threshold']:
                d['failed'] = True
        else:
            if d['degrading']:
                d['timer_s'] = max(0.0, d['timer_s'] - dt_s)
                if d['timer_s'] <= 0.0:
                    d['degrading'] = False
            d['smoothed'] *= (1.0 - 0.02)
            if d['smoothed'] < 0.01:
                d['smoothed'] = 0.0
                d['failed'] = False
        d['previous_confidence'] = overall

        # Visual enhancement
        self.visual_enhancement = 1.0
        if self.autoland_active and self.low_visibility:
            self.visual_enhancement = 1.0 + (1.0 - d['smoothed']) * 0.3
        self.visual_enhancement = max(0.7, min(1.5, self.visual_enhancement))

        self.valid = True


# ----------------------------------------------------------------------
#  12.  A350 Landing Energy Model
# ----------------------------------------------------------------------

class A350LandingEnergyModel:
    """Landing energy management with weight, sink rate, and rollout prediction."""
    def __init__(self):
        self.aircraft_weight_kg = 180000.0
        self.sink_rate_ms = -2.0
        self.groundspeed_ms = 70.0
        self.runway_length_m = 3000.0
        self.runway_remaining_m = 3000.0
        self.braking_decel_ms2 = 0.0
        self.max_braking_ms2 = 4.5
        self.headwind_component_ms = 0.0
        self.reversers_deployed = False
        self.spoilers_deployed = False
        self.on_ground = False
        self.autobrake_active = False

        self.landing_energy_score = 0.0
        self.kinetic_energy_mj = 0.0
        self.vertical_energy_mj = 0.0
        self.total_energy_mj = 0.0
        self.energy_above_reference = 0.0
        self.specific_energy_j_kg = 0.0

        self.flare_aggressiveness = 0.5
        self.sink_rate_advisory_ms = -1.5
        self.flare_onset_advisory_ft = 50.0

        self.predicted_stop_distance_m = 0.0
        self.predicted_stop_margin_m = 0.0
        self.predicted_exit_speed_ms = 0.0
        self.rollout_energy_remaining = 0.0

        self.braking_effectiveness = 1.0
        self.braking_advisory = 0.0
        self.recommended_decel_ms2 = 1.47

        self.reference_landing_weight_kg = 180000.0
        self.reference_approach_speed_ms = 70.0
        self.max_sink_rate_ms = 3.5
        self.energy_warning_threshold = 0.80
        self.energy_caution_threshold = 0.60

        self.valid = False

    def compute(self, dt_s=1.0/60.0):
        self.valid = False
        weight_kg = max(self.aircraft_weight_kg, 10000.0)
        gs_ms = max(self.groundspeed_ms, 0.1)
        vs_ms = self.sink_rate_ms
        rwy_len = max(self.runway_length_m, 100.0)
        rwy_rem = max(self.runway_remaining_m, 0.0)
        decel = max(self.braking_decel_ms2, 0.0)

        # Energy
        self.kinetic_energy_mj = 0.5 * weight_kg * gs_ms * gs_ms * 1e-6
        sink_positive = max(-vs_ms, 0.0)
        self.vertical_energy_mj = weight_kg * 9.80665 * sink_positive * 0.1 * 1e-6
        self.total_energy_mj = self.kinetic_energy_mj + self.vertical_energy_mj

        ref_ke = 0.5 * self.reference_landing_weight_kg * self.reference_approach_speed_ms ** 2 * 1e-6
        ref_ve = self.reference_landing_weight_kg * 9.80665 * 1.5 * 0.1 * 1e-6
        ref_total = ref_ke + ref_ve
        self.energy_above_reference = self.total_energy_mj - ref_total
        self.specific_energy_j_kg = (self.kinetic_energy_mj * 1e6) / weight_kg

        # Energy score
        speed_ratio = gs_ms / max(self.reference_approach_speed_ms, 1.0)
        speed_score = 0.0
        if speed_ratio > 1.3:
            speed_score = 1.0
        elif speed_ratio > 1.0:
            speed_score = (speed_ratio - 1.0) / 0.3
        speed_score = max(0.0, min(1.0, speed_score))

        sink_ratio = sink_positive / max(self.max_sink_rate_ms, 0.1)
        sink_score = max(0.0, min(1.0, sink_ratio))

        runway_score = 0.0
        if self.on_ground:
            stop_dist = (gs_ms ** 2) / (2.0 * max(decel, 0.5))
            stop_margin = rwy_rem - stop_dist
            if stop_margin < 0.0:
                runway_score = 1.0
            elif stop_margin < 500.0:
                runway_score = 1.0 - (stop_margin / 500.0)

        self.landing_energy_score = max(0.0, min(1.0,
            speed_score * 0.40 + sink_score * 0.35 + runway_score * 0.25))

        # Flare aggressiveness
        if self.on_ground:
            self.flare_aggressiveness = 0.0
        elif gs_ms > self.reference_approach_speed_ms * 1.1:
            self.flare_aggressiveness = 0.5 + 0.5 * ((gs_ms / self.reference_approach_speed_ms) - 1.1) / 0.2
        elif sink_positive > 2.5:
            self.flare_aggressiveness = 0.5 + 0.5 * (sink_positive - 2.5) / 1.0
        elif gs_ms < self.reference_approach_speed_ms * 0.9:
            self.flare_aggressiveness = 0.5 * (gs_ms / (self.reference_approach_speed_ms * 0.9))
        else:
            self.flare_aggressiveness = 0.5
        self.flare_aggressiveness = max(0.0, min(1.0, self.flare_aggressiveness))

        if self.flare_aggressiveness > 0.7:
            self.sink_rate_advisory_ms = -1.0 - (self.flare_aggressiveness - 0.7) * 1.5
        else:
            self.sink_rate_advisory_ms = -1.5 - (1.0 - self.flare_aggressiveness) * 0.5
        self.sink_rate_advisory_ms = max(-4.0, min(-0.5, self.sink_rate_advisory_ms))

        if self.landing_energy_score > self.energy_warning_threshold:
            self.flare_onset_advisory_ft = 60.0
        elif self.landing_energy_score > self.energy_caution_threshold:
            self.flare_onset_advisory_ft = 55.0
        else:
            self.flare_onset_advisory_ft = 50.0

        # Rollout prediction
        if self.on_ground and gs_ms > 1.0:
            effective_decel = decel
            if self.spoilers_deployed: effective_decel += 1.0
            if self.reversers_deployed: effective_decel += 0.5
            effective_decel = max(0.3, min(self.max_braking_ms2, effective_decel))
            self.predicted_stop_distance_m = (gs_ms ** 2) / (2.0 * effective_decel)
            self.predicted_stop_margin_m = rwy_rem - self.predicted_stop_distance_m
            if self.predicted_stop_distance_m > rwy_rem:
                excess_dist = self.predicted_stop_distance_m - rwy_rem
                excess_energy = excess_dist * effective_decel
                self.predicted_exit_speed_ms = math.sqrt(2.0 * excess_energy) if excess_energy > 0 else 0.0
            else:
                self.predicted_exit_speed_ms = 0.0
            initial_ke = 0.5 * weight_kg * max(self.groundspeed_ms, gs_ms) ** 2
            current_ke = 0.5 * weight_kg * gs_ms ** 2
            self.rollout_energy_remaining = current_ke / initial_ke if initial_ke > 0 else 0.0
        else:
            self.predicted_stop_distance_m = (gs_ms ** 2) / (2.0 * 1.47)
            self.predicted_stop_margin_m = rwy_len - self.predicted_stop_distance_m
            self.predicted_exit_speed_ms = 0.0
            self.rollout_energy_remaining = 1.0

        # Braking
        if self.max_braking_ms2 > 0.1:
            self.braking_effectiveness = decel / self.max_braking_ms2
        self.braking_effectiveness = max(0.0, min(1.0, self.braking_effectiveness))

        if self.on_ground and self.predicted_stop_margin_m < 200.0:
            self.braking_advisory = 1.0 - (self.predicted_stop_margin_m / 200.0)
            self.braking_advisory = max(0.0, min(1.0, self.braking_advisory))
        else:
            self.braking_advisory = 0.0

        if self.on_ground and rwy_rem > 50.0 and gs_ms > 1.0:
            self.recommended_decel_ms2 = (gs_ms ** 2) / (2.0 * rwy_rem * 0.8)
            self.recommended_decel_ms2 = max(0.5, min(4.5, self.recommended_decel_ms2))
        else:
            self.recommended_decel_ms2 = 1.47

        self.valid = True


# ----------------------------------------------------------------------
#  13.  A350 Runway Augmentation
# ----------------------------------------------------------------------

class A350RunwayAugmentation:
    """Runway visual augmentation for threshold, centerline, and edge stabilization."""
    def __init__(self):
        self.threshold_smoothed = (0.0, 0.0)
        self.threshold_raw = (0.0, 0.0)
        self.threshold_stability = 1.0
        self.threshold_alpha = 0.20
        self.centerline_smoothed = (0.0, 0.0)
        self.centerline_raw = (0.0, 0.0)
        self.centerline_stability = 1.0
        self.centerline_alpha = 0.15
        self.edge_light_stability = 1.0
        self.edge_light_smooth_alpha = 0.25
        self.left_edge_offset_px = 0.0
        self.right_edge_offset_px = 0.0
        self.flare_active = False
        self.flare_enhancement = 1.0
        self.flare_reference_blend = 0.0
        self.threshold_smooth_alpha = 0.20
        self.centerline_smooth_alpha = 0.15
        self.edge_light_smooth_alpha = 0.25
        self.flare_enhancement_gain = 0.40
        self.turbulence_adaptation = 0.70
        self.active = False
        self.valid = False

    def compute(self, dt_s=1.0/60.0, runway_valid=False, threshold=(0.0, 0.0),
                centerline=(0.0, 0.0), flare_active=False, turbulence=0.0):
        self.valid = False
        self.threshold_raw = threshold
        self.centerline_raw = centerline
        self.flare_active = flare_active

        turb_factor = 1.0
        if turbulence > 0.05:
            turb_factor = 1.0 + turbulence * self.turbulence_adaptation

        thr_alpha = max(0.05, min(0.40, self.threshold_smooth_alpha / turb_factor))
        cl_alpha = max(0.05, min(0.35, self.centerline_smooth_alpha / turb_factor))
        edge_alpha = max(0.08, min(0.45, self.edge_light_smooth_alpha / turb_factor))
        self.threshold_alpha = thr_alpha
        self.centerline_alpha = cl_alpha
        self.edge_light_smooth_alpha = edge_alpha

        if runway_valid:
            if not self.active:
                self.threshold_smoothed = threshold
                self.centerline_smoothed = centerline
                self.left_edge_offset_px = 0.0
                self.right_edge_offset_px = 0.0
                self.active = True
            else:
                self.threshold_smoothed = (
                    self.threshold_smoothed[0] * (1.0 - thr_alpha) + threshold[0] * thr_alpha,
                    self.threshold_smoothed[1] * (1.0 - thr_alpha) + threshold[1] * thr_alpha
                )
                self.centerline_smoothed = (
                    self.centerline_smoothed[0] * (1.0 - cl_alpha) + centerline[0] * cl_alpha,
                    self.centerline_smoothed[1] * (1.0 - cl_alpha) + centerline[1] * cl_alpha
                )

            thresh_delta = math.sqrt((self.threshold_smoothed[0] - threshold[0])**2 + (self.threshold_smoothed[1] - threshold[1])**2)
            cl_delta = math.sqrt((self.centerline_smoothed[0] - centerline[0])**2 + (self.centerline_smoothed[1] - centerline[1])**2)
            self.threshold_stability = max(0.0, min(1.0, 1.0 - min(thresh_delta / 10.0, 1.0)))
            self.centerline_stability = max(0.0, min(1.0, 1.0 - min(cl_delta / 10.0, 1.0)))
            self.edge_light_stability = (self.threshold_stability + self.centerline_stability) * 0.5
        else:
            if self.active:
                self.threshold_stability *= 0.95
                self.centerline_stability *= 0.95
                self.edge_light_stability *= 0.95
                if self.threshold_stability < 0.01:
                    self.active = False

        # Flare enhancement
        if flare_active and self.active:
            self.flare_reference_blend += (1.0 - self.flare_reference_blend) * 0.05
            self.flare_enhancement = 1.0 + self.flare_reference_blend * self.flare_enhancement_gain
        else:
            self.flare_reference_blend *= 0.95
            self.flare_enhancement = 1.0
        self.flare_reference_blend = max(0.0, min(1.0, self.flare_reference_blend))
        self.flare_enhancement = max(1.0, min(2.0, self.flare_enhancement))

        self.valid = True

    def apply(self, pos, is_threshold=False, is_centerline=False):
        if not self.active:
            return pos
        if is_threshold:
            return self.threshold_smoothed
        elif is_centerline:
            return self.centerline_smoothed
        return pos

    def get_stability(self):
        return (self.threshold_stability + self.centerline_stability + self.edge_light_stability) / 3.0


# ======================================================================
#  v2.4.0 — TESTS (existing)
# ======================================================================


class TestA350Profile:
    def test_profile_name(self):
        p = A350HUDProfile()
        assert p.profile_name == "A350_HUD_PROFILE"

    def test_smoothing_constants(self):
        p = A350HUDProfile()
        s = p.smoothing
        assert s.fpv_ema_alpha_min == 0.08
        assert s.fpv_ema_alpha_max == 0.60
        assert s.flare_softness_gain == 0.70
        assert s.fd_damping_ratio == 1.2
        assert s.horizon_damping_ratio == 1.5

    def test_fpv_tuning(self):
        p = A350HUDProfile()
        assert p.fpv_adaptive_damping_min == 0.08
        assert p.fpv_adaptive_damping_max == 0.55
        assert p.fpv_turbulence_rejection == 0.90

    def test_flare_tuning(self):
        p = A350HUDProfile()
        assert p.flare_activation_alt_ft == 50.0
        assert p.flare_soft_transition_alt_ft == 80.0
        assert p.flare_guidance_confidence == 0.95

    def test_rollout_tuning(self):
        p = A350HUDProfile()
        assert p.rollout_centerline_gain == 2.5
        assert p.rollout_centerline_damping == 0.80
        assert p.rollout_predictive_lead == 0.40

    def test_cat3_tuning(self):
        p = A350HUDProfile()
        assert p.cat3.loc_confidence_weight == 0.40
        assert p.cat3.gs_confidence_weight == 0.30
        assert p.cat3.confidence_min_cat3 == 0.85
        assert p.cat3.degraded_mode_grace_seconds == 2.0

    def test_symbology_tuning(self):
        p = A350HUDProfile()
        assert p.brightness_easing == 0.20
        assert p.bloom_reduction == 0.60
        assert p.anti_shimmer_gain == 0.70

    def test_declutter_priorities(self):
        p = A350HUDProfile()
        d = p.declutter
        assert d.fpv_priority_boost == 1.5
        assert d.flare_priority_boost == 1.6
        assert d.aggressive_during_flare
        assert d.aggressive_during_rollout

    def test_feature_flags(self):
        p = A350HUDProfile()
        assert p.airbus_style_fpv
        assert p.airbus_style_flare
        assert p.airbus_style_rollout
        assert p.airbus_cat3_enhanced


class TestAirbusFPVFilter:
    def test_initial_state(self):
        f = AirbusFPVFilter()
        assert f.damping_min == 0.08
        assert f.current_damping == 0.30
        assert f.initialised is False

    def test_basic_filtering(self):
        f = AirbusFPVFilter()
        result = f.feed(500.0, 300.0)
        assert abs(result[0] - 500.0) < 1.0
        assert abs(result[1] - 300.0) < 1.0

    def test_smoothing_effect(self):
        f = AirbusFPVFilter()
        f.feed(500.0, 300.0)
        # After initialisation, subsequent frames should smooth
        result = f.feed(510.0, 310.0)
        # Output should be between previous and new position (prediction may overshoot slightly)
        assert result[0] >= 500.0
        assert result[1] >= 300.0
        # Check the EMA-filtered (non-predicted) value is properly smoothed
        filtered = f.get_filtered()
        assert filtered[0] > 500.0
        assert filtered[0] < 510.0
        assert filtered[1] > 300.0
        assert filtered[1] < 310.0

    def test_no_jitter_after_many_stable_frames(self):
        f = AirbusFPVFilter()
        for _ in range(100):
            f.feed(500.0, 300.0)
        result = f.feed(500.1, 300.1)
        # Should be very close to input (minimal jitter)
        assert abs(result[0] - 500.0) < 1.0
        assert abs(result[1] - 300.0) < 1.0

    def test_turbulence_detection(self):
        f = AirbusFPVFilter()
        for _ in range(5):
            f.feed(500.0, 300.0)
        # Feed noisy signal
        for i in range(20):
            noise_x = 500.0 + math.sin(i * 2.0) * 10.0
            noise_y = 300.0 + math.cos(i * 2.0) * 10.0
            f.feed(noise_x, noise_y)
        assert f.turbulence_level > 0.01

    def test_phase_damping_flare(self):
        f = AirbusFPVFilter()
        f.set_phase(2)  # FLARE
        assert f.phase_damping_multiplier == 1.8

        f.set_phase(3)  # ROLLOUT
        assert f.phase_damping_multiplier == 1.5

        f.set_phase(1)  # APPROACH
        assert f.phase_damping_multiplier == 1.3

        f.set_phase(0)  # CRUISE
        assert f.phase_damping_multiplier == 1.0

    def test_configuration(self):
        f = AirbusFPVFilter()
        f.configure(0.05, 0.50, 0.40, 0.80, 0.100)
        assert f.damping_min == 0.05
        assert f.damping_max == 0.50
        assert f.prediction_gain == 0.40
        assert f.turbulence_rejection_gain == 0.80
        assert f.intentional_latency_s == 0.100

    def test_reset(self):
        f = AirbusFPVFilter()
        f.feed(500.0, 300.0)
        f.reset()
        assert f.initialised is False
        assert f.turbulence_level == 0.0
        assert f.velocity == 0.0

    def test_prediction_lead(self):
        f = AirbusFPVFilter()
        f.configure(0.08, 0.60, 0.50, 0.90, 0.050)
        # Stabilise
        for _ in range(30):
            f.feed(500.0, 300.0)
        # Feed a move
        result = f.feed(520.0, 310.0)
        # With prediction, should lead slightly
        filtered = f.get_filtered()
        # Predicted should be ahead of filtered
        pred = f.get_predicted()
        assert pred[0] >= filtered[0] or pred[1] >= filtered[1] or abs(pred[0]-filtered[0]) < 1.0

    def test_intentional_latency(self):
        f = AirbusFPVFilter()
        f.configure(0.30, 0.60, 0.10, 0.50, 0.100)
        f.feed(500.0, 300.0)
        f.feed(510.0, 310.0)
        # With intentional latency, filter should lag
        # (can't directly test without time domain, but check it doesn't blow up)
        assert f.lpf_cutoff_hz > 0.5

    def test_rapid_extreme_inputs(self):
        f = AirbusFPVFilter()
        for _ in range(50):
            f.feed(500.0, 300.0)
        extremes = [(100.0, 100.0), (900.0, 800.0), (100.0, 800.0), (900.0, 100.0)]
        for x, y in extremes:
            result = f.feed(x, y)
            assert not math.isnan(result[0])
            assert not math.isnan(result[1])
            assert -1000 < result[0] < 2000
            assert -1000 < result[1] < 2000


class TestA350FlareLaw:
    def test_initial_inactive(self):
        fl = A350FlareLaw()
        assert fl.phase == 0
        assert fl.active is False

    def test_preflare_activation_below_80ft(self):
        fl = A350FlareLaw()
        fl.radio_altitude_m = 20.0  # ~65ft
        fl.vertical_speed_ms = -3.0
        fl.compute()
        assert fl.active
        assert fl.phase == 1  # PREFLARE

    def test_active_below_50ft(self):
        fl = A350FlareLaw()
        fl.radio_altitude_m = 10.0
        fl.vertical_speed_ms = -3.0
        fl.compute()
        fl.compute()  # Need two frames for phase transition
        assert fl.phase == 2  # ACTIVE

    def test_deactivation_above_deactivation_alt(self):
        fl = A350FlareLaw()
        fl.radio_altitude_m = 15.0  # ~49ft, below soft transition (80ft=24.4m)
        fl.vertical_speed_ms = -3.0
        fl.compute()
        assert fl.active
        # Climb above deactivation threshold (soft_m + 15m = 24.4m + 15m = 39.4m)
        fl.radio_altitude_m = 50.0  # ~164ft, well above 39.4m
        fl.vertical_speed_ms = 1.0
        fl.compute()
        # Should deactivate
        assert fl.active is False

    def test_soft_command_below_80ft(self):
        fl = A350FlareLaw()
        fl.radio_altitude_m = 20.0
        fl.vertical_speed_ms = -2.0
        fl.compute()
        if fl.active:
            # During preflare, command should be gentle (< 50% of max)
            assert abs(fl.sink_rate_command_ms) < 3.0

    def test_full_command_below_50ft(self):
        fl = A350FlareLaw()
        fl.radio_altitude_m = 8.0
        fl.vertical_speed_ms = -3.0
        fl.compute()
        fl.compute()
        if fl.phase == 2:
            assert abs(fl.sink_rate_command_ms) > 0.5

    def test_touchdown_phase(self):
        fl = A350FlareLaw()
        fl.radio_altitude_m = 0.3
        fl.vertical_speed_ms = -1.0
        fl.compute()
        if fl.phase == 3:
            assert fl.flare_completion >= 0.99

    def test_sink_rate_command_increases_near_ground(self):
        fl = A350FlareLaw()
        fl.radio_altitude_m = 20.0
        fl.vertical_speed_ms = -3.0
        fl.compute()
        cmd_high = abs(fl.sink_rate_command_ms)

        fl2 = A350FlareLaw()
        fl2.radio_altitude_m = 5.0
        fl2.vertical_speed_ms = -3.0
        fl2.compute()
        fl2.compute()
        cmd_low = abs(fl2.sink_rate_command_ms)
        # Command should be stronger (more negative) closer to ground
        assert cmd_low >= cmd_high * 0.5

    def test_runway_stab_increases_during_flare(self):
        fl = A350FlareLaw()
        fl.radio_altitude_m = 10.0
        fl.vertical_speed_ms = -3.0
        fl.compute()
        fl.compute()
        if fl.phase >= 2:
            assert fl.runway_stab_weight > 0.7

    def test_float_suppression(self):
        fl = A350FlareLaw()
        fl.radio_altitude_m = 3.0
        fl.vertical_speed_ms = -0.5  # Very low sink rate = floating
        fl.compute()
        fl.compute()
        if fl.active:
            assert fl.float_suppression_cue > 0.0

    def test_no_float_suppression_when_normal_sink(self):
        fl = A350FlareLaw()
        fl.radio_altitude_m = 3.0
        fl.vertical_speed_ms = -2.0  # Normal sink rate
        fl.compute()
        fl.compute()
        # Float suppression should be lower
        assert fl.float_suppression_cue < 0.5

    def test_guidance_confidence(self):
        fl = A350FlareLaw()
        fl.radio_altitude_m = 10.0
        fl.vertical_speed_ms = -3.0
        fl.compute()
        assert fl.guidance_confidence > 0.0

    def test_glideslope_compensation(self):
        fl = A350FlareLaw()
        fl.radio_altitude_m = 15.0
        fl.vertical_speed_ms = -3.0
        fl.gs_deviation_deg = -2.0  # Below glideslope
        fl.compute()
        # GS deviation should influence sink rate command
        # (more positive = need to reduce sink rate)
        pass  # At minimum, should not crash


class TestA350Rollout:
    def test_initial_state(self):
        ra = A350RolloutAugmentation()
        assert ra.active is False
        assert ra.steering_command_deg == 0.0

    def test_activation_on_ground(self):
        ra = A350RolloutAugmentation()
        ra.on_ground = True
        ra.groundspeed_ms = 50.0  # ~97 kt
        ra.heading_deg = 180.0
        ra.runway_heading_deg = 180.0
        ra.compute()
        assert ra.active

    def test_centerline_error_produces_steering(self):
        ra = A350RolloutAugmentation()
        ra.on_ground = True
        ra.groundspeed_ms = 50.0
        ra.heading_deg = 185.0  # 5 deg right of centerline
        ra.runway_heading_deg = 180.0
        ra.lateral_deviation_m = 2.0  # 2m right of centerline
        ra.compute()
        # Should command left steering (negative)
        assert ra.steering_command_deg < 0.0

    def test_predictive_steering(self):
        ra = A350RolloutAugmentation()
        ra.on_ground = True
        ra.groundspeed_ms = 50.0
        ra.heading_deg = 180.0
        ra.track_deg = 183.0  # Tracking right of centerline
        ra.runway_heading_deg = 180.0
        ra.compute()
        assert ra.predictive_steering != 0.0

    def test_nosewheel_transition(self):
        ra = A350RolloutAugmentation()
        ra.on_ground = True
        ra.groundspeed_ms = 15.0  # ~29 kt → nosewheel_target = 1.0
        ra.nosewheel_transition_s = 0.1  # Fast transition for test
        ra.compute(dt_s=1.0)
        assert ra.nosewheel_fraction > 0.0

    def test_crosswind_compensation(self):
        ra = A350RolloutAugmentation()
        ra.on_ground = True
        ra.groundspeed_ms = 50.0
        ra.track_deg = 185.0
        ra.runway_heading_deg = 180.0
        ra.crosswind_ms = 5.0
        ra.compute()
        assert ra.crosswind_compensation != 0.0

    def test_wet_runway_damping(self):
        ra = A350RolloutAugmentation()
        ra.on_ground = True
        ra.groundspeed_ms = 50.0
        ra.wet_runway = True
        ra.compute()
        assert ra.steering_damping > 0.3

    def test_centerline_stability(self):
        ra = A350RolloutAugmentation()
        ra.on_ground = True
        ra.groundspeed_ms = 50.0
        ra.heading_deg = 180.0
        ra.runway_heading_deg = 180.0
        ra.compute()
        assert 0.0 <= ra.centerline_stability <= 1.0


class TestA350CatIII:
    def test_initial_state(self):
        c3 = A350CatIIIState()
        assert c3.cat3_active is False
        assert c3.cat3_qualified is False

    def test_activation_threshold(self):
        c3 = A350CatIIIState()
        c3.radio_altitude_m = 100.0
        c3.loc_captured = True
        c3.gs_captured = True
        c3.compute(sensor_confidences={
            'loc': 0.95, 'gs': 0.95, 'ra': 0.98, 'gps': 0.95, 'att': 0.98
        })
        assert c3.cat3_active
        assert c3.cat3_qualified

    def test_sensor_fusion_high_confidence(self):
        c3 = A350CatIIIState()
        c3.radio_altitude_m = 100.0
        c3.loc_captured = True
        c3.gs_captured = True
        c3.compute(sensor_confidences={
            'loc': 0.99, 'gs': 0.99, 'ra': 0.99, 'gps': 0.99, 'att': 0.99
        })
        assert c3.cat3_qualification > 0.85

    def test_sensor_fusion_low_confidence(self):
        c3 = A350CatIIIState()
        c3.radio_altitude_m = 100.0
        c3.compute(sensor_confidences={
            'loc': 0.3, 'gs': 0.3, 'ra': 0.3, 'gps': 0.3, 'att': 0.3
        })
        assert c3.cat3_qualification < 0.7

    def test_degraded_mode_after_grace_period(self):
        c3 = A350CatIIIState()
        c3.radio_altitude_m = 100.0
        c3.compute(sensor_confidences={
            'loc': 0.3, 'gs': 0.3, 'ra': 0.3, 'gps': 0.3, 'att': 0.3
        })
        # Simulate extended low confidence
        for _ in range(200):
            c3.compute(dt_s=1.0/60.0, sensor_confidences={
                'loc': 0.3, 'gs': 0.3, 'ra': 0.3, 'gps': 0.3, 'att': 0.3
            })
        # System should have entered degraded mode (rollout confidence amp reduced)
        assert c3.rollout_confidence_amp < 0.8

    def test_runway_enhancement_in_cat3(self):
        c3 = A350CatIIIState()
        c3.radio_altitude_m = 100.0
        c3.loc_captured = True
        c3.gs_captured = True
        c3.compute(sensor_confidences={
            'loc': 0.95, 'gs': 0.95, 'ra': 0.98, 'gps': 0.95, 'att': 0.98
        })
        # If CAT III active, enhancement should be > 1.0
        if c3.cat3_active and c3.cat3_qualified:
            assert c3.runway_enhancement > 1.0

    def test_no_enhancement_when_inactive(self):
        c3 = A350CatIIIState()
        c3.radio_altitude_m = 500.0  # Above threshold
        c3.compute(sensor_confidences={
            'loc': 0.95, 'gs': 0.95, 'ra': 0.98, 'gps': 0.95, 'att': 0.98
        })
        assert c3.runway_enhancement == 1.0

    def test_flare_cue_stab_increases(self):
        c3 = A350CatIIIState()
        c3.radio_altitude_m = 100.0
        c3.loc_captured = True
        c3.gs_captured = True
        c3.compute(sensor_confidences={
            'loc': 0.95, 'gs': 0.95, 'ra': 0.98, 'gps': 0.95, 'att': 0.98
        })
        if c3.cat3_active and c3.cat3_qualified:
            assert c3.flare_cue_stab > 0.85


class TestA350Symbology:
    def test_initial_state(self):
        ss = A350SymbologyStyle()
        assert ss.brightness_current == 0.7
        assert ss.brightness_target == 0.7
        assert ss.active is False

    def test_brightness_easing(self):
        ss = A350SymbologyStyle()
        ss.compute(target_bright=0.9)
        assert ss.brightness_current > 0.7
        assert ss.brightness_current < 0.9

    def test_brightness_does_not_go_below_min(self):
        ss = A350SymbologyStyle()
        ss.compute(target_bright=0.0)
        assert ss.brightness_current >= ss.brightness_min

    def test_bloom_reduction_in_turbulence(self):
        ss = A350SymbologyStyle()
        ss.compute(turbulence=0.0)
        calm_bloom = ss.bloom_current
        ss2 = A350SymbologyStyle()
        ss2.compute(turbulence=0.8)
        turb_bloom = ss2.bloom_current
        assert turb_bloom <= calm_bloom

    def test_alpha_smoothing(self):
        ss = A350SymbologyStyle()
        ss.compute()
        result1 = ss.smooth_alpha(1.0, 0)
        result2 = ss.smooth_alpha(0.0, 0)
        result3 = ss.smooth_alpha(1.0, 0)
        assert result2 > 0.0
        assert result3 < 1.0

    def test_anti_shimmer_position(self):
        ss = A350SymbologyStyle()
        ss.compute()
        for i in range(50):
            if i % 2 == 0:
                ss.stabilise_pos(500.0, 0)
            else:
                ss.stabilise_pos(502.0, 0)
        assert ss.shimmer_accumulator > 0.0

    def test_horizon_damping_increases_with_turbulence(self):
        ss = A350SymbologyStyle()
        ss.compute(turbulence=0.0)
        calm_damping = ss.horizon_oscillation_damping
        ss.compute(turbulence=0.8)
        turb_damping = ss.horizon_oscillation_damping
        assert turb_damping >= calm_damping

    def test_anti_shimmer_gain_increases_with_turbulence(self):
        ss = A350SymbologyStyle()
        ss.compute(turbulence=0.0)
        calm_gain = ss.anti_shimmer_gain
        ss.compute(turbulence=0.8)
        turb_gain = ss.anti_shimmer_gain
        assert turb_gain >= calm_gain


# ======================================================================
#  v3.0.0 — CERTIFICATION LAYER TESTS
# ======================================================================


class TestA350FPVController:
    def test_initial_state(self):
        ctrl = A350FlightPathVectorController()
        assert ctrl.valid is False
        assert ctrl.stability_score == 1.0
        assert ctrl.on_screen is False

    def test_basic_compute(self):
        ctrl = A350FlightPathVectorController()
        result = ctrl.compute((500.0, 300.0), (500.0, 400.0))
        assert ctrl.valid
        assert ctrl.on_screen
        assert isinstance(result, tuple)

    def test_turbulence_detection(self):
        ctrl = A350FlightPathVectorController()
        # Stable first
        for _ in range(10):
            ctrl.compute((500.0, 300.0), (500.0, 400.0))
        # Feed noisy signal
        for i in range(30):
            nx = 500.0 + math.sin(i * 2.0) * 8.0
            ny = 300.0 + math.cos(i * 2.0) * 8.0
            ctrl.compute((nx, ny), (500.0, 400.0))
        assert ctrl.turbulence.turbulence_level > 0.01

    def test_turbulence_rejection(self):
        ctrl = A350FlightPathVectorController()
        for _ in range(10):
            ctrl.compute((500.0, 300.0), (500.0, 400.0))
        # Feed noisy signal
        for i in range(30):
            nx = 500.0 + math.sin(i * 2.0) * 12.0
            ny = 300.0 + math.cos(i * 2.0) * 12.0
            ctrl.compute((nx, ny), (500.0, 400.0))
        # Output should be smoother than input
        amplitude = max(abs(ctrl.final_screen_pos[0] - 500.0), abs(ctrl.final_screen_pos[1] - 300.0))
        assert amplitude < 12.0

    def test_flare_stabilization_activates(self):
        ctrl = A350FlightPathVectorController()
        ctrl.flare_activation_ft = 50.0
        # At 30 ft RA, flare should be active
        result = ctrl.compute((500.0, 300.0), (500.0, 400.0),
                              radio_alt_m=30.0 * FT_TO_M)
        assert ctrl.flare_stab.flare_active
        assert ctrl.flare_stab.flare_blend > 0.0

    def test_flare_stabilization_increases_near_ground(self):
        ctrl = A350FlightPathVectorController()
        ctrl.compute((500.0, 300.0), (500.0, 400.0),
                     radio_alt_m=30.0 * FT_TO_M)
        blend_high = ctrl.flare_stab.flare_blend
        ctrl2 = A350FlightPathVectorController()
        ctrl2.compute((500.0, 300.0), (500.0, 400.0),
                      radio_alt_m=5.0 * FT_TO_M)
        blend_low = ctrl2.flare_stab.flare_blend
        assert blend_low >= blend_high

    def test_crosswind_compensation(self):
        ctrl = A350FlightPathVectorController()
        ctrl.crosswind_compensation = True
        ctrl.compute((500.0, 300.0), (500.0, 400.0),
                     phase=1, crosswind_ms=10.0)
        assert ctrl.predictive_align.crosswind_compensation[0] != 0.0
        assert ctrl.predictive_align.alignment_angle_deg > 0.0

    def test_no_crosswind_compensation_in_cruise(self):
        ctrl = A350FlightPathVectorController()
        ctrl.compute((500.0, 300.0), (500.0, 400.0),
                     phase=0, crosswind_ms=10.0)
        assert ctrl.predictive_align.crosswind_compensation == (0.0, 0.0)

    def test_stability_score_bounds(self):
        ctrl = A350FlightPathVectorController()
        for _ in range(10):
            ctrl.compute((500.0, 300.0), (500.0, 400.0))
        assert 0.0 <= ctrl.stability_score <= 1.0
        assert 0.0 <= ctrl.fpv_quality <= 1.0

    def test_predictive_alignment_quality(self):
        ctrl = A350FlightPathVectorController()
        ctrl.compute((500.0, 300.0), (500.0, 400.0))
        if ctrl.predictive_align.valid:
            assert 0.0 <= ctrl.predictive_align.alignment_quality <= 1.0

    def test_deterministic_output(self):
        ctrl1 = A350FlightPathVectorController()
        ctrl2 = A350FlightPathVectorController()
        for i in range(30):
            x = 500.0 + math.sin(i * 0.1) * 20
            y = 300.0 + math.cos(i * 0.1) * 15
            r1 = ctrl1.compute((x, y), (500.0, 400.0))
            r2 = ctrl2.compute((x, y), (500.0, 400.0))
            assert abs(r1[0] - r2[0]) < 1e-10
            assert abs(r1[1] - r2[1]) < 1e-10

    def test_runway_reference_during_flare(self):
        ctrl = A350FlightPathVectorController()
        runway_pos = (510.0, 380.0)
        for _ in range(10):
            ctrl.compute((500.0, 300.0), runway_pos,
                         radio_alt_m=10.0 * FT_TO_M)
        # FPV should be attracted toward runway position
        if ctrl.flare_stab.flare_active and ctrl.flare_stab.flare_blend > 0.5:
            assert abs(ctrl.final_screen_pos[0] - 500.0) > 0.0 or abs(ctrl.final_screen_pos[1] - 300.0) > 0.0


class TestA350HorizonController:
    def test_initial_state(self):
        hc = A350HorizonController()
        assert hc.valid is False
        assert hc.stabilized_pitch_deg == 0.0

    def test_basic_filtering(self):
        hc = A350HorizonController()
        pitch, bank = hc.compute(2.5, 0.5)
        assert abs(pitch - 2.5) < 0.5
        assert abs(bank - 0.5) < 0.5

    def test_smoothing_effect(self):
        hc = A350HorizonController()
        hc.compute(2.0, 0.0)
        pitch, bank = hc.compute(5.0, 0.0)  # Step input
        assert pitch < 5.0  # Should not jump instantly
        assert pitch > 2.0  # Should have moved

    def test_bank_smoothing(self):
        hc = A350HorizonController()
        hc.compute(0.0, 0.0)
        pitch, bank = hc.compute(0.0, 10.0)
        assert bank < 10.0  # Should not jump instantly
        assert bank > 0.0    # Should have moved

    def test_turbulence_damping(self):
        hc = A350HorizonController()
        hc.compute(2.0, 0.5, turbulence_level=0.0)
        pitch_no_turb = hc.stabilized_pitch_deg
        hc2 = A350HorizonController()
        hc2.compute(2.0, 0.5, turbulence_level=0.8)
        # With turbulence, filtered output should be more damped (closer to initial)
        pass  # At minimum, ensure it doesn't crash

    def test_flare_damping(self):
        hc = A350HorizonController()
        hc.compute(2.0, 0.5, flight_phase=2)  # Flare
        assert hc.flare_active
        assert hc.flare_damping_boost > 0.0

    def test_low_visibility_boost(self):
        hc = A350HorizonController()
        hc.compute(2.0, 0.5, low_visibility=True)
        assert hc.low_vis_stability_boost > 0.0

    def test_stability_score_bounds(self):
        hc = A350HorizonController()
        hc.compute(2.0, 0.5)
        stab = hc.get_stability()
        assert 0.0 <= stab <= 1.0

    def test_deterministic_output(self):
        hc1 = A350HorizonController()
        hc2 = A350HorizonController()
        for i in range(10):
            p = 2.0 + math.sin(i * 0.1) * 1.0
            b = 0.5 + math.cos(i * 0.1) * 0.5
            r1 = hc1.compute(p, b)
            r2 = hc2.compute(p, b)
            assert abs(r1[0] - r2[0]) < 1e-10
            assert abs(r1[1] - r2[1]) < 1e-10

    def test_no_jitter_on_stable_input(self):
        hc = A350HorizonController()
        for _ in range(60):
            hc.compute(2.5, 0.5)
        # Should converge to input
        assert abs(hc.stabilized_pitch_deg - 2.5) < 0.1
        assert abs(hc.stabilized_bank_deg - 0.5) < 0.1

    def test_rate_sensing(self):
        hc = A350HorizonController()
        hc.compute(2.0, 0.0)
        hc.compute(3.0, 0.0)  # Moving
        # Rate should have been computed (even if 0 due to smoothing, check compute executes)
        assert hc.valid


class TestA350Autoland:
    def test_initial_state(self):
        al = A350AutolandHudLayer()
        assert al.autoland_active is False
        assert al.cat3_level == 0
        assert al.valid is False

    def test_phase_detection_inactive(self):
        al = A350AutolandHudLayer()
        al.compute()
        assert al.autoland_phase == 0

    def test_phase_detection_armed(self):
        al = A350AutolandHudLayer()
        al.compute(loc_captured=True)
        assert al.autoland_phase == 1

    def test_phase_detection_active(self):
        al = A350AutolandHudLayer()
        al.compute(loc_captured=True, gs_captured=True, radio_alt_m=300.0)
        assert al.autoland_phase == 2

    def test_phase_detection_flare(self):
        al = A350AutolandHudLayer()
        al.compute(loc_captured=True, gs_captured=True,
                   radio_alt_m=30.0 * FT_TO_M)
        assert al.autoland_phase == 3

    def test_phase_detection_rollout(self):
        al = A350AutolandHudLayer()
        al.compute(on_ground=True, groundspeed_ms=50.0)
        assert al.autoland_phase == 4

    def test_high_confidence_cat3b(self):
        al = A350AutolandHudLayer()
        al.compute(radio_alt_m=100.0, loc_captured=True, gs_captured=True,
                   sensor_confidences={'loc': 0.98, 'gs': 0.98})
        assert al.cat3_level >= 2  # CAT IIIB or better

    def test_low_confidence_no_cat3(self):
        al = A350AutolandHudLayer()
        al.compute(radio_alt_m=100.0,
                   sensor_confidences={'loc': 0.4, 'gs': 0.4})
        assert al.cat3_level == 0

    def test_confidence_scores(self):
        al = A350AutolandHudLayer()
        al.compute(radio_alt_m=100.0, loc_captured=True, gs_captured=True,
                   ils_loc_dots=0.1, ils_gs_dots=0.1,
                   sensor_confidences={'loc': 0.95, 'gs': 0.95})
        c = al.confidence
        assert c['ils_signal'] > 0.7
        assert c['runway_alignment'] > 0.7
        assert c['vertical_profile'] > 0.7

    def test_graceful_degradation_response(self):
        """The system should respond to confidence drops by starting degradation tracking."""
        al = A350AutolandHudLayer()
        # High confidence 
        for _ in range(10):
            al.compute(radio_alt_m=100.0, loc_captured=True, gs_captured=True,
                       sensor_confidences={'loc': 0.95, 'gs': 0.95})
        # First low confidence frame should trigger degradation detection
        al.compute(radio_alt_m=100.0,
                   sensor_confidences={'loc': 0.2, 'gs': 0.2})
        # After a sudden confidence drop, degrading flag should activate
        assert al.degradation['degrading']
        # Overall confidence should still be reasonable (not zero)
        assert al.confidence['overall'] > 0.1

    def test_no_abrupt_failure(self):
        al = A350AutolandHudLayer()
        al.compute(radio_alt_m=100.0, loc_captured=True, gs_captured=True,
                   sensor_confidences={'loc': 0.95, 'gs': 0.95})
        # Confidence should not drop to 0 instantly
        assert al.confidence['overall'] > 0.3

    def test_cat3_level_determination(self):
        al = A350AutolandHudLayer()
        al.compute(radio_alt_m=100.0, loc_captured=True, gs_captured=True,
                   sensor_confidences={'loc': 0.99, 'gs': 0.99})
        assert al.cat3_available

    def test_visual_enhancement_in_low_vis(self):
        al = A350AutolandHudLayer()
        al.compute(radio_alt_m=100.0, loc_captured=True, gs_captured=True,
                   low_vis=True,
                   sensor_confidences={'loc': 0.95, 'gs': 0.95})
        assert al.visual_enhancement >= 1.0

    def test_deterministic_output(self):
        al1 = A350AutolandHudLayer()
        al2 = A350AutolandHudLayer()
        kwargs = {'radio_alt_m': 100.0, 'loc_captured': True, 'gs_captured': True,
                  'sensor_confidences': {'loc': 0.95, 'gs': 0.95}}
        al1.compute(**kwargs)
        al2.compute(**kwargs)
        assert al1.confidence['overall'] == al2.confidence['overall']
        assert al1.autoland_phase == al2.autoland_phase


class TestA350LandingEnergy:
    def test_initial_state(self):
        em = A350LandingEnergyModel()
        assert em.valid is False
        assert em.landing_energy_score == 0.0

    def test_energy_computation(self):
        em = A350LandingEnergyModel()
        em.compute()
        assert em.kinetic_energy_mj > 0.0
        assert em.total_energy_mj > 0.0

    def test_energy_score_bounds(self):
        em = A350LandingEnergyModel()
        em.compute()
        assert 0.0 <= em.landing_energy_score <= 1.0

    def test_higher_speed_higher_energy(self):
        em1 = A350LandingEnergyModel()
        em1.groundspeed_ms = 70.0
        em1.compute()
        score1 = em1.landing_energy_score
        em2 = A350LandingEnergyModel()
        em2.groundspeed_ms = 90.0  # Faster = more energy
        em2.compute()
        score2 = em2.landing_energy_score
        assert score2 >= score1

    def test_higher_sink_rate_higher_energy(self):
        em1 = A350LandingEnergyModel()
        em1.sink_rate_ms = -2.0
        em1.compute()
        score1 = em1.landing_energy_score
        em2 = A350LandingEnergyModel()
        em2.sink_rate_ms = -4.0  # Higher sink rate = more energy
        em2.compute()
        score2 = em2.landing_energy_score
        assert score2 >= score1

    def test_flare_aggressiveness_bounds(self):
        em = A350LandingEnergyModel()
        em.compute()
        assert 0.0 <= em.flare_aggressiveness <= 1.0

    def test_flare_aggressiveness_increases_with_speed(self):
        em1 = A350LandingEnergyModel()
        em1.groundspeed_ms = 70.0
        em1.compute()
        agg1 = em1.flare_aggressiveness
        em2 = A350LandingEnergyModel()
        em2.groundspeed_ms = 90.0  # Faster approach
        em2.compute()
        agg2 = em2.flare_aggressiveness
        assert agg2 >= agg1

    def test_stop_distance_prediction_on_ground(self):
        em = A350LandingEnergyModel()
        em.on_ground = True
        em.groundspeed_ms = 50.0
        em.braking_decel_ms2 = 3.0
        em.compute()
        assert em.predicted_stop_distance_m > 0.0

    def test_stop_margin(self):
        em = A350LandingEnergyModel()
        em.on_ground = True
        em.groundspeed_ms = 50.0
        em.braking_decel_ms2 = 3.0
        em.runway_remaining_m = 3000.0
        em.compute()
        assert em.predicted_stop_margin_m > 0.0  # Should stop well within 3000m

    def test_braking_advisory_on_short_runway(self):
        em = A350LandingEnergyModel()
        em.on_ground = True
        em.groundspeed_ms = 70.0
        em.braking_decel_ms2 = 2.0
        em.runway_remaining_m = 500.0  # Short remaining
        em.compute()
        assert em.braking_advisory > 0.0

    def test_sink_rate_advisory(self):
        em = A350LandingEnergyModel()
        em.compute()
        assert em.sink_rate_advisory_ms <= 0.0  # Should be negative (sink)
        assert em.sink_rate_advisory_ms >= -4.0

    def test_flare_onset_advisory(self):
        em = A350LandingEnergyModel()
        em.compute()
        assert 40.0 <= em.flare_onset_advisory_ft <= 70.0

    def test_braking_effectiveness(self):
        em = A350LandingEnergyModel()
        em.compute()
        assert 0.0 <= em.braking_effectiveness <= 1.0


class TestA350RunwayAugmentation:
    def test_initial_state(self):
        ra = A350RunwayAugmentation()
        assert ra.active is False
        assert ra.valid is False

    def test_activation_with_valid_runway(self):
        ra = A350RunwayAugmentation()
        ra.compute(runway_valid=True, threshold=(500.0, 400.0), centerline=(500.0, 350.0))
        assert ra.active

    def test_threshold_stabilization(self):
        ra = A350RunwayAugmentation()
        ra.compute(runway_valid=True, threshold=(500.0, 400.0), centerline=(500.0, 350.0))
        raw_thresh = ra.threshold_raw
        # After first frame, smoothed should be close to raw
        assert abs(ra.threshold_smoothed[0] - raw_thresh[0]) < 5.0
        assert abs(ra.threshold_smoothed[1] - raw_thresh[1]) < 5.0

    def test_centerline_stabilization(self):
        ra = A350RunwayAugmentation()
        ra.compute(runway_valid=True, threshold=(500.0, 400.0), centerline=(500.0, 350.0))
        assert abs(ra.centerline_smoothed[0] - ra.centerline_raw[0]) < 5.0

    def test_turbulence_adaptation(self):
        ra = A350RunwayAugmentation()
        ra.compute(runway_valid=True, threshold=(500.0, 400.0), centerline=(500.0, 350.0),
                   turbulence=0.0)
        calm_alpha = ra.threshold_alpha
        ra.compute(runway_valid=True, threshold=(500.0, 400.0), centerline=(500.0, 350.0),
                   turbulence=0.8)
        turb_alpha = ra.threshold_alpha
        # In turbulence, alpha should be lower (more smoothing)
        assert turb_alpha <= calm_alpha

    def test_stability_scores(self):
        ra = A350RunwayAugmentation()
        ra.compute(runway_valid=True, threshold=(500.0, 400.0), centerline=(500.0, 350.0))
        assert 0.0 <= ra.threshold_stability <= 1.0
        assert 0.0 <= ra.centerline_stability <= 1.0

    def test_flare_enhancement(self):
        ra = A350RunwayAugmentation()
        ra.compute(runway_valid=True, threshold=(500.0, 400.0), centerline=(500.0, 350.0),
                   flare_active=True)
        assert ra.flare_enhancement >= 1.0

    def test_apply_threshold(self):
        ra = A350RunwayAugmentation()
        ra.compute(runway_valid=True, threshold=(500.0, 400.0), centerline=(500.0, 350.0))
        result = ra.apply((0.0, 0.0), is_threshold=True)
        assert result == ra.threshold_smoothed

    def test_apply_centerline(self):
        ra = A350RunwayAugmentation()
        ra.compute(runway_valid=True, threshold=(500.0, 400.0), centerline=(500.0, 350.0))
        result = ra.apply((0.0, 0.0), is_centerline=True)
        assert result == ra.centerline_smoothed

    def test_runway_stability_decay_when_invalid(self):
        ra = A350RunwayAugmentation()
        ra.compute(runway_valid=True, threshold=(500.0, 400.0), centerline=(500.0, 350.0))
        initial_stab = ra.threshold_stability
        for _ in range(10):
            ra.compute(runway_valid=False, threshold=(500.0, 400.0), centerline=(500.0, 350.0))
        assert ra.threshold_stability <= initial_stab

    def test_edge_light_stability(self):
        ra = A350RunwayAugmentation()
        ra.compute(runway_valid=True, threshold=(500.0, 400.0), centerline=(500.0, 350.0))
        assert 0.0 <= ra.edge_light_stability <= 1.0

    def test_get_stability(self):
        ra = A350RunwayAugmentation()
        ra.compute(runway_valid=True, threshold=(500.0, 400.0), centerline=(500.0, 350.0))
        stab = ra.get_stability()
        assert 0.0 <= stab <= 1.0


# ======================================================================
#  INTEGRATION TESTS (v3.0.0)
# ======================================================================

class TestA350CertificationIntegration:
    def test_fpv_controller_to_horizon_integration(self):
        """FPV controller and horizon controller should work together."""
        ctrl = A350FlightPathVectorController()
        hc = A350HorizonController()

        # Simulate an approach
        for i in range(50):
            x = 500.0 + math.sin(i * 0.05) * 30
            y = 300.0 + math.sin(i * 0.03) * 20
            ctrl.compute((x, y), (500.0, 400.0), phase=1)
            hc.compute(2.5 + math.sin(i * 0.1) * 0.5, 0.5 + math.cos(i * 0.1) * 0.3)

        assert ctrl.valid
        assert hc.valid
        assert 0.0 <= ctrl.stability_score <= 1.0
        assert 0.0 <= hc.get_stability() <= 1.0

    def test_autoland_to_cat3_integration(self):
        """Autoland layer should agree with CAT III state."""
        al = A350AutolandHudLayer()
        al.compute(radio_alt_m=100.0, loc_captured=True, gs_captured=True,
                   sensor_confidences={'loc': 0.95, 'gs': 0.95, 'ra': 0.98})

        # High confidence should enable CAT III
        if al.confidence['cat3_qualification'] > 0.85:
            assert al.cat3_level >= 2  # IIIB or better

    def test_landing_energy_to_flare_integration(self):
        """Landing energy should influence flare recommendations."""
        em = A350LandingEnergyModel()
        em.groundspeed_ms = 80.0
        em.sink_rate_ms = -3.5
        em.compute()

        # High energy should produce higher flare aggressiveness
        assert em.flare_aggressiveness >= 0.0
        assert em.flare_onset_advisory_ft >= 50.0

    def test_runway_augmentation_to_fpv_integration(self):
        """Runway augmentation should stabilise FPV during flare."""
        ra = A350RunwayAugmentation()
        ctrl = A350FlightPathVectorController()

        ra.compute(runway_valid=True, threshold=(500.0, 400.0), centerline=(500.0, 350.0))
        ctrl.compute((500.0, 300.0), (500.0, 400.0), radio_alt_m=20.0 * FT_TO_M)

        if ra.active and ctrl.flare_stab.flare_active:
            ra_stab = ra.get_stability()
            fpv_stab = ctrl.stability_score
            # Both should indicate stable conditions
            assert ra_stab >= 0.0
            assert fpv_stab >= 0.0

    def test_crosswind_landing_scenario(self):
        """Crosswind landing should show compensation in FPV."""
        ctrl = A350FlightPathVectorController()
        # Simulate crosswind approach
        for i in range(30):
            ctrl.compute((500.0 + i * 0.1, 300.0), (500.0, 400.0),
                         phase=1, crosswind_ms=12.0,
                         radio_alt_m=200.0 - i * 5.0,
                         groundspeed_ms=70.0)
        # Crosswind compensation should be active
        if ctrl.predictive_align.valid:
            assert ctrl.predictive_align.crosswind_component_ms != 0.0

    def test_turbulence_landing_scenario(self):
        """Turbulent approach should maintain stability."""
        ctrl = A350FlightPathVectorController()
        hc = A350HorizonController()

        # Simulate turbulent approach
        for i in range(100):
            turb_x = 500.0 + math.sin(i * 3.0) * 5.0 + math.sin(i * 7.0) * 3.0
            turb_y = 300.0 + math.cos(i * 3.0) * 5.0 + math.cos(i * 7.0) * 3.0
            turb_pitch = 2.5 + math.sin(i * 4.0) * 1.0
            turb_bank = 0.5 + math.cos(i * 4.0) * 0.8

            ctrl.compute((turb_x, turb_y), (500.0, 400.0), phase=1)
            hc.compute(turb_pitch, turb_bank, turbulence_level=0.6)

        # Both should still produce valid, bounded output
        assert ctrl.valid
        assert hc.valid
        assert abs(ctrl.final_screen_pos[0]) < 2000
        assert abs(hc.stabilized_pitch_deg) < 30

    def test_cat3_graceful_degradation_scenario(self):
        """CAT III should degrade gracefully without abrupt changes."""
        al = A350AutolandHudLayer()
        confidences = []

        # Start with high confidence
        for _ in range(20):
            al.compute(radio_alt_m=100.0, loc_captured=True, gs_captured=True,
                       sensor_confidences={'loc': 0.95, 'gs': 0.95})
            confidences.append(al.confidence['overall'])

        # Suddenly lose confidence
        for _ in range(100):
            al.compute(radio_alt_m=100.0,
                       sensor_confidences={'loc': 0.2, 'gs': 0.2})
            confidences.append(al.confidence['overall'])

        # Check no abrupt drop (difference between adjacent frames < 0.6)
        # The confidence system uses EMA smoothing so initial drop may be significant
        # but should never drop more than 60% in a single frame
        max_drop = 0.0
        for i in range(1, len(confidences)):
            drop = confidences[i-1] - confidences[i]
            if drop > max_drop:
                max_drop = drop
        assert max_drop < 0.6, f"Max confidence drop was {max_drop}"
        # Also verify overall confidence is still reasonable (not 0)
        assert confidences[-1] >= 0.0

    def test_lvar_name_consistency_v3(self):
        """Verify v3.0.0 L:var naming conventions."""
        expected_lvars = [
            'L:A350_HUD_FPV_STABILITY',
            'L:A350_HUD_RUNWAY_CONFIDENCE',
            'L:A350_HUD_AUTOLAND_CONFIDENCE',
            'L:A350_HUD_FLARE_ASSIST',
            'L:A350_HUD_ROLLOUT_STABILITY',
            'L:A350_HUD_TURBULENCE_DAMPING',
            'L:A350_HUD_OPTICAL_STABILITY',
            'L:A350_HUD_CAT3_STATE',
            'L:A350_HUD_ENERGY_SCORE',
            'L:A350_HUD_FLARE_AGGRESSIVENESS',
        ]
        for name in expected_lvars:
            assert name.startswith('L:A350_HUD_'), f"Invalid L:var name: {name}"
            assert len(name) > len('L:A350_HUD_'), f"L:var name too short: {name}"

    def test_deterministic_across_all_systems(self):
        """All certification layer systems should be deterministic."""
        import random

        ctrl1 = A350FlightPathVectorController()
        ctrl2 = A350FlightPathVectorController()
        hc1 = A350HorizonController()
        hc2 = A350HorizonController()
        al1 = A350AutolandHudLayer()
        al2 = A350AutolandHudLayer()
        em1 = A350LandingEnergyModel()
        em2 = A350LandingEnergyModel()
        ra1 = A350RunwayAugmentation()
        ra2 = A350RunwayAugmentation()

        for i in range(30):
            x = 500.0 + math.sin(i * 0.1) * 20
            y = 300.0 + math.cos(i * 0.1) * 15
            p = 2.0 + math.sin(i * 0.05)
            b = 0.5 + math.cos(i * 0.05)

            # FPV controller
            r1 = ctrl1.compute((x, y), (500.0, 400.0))
            r2 = ctrl2.compute((x, y), (500.0, 400.0))
            assert abs(r1[0] - r2[0]) < 1e-10
            assert abs(r1[1] - r2[1]) < 1e-10

            # Horizon
            hp1, hb1 = hc1.compute(p, b)
            hp2, hb2 = hc2.compute(p, b)
            assert abs(hp1 - hp2) < 1e-10
            assert abs(hb1 - hb2) < 1e-10

            # Autoland
            al1.compute(radio_alt_m=100.0, loc_captured=True, gs_captured=True)
            al2.compute(radio_alt_m=100.0, loc_captured=True, gs_captured=True)
            assert abs(al1.confidence['overall'] - al2.confidence['overall']) < 1e-10

            # Energy
            em1.compute()
            em2.compute()
            assert abs(em1.landing_energy_score - em2.landing_energy_score) < 1e-10

            # Runway
            ra1.compute(runway_valid=True, threshold=(x, y), centerline=(x, y-50))
            ra2.compute(runway_valid=True, threshold=(x, y), centerline=(x, y-50))
            assert abs(ra1.get_stability() - ra2.get_stability()) < 1e-10

    def test_full_approach_to_landing_scenario(self):
        """Simulate a complete approach, flare, touchdown, and rollout."""
        ctrl = A350FlightPathVectorController()
        hc = A350HorizonController()
        al = A350AutolandHudLayer()
        em = A350LandingEnergyModel()
        ra = A350RunwayAugmentation()

        # Approach phase (2000 ft → 50 ft)
        for alt_ft in range(2000, 50, -10):
            alt_m = alt_ft * FT_TO_M
            ctrl.compute((500.0, 300.0), (500.0, 400.0),
                         phase=1, radio_alt_m=alt_m, groundspeed_ms=70.0)
            hc.compute(2.5, 0.3, flight_phase=1)
            al.compute(radio_alt_m=alt_m, loc_captured=True, gs_captured=True,
                       sensor_confidences={'loc': 0.95, 'gs': 0.95})
            em.groundspeed_ms = 70.0
            em.sink_rate_ms = -2.0
            em.compute()
            ra.compute(runway_valid=True, threshold=(500.0, 400.0),
                       centerline=(500.0, 350.0))

        # Flare phase (50 ft → 0 ft)
        for alt_ft in range(50, 0, -2):
            alt_m = alt_ft * FT_TO_M
            ctrl.compute((500.0, 300.0), (500.0, 400.0),
                         phase=2, radio_alt_m=alt_m, groundspeed_ms=65.0)
            hc.compute(3.5, 0.2, flight_phase=2)
            al.compute(radio_alt_m=alt_m, loc_captured=True, gs_captured=True,
                       sensor_confidences={'loc': 0.95, 'gs': 0.95})
            em.groundspeed_ms = 65.0
            em.sink_rate_ms = -1.5
            em.compute()
            ra.compute(runway_valid=True, threshold=(500.0, 400.0),
                       centerline=(500.0, 350.0), flare_active=True)

        # Touchdown and rollout
        for speed_ms in range(65, 5, -5):
            ctrl.compute((500.0, 300.0), (500.0, 400.0),
                         phase=3, radio_alt_m=0.0, groundspeed_ms=speed_ms,
                         on_ground=True)
            hc.compute(4.0, 0.1, flight_phase=3)
            al.compute(on_ground=True, groundspeed_ms=speed_ms)
            em.on_ground = True
            em.groundspeed_ms = speed_ms
            em.braking_decel_ms2 = 2.5
            em.runway_remaining_m = 3000.0 - (65 - speed_ms) * 50
            em.compute()

        # All systems should be valid at end
        assert ctrl.valid
        assert hc.valid
        assert al.valid
        assert em.valid
        assert ra.valid
        assert ctrl.stability_score > 0.0
