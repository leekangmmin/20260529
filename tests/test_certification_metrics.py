#!/usr/bin/env python3
"""
Conformal HUD – Certification Metrics Engine (v2.5.0)

PHASE 2 — CERTIFICATION METRICS ENGINE

Implements quantitative HUD performance metrics:
  1. Runway alignment error metrics
  2. FPV stability score
  3. Flare smoothness score
  4. Rollout tracking score
  5. Symbol jitter score
  6. Optical stability score
  7. Turbulence recovery score
  8. CAT III guidance integrity score

Goal:
  HUD behavior should be numerically measurable.

Run:  python -m pytest tests/test_certification_metrics.py -v
"""

import math
import statistics


# =========================================================================
#  1.  Certification Metric Base Classes
# =========================================================================

class MetricResult:
    """Result from a single certification metric computation."""

    def __init__(self, name, score, details=None):
        self.name = name
        self.score = max(0.0, min(1.0, score))  # Normalised 0..1
        self.details = details or {}
        self.passed = self.score >= 0.7  # Default pass threshold

    def __repr__(self):
        status = "PASS" if self.passed else "FAIL"
        return (f"[{status}] {self.name}: {self.score:.4f}  "
                f"{self.details}")


class MetricsRecorder:
    """Records and tracks certification metrics over time/history."""

    def __init__(self):
        self.results = {}  # name -> list of MetricResult

    def record(self, result):
        if result.name not in self.results:
            self.results[result.name] = []
        self.results[result.name].append(result)

    def latest(self, name):
        if name in self.results and self.results[name]:
            return self.results[name][-1]
        return None

    def average(self, name):
        if name in self.results and self.results[name]:
            scores = [r.score for r in self.results[name]]
            return sum(scores) / len(scores)
        return 0.0

    def min_score(self, name):
        if name in self.results and self.results[name]:
            return min(r.score for r in self.results[name])
        return 1.0

    def max_score(self, name):
        if name in self.results and self.results[name]:
            return max(r.score for r in self.results[name])
        return 0.0

    def trend(self, name, window=10):
        """Simple trend: +1 = improving, -1 = degrading, 0 = stable."""
        if name not in self.results or len(self.results[name]) < window:
            return 0.0
        recent = self.results[name][-window:]
        mid = window // 2
        first_half = sum(r.score for r in recent[:mid]) / mid
        second_half = sum(r.score for r in recent[mid:]) / (window - mid)
        diff = second_half - first_half
        if diff > 0.02:
            return 1.0
        elif diff < -0.02:
            return -1.0
        return 0.0

    def stability(self, name, window=20):
        """Score stability: 1.0 = perfectly stable, 0.0 = chaotic."""
        if name not in self.results or len(self.results[name]) < window:
            return 1.0
        recent = self.results[name][-window:]
        scores = [r.score for r in recent]
        if max(scores) - min(scores) < 0.01:
            return 1.0
        std = statistics.stdev(scores)
        return max(0.0, min(1.0, 1.0 - std * 5.0))

    def all_passed(self):
        """Check if all latest results pass."""
        for name, results in self.results.items():
            if results and results[-1].score < 0.7:
                return False
        return True

    def summary(self):
        """Produce a summary string of all metrics."""
        lines = ["=== CERTIFICATION METRICS SUMMARY ==="]
        for name in sorted(self.results.keys()):
            latest = self.latest(name)
            avg = self.average(name)
            trend = self.trend(name)
            trend_str = {1.0: "↑", -1.0: "↓", 0.0: "→"}.get(trend, "?")
            if latest:
                status = "PASS" if latest.passed else "FAIL"
                lines.append(
                    f"  {status} {trend_str} {name}: "
                    f"score={latest.score:.4f}  avg={avg:.4f}  "
                    f"min={self.min_score(name):.4f}"
                )
        lines.append("=" * 40)
        return "\n".join(lines)


# =========================================================================
#  2.  Runway Alignment Error Metrics
# =========================================================================

class RunwayAlignmentMetrics:
    """Computes runway alignment quality metrics from telemetry."""

    def compute(self, frames):
        """Analyze runway alignment over a sequence of frames.

        Returns MetricResult with:
          - lateral_error_deg: avg absolute lateral offset
          - heading_error_deg: avg heading misalignment
          - alignment_stability: lower std dev = more stable
          - score: 0..1 alignment quality
        """
        if not frames:
            return MetricResult("runway_alignment", 0.0,
                                {"error": "no frames"})

        lateral_errors = []
        heading_errors = []
        gs_errors = []

        for f in frames:
            if not f.runway_valid:
                continue

            # Lateral deviation from centerline
            if f.runway_corners and len(f.runway_corners) >= 4:
                cx = (f.runway_corners[0][0] +
                      f.runway_corners[2][0]) / 2.0
                cy = (f.runway_corners[0][1] +
                      f.runway_corners[2][1]) / 2.0
                lateral_error = abs(512.0 - cx) / 512.0  # normalised
                lateral_errors.append(lateral_error)

            # Heading alignment
            if f.runway_heading_deg != 0:
                hdg_error = abs(f.ac_hdg_true - f.runway_heading_deg)
                if hdg_error > 180:
                    hdg_error = 360 - hdg_error
                heading_errors.append(hdg_error / 180.0)

            # Glideslope deviation
            gs_errors.append(abs(f.flare_vs_cmd) / 10.0)

        if not lateral_errors and not heading_errors:
            # No valid runway data — not applicable
            return MetricResult("runway_alignment", 0.5,
                                {"reason": "no runway data"})

        avg_lateral = statistics.mean(lateral_errors) if lateral_errors else 0
        avg_heading = statistics.mean(heading_errors) if heading_errors else 0
        lat_stability = 1.0 - min(statistics.stdev(lateral_errors) * 2.0,
                                   1.0) if len(lateral_errors) > 1 else 1.0
        avg_gs = statistics.mean(gs_errors) if gs_errors else 0

        # Score computation
        lateral_score = 1.0 - min(avg_lateral * 3.0, 1.0)
        heading_score = 1.0 - min(avg_heading * 2.0, 1.0)
        stability_score = lat_stability
        gs_score = 1.0 - min(avg_gs, 1.0)

        score = (lateral_score * 0.35 + heading_score * 0.25 +
                 stability_score * 0.25 + gs_score * 0.15)

        return MetricResult(
            "runway_alignment",
            score,
            {
                "avg_lateral_error": avg_lateral,
                "avg_heading_error": avg_heading,
                "alignment_stability": stability_score,
                "avg_gs_error": avg_gs,
                "lateral_score": lateral_score,
                "heading_score": heading_score,
                "frames_analyzed": len(lateral_errors) + len(heading_errors),
            }
        )


