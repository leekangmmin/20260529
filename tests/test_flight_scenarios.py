#!/usr/bin/env python3
"""
Conformal HUD – Real Flight Test Infrastructure Suite (v2.5.0)

PHASE 5 — REAL FLIGHT TEST INFRASTRUCTURE

Creates repeatable flight validation scenarios:
  1. CAT III fog approaches
  2. Severe turbulence approaches
  3. Crosswind landing tests
  4. Wet runway rollout tests
  5. Rejected landing tests
  6. Night operation tests

Includes:
  - Automatic scoring
  - Replay export/import
  - Validation reports
  - Scenario comparison tools

Goal:
  Every major feature should be testable under repeatable conditions.

Run:  python -m pytest tests/test_flight_scenarios.py -v
"""

import math
import json
import copy


# =========================================================================
#  1.  Flight Scenario Base
# =========================================================================

from test_telemetry import TelemetryFrame, TelemetryRecorder, \
    TelemetryReplay, ReplayComparator, ReplayMode


class FlightScenario:
    """Base class for repeatable flight test scenarios."""

    def __init__(self, name, description=""):
        self.name = name
        self.description = description
        self._frames = []
        self._recorder = TelemetryRecorder()
        self._actual = TelemetryRecorder()

    def generate(self, num_frames):
        """Generate the scenario telemetry. Override in subclasses."""
        raise NotImplementedError

    def record(self, frames):
        """Record generated frames into the scenario recorder."""
        self._recorder = TelemetryRecorder()
        self._recorder.start()
        for f in frames:
            self._recorder.record_frame(f.frame_index, f.timestamp_s, f)
        self._recorder.stop()
        self._frames = frames

    def get_recorder(self):
        return self._recorder

    def get_frames(self):
        return self._frames

    def score(self, actual_frames):
        """Score the scenario against expected frames.

        Returns a ScenarioResult.
        """
        # Create recorders for comparison
        expected_rec = TelemetryRecorder()
        expected_rec.start()
        for f in self._frames:
            expected_rec.record_frame(f.frame_index, f.timestamp_s, f)
        expected_rec.stop()

        actual_rec = TelemetryRecorder()
        actual_rec.start()
        for f in actual_frames:
            actual_rec.record_frame(f.frame_index, f.timestamp_s, f)
        actual_rec.stop()

        # Compare
        comp = ReplayComparator(tolerance=1e-6)
        result = comp.compare_recordings(expected_rec, actual_rec)

        return ScenarioResult(
            self.name,
            result.consistency_score,
            total_frames=result.total_frames,
            matching_frames=result.matching_frames,
            divergent_frames=result.divergent_frames,
            max_divergence=result.max_divergence,
            avg_divergence=result.avg_divergence,
            consistency_score=result.consistency_score,
            details={
                'scenario': self.name,
                'description': self.description,
                'frames_expected': len(self._frames),
                'frames_actual': len(actual_frames),
                'field_divergences': result.divergence_by_field,
            }
        )


class ScenarioResult:
    """Result of scoring a flight scenario."""

    def __init__(self, name, score, **kwargs):
        self.name = name
        self.score = max(0.0, min(1.0, score))
        self.total_frames = kwargs.get('total_frames', 0)
        self.matching_frames = kwargs.get('matching_frames', 0)
        self.divergent_frames = kwargs.get('divergent_frames', 0)
        self.max_divergence = kwargs.get('max_divergence', 0.0)
        self.avg_divergence = kwargs.get('avg_divergence', 0.0)
        self.consistency_score = kwargs.get('consistency_score', 0.0)
        self.details = kwargs.get('details', {})
        self.passed = self.score >= 0.7

    def to_dict(self):
        return {
            'name': self.name,
            'score': self.score,
            'total_frames': self.total_frames,
            'matching_frames': self.matching_frames,
            'divergent_frames': self.divergent_frames,
            'max_divergence': self.max_divergence,
            'avg_divergence': self.avg_divergence,
            'consistency_score': self.consistency_score,
            'passed': self.passed,
            'details': self.details,
        }

    def __repr__(self):
        status = "PASS" if self.passed else "FAIL"
        return (f"[{status}] {self.name}: score={self.score:.4f} "
                f"({self.matching_frames}/{self.total_frames} frames)")


# =========================================================================
#  2.  Scenario Generator: CAT III Fog Approach
# =========================================================================