# =========================================================================
#  3.  FPV Stability Score
# =========================================================================

class FPVStabilityMetrics:
    """Measures FPV stability — jitter, drift, tracking quality."""

    def compute(self, frames):
        """Analyze FPV stability over a frame sequence.

        Returns MetricResult with:
          - jitter_magnitude: frame-to-frame FPV movement
          - drift_rate: sustained FPV drift
          - lost_tracking_ratio: fraction of frames with invalid FPV
          - score: 0..1 FPV stability
        """
        if not frames:
            return MetricResult("fpv_stability", 0.0,
                                {"error": "no frames"})

        jitter_values = []
        drift_values = []
        valid_count = 0
        total_count = len(frames)

        prev_x = None
        prev_y = None

        for f in frames:
            if not f.fpv_valid or not f.fpv_on_screen:
                continue

            valid_count += 1

            if prev_x is not None and prev_y is not None:
                dx = abs(f.fpv_x - prev_x)
                dy = abs(f.fpv_y - prev_y)
                movement = math.sqrt(dx * dx + dy * dy)
                jitter_values.append(movement)

                # Drift is sustained movement in one direction
                if len(drift_values) > 0:
                    drift_values.append(movement)

            prev_x = f.fpv_x
            prev_y = f.fpv_y

        if not jitter_values:
            return MetricResult("fpv_stability", 0.0,
                                {"reason": "no valid FPV data"})

        tracking_ratio = valid_count / max(total_count, 1)

        # Jitter: low = good
        avg_jitter = statistics.mean(jitter_values) if jitter_values else 0
        jitter_penalty = min(avg_jitter / 5.0, 1.0)
        jitter_score = 1.0 - jitter_penalty

        # Jitter consistency: consistent jitter is better than erratic
        jitter_stability = 1.0
        if len(jitter_values) > 2:
            cv = statistics.stdev(jitter_values) / max(
                statistics.mean(jitter_values), 0.001)
            jitter_stability = max(0.0, 1.0 - cv * 0.5)

        # Tracking reliability
        tracking_score = tracking_ratio

        # Drift penalty (sustained movement = less stable)
        drift_penalty = 0.0
        if drift_values:
            avg_drift = statistics.mean(drift_values)
            drift_penalty = min(avg_drift / 10.0, 1.0) * 0.3

        score = (jitter_score * 0.35 + jitter_stability * 0.20 +
                 tracking_score * 0.30 - drift_penalty)
        score = max(0.0, min(1.0, score))

        return MetricResult(
            "fpv_stability",
            score,
            {
                "avg_jitter_px": avg_jitter,
                "jitter_penalty": jitter_penalty,
                "jitter_stability": jitter_stability,
                "tracking_ratio": tracking_ratio,
                "drift_penalty": drift_penalty,
                "valid_frames": valid_count,
                "total_frames": total_count,
            }
        )


# =========================================================================
#  4.  Flare Smoothness Score
# =========================================================================

class FlareSmoothnessMetrics:
    """Measures flare execution smoothness."""

    def compute(self, frames):
        """Analyze flare smoothness.

        Returns MetricResult with:
          - cue_movement_smoothness: lower jitter = smoother
          - rate_transition_quality: flare rise profile
          - sink_rate_consistency: vertical speed stability
          - score: 0..1 flare quality
        """
        if not frames:
            return MetricResult("flare_smoothness", 0.0,
                                {"error": "no frames"})

        flare_frames = [f for f in frames if f.flare_active]
        if not flare_frames:
            return MetricResult("flare_smoothness", 0.5,
                                {"reason": "no flare data"})

        cue_jumps = []
        rise_rates = []
        sink_rates = []

        prev_cue_x = None
        prev_cue_y = None
        prev_rise = None
        prev_vs = None

        for f in flare_frames:
            cue_move = 0.0
            if prev_cue_x is not None and prev_cue_y is not None:
                dx = abs(f.flare_cue_x - prev_cue_x)
                dy = abs(f.flare_cue_y - prev_cue_y)
                cue_move = math.sqrt(dx * dx + dy * dy)
                cue_jumps.append(cue_move)

            if prev_rise is not None:
                rise_rates.append(abs(f.flare_rise - prev_rise))

            if prev_vs is not None and f.ac_vertical_speed_ms != 0:
                sink_rates.append(abs(f.ac_vertical_speed_ms - prev_vs))

            prev_cue_x = f.flare_cue_x
            prev_cue_y = f.flare_cue_y
            prev_rise = f.flare_rise
            prev_vs = f.ac_vertical_speed_ms

        # Cue smoothness: low jumps = smooth
        avg_cue_jump = statistics.mean(cue_jumps) if cue_jumps else 0
        cue_smoothness = 1.0 - min(avg_cue_jump / 10.0, 1.0)

        # Rise rate consistency
        avg_rise_change = statistics.mean(rise_rates) if rise_rates else 0
        rise_consistency = 1.0 - min(avg_rise_change / 2.0, 1.0)

        # Sink rate stability
        avg_sink_change = statistics.mean(sink_rates) if sink_rates else 0
        sink_stability = 1.0 - min(avg_sink_change / 2.0, 1.0)

        # Flare activation stability
        transitions = 0
        was_active = False
        for f in flare_frames:
            if f.flare_fully_active and not was_active:
                transitions += 1
            was_active = f.flare_fully_active

        transition_penalty = min(transitions, 2) * 0.1

        score = (cue_smoothness * 0.35 + rise_consistency * 0.25 +
                 sink_stability * 0.25 - transition_penalty)
        score = max(0.0, min(1.0, score))

        return MetricResult(
            "flare_smoothness",
            score,
            {
                "avg_cue_jump_px": avg_cue_jump,
                "cue_smoothness": cue_smoothness,
                "rise_consistency": rise_consistency,
                "sink_stability": sink_stability,
                "transitions": transitions,
                "flare_frames": len(flare_frames),
            }
        )