class CAT3FogApproach(FlightScenario):
    """CAT III approach in low visibility / fog conditions."""

    def __init__(self, visibility_m=200, rvr_m=175):
        super().__init__(
            "cat3_fog_approach",
            f"CAT III approach with {visibility_m}m visibility, "
            f"RVR {rvr_m}m"
        )
        self.visibility_m = visibility_m
        self.rvr_m = rvr_m

    def generate(self, num_frames=900):
        """Generate 15-second CAT III approach (900 frames at 60fps).

        Approach profile:
          - Starts at 200ft AGL, on glideslope
          - Fog reduces visibility to <200m
          - Flare at 50ft, touchdown at 20ft
          - CAT III guidance active throughout
        """
        frames = []
        # Use 5nm approach at 140kt
        gs_ms = 72.0  # ~140kt
        initial_alt = 200 * 0.3048  # 200ft in meters
        vs_ms = -2.5  # ~500fpm
        flare_alt_m = 15.24  # 50ft

        lat0, lon0 = 51.4775, -0.4614  # EGLL 27L
        rwy_hdg = 270.0

        for i in range(num_frames):
            t = i / 60.0
            progress = i / num_frames
            tf = TelemetryFrame()
            tf.frame_index = i
            tf.timestamp_s = t

            # Position
            tf.ac_lat = lat0
            tf.ac_lon = lon0 - progress * 0.005
            tf.ac_alt_m = initial_alt * (1.0 - progress * 0.95)
            tf.ac_hdg_true = rwy_hdg
            tf.ac_pitch_deg = -2.5
            tf.ac_bank_deg = 0.0
            tf.ac_groundspeed_ms = gs_ms
            tf.ac_true_airspeed_ms = gs_ms
            tf.ac_vertical_speed_ms = vs_ms
            tf.ac_track_deg_true = rwy_hdg
            tf.ac_radio_alt_m = tf.ac_alt_m
            tf.ac_accel_ms2 = 0.0
            tf.ac_on_ground = progress > 0.88

            # FPV
            tf.fpv_x = 512.0
            tf.fpv_y = 400.0 - progress * 200.0
            tf.fpv_on_screen = True
            tf.fpv_valid = True
            tf.fpv_pitch = -2.5
            tf.fpv_drift = 0.0

            # Runway (visible at low altitude even in fog)
            if tf.ac_alt_m < 100:
                tf.runway_valid = True
                tf.runway_visible_count = 4
                screen_size = max(50, int(400 * (1.0 - tf.ac_alt_m / 100)))
                cx, cy = 512.0, 300.0
                tf.runway_corners = [
                    (cx - screen_size, cy - screen_size * 0.3),
                    (cx + screen_size, cy - screen_size * 0.3),
                    (cx + screen_size, cy + screen_size * 0.3),
                    (cx - screen_size, cy + screen_size * 0.3),
                ]
                tf.runway_heading_deg = rwy_hdg

            # Flare
            flare_start = int(num_frames * 0.75)
            touchdown = int(num_frames * 0.88)
            if flare_start <= i < touchdown:
                fl_progress = (i - flare_start) / (touchdown - flare_start)
                tf.flare_active = True
                tf.flare_fully_active = fl_progress > 0.5
                tf.flare_cue_x = 512.0
                tf.flare_cue_y = 350.0 + fl_progress * 50.0
                tf.flare_cue_size = 20.0 + fl_progress * 10.0
                tf.flare_cue_alpha = min(1.0, fl_progress * 2.0)
                tf.flare_rise = fl_progress * 3.0
                tf.flare_error = (1.0 - fl_progress) * 2.0
                tf.flare_vs_cmd = -3.0 + fl_progress * 2.0

            # CAT III — high integrity in fog
            tf.cat3_confidence = 0.95
            tf.system_integrity = 0.96
            tf.ils_integrity = 0.95
            tf.guidance_integrity = 0.97

            # Optical
            tf.optical_brightness = 0.6  # Dimmer in fog
            tf.optical_bloom = 0.15
            tf.optical_phosphor_ms = 3.0

            # Weather
            tf.visibility_m = self.visibility_m
            if tf.ac_radio_alt_m < 60:
                # Slight improvement near ground
                tf.visibility_m = min(self.visibility_m + 50, 800)

            # Minimal turbulence
            tf.turbulence_intensity = 0.05
            tf.jitter_ms = 1.0

            frames.append(tf)

        self.record(frames)
        return frames


# =========================================================================
#  3.  Scenario Generator: Severe Turbulence Approach
# =========================================================================

class SevereTurbulenceApproach(FlightScenario):
    """Approach with severe turbulence."""

    def __init__(self, turbulence_intensity=0.8):
        super().__init__(
            "severe_turbulence_approach",
            f"Approach with {turbulence_intensity:.0%} turbulence"
        )
        self.turbulence_intensity = turbulence_intensity

    def generate(self, num_frames=900):
        frames = []
        gs_ms = 72.0
        initial_alt = 500 * 0.3048  # 500ft
        vs_ms = -3.0
        turbulence = self.turbulence_intensity

        lat0, lon0 = 51.4775, -0.4614
        rwy_hdg = 270.0

        # Turbulence seed
        phase = 0.0

        for i in range(num_frames):
            t = i / 60.0
            progress = i / num_frames
            tf = TelemetryFrame()
            tf.frame_index = i
            tf.timestamp_s = t

            # Turbulence-induced perturbations
            turb_x = math.sin(phase + i * 0.3) * 30.0 * turbulence
            turb_y = math.cos(phase + i * 0.4) * 20.0 * turbulence
            turb_bank = math.sin(i * 0.15) * 5.0 * turbulence
            turb_pitch = math.cos(i * 0.2) * 2.0 * turbulence
            turb_vs = math.sin(i * 0.1) * 2.0 * turbulence

            tf.ac_lat = lat0
            tf.ac_lon = lon0 - progress * 0.005
            tf.ac_alt_m = initial_alt * (1.0 - progress * 0.95)
            tf.ac_hdg_true = rwy_hdg + math.sin(i * 0.1) * 3.0 * turbulence
            tf.ac_pitch_deg = -2.5 + turb_pitch
            tf.ac_bank_deg = turb_bank
            tf.ac_groundspeed_ms = gs_ms + math.sin(i * 0.05) * 5.0 * turbulence
            tf.ac_true_airspeed_ms = tf.ac_groundspeed_ms
            tf.ac_vertical_speed_ms = vs_ms + turb_vs
            tf.ac_track_deg_true = rwy_hdg + turb_bank * 0.3
            tf.ac_radio_alt_m = tf.ac_alt_m
            tf.ac_accel_ms2 = math.sin(i * 0.1) * 2.0 * turbulence
            tf.ac_on_ground = progress > 0.88

            # FPV with turbulence jitter
            tf.fpv_x = 512.0 + turb_x
            tf.fpv_y = 400.0 - progress * 200.0 + turb_y
            tf.fpv_on_screen = True
            tf.fpv_valid = True
            tf.fpv_pitch = -2.5 + turb_pitch
            tf.fpv_drift = turb_bank * 0.5

            # Runway
            if tf.ac_alt_m < 100:
                tf.runway_valid = True
                tf.runway_visible_count = 4
                screen_size = max(50, int(400 * (1.0 - tf.ac_alt_m / 100)))
                tf.runway_corners = [
                    (512 - screen_size + turb_x * 0.3, 300 - screen_size * 0.3),
                    (512 + screen_size + turb_x * 0.3, 300 - screen_size * 0.3),
                    (512 + screen_size + turb_x * 0.3, 300 + screen_size * 0.3),
                    (512 - screen_size + turb_x * 0.3, 300 + screen_size * 0.3),
                ]
                tf.runway_heading_deg = rwy_hdg

            # Flare
            flare_start = int(num_frames * 0.75)
            touchdown = int(num_frames * 0.88)
            if flare_start <= i < touchdown:
                fl_progress = (i - flare_start) / (touchdown - flare_start)
                tf.flare_active = True
                tf.flare_fully_active = fl_progress > 0.5
                tf.flare_cue_x = 512.0 + turb_x * 0.5
                tf.flare_cue_y = 350.0 + fl_progress * 50.0 + turb_y * 0.3
                tf.flare_cue_size = 20.0 + fl_progress * 10.0
                tf.flare_cue_alpha = min(1.0, fl_progress * 2.0)
                tf.flare_rise = fl_progress * 3.0
                tf.flare_error = (1.0 - fl_progress) * 2.0
                tf.flare_vs_cmd = -3.0 + fl_progress * 2.0 + turb_vs

            # CAT III confidence reduced by turbulence
            cat3_reduction = turbulence * 0.2
            tf.cat3_confidence = max(0.5, 0.95 - cat3_reduction)
            tf.system_integrity = max(0.5, 0.95 - cat3_reduction * 0.5)
            tf.ils_integrity = max(0.5, 0.96 - cat3_reduction)
            tf.guidance_integrity = max(0.5, 0.97 - cat3_reduction * 0.5)

            # Turbulence indicator
            tf.turbulence_intensity = turbulence
            tf.jitter_ms = 5.0 + turbulence * 10.0

            # Optical
            tf.optical_brightness = 0.8
            tf.optical_bloom = 0.2
            tf.optical_phosphor_ms = 5.0
            tf.visibility_m = 8000.0

            frames.append(tf)

        self.record(frames)
        return frames


# =========================================================================
#  4.  Scenario Generator: Crosswind Landing
# =========================================================================