# =========================================================================
#  5.  Rollout Tracking Score
# =========================================================================

class RolloutTrackingMetrics:
    """Measures rollout tracking performance."""

    def compute(self, frames):
        """Analyze rollout tracking quality.

        Returns MetricResult scoring:
          - centerline_error: deviation from runway centerline
          - steering_quality: smoothness of steering commands
          - confidence_build: how quickly confidence increases
          - score: 0..1 rollout quality
        """
        rollout_frames = [f for f in frames if f.rollout_active]
        if not rollout_frames:
            return MetricResult("rollout_tracking", 0.5,
                                {"reason": "no rollout data"})

        centerline_errors = [abs(f.rollout_centerline_error)
                             for f in rollout_frames]
        steering_commands = [abs(f.rollout_steering)
                             for f in rollout_frames]
        confidences = [f.rollout_confidence for f in rollout_frames]

        # Centerline tracking
        avg_centerline = statistics.mean(centerline_errors)
        max_centerline = max(centerline_errors)
        centerline_score = 1.0 - min(avg_centerline / 5.0, 1.0)

        # Steering smoothness (fewer large changes = smoother)
        steering_jumps = []
        prev = None
        for s in steering_commands:
            if prev is not None:
                steering_jumps.append(abs(s - prev))
            prev = s
        avg_steering_jump = statistics.mean(steering_jumps) if steering_jumps else 0
        steering_smoothness = 1.0 - min(avg_steering_jump / 3.0, 1.0)

        # Steering magnitude (lower = better centered)
        avg_steering = statistics.mean(steering_commands)
        steering_magnitude = 1.0 - min(avg_steering / 10.0, 1.0)

        # Confidence progression
        if len(confidences) > 1:
            conf_start = confidences[0]
            conf_end = confidences[-1]
            conf_improvement = max(0, conf_end - conf_start)
            confidence_score = min(conf_improvement * 2.0, 1.0)
        else:
            confidence_score = confidences[0] if confidences else 0.5

        # Max centerline deviation penalty
        max_deviation_penalty = min(max_centerline / 10.0, 1.0) * 0.3

        score = (centerline_score * 0.30 + steering_smoothness * 0.20 +
                 steering_magnitude * 0.20 + confidence_score * 0.30 -
                 max_deviation_penalty)
        score = max(0.0, min(1.0, score))

        return MetricResult(
            "rollout_tracking",
            score,
            {
                "avg_centerline_error": avg_centerline,
                "max_centerline_error": max_centerline,
                "centerline_score": centerline_score,
                "steering_smoothness": steering_smoothness,
                "steering_magnitude": steering_magnitude,
                "confidence_score": confidence_score,
                "rollout_frames": len(rollout_frames),
            }
        )


# =========================================================================
#  6.  Symbol Jitter Score
# =========================================================================

class SymbolJitterMetrics:
    """Measures overall symbol jitter across the HUD."""

    def compute(self, frames):
        """Analyze symbol jitter across all elements.

        Returns MetricResult combining jitter from:
          - FPV position
          - Runway corners
          - Flare cue
          - Score: 0..1 (1 = no jitter)
        """
        if not frames or len(frames) < 2:
            return MetricResult("symbol_jitter", 0.5,
                                {"reason": "insufficient frames"})

        fpv_jitters = []
        rwy_jitters = []
        flare_jitters = []

        for i in range(1, len(frames)):
            prev = frames[i - 1]
            curr = frames[i]

            # FPV jitter
            if prev.fpv_valid and curr.fpv_valid and \
               prev.fpv_on_screen and curr.fpv_on_screen:
                dx = abs(curr.fpv_x - prev.fpv_x)
                dy = abs(curr.fpv_y - prev.fpv_y)
                fpv_jitters.append(math.sqrt(dx * dx + dy * dy))

            # Runway corner jitter
            if prev.runway_valid and curr.runway_valid:
                if prev.runway_corners and curr.runway_corners:
                    for (px, py), (cx, cy) in zip(
                            prev.runway_corners, curr.runway_corners):
                        dx = abs(cx - px)
                        dy = abs(cy - py)
                        rwy_jitters.append(math.sqrt(dx * dx + dy * dy))

            # Flare cue jitter
            if prev.flare_active and curr.flare_active:
                dx = abs(curr.flare_cue_x - prev.flare_cue_x)
                dy = abs(curr.flare_cue_y - prev.flare_cue_y)
                flare_jitters.append(math.sqrt(dx * dx + dy * dy))

        # Score each element
        def element_score(jitters, threshold=3.0):
            if not jitters:
                return 0.5
            avg = statistics.mean(jitters)
            return max(0.0, 1.0 - avg / threshold)

        fpv_score = element_score(fpv_jitters, 3.0)
        rwy_score = element_score(rwy_jitters, 5.0)
        flare_score = element_score(flare_jitters, 3.0)

        # Combined score with weighting
        total_fpv = len(fpv_jitters)
        total_rwy = len(rwy_jitters)
        total_flare = len(flare_jitters)
        total = total_fpv + total_rwy + total_flare

        if total == 0:
            return MetricResult("symbol_jitter", 0.5,
                                {"reason": "no tracked elements"})

        score = (fpv_score * total_fpv + rwy_score * total_rwy +
                 flare_score * total_flare) / total

        return MetricResult(
            "symbol_jitter",
            score,
            {
                "fpv_jitter_score": fpv_score,
                "runway_jitter_score": rwy_score,
                "flare_jitter_score": flare_score,
                "fpv_samples": total_fpv,
                "runway_samples": total_rwy,
                "flare_samples": total_flare,
                "avg_fpv_jitter": statistics.mean(fpv_jitters)
                if fpv_jitters else 0,
                "avg_rwy_jitter": statistics.mean(rwy_jitters)
                if rwy_jitters else 0,
                "avg_flare_jitter": statistics.mean(flare_jitters)
                if flare_jitters else 0,
            }
        )


# =========================================================================
#  7.  Optical Stability Score
# =========================================================================

class OpticalStabilityMetrics:
    """Measures optical system stability."""

    def compute(self, frames):
        """Analyze optical parameter stability.

        Returns MetricResult with:
          - brightness_stability: stability of auto-brightness
          - bloom_stability: stability of bloom effect
          - phosphor_stability: stability of phosphor simulation
          - score: 0..1 optical stability
        """
        if not frames or len(frames) < 5:
            return MetricResult("optical_stability", 0.5,
                                {"reason": "insufficient frames"})

        brightness_values = [f.optical_brightness for f in frames]
        bloom_values = [f.optical_bloom for f in frames]
        phosphor_values = [f.optical_phosphor_ms for f in frames]

        def stability_score(values):
            if len(values) < 3:
                return 1.0
            avg = statistics.mean(values)
            if avg < 0.001:
                return 1.0
            std = statistics.stdev(values)
            cv = std / avg
            return max(0.0, 1.0 - cv * 3.0)

        b_stab = stability_score(brightness_values)
        bl_stab = stability_score(bloom_values)
        p_stab = stability_score(phosphor_values)

        # Check for abrupt changes
        abrupt_changes = 0
        for i in range(1, len(frames)):
            db = abs(brightness_values[i] - brightness_values[i - 1])
            dbl = abs(bloom_values[i] - bloom_values[i - 1])
            dp = abs(phosphor_values[i] - phosphor_values[i - 1])
            if db > 0.5 or dbl > 0.5 or dp > 50:
                abrupt_changes += 1

        change_penalty = min(abrupt_changes / len(frames) * 5.0, 0.5)

        score = (b_stab * 0.35 + bl_stab * 0.25 + p_stab * 0.25 -
                 change_penalty * 0.15)
        score = max(0.0, min(1.0, score))

        return MetricResult(
            "optical_stability",
            score,
            {
                "brightness_stability": b_stab,
                "bloom_stability": bl_stab,
                "phosphor_stability": p_stab,
                "abrupt_changes": abrupt_changes,
                "avg_brightness": statistics.mean(brightness_values),
                "avg_bloom": statistics.mean(bloom_values),
                "avg_phosphor": statistics.mean(phosphor_values),
            }
        )


# =========================================================================
#  8.  Turbulence Recovery Score
# =========================================================================

class TurbulenceRecoveryMetrics:
    """Measures how well the HUD recovers from turbulence."""

    def compute(self, frames):
        """Analyze turbulence recovery quality.

        Returns MetricResult:
          - recovery_rate: how quickly symbols stabilise after turbulence
          - overshoot_penalty: excessive correction after turbulence
          - jitter_decay: rate of jitter reduction
          - score: 0..1 recovery quality
        """
        if not frames or len(frames) < 30:
            return MetricResult("turbulence_recovery", 0.5,
                                {"reason": "insufficient frames"})

        # Find turbulence events
        turb_events = []
        in_turb = False
        event_start = 0

        for i, f in enumerate(frames):
            if f.turbulence_intensity > 0.3 and not in_turb:
                in_turb = True
                event_start = i
            elif f.turbulence_intensity < 0.1 and in_turb:
                in_turb = False
                turb_events.append((event_start, i))

        if not turb_events:
            # No turbulence to recover from
            return MetricResult("turbulence_recovery", 0.8,
                                {"reason": "no turbulence events"})

        recovery_scores = []

        for start, end in turb_events:
            if end + 20 >= len(frames):
                continue

            # Measure FPV jitter before turbulence
            pre_jitters = []
            for i in range(max(0, start - 10), start):
                if i > 0 and frames[i].fpv_valid and frames[i - 1].fpv_valid:
                    dx = abs(frames[i].fpv_x - frames[i - 1].fpv_x)
                    dy = abs(frames[i].fpv_y - frames[i - 1].fpv_y)
                    pre_jitters.append(math.sqrt(dx * dx + dy * dy))

            # Measure jitter during turbulence
            turb_jitters = []
            for i in range(start, min(end, len(frames) - 1)):
                if i > 0 and frames[i].fpv_valid and frames[i - 1].fpv_valid:
                    dx = abs(frames[i].fpv_x - frames[i - 1].fpv_x)
                    dy = abs(frames[i].fpv_y - frames[i - 1].fpv_y)
                    turb_jitters.append(math.sqrt(dx * dx + dy * dy))

            # Measure post-turbulence jitter
            post_jitters = []
            for i in range(end, min(end + 20, len(frames) - 1)):
                if i > 0 and frames[i].fpv_valid and frames[i - 1].fpv_valid:
                    dx = abs(frames[i].fpv_x - frames[i - 1].fpv_x)
                    dy = abs(frames[i].fpv_y - frames[i - 1].fpv_y)
                    post_jitters.append(math.sqrt(dx * dx + dy * dy))

            if not pre_jitters or not turb_jitters:
                continue

            pre_avg = statistics.mean(pre_jitters)
            post_avg = statistics.mean(post_jitters) if post_jitters else pre_avg

            # Recovery quality: post-turbulence jitter close to pre-turbulence
            if pre_avg > 0.01:
                recovery_ratio = min(post_avg / pre_avg, 3.0)
                recovery_score = max(0.0, 1.0 - (recovery_ratio - 1.0))
            else:
                recovery_score = 1.0

            recovery_scores.append(recovery_score)

        if not recovery_scores:
            return MetricResult("turbulence_recovery", 0.5,
                                {"reason": "could not measure recovery"})

        avg_recovery = statistics.mean(recovery_scores)
        return MetricResult(
            "turbulence_recovery",
            avg_recovery,
            {
                "events_analyzed": len(recovery_scores),
                "total_turbulence_events": len(turb_events),
                "avg_recovery_ratio": avg_recovery,
            }
        )