class CrosswindLandingTest(FlightScenario):
    """Crosswind landing scenario."""

    def __init__(self, crosswind_kt=20):
        super().__init__(
            "crosswind_landing",
            f"Crosswind landing with {crosswind_kt}kt crosswind"
        )
        self.crosswind_kt = crosswind_kt

    def generate(self, num_frames=900):
        frames = []
        gs_ms = 72.0
        initial_alt = 200 * 0.3048
        vs_ms = -2.5
        crosswind_ms = self.crosswind_kt * 0.514444  # kt to m/s
        drift_deg = math.degrees(math.atan2(crosswind_ms, gs_ms))

        lat0, lon0 = 51.4775, -0.4614
        rwy_hdg = 270.0
        # Crab into the wind
        crab_angle = drift_deg * 0.7  # 70% crab, 30% sideslip

        for i in range(num_frames):
            t = i / 60.0
            progress = i / num_frames
            tf = TelemetryFrame()
            tf.frame_index = i
            tf.timestamp_s = t

            tf.ac_lat = lat0 + progress * 0.001 * drift_deg * 0.01
            tf.ac_lon = lon0 - progress * 0.005
            tf.ac_alt_m = initial_alt * (1.0 - progress * 0.95)
            tf.ac_hdg_true = rwy_hdg + crab_angle
            tf.ac_pitch_deg = -2.5
            tf.ac_bank_deg = -drift_deg * 0.3  # bank into wind
            tf.ac_groundspeed_ms = gs_ms
            tf.ac_true_airspeed_ms = gs_ms + crosswind_ms * 0.1
            tf.ac_vertical_speed_ms = vs_ms
            tf.ac_track_deg_true = rwy_hdg  # Track aligned with runway
            tf.ac_radio_alt_m = tf.ac_alt_m
            tf.ac_accel_ms2 = 0.0
            tf.ac_on_ground = progress > 0.88

            # FPV offset by crosswind
            tf.fpv_x = 512.0 - drift_deg * 5.0
            tf.fpv_y = 400.0 - progress * 200.0
            tf.fpv_on_screen = True
            tf.fpv_valid = True
            tf.fpv_pitch = -2.5
            tf.fpv_drift = drift_deg

            # Runway
            if tf.ac_alt_m < 100:
                tf.runway_valid = True
                tf.runway_visible_count = 4
                screen_size = max(50, int(400 * (1.0 - tf.ac_alt_m / 100)))
                offset = drift_deg * 2.0  # Runway appears offset
                tf.runway_corners = [
                    (512 - screen_size + offset, 300 - screen_size * 0.3),
                    (512 + screen_size + offset, 300 - screen_size * 0.3),
                    (512 + screen_size + offset, 300 + screen_size * 0.3),
                    (512 - screen_size + offset, 300 + screen_size * 0.3),
                ]
                tf.runway_heading_deg = rwy_hdg

            # Normal flare
            flare_start = int(num_frames * 0.75)
            touchdown = int(num_frames * 0.88)
            if flare_start <= i < touchdown:
                fl_progress = (i - flare_start) / (touchdown - flare_start)
                tf.flare_active = True
                tf.flare_fully_active = fl_progress > 0.5
                tf.flare_cue_x = 512.0 - drift_deg * 3.0
                tf.flare_cue_y = 350.0 + fl_progress * 50.0
                tf.flare_cue_size = 20.0 + fl_progress * 10.0
                tf.flare_cue_alpha = min(1.0, fl_progress * 2.0)
                tf.flare_rise = fl_progress * 3.0
                tf.flare_error = (1.0 - fl_progress) * 2.0
                tf.flare_vs_cmd = -3.0 + fl_progress * 2.0

            tf.cat3_confidence = 0.90
            tf.system_integrity = 0.92
            tf.ils_integrity = 0.90
            tf.guidance_integrity = 0.93
            tf.turbulence_intensity = 0.1
            tf.jitter_ms = 2.0
            tf.optical_brightness = 0.8
            tf.optical_bloom = 0.2
            tf.optical_phosphor_ms = 5.0
            tf.visibility_m = 10000.0

            frames.append(tf)

        self.record(frames)
        return frames


# =========================================================================
#  5.  Scenario Generator: Wet Runway Rollout
# =========================================================================

class WetRunwayRolloutTest(FlightScenario):
    """Rollout on wet runway with reduced braking."""

    def __init__(self, braking_coefficient=0.4):
        super().__init__(
            "wet_runway_rollout",
            f"Wet runway rollout with μ={braking_coefficient}"
        )
        self.braking_coefficient = braking_coefficient

    def generate(self, num_frames=900):
        frames = []
        gs_ms = 72.0
        lat0, lon0 = 51.4775, -0.4614
        rwy_hdg = 270.0
        braking = self.braking_coefficient
        wet_decel = 1.47 * braking  # Reduced braking

        touchdown_frame = int(num_frames * 0.80)
        rollout_start = touchdown_frame

        lat_deviation = 0.0

        for i in range(num_frames):
            t = i / 60.0
            progress = i / num_frames
            tf = TelemetryFrame()
            tf.frame_index = i
            tf.timestamp_s = t

            tf.ac_lat = lat0
            tf.ac_lon = lon0 - progress * 0.008
            tf.ac_hdg_true = rwy_hdg
            tf.ac_pitch_deg = -2.5 if progress < 0.8 else 0.0
            tf.ac_bank_deg = 0.0

            if i >= touchdown_frame:
                roll_progress = (i - touchdown_frame) / (num_frames - touchdown_frame)
                remaining_speed = gs_ms * (1.0 - roll_progress * wet_decel)
                tf.ac_groundspeed_ms = max(5.0, remaining_speed)
                tf.ac_true_airspeed_ms = tf.ac_groundspeed_ms
                tf.ac_vertical_speed_ms = 0.0
                tf.ac_on_ground = True
                tf.ac_radio_alt_m = 0.0

                # Lateral drift on wet runway
                lat_deviation += (0.5 - 0.5 * braking) * 0.01
                tf.ac_lat += lat_deviation
                tf.ac_hdg_true = rwy_hdg + lat_deviation * 10.0
            else:
                tf.ac_groundspeed_ms = gs_ms
                tf.ac_true_airspeed_ms = gs_ms
                tf.ac_vertical_speed_ms = -2.5
                tf.ac_on_ground = False
                tf.ac_radio_alt_m = tf.ac_alt_m

            tf.ac_track_deg_true = tf.ac_hdg_true
            tf.ac_accel_ms2 = -wet_decel if i >= touchdown_frame else 0.0
            tf.ac_alt_m = max(0, 60 * (1.0 - progress * 0.95))

            # FPV
            tf.fpv_x = 512.0
            tf.fpv_y = 300.0 if i >= touchdown_frame else 400.0 - progress * 200.0
            tf.fpv_on_screen = True
            tf.fpv_valid = True
            tf.fpv_pitch = 0.0
            tf.fpv_drift = lat_deviation * 5.0

            # Runway
            tf.runway_valid = True
            tf.runway_visible_count = 4
            offset = lat_deviation * 50.0
            tf.runway_corners = [
                (412 + offset, 280), (612 + offset, 280),
                (612 + offset, 320), (412 + offset, 320),
            ]
            tf.runway_heading_deg = rwy_hdg

            # Rollout
            if i >= rollout_start:
                tf.rollout_active = True
                tf.rollout_steering = -lat_deviation * 20.0
                tf.rollout_centerline_error = lat_deviation * 10.0
                tf.rollout_confidence = max(0.3, 0.7 - lat_deviation * 2.0)
                tf.rollout_nosewheel = min(1.0, roll_progress * 2.0) if i >= rollout_start else 0.0

            tf.cat3_confidence = 0.85 if i >= touchdown_frame else 0.95
            tf.system_integrity = 0.85 if i >= touchdown_frame else 0.95
            tf.ils_integrity = 0.80 if i >= touchdown_frame else 0.95
            tf.guidance_integrity = 0.85 if i >= touchdown_frame else 0.95
            tf.turbulence_intensity = 0.05
            tf.jitter_ms = 1.0
            tf.optical_brightness = 0.75
            tf.optical_bloom = 0.18
            tf.optical_phosphor_ms = 5.0
            tf.visibility_m = 5000.0

            frames.append(tf)

        self.record(frames)
        return frames