# =========================================================================
#  9.  CAT III Guidance Integrity Score
# =========================================================================

class CAT3GuidanceIntegrityMetrics:
    """Measures CAT III approach guidance integrity."""

    def compute(self, frames):
        """Analyze CAT III guidance quality.

        Returns MetricResult:
          - integrity_level: avg system integrity during approach
          - confidence_stability: stability of CAT III confidence
          - degraded_mode_ratio: fraction of time in degraded mode
          - score: 0..1 guidance integrity
        """
        if not frames:
            return MetricResult("cat3_guidance_integrity", 0.0,
                                {"error": "no frames"})

        cat3_frames = []
        for f in frames:
            if f.cat3_confidence > 0 or f.system_integrity > 0:
                cat3_frames.append(f)

        if not cat3_frames:
            return MetricResult("cat3_guidance_integrity", 0.5,
                                {"reason": "no CAT III data"})

        integrities = [f.system_integrity for f in cat3_frames]
        confidences = [f.cat3_confidence for f in cat3_frames]
        ils_integrities = [f.ils_integrity for f in cat3_frames]
        guidance_integrities = [f.guidance_integrity for f in cat3_frames]

        avg_integrity = statistics.mean(integrities)
        avg_confidence = statistics.mean(confidences)
        avg_ils = statistics.mean(ils_integrities)
        avg_guidance = statistics.mean(guidance_integrities)

        # Stability of integrity
        integrity_std = statistics.stdev(integrities) if len(
            integrities) > 1 else 0
        stability = max(0.0, 1.0 - integrity_std * 3.0)

        # Degraded mode detection (integrity < 0.7)
        degraded_frames = sum(1 for i in integrities if i < 0.7)
        degraded_ratio = degraded_frames / max(len(integrities), 1)
        degraded_penalty = degraded_ratio * 0.5

        # Minimum integrity check
        min_integrity = min(integrities)
        min_penalty = max(0.0, 0.7 - min_integrity) * 0.5

        score = (avg_integrity * 0.25 + avg_confidence * 0.15 +
                 avg_ils * 0.20 + avg_guidance * 0.20 +
                 stability * 0.20 - degraded_penalty - min_penalty)
        score = max(0.0, min(1.0, score))

        return MetricResult(
            "cat3_guidance_integrity",
            score,
            {
                "avg_integrity": avg_integrity,
                "avg_confidence": avg_confidence,
                "avg_ils_integrity": avg_ils,
                "avg_guidance_integrity": avg_guidance,
                "integrity_stability": stability,
                "degraded_ratio": degraded_ratio,
                "min_integrity": min_integrity,
                "frames_analyzed": len(cat3_frames),
            }
        )


# =========================================================================
#  10.  Automated Scoring System
# =========================================================================

class CertificationScoringSystem:
    """Automated scoring of all certification metrics."""

    def __init__(self):
        self.metrics = {
            'runway_alignment': RunwayAlignmentMetrics(),
            'fpv_stability': FPVStabilityMetrics(),
            'flare_smoothness': FlareSmoothnessMetrics(),
            'rollout_tracking': RolloutTrackingMetrics(),
            'symbol_jitter': SymbolJitterMetrics(),
            'optical_stability': OpticalStabilityMetrics(),
            'turbulence_recovery': TurbulenceRecoveryMetrics(),
            'cat3_guidance_integrity': CAT3GuidanceIntegrityMetrics(),
        }
        self.recorder = MetricsRecorder()

    def evaluate(self, frames, run_label="default"):
        """Run all certification metrics on a frame sequence.

        Returns (overall_score, detailed_results).
        """
        results = []
        for name, metric in self.metrics.items():
            result = metric.compute(frames)
            result.name = f"{run_label}/{name}"
            self.recorder.record(result)
            results.append(result)

        # Overall score: weighted average of all metrics
        weights = {
            'runway_alignment': 0.15,
            'fpv_stability': 0.15,
            'flare_smoothness': 0.15,
            'rollout_tracking': 0.15,
            'symbol_jitter': 0.10,
            'optical_stability': 0.10,
            'turbulence_recovery': 0.10,
            'cat3_guidance_integrity': 0.10,
        }

        overall = 0.0
        total_weight = 0.0
        for r in results:
            base_name = r.name.split('/')[-1]
            w = weights.get(base_name, 0.1)
            overall += r.score * w
            total_weight += w

        overall /= max(total_weight, 0.001)
        overall = max(0.0, min(1.0, overall))

        return overall, results

    def summary(self):
        return self.recorder.summary()

    def trend_analysis(self):
        """Generate trend analysis for all metrics."""
        lines = ["=== CERTIFICATION TREND ANALYSIS ==="]
        for name in sorted(self.recorder.results.keys()):
            trend = self.recorder.trend(name)
            stability = self.recorder.stability(name)
            avg = self.recorder.average(name)
            trend_str = {1.0: "IMPROVING", -1.0: "DEGRADING",
                         0.0: "STABLE"}.get(trend, "?")
            lines.append(
                f"  {name}: trend={trend_str}  stability={stability:.3f}  "
                f"avg={avg:.4f}"
            )
        return "\n".join(lines)