# =========================================================================
#  6.  Scenario Generator: Rejected Landing / Go-Around
# =========================================================================

class RejectedLandingTest(FlightScenario):
    """Rejected landing with go-around maneuver."""

    def __init__(self):
        super().__init__(
            "rejected_landing",
            "Rejected landing with go-around at 50ft"
        )

    def generate(self, num_frames=1200):
        frames = []
        gs_ms = 72.0
        initial_alt = 200 * 0.3048
        lat0, lon0 = 51.4775, -0.4614
        rwy_hdg = 270.0

        go_around_frame = int(num_frames * 0.60)

        for i in range(num_frames):
            t = i / 60.0
            progress = i / num_frames
            tf = TelemetryFrame()
            tf.frame_index = i
            tf.timestamp_s = t

            if i < go_around_frame:
                # Descent
                alt_progress = i / go_around_frame
                tf.ac_alt_m = initial_alt * (1.0 - alt_progress * 0.95)
                tf.ac_pitch_deg = -2.5
                tf.ac_vertical_speed_ms = -3.0
                tf.ac_groundspeed_ms = gs_ms
                tf.ac_on_ground = False
            else:
                # Go-around: climb out
                ga_progress = (i - go_around_frame) / (num_frames - go_around_frame)
                tf.ac_alt_m = 10 + ga_progress * 200
                tf.ac_pitch_deg = 8.0 + ga_progress * 2.0  # Pitch up
                tf.ac_vertical_speed_ms = 5.0 + ga_progress * 3.0
                tf.ac_groundspeed_ms = gs_ms * (1.0 + ga_progress * 0.2)
                tf.ac_on_ground = False

            tf.ac_lat = lat0
            tf.ac_lon = lon0 - progress * 0.005
            tf.ac_hdg_true = rwy_hdg
            tf.ac_bank_deg = 0.0 if i < go_around_frame else 5.0
            tf.ac_true_airspeed_ms = tf.ac_groundspeed_ms
            tf.ac_track_deg_true = rwy_hdg
            tf.ac_radio_alt_m = max(0, tf.ac_alt_m)
            tf.ac_accel_ms2 = 2.0 if i >= go_around_frame else 0.0

            # FPV
            tf.fpv_x = 512.0
            tf.fpv_y = 400.0 - (i / go_around_frame) * 200.0 \
                if i < go_around_frame else 200.0
            tf.fpv_on_screen = True
            tf.fpv_valid = True
            tf.fpv_pitch = tf.ac_pitch_deg
            tf.fpv_drift = 0.0

            # Runway
            if i < go_around_frame + 30 and tf.ac_alt_m < 60:
                tf.runway_valid = True
                tf.runway_visible_count = 4
                screen_size = max(50, int(300 * (1.0 - tf.ac_alt_m / 60)))
                tf.runway_corners = [
                    (512 - screen_size, 300 - screen_size * 0.3),
                    (512 + screen_size, 300 - screen_size * 0.3),
                    (512 + screen_size, 300 + screen_size * 0.3),
                    (512 - screen_size, 300 + screen_size * 0.3),
                ]
                tf.runway_heading_deg = rwy_hdg
            else:
                tf.runway_valid = False
                tf.runway_visible_count = 0

            # Flare started then rejected
            if go_around_frame - 60 <= i < go_around_frame:
                fl_progress = (i - (go_around_frame - 60)) / 60.0
                tf.flare_active = True
                tf.flare_fully_active = fl_progress > 0.5
                tf.flare_cue_x = 512.0
                tf.flare_cue_y = 350.0 + fl_progress * 50.0
                tf.flare_cue_size = 20.0 + fl_progress * 10.0
                tf.flare_cue_alpha = min(1.0, fl_progress * 2.0)
                tf.flare_rise = fl_progress * 3.0
                tf.flare_error = (1.0 - fl_progress) * 2.0
                tf.flare_vs_cmd = -3.0 + fl_progress * 2.0

            tf.cat3_confidence = 0.90 if i < go_around_frame else 0.60
            tf.system_integrity = 0.92 if i < go_around_frame else 0.70
            tf.ils_integrity = 0.90 if i < go_around_frame else 0.50
            tf.guidance_integrity = 0.92 if i < go_around_frame else 0.65

            tf.turbulence_intensity = 0.05
            tf.jitter_ms = 1.0
            tf.optical_brightness = 0.8
            tf.optical_bloom = 0.2
            tf.optical_phosphor_ms = 5.0
            tf.visibility_m = 10000.0

            frames.append(tf)

        self.record(frames)
        return frames


# =========================================================================
#  7.  Scenario Generator: Night Operation
# =========================================================================

class NightOperationTest(FlightScenario):
    """Night operation with reduced ambient light."""

    def __init__(self):
        super().__init__(
            "night_operation",
            "Night approach and landing"
        )

    def generate(self, num_frames=900):
        frames = []
        gs_ms = 72.0
        initial_alt = 200 * 0.3048
        vs_ms = -2.5
        lat0, lon0 = 51.4775, -0.4614
        rwy_hdg = 270.0

        for i in range(num_frames):
            t = i / 60.0
            progress = i / num_frames
            tf = TelemetryFrame()
            tf.frame_index = i
            tf.timestamp_s = t

            tf.ac_lat = lat0
            tf.ac_lon = lon0 - progress * 0.005
            tf.ac_alt_m = initial_alt * (1.0 - progress * 0.95)
            tf.ac_hdg_true = rwy_hdg
            tf.ac_pitch_deg = -2.5
            tf.ac_bank_deg = 0.0
            tf.ac_groundspeed_ms = gs_ms
            tf.ac_true_airspeed_ms = gs_ms
            tf.ac_vertical_speed_ms = vs_ms
            tf.ac_track_deg_true = rwy_hdg
            tf.ac_radio_alt_m = tf.ac_alt_m
            tf.ac_accel_ms2 = 0.0
            tf.ac_on_ground = progress > 0.88

            # FPV
            tf.fpv_x = 512.0
            tf.fpv_y = 400.0 - progress * 200.0
            tf.fpv_on_screen = True
            tf.fpv_valid = True
            tf.fpv_pitch = -2.5
            tf.fpv_drift = 0.0

            # Runway
            if tf.ac_alt_m < 100:
                tf.runway_valid = True
                tf.runway_visible_count = 4
                screen_size = max(50, int(400 * (1.0 - tf.ac_alt_m / 100)))
                tf.runway_corners = [
                    (512 - screen_size, 300 - screen_size * 0.3),
                    (512 + screen_size, 300 - screen_size * 0.3),
                    (512 + screen_size, 300 + screen_size * 0.3),
                    (512 - screen_size, 300 + screen_size * 0.3),
                ]
                tf.runway_heading_deg = rwy_hdg

            # Flare
            flare_start = int(num_frames * 0.75)
            touchdown = int(num_frames * 0.88)
            if flare_start <= i < touchdown:
                fl_progress = (i - flare_start) / (touchdown - flare_start)
                tf.flare_active = True
                tf.flare_fully_active = fl_progress > 0.5
                tf.flare_cue_x = 512.0
                tf.flare_cue_y = 350.0 + fl_progress * 50.0
                tf.flare_cue_size = 20.0 + fl_progress * 10.0
                tf.flare_cue_alpha = min(1.0, fl_progress * 2.0)
                tf.flare_rise = fl_progress * 3.0
                tf.flare_error = (1.0 - fl_progress) * 2.0
                tf.flare_vs_cmd = -3.0 + fl_progress * 2.0

            # CAT III
            tf.cat3_confidence = 0.92
            tf.system_integrity = 0.94
            tf.ils_integrity = 0.93
            tf.guidance_integrity = 0.95

            # Night optical settings
            tf.optical_brightness = 0.35  # Dimmer at night
            tf.optical_bloom = 0.4  # More bloom in dark
            tf.optical_phosphor_ms = 15.0  # More phosphor persistence
            tf.visibility_m = 8000.0
            tf.turbulence_intensity = 0.05
            tf.jitter_ms = 1.0

            frames.append(tf)

        self.record(frames)
        return frames


# =========================================================================
#  8.  Validation Report Generator
# =========================================================================