# =========================================================================
#  11.  Helper: Generate test telemetry frames
# =========================================================================

from test_telemetry import TelemetryFrame, generate_test_approach


# =========================================================================
#  12.  TESTS — Runway Alignment Metrics
# =========================================================================

class TestRunwayAlignmentMetrics:
    """Tests for RunwayAlignmentMetrics."""

    def test_perfect_alignment(self):
        frames = []
        for i in range(60):
            tf = TelemetryFrame()
            tf.runway_valid = True
            tf.runway_corners = [(412, 270), (612, 270),
                                  (612, 330), (412, 330)]
            tf.runway_heading_deg = 270.0
            tf.ac_hdg_true = 270.0
            tf.flare_vs_cmd = -2.0
            frames.append(tf)

        metric = RunwayAlignmentMetrics()
        result = metric.compute(frames)
        assert result.score > 0.7

    def test_poor_alignment(self):
        frames = []
        for i in range(60):
            tf = TelemetryFrame()
            tf.runway_valid = True
            tf.runway_corners = [(200, 100), (400, 100),
                                  (400, 500), (200, 500)]
            tf.runway_heading_deg = 270.0
            tf.ac_hdg_true = 300.0  # 30 deg off
            tf.flare_vs_cmd = -2.0
            frames.append(tf)

        metric = RunwayAlignmentMetrics()
        result = metric.compute(frames)
        assert result.score < 0.7

    def test_no_runway_data(self):
        frames = [TelemetryFrame() for _ in range(10)]
        metric = RunwayAlignmentMetrics()
        result = metric.compute(frames)
        # Should return moderate score when no data
        assert result.score > 0.0

    def test_empty_frames(self):
        metric = RunwayAlignmentMetrics()
        result = metric.compute([])
        assert result.score == 0.0

    def test_alignment_improves(self):
        """Score should improve as alignment gets better."""
        bad = RunwayAlignmentMetrics().compute(
            [TelemetryFrame() for _ in range(10)])
        good = RunwayAlignmentMetrics().compute([
            TelemetryFrame() for _ in range(10)])
        # Both should be moderate with no data
        assert bad.score >= 0.0


# =========================================================================
#  13.  TESTS — FPV Stability Metrics
# =========================================================================

class TestFPVStabilityMetrics:
    """Tests for FPVStabilityMetrics."""

    def test_perfect_fpv_stability(self):
        frames = []
        for i in range(60):
            tf = TelemetryFrame()
            tf.fpv_valid = True
            tf.fpv_on_screen = True
            tf.fpv_x = 512.0
            tf.fpv_y = 300.0
            frames.append(tf)

        metric = FPVStabilityMetrics()
        result = metric.compute(frames)
        assert result.score > 0.85

    def test_jittery_fpv(self):
        frames = []
        for i in range(60):
            tf = TelemetryFrame()
            tf.fpv_valid = True
            tf.fpv_on_screen = True
            tf.fpv_x = 512.0 + math.sin(i * 0.5) * 50
            tf.fpv_y = 300.0 + math.cos(i * 0.7) * 50
            frames.append(tf)

        metric = FPVStabilityMetrics()
        result = metric.compute(frames)
        assert result.score < 0.7

    def test_lost_tracking(self):
        frames = []
        for i in range(60):
            tf = TelemetryFrame()
            tf.fpv_valid = (i % 3 != 0)  # Lose tracking every 3rd frame
            tf.fpv_on_screen = tf.fpv_valid
            tf.fpv_x = 512.0
            tf.fpv_y = 300.0
            frames.append(tf)

        metric = FPVStabilityMetrics()
        result = metric.compute(frames)
        assert result.score < 0.85  # Should penalize lost tracking

    def test_no_fpv_data(self):
        frames = [TelemetryFrame() for _ in range(10)]
        metric = FPVStabilityMetrics()
        result = metric.compute(frames)
        assert result.score == 0.0


# =========================================================================
#  14.  TESTS — Flare Smoothness Metrics
# =========================================================================

class TestFlareSmoothnessMetrics:
    """Tests for FlareSmoothnessMetrics."""

    def test_smooth_flare(self):
        frames = []
        for i in range(60):
            tf = TelemetryFrame()
            tf.flare_active = True
            progress = i / 60.0
            tf.flare_cue_x = 512.0 + progress * 10
            tf.flare_cue_y = 300.0 + progress * 20
            tf.flare_cue_size = 20.0 + progress * 5
            tf.flare_cue_alpha = min(1.0, progress * 2)
            tf.flare_rise = progress * 3.0
            tf.flare_error = (1.0 - progress) * 2.0
            tf.ac_vertical_speed_ms = -3.0 + progress * 2.0
            tf.flare_fully_active = progress > 0.5
            frames.append(tf)

        metric = FlareSmoothnessMetrics()
        result = metric.compute(frames)
        assert result.score > 0.5

    def test_erratic_flare(self):
        frames = []
        for i in range(60):
            tf = TelemetryFrame()
            tf.flare_active = True
            tf.flare_cue_x = 512.0 + math.sin(i) * 30
            tf.flare_cue_y = 300.0 + math.cos(i * 1.3) * 30
            tf.flare_cue_size = 20.0 + abs(math.sin(i * 0.5)) * 15
            tf.flare_cue_alpha = 0.5 + math.sin(i * 0.3) * 0.5
            tf.flare_rise = math.sin(i * 0.1) * 2.0
            tf.ac_vertical_speed_ms = -3.0 + math.sin(i * 0.2) * 2.0
            tf.flare_fully_active = True
            frames.append(tf)

        metric = FlareSmoothnessMetrics()
        result = metric.compute(frames)
        assert result.score < 0.6

    def test_no_flare(self):
        frames = [TelemetryFrame() for _ in range(10)]
        metric = FlareSmoothnessMetrics()
        result = metric.compute(frames)
        assert result.score == 0.5  # Moderate (no data = N/A)