class ValidationReport:
    """Generates structured validation reports for flight scenarios."""

    def __init__(self, title="HUD Validation Report"):
        self.title = title
        self.results = []
        self.metadata = {}

    def add_result(self, result):
        self.results.append(result)

    def add_metadata(self, key, value):
        self.metadata[key] = value

    def overall_score(self):
        if not self.results:
            return 0.0
        return sum(r.score for r in self.results) / len(self.results)

    def all_passed(self):
        return all(r.passed for r in self.results)

    def to_dict(self):
        return {
            'title': self.title,
            'metadata': self.metadata,
            'overall_score': self.overall_score(),
            'all_passed': self.all_passed(),
            'num_scenarios': len(self.results),
            'num_passed': sum(1 for r in self.results if r.passed),
            'num_failed': sum(1 for r in self.results if not r.passed),
            'results': [r.to_dict() for r in self.results],
        }

    def to_json(self, indent=2):
        return json.dumps(self.to_dict(), indent=indent)

    def summary(self):
        lines = [
            f"=== {self.title} ===",
            f"Overall Score: {self.overall_score():.4f}",
            f"Status: {'ALL PASS' if self.all_passed() else 'SOME FAILED'}",
            f"Scenarios: {len(self.results)} total, "
            f"{sum(1 for r in self.results if r.passed)} passed, "
            f"{sum(1 for r in self.results if not r.passed)} failed",
            "",
        ]
        for r in self.results:
            status = "✓" if r.passed else "✗"
            lines.append(f"  {status} {r.name}: {r.score:.4f} "
                         f"({r.matching_frames}/{r.total_frames})")
        lines.append("=" * 40)
        return "\n".join(lines)


# =========================================================================
#  9.  Scenario Comparison Tool
# =========================================================================

class ScenarioComparator:
    """Compare outputs from two scenario runs."""

    def compare(self, scenario_a, scenario_b):
        """Compare two scenarios.

        Returns dict with comparison metrics.
        """
        frames_a = scenario_a.get_frames()
        frames_b = scenario_b.get_frames()

        n = min(len(frames_a), len(frames_b))

        comp = ReplayComparator(tolerance=1e-6)
        rec_a = TelemetryRecorder()
        rec_b = TelemetryRecorder()
        rec_a.start()
        rec_b.start()

        for i in range(n):
            rec_a.record_frame(i, i / 60.0, frames_a[i])
            rec_b.record_frame(i, i / 60.0, frames_b[i])

        rec_a.stop()
        rec_b.stop()

        comparison = comp.compare_recordings(rec_a, rec_b)

        return {
            'similarity_score': comparison.consistency_score,
            'matching_frames': comparison.matching_frames,
            'divergent_frames': comparison.divergent_frames,
            'max_divergence': comparison.max_divergence,
            'avg_divergence': comparison.avg_divergence,
            'field_divergences': comparison.divergence_by_field,
            'total_frames': n,
        }


# =========================================================================
#  10.  TESTS — Scenario Generation
# =========================================================================

class TestScenarioGeneration:
    """Tests for scenario generation."""

    def test_cat3_fog_generates_frames(self):
        scenario = CAT3FogApproach()
        frames = scenario.generate(600)
        assert len(frames) == 600
        assert frames[0].visibility_m < 300

    def test_cat3_fog_high_integrity(self):
        scenario = CAT3FogApproach()
        frames = scenario.generate(600)
        # CAT III integrity should be high
        for f in frames:
            assert f.cat3_confidence > 0.5
            assert f.system_integrity > 0.5

    def test_cat3_fog_weather(self):
        scenario = CAT3FogApproach(visibility_m=150)
        frames = scenario.generate(100)
        for f in frames:
            assert f.visibility_m <= 300

    def test_turbulence_approach(self):
        scenario = SevereTurbulenceApproach(0.8)
        frames = scenario.generate(600)
        assert len(frames) == 600
        # Should have significant jitter
        jitter_values = [f.jitter_ms for f in frames]
        assert max(jitter_values) > 5.0

    def test_turbulence_fpv_jitter(self):
        scenario = SevereTurbulenceApproach(0.8)
        frames = scenario.generate(600)
        fpv_x_values = [f.fpv_x for f in frames]
        # FPV should vary due to turbulence
        assert max(fpv_x_values) - min(fpv_x_values) > 10.0

    def test_crosswind_landing(self):
        scenario = CrosswindLandingTest(20)
        frames = scenario.generate(600)
        assert len(frames) == 600
        # Should have drift
        drift_values = [abs(f.fpv_drift) for f in frames if f.fpv_valid]
        assert max(drift_values) > 1.0

    def test_crosswind_bank(self):
        scenario = CrosswindLandingTest(25)
        frames = scenario.generate(600)
        # Should have bank into wind
        bank_values = [abs(f.ac_bank_deg) for f in frames]
        assert max(bank_values) > 0.5

    def test_wet_runway_rollout(self):
        scenario = WetRunwayRolloutTest(0.4)
        frames = scenario.generate(600)
        assert len(frames) == 600
        # Should have rollout frames
        rollout_frames = [f for f in frames if f.rollout_active]
        assert len(rollout_frames) > 0

    def test_wet_runway_lateral_drift(self):
        scenario = WetRunwayRolloutTest(0.4)
        frames = scenario.generate(600)
        rollout_frames = [f for f in frames if f.rollout_active]
        # At least some centerline error on wet runway
        errors = [abs(f.rollout_centerline_error) for f in rollout_frames]
        if errors:
            assert max(errors) > 0.01

    def test_rejected_landing(self):
        scenario = RejectedLandingTest()
        frames = scenario.generate(1200)
        assert len(frames) == 1200
        # Should have go-around with positive vertical speed
        vs_values = [f.ac_vertical_speed_ms for f in frames]
        assert max(vs_values) > 3.0  # Climb out

    def test_night_operation(self):
        scenario = NightOperationTest()
        frames = scenario.generate(600)
        assert len(frames) == 600
        # Night = dimmer, more bloom, more phosphor
        assert frames[0].optical_brightness < 0.5
        assert frames[0].optical_phosphor_ms > 5.0