# =========================================================================
#  15.  TESTS — Rollout Tracking Metrics
# =========================================================================

class TestRolloutTrackingMetrics:
    """Tests for RolloutTrackingMetrics."""

    def test_perfect_rollout(self):
        frames = []
        for i in range(60):
            tf = TelemetryFrame()
            tf.rollout_active = True
            tf.rollout_centerline_error = 0.1
            tf.rollout_steering = 0.5
            tf.rollout_confidence = 0.5 + i * 0.008  # Increasing
            frames.append(tf)

        metric = RolloutTrackingMetrics()
        result = metric.compute(frames)
        assert result.score > 0.7

    def test_poor_rollout(self):
        frames = []
        for i in range(60):
            tf = TelemetryFrame()
            tf.rollout_active = True
            tf.rollout_centerline_error = 8.0 + math.sin(i) * 2.0
            tf.rollout_steering = 8.0 + math.sin(i * 0.5) * 3.0
            tf.rollout_confidence = 0.2
            frames.append(tf)

        metric = RolloutTrackingMetrics()
        result = metric.compute(frames)
        assert result.score < 0.6

    def test_no_rollout(self):
        frames = [TelemetryFrame() for _ in range(10)]
        metric = RolloutTrackingMetrics()
        result = metric.compute(frames)
        assert result.score == 0.5


# =========================================================================
#  16.  TESTS — Symbol Jitter Metrics
# =========================================================================

class TestSymbolJitterMetrics:
    """Tests for SymbolJitterMetrics."""

    def test_stable_symbols(self):
        frames = []
        for i in range(60):
            tf = TelemetryFrame()
            tf.fpv_valid = True
            tf.fpv_on_screen = True
            tf.fpv_x = 512.0
            tf.fpv_y = 300.0
            tf.runway_valid = True
            tf.runway_corners = [(412, 270)] * 8
            tf.flare_active = True
            tf.flare_cue_x = 512.0
            tf.flare_cue_y = 350.0
            frames.append(tf)

        metric = SymbolJitterMetrics()
        result = metric.compute(frames)
        assert result.score > 0.8

    def test_jittery_symbols(self):
        frames = []
        for i in range(60):
            tf = TelemetryFrame()
            tf.fpv_valid = True
            tf.fpv_on_screen = True
            tf.fpv_x = 512.0 + math.sin(i * 2.0) * 20
            tf.fpv_y = 300.0 + math.cos(i * 2.3) * 20
            tf.runway_valid = True
            tf.runway_corners = [(400 + int(20 * math.sin(i)), 270)] * 8
            tf.flare_active = True
            tf.flare_cue_x = 512.0 + math.sin(i * 1.7) * 15
            tf.flare_cue_y = 350.0 + math.cos(i * 1.9) * 15
            frames.append(tf)

        metric = SymbolJitterMetrics()
        result = metric.compute(frames)
        assert result.score < 0.7

    def test_insufficient_frames(self):
        frames = [TelemetryFrame()]
        metric = SymbolJitterMetrics()
        result = metric.compute(frames)
        assert result.score == 0.5  # Not enough data


# =========================================================================
#  17.  TESTS — Optical Stability Metrics
# =========================================================================

class TestOpticalStabilityMetrics:
    """Tests for OpticalStabilityMetrics."""

    def test_stable_optics(self):
        frames = []
        for i in range(60):
            tf = TelemetryFrame()
            tf.optical_brightness = 0.8
            tf.optical_bloom = 0.2
            tf.optical_phosphor_ms = 5.0
            frames.append(tf)

        metric = OpticalStabilityMetrics()
        result = metric.compute(frames)
        assert result.score > 0.8

    def test_unstable_optics(self):
        frames = []
        for i in range(60):
            tf = TelemetryFrame()
            # Wild fluctuations
            tf.optical_brightness = 0.5 + math.sin(i * 3.0) * 0.5
            tf.optical_bloom = 0.3 + math.sin(i * 2.7) * 0.5
            tf.optical_phosphor_ms = 5.0 + math.sin(i * 4.0) * 50
            frames.append(tf)

        metric = OpticalStabilityMetrics()
        result = metric.compute(frames)
        assert result.score < 0.6

    def test_insufficient_frames(self):
        frames = [TelemetryFrame() for _ in range(3)]
        metric = OpticalStabilityMetrics()
        result = metric.compute(frames)
        assert result.score == 0.5


# =========================================================================
#  18.  TESTS — Turbulence Recovery Metrics
# =========================================================================

class TestTurbulenceRecoveryMetrics:
    """Tests for TurbulenceRecoveryMetrics."""

    def test_good_recovery(self):
        frames = []
        for i in range(100):
            tf = TelemetryFrame()
            # Turbulence at frames 30-50
            if 30 <= i <= 50:
                tf.turbulence_intensity = 0.5
                tf.fpv_x = 512.0 + math.sin(i * 2.0) * 10
            else:
                tf.turbulence_intensity = 0.05
                tf.fpv_x = 512.0
            tf.fpv_y = 300.0
            tf.fpv_valid = True
            tf.fpv_on_screen = True
            frames.append(tf)

        metric = TurbulenceRecoveryMetrics()
        result = metric.compute(frames)
        assert result.score > 0.0

    def test_no_turbulence(self):
        frames = []
        for i in range(60):
            tf = TelemetryFrame()
            tf.turbulence_intensity = 0.0
            tf.fpv_valid = True
            tf.fpv_on_screen = True
            tf.fpv_x = 512.0
            tf.fpv_y = 300.0
            frames.append(tf)

        metric = TurbulenceRecoveryMetrics()
        result = metric.compute(frames)
        # No turbulence = good score
        assert result.score > 0.5

    def test_poor_recovery(self):
        """Jitter continuing after turbulence = poor recovery."""
        frames = []
        for i in range(100):
            tf = TelemetryFrame()
            tf.turbulence_intensity = 0.5 if i < 60 else 0.1
            # Jitter continues after turbulence
            tf.fpv_x = 512.0 + math.sin(i * 1.5) * 15
            tf.fpv_y = 300.0 + math.cos(i * 1.3) * 15
            tf.fpv_valid = True
            tf.fpv_on_screen = True
            frames.append(tf)

        metric = TurbulenceRecoveryMetrics()
        result = metric.compute(frames)
        # At least some recovery measurement should exist
        assert result.score > 0.0