# =========================================================================
#  11.  TESTS — Scenario Scoring
# =========================================================================

class TestScenarioScoring:
    """Tests for scenario scoring."""

    def test_perfect_match(self):
        scenario = CAT3FogApproach()
        frames = scenario.generate(300)
        result = scenario.score(frames)
        assert result.passed is True
        assert result.score >= 0.99

    def test_poor_match(self):
        scenario = CAT3FogApproach()
        frames = scenario.generate(300)
        # Alter frames
        bad_frames = []
        for f in frames:
            modified = copy.deepcopy(f)
            modified.ac_lat += 10.0  # Large offset
            bad_frames.append(modified)

        result = scenario.score(bad_frames)
        assert result.score < 0.5

    def test_wrong_frame_count(self):
        scenario = CAT3FogApproach()
        frames = scenario.generate(300)
        partial = frames[:100]
        result = scenario.score(partial)
        # Should still produce a result
        assert result.score >= 0

    def test_result_serialization(self):
        scenario = CAT3FogApproach()
        frames = scenario.generate(300)
        result = scenario.score(frames)
        d = result.to_dict()
        assert 'name' in d
        assert 'score' in d
        assert d['passed'] is True


# =========================================================================
#  12.  TESTS — Scenario Comparison
# =========================================================================

class TestScenarioComparison:
    """Tests for scenario comparison."""

    def test_same_scenario_high_similarity(self):
        scenario = CAT3FogApproach()
        frames = scenario.generate(300)
        # Run same scenario twice
        s2 = CAT3FogApproach()
        s2.record(copy.deepcopy(frames))

        comp = ScenarioComparator()
        result = comp.compare(scenario, s2)
        assert result['similarity_score'] > 0.99

    def test_different_scenarios_low_similarity(self):
        fog = CAT3FogApproach()
        fog.generate(300)
        turb = SevereTurbulenceApproach(0.8)
        turb.generate(300)

        comp = ScenarioComparator()
        result = comp.compare(fog, turb)
        assert result['similarity_score'] < 0.95  # Should differ

    def test_comparison_report(self):
        fog = CAT3FogApproach()
        fog.generate(300)
        s2 = CAT3FogApproach()
        s2.record(copy.deepcopy(fog.get_frames()))

        comp = ScenarioComparator()
        result = comp.compare(fog, s2)
        assert result['total_frames'] > 0
        assert result['matching_frames'] > 0


# =========================================================================
#  13.  TESTS — Validation Reports
# =========================================================================

class TestValidationReports:
    """Tests for validation report generation."""

    def test_report_empty(self):
        report = ValidationReport()
        assert report.overall_score() == 0.0
        assert report.all_passed() is True

    def test_report_with_results(self):
        report = ValidationReport("Test Report")
        for scenario in [CAT3FogApproach(), SevereTurbulenceApproach(),
                          CrosswindLandingTest()]:
            scenario.generate(300)
            result = scenario.score(scenario.get_frames())
            report.add_result(result)

        assert report.overall_score() > 0.5
        assert report.all_passed() is True

    def test_report_partial_failure(self):
        report = ValidationReport()
        scenario = CAT3FogApproach()
        scenario.generate(300)
        bad_frames = []
        for f in scenario.get_frames():
            modified = copy.deepcopy(f)
            modified.ac_lat = 999.0
            bad_frames.append(modified)

        result = scenario.score(bad_frames)
        report.add_result(result)
        assert report.overall_score() < 0.5
        assert report.all_passed() is False

    def test_report_json_serialization(self):
        report = ValidationReport("JSON Test")
        scenario = CAT3FogApproach()
        scenario.generate(300)
        result = scenario.score(scenario.get_frames())
        report.add_result(result)
        json_str = report.to_json()
        d = json.loads(json_str)
        assert d['title'] == "JSON Test"
        assert d['num_scenarios'] == 1

    def test_report_summary(self):
        report = ValidationReport("Summary Test")
        scenario = CAT3FogApproach()
        scenario.generate(300)
        result = scenario.score(scenario.get_frames())
        report.add_result(result)
        summary = report.summary()
        assert "Summary Test" in summary
        assert "ALL PASS" in summary or "SOME FAILED" in summary