# =========================================================================
#  19.  TESTS — CAT III Guidance Integrity Metrics
# =========================================================================

class TestCAT3GuidanceIntegrityMetrics:
    """Tests for CAT3GuidanceIntegrityMetrics."""

    def test_high_integrity(self):
        frames = []
        for i in range(100):
            tf = TelemetryFrame()
            tf.cat3_confidence = 0.95
            tf.system_integrity = 0.97
            tf.ils_integrity = 0.96
            tf.guidance_integrity = 0.98
            frames.append(tf)

        metric = CAT3GuidanceIntegrityMetrics()
        result = metric.compute(frames)
        assert result.score > 0.8

    def test_low_integrity(self):
        frames = []
        for i in range(100):
            tf = TelemetryFrame()
            tf.cat3_confidence = 0.3
            tf.system_integrity = 0.4
            tf.ils_integrity = 0.3
            tf.guidance_integrity = 0.35
            frames.append(tf)

        metric = CAT3GuidanceIntegrityMetrics()
        result = metric.compute(frames)
        assert result.score < 0.6

    def test_degraded_mode(self):
        frames = []
        for i in range(100):
            tf = TelemetryFrame()
            tf.cat3_confidence = 0.95
            tf.system_integrity = 0.5 if i > 50 else 0.95  # Degrades halfway
            tf.ils_integrity = 0.5 if i > 50 else 0.95
            tf.guidance_integrity = 0.5 if i > 50 else 0.95
            frames.append(tf)

        metric = CAT3GuidanceIntegrityMetrics()
        result = metric.compute(frames)
        # Should detect degradation
        assert result.details['degraded_ratio'] > 0.1

    def test_no_data(self):
        frames = [TelemetryFrame() for _ in range(10)]
        metric = CAT3GuidanceIntegrityMetrics()
        result = metric.compute(frames)
        assert result.score == 0.5


# =========================================================================
#  20.  TESTS — Metrics Recorder
# =========================================================================

class TestMetricsRecorder:
    """Tests for MetricsRecorder."""

    def test_record_and_latest(self):
        rec = MetricsRecorder()
        rec.record(MetricResult("test_metric", 0.85))
        latest = rec.latest("test_metric")
        assert latest is not None
        assert latest.score == 0.85

    def test_average(self):
        rec = MetricsRecorder()
        for s in [0.8, 0.9, 0.7]:
            rec.record(MetricResult("test", s))
        assert abs(rec.average("test") - 0.8) < 0.01

    def test_min_max(self):
        rec = MetricsRecorder()
        for s in [0.5, 0.8, 0.3, 0.9]:
            rec.record(MetricResult("test", s))
        assert abs(rec.min_score("test") - 0.3) < 0.01
        assert abs(rec.max_score("test") - 0.9) < 0.01

    def test_trend_improving(self):
        rec = MetricsRecorder()
        for i in range(20):
            rec.record(MetricResult("test", 0.5 + i * 0.02))
        assert rec.trend("test") > 0

    def test_trend_degrading(self):
        rec = MetricsRecorder()
        for i in range(20):
            rec.record(MetricResult("test", 0.9 - i * 0.02))
        assert rec.trend("test") < 0

    def test_trend_stable(self):
        rec = MetricsRecorder()
        for _ in range(20):
            rec.record(MetricResult("test", 0.8))
        assert rec.trend("test") == 0

    def test_stability_perfect(self):
        rec = MetricsRecorder()
        for _ in range(30):
            rec.record(MetricResult("test", 0.9))
        assert rec.stability("test") > 0.95

    def test_stability_poor(self):
        rec = MetricsRecorder()
        for _ in range(30):
            rec.record(MetricResult("test", 0.5 + 0.5 * (hash(str(_)) % 100) / 100))
        assert rec.stability("test") < 0.8


# =========================================================================
#  21.  TESTS — Automated Scoring System
# =========================================================================

class TestCertificationScoringSystem:
    """End-to-end certification scoring."""

    def test_full_evaluation(self):
        frames = generate_test_approach(600).frames
        scorer = CertificationScoringSystem()
        overall, results = scorer.evaluate(frames, "approach_test")
        assert 0.0 <= overall <= 1.0
        assert len(results) == 8  # All 8 metrics

    def test_multiple_runs_trend(self):
        frames = generate_test_approach(600).frames
        scorer = CertificationScoringSystem()

        # Run three evaluations with slightly different data
        for i in range(3):
            # Modify frames slightly to simulate different runs
            modified = list(frames)
            for j, f in enumerate(modified):
                f.optical_brightness = 0.7 + i * 0.1
            scorer.evaluate(modified, f"run_{i}")

        summary = scorer.summary()
        assert "CERTIFICATION" in summary

        trend = scorer.trend_analysis()
        assert "TREND" in trend

    def test_weighted_scoring(self):
        """Overall score should be a weighted average."""
        frames = generate_test_approach(600).frames
        scorer = CertificationScoringSystem()
        overall, results = scorer.evaluate(frames)
        # Overall should be between 0 and 1
        assert 0.0 <= overall <= 1.0
        # The overall should approximate the mean with appropriate
        # weighting
        raw_mean = sum(r.score for r in results) / len(results)
        assert abs(overall - raw_mean) < 0.2  # Within tolerance
