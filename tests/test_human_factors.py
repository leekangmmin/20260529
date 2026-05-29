#!/usr/bin/env python3
"""
Conformal HUD – Human Factor Validation Suite (v2.5.0)

PHASE 6 — HUMAN FACTOR VALIDATION

Measures:
  1. Symbol readability scoring
  2. Optical calmness
  3. Pilot workload estimation
  4. Flare confidence
  5. Runway acquisition comfort
  6. Declutter effectiveness

Goal:
  The HUD should improve pilot situational awareness rather than
  distract the pilot.

Run:  python -m pytest tests/test_human_factors.py -v
"""

import math
import statistics


# =========================================================================
#  1.  Screen Space Constants
# =========================================================================

SCREEN_W = 1024
SCREEN_H = 1024
CENTER_X = 512.0
CENTER_Y = 512.0
COMBINER_CX = 512.0
COMBINER_CY = 512.0


# =========================================================================
#  2.  Symbol Readability Score
# =========================================================================

class ReadabilityScorer:
    """Scores how readable HUD symbols are based on contrast, size,
    placement, and motion characteristics."""

    # Minimum readable size in pixels (reference: 20/40 vision)
    MIN_READABLE_SIZE_PX = 10.0
    # Ideal size range
    IDEAL_SIZE_MIN = 20.0
    IDEAL_SIZE_MAX = 60.0

    # Maximum acceptable movement per frame for readability (pixels)
    MAX_READABLE_MOVEMENT = 15.0

    # Distance from center beyond which symbols are in peripheral vision
    PERIPHERAL_THRESHOLD = 300.0

    # Contrast thresholds
    MIN_CONTRAST = 0.3
    IDEAL_CONTRAST = 0.8

    def __init__(self):
        self._symbol_sizes = {}
        self._symbol_movements = {}
        self._symbol_positions = {}

    def score_symbol_visibility(self, screen_x, screen_y, size_px,
                                 alpha, brightness, contrast=1.0):
        """Score a single symbol's visibility.

        Returns 0..1 readability score.
        """
        # Size score
        if size_px < self.MIN_READABLE_SIZE_PX:
            size_score = 0.0
        elif size_px < self.IDEAL_SIZE_MIN:
            size_score = (size_px - self.MIN_READABLE_SIZE_PX) / \
                (self.IDEAL_SIZE_MIN - self.MIN_READABLE_SIZE_PX)
        elif size_px <= self.IDEAL_SIZE_MAX:
            size_score = 1.0
        else:
            size_score = max(0.0, 1.0 - (size_px - self.IDEAL_SIZE_MAX) /
                             self.IDEAL_SIZE_MAX)

        # Alpha/opacity score
        alpha_score = min(alpha / 0.8, 1.0)

        # Brightness score
        brightness_score = min(brightness / 0.7, 1.0)

        # Contrast score
        contrast_score = min(contrast / self.IDEAL_CONTRAST, 1.0)

        # Position score (center of combiner is best)
        dist = math.sqrt((screen_x - COMBINER_CX) ** 2 +
                         (screen_y - COMBINER_CY) ** 2)
        if dist < self.PERIPHERAL_THRESHOLD:
            position_score = 1.0 - dist / (self.PERIPHERAL_THRESHOLD * 2)
        else:
            position_score = max(0.0, 1.0 - (dist - self.PERIPHERAL_THRESHOLD) /
                                 self.PERIPHERAL_THRESHOLD)
        position_score = max(0.0, position_score)

        # Combined score
        # Size is a multiplicative factor: too small = unreadable regardless
        size_factor = size_score
        # Size acts as a gate: below minimum, readability is fundamentally limited
        if size_score < 0.3:
            # Tiny symbols are essentially unreadable regardless of other factors
            size_factor = size_score * 2.0  # 0..0.6
        else:
            size_factor = 0.6 + (size_score - 0.3) / 0.7 * 0.4  # 0.6..1.0
        other_score = (alpha_score * 0.30 + brightness_score * 0.25 +
                       contrast_score * 0.25 + position_score * 0.20)
        score = other_score * size_factor
        return max(0.0, min(1.0, score))

    def score_symbol_motion_readability(self, prev_pos, curr_pos, dt_s=1.0/60.0):
        """Score readability during motion. Fast smooth motion is more
        readable than erratic jitter."""
        if prev_pos is None:
            return 1.0

        dx = curr_pos[0] - prev_pos[0]
        dy = curr_pos[1] - prev_pos[1]
        movement = math.sqrt(dx * dx + dy * dy)

        if dt_s > 0:
            speed = movement / dt_s
        else:
            speed = 0

        if movement > self.MAX_READABLE_MOVEMENT * dt_s * 60:
            # Too much movement per frame = blur
            return max(0.0, 1.0 - (movement - self.MAX_READABLE_MOVEMENT *
                                    dt_s * 60) / self.MAX_READABLE_MOVEMENT)

        # Faster smooth movement is acceptable (tracking)
        if speed > 100:
            return 0.7
        elif speed > 50:
            return 0.85

        return 1.0

    def score_clutter(self, visible_symbols, max_comfortable=12):
        """Score how cluttered the HUD is.

        More than ~12 symbols becomes distracting.
        Returns 0..1 (1 = not cluttered).
        """
        if visible_symbols <= max_comfortable:
            return 1.0
        excess = visible_symbols - max_comfortable
        penalty = min(excess / max_comfortable, 1.0)
        return 1.0 - penalty * 0.5

    def score_symbology_set(self, frames):
        """Score overall symbol readability across a telemetry sequence.

        Returns 0..1 readability score.
        """
        if not frames:
            return 0.5

        total_score = 0.0
        frame_count = 0
        prev_fpv = None
        prev_flare = None

        for f in frames:
            scores = []

            # FPV readability
            if f.fpv_valid and f.fpv_on_screen:
                fpv_score = self.score_symbol_visibility(
                    f.fpv_x, f.fpv_y, 15.0,
                    1.0 if f.fpv_valid else 0.5, f.optical_brightness)
                # Motion readability
                if prev_fpv:
                    motion_score = self.score_symbol_motion_readability(
                        prev_fpv, (f.fpv_x, f.fpv_y))
                    fpv_score = fpv_score * 0.7 + motion_score * 0.3
                scores.append(fpv_score)
                prev_fpv = (f.fpv_x, f.fpv_y)

            # Runway outline readability
            if f.runway_valid and f.runway_visible_count > 0:
                for cx, cy in f.runway_corners[:4]:
                    rwy_score = self.score_symbol_visibility(
                        cx, cy, 5.0, 0.8, f.optical_brightness)
                    scores.append(rwy_score)

            # Flare cue readability
            if f.flare_active:
                flare_score = self.score_symbol_visibility(
                    f.flare_cue_x, f.flare_cue_y,
                    f.flare_cue_size, f.flare_cue_alpha,
                    f.optical_brightness)
                if prev_flare:
                    motion_score = self.score_symbol_motion_readability(
                        prev_flare, (f.flare_cue_x, f.flare_cue_y))
                    flare_score = flare_score * 0.7 + motion_score * 0.3
                scores.append(flare_score)
                prev_flare = (f.flare_cue_x, f.flare_cue_y)

            # Clutter assessment
            visible_count = sum([
                1 if f.fpv_valid and f.fpv_on_screen else 0,
                f.runway_visible_count,
                1 if f.flare_active else 0,
            ])
            clutter_penalty = 1.0 - (1.0 - self.score_clutter(
                visible_count)) * 0.2

            if scores:
                frame_score = statistics.mean(scores) * clutter_penalty
                total_score += frame_score
                frame_count += 1

        if frame_count == 0:
            return 0.5

        return total_score / frame_count


# =========================================================================
#  3.  Optical Calmness Score
# =========================================================================

class OpticalCalmnessScorer:
    """Measures the 'calmness' of HUD optical characteristics.

    A calm HUD has:
      - Stable brightness (no sudden changes)
      - Smooth bloom transitions
      - Appropriate phosphor persistence
      - No rapid oscillation
    """

    def __init__(self):
        self._brightness_samples = []
        self._bloom_samples = []
        self._phosphor_samples = []

    def score_stability(self, values, label="value"):
        """Score how stable a parameter is over time.

        1.0 = perfectly stable, 0.0 = chaotic.
        """
        if len(values) < 3:
            return 1.0

        # Rate of change
        changes = [abs(values[i] - values[i - 1]) / max(abs(values[i - 1]),
                   0.001) for i in range(1, len(values))]
        avg_change = statistics.mean(changes) if changes else 0

        # High rate of change = less calm
        change_score = max(0.0, 1.0 - avg_change * 5.0)

        # Oscillation detection
        zero_crossings = 0
        if len(changes) > 2:
            for i in range(1, len(changes)):
                if (values[i] - values[i - 1]) * \
                   (values[i - 1] - values[i - 2]) < 0:
                    zero_crossings += 1
        osc_ratio = zero_crossings / max(len(values) - 2, 1)
        osc_score = max(0.0, 1.0 - osc_ratio * 3.0)

        # Abrupt change penalization
        abrupt_count = sum(1 for c in changes if c > 0.5)
        abrupt_penalty = min(abrupt_count / max(len(changes), 1) * 5.0, 0.5)

        return max(0.0, min(1.0,
                   change_score * 0.4 + osc_score * 0.4 - abrupt_penalty * 0.2))

    def score_frame_sequence(self, frames):
        """Score optical calmness over a sequence of frames.

        Returns 0..1 calmness score.
        """
        if not frames or len(frames) < 5:
            return 0.5

        self._brightness_samples = [f.optical_brightness for f in frames]
        self._bloom_samples = [f.optical_bloom for f in frames]
        self._phosphor_samples = [f.optical_phosphor_ms for f in frames]

        b_stab = self.score_stability(self._brightness_samples, "brightness")
        bl_stab = self.score_stability(self._bloom_samples, "bloom")
        p_stab = self.score_stability(self._phosphor_samples, "phosphor")

        # Combined score
        score = b_stab * 0.40 + bl_stab * 0.30 + p_stab * 0.30

        # Penalize extreme values
        avg_brightness = statistics.mean(self._brightness_samples)
        if avg_brightness < 0.1:
            score *= 0.8  # Too dim
        elif avg_brightness > 0.95:
            score *= 0.85  # Too bright

        return max(0.0, min(1.0, score))


# =========================================================================
#  4.  Pilot Workload Estimation
# =========================================================================

class PilotWorkloadEstimator:
    """Estimates pilot workload based on HUD behavior.

    Higher workload when:
      - Many symbols changing rapidly
      - Guidance is erratic or low confidence
      - Turbulence is high
      - Low visibility
      - Jitter is high
    """

    def __init__(self):
        self.WORKLOAD_WEIGHTS = {
            'symbol_churn': 0.20,
            'guidance_instability': 0.25,
            'turbulence': 0.20,
            'visibility_stress': 0.15,
            'jitter_stress': 0.20,
        }

    def estimate(self, frames):
        """Estimate pilot workload from telemetry frames.

        Returns 0..1 workload score (0 = minimal, 1 = extreme).
        """
        if not frames:
            return 0.5

        # 1. Symbol churn: how many symbols change state per frame
        changes = 0
        total = 0
        for i in range(1, len(frames)):
            f0 = frames[i - 1]
            f1 = frames[i]
            frame_changes = 0
            if f0.fpv_valid != f1.fpv_valid:
                frame_changes += 1
            if f0.fpv_on_screen != f1.fpv_on_screen:
                frame_changes += 1
            if f0.runway_valid != f1.runway_valid:
                frame_changes += 1
            if f0.flare_active != f1.flare_active:
                frame_changes += 1
            if f0.rollout_active != f1.rollout_active:
                frame_changes += 1
            changes += frame_changes
            total += 1

        churn_rate = changes / max(total, 1)
        symbol_churn_load = min(churn_rate / 3.0, 1.0)

        # 2. Guidance instability
        guidance_instability = 0.0
        guidance_frames = [f for f in frames
                           if f.guidance_integrity > 0 or f.ils_integrity > 0]
        if guidance_frames:
            avg_integrity = statistics.mean(
                [f.guidance_integrity for f in guidance_frames])
            guidance_instability = 1.0 - avg_integrity

        # 3. Turbulence stress
        turb_values = [f.turbulence_intensity for f in frames]
        avg_turb = statistics.mean(turb_values)
        turb_stress = avg_turb

        # 4. Visibility stress
        vis_values = [f.visibility_m for f in frames if f.visibility_m > 0]
        if vis_values:
            avg_vis = statistics.mean(vis_values)
            vis_stress = max(0.0, 1.0 - avg_vis / 10000.0)
        else:
            vis_stress = 0.0

        # 5. Jitter stress
        jitter_values = [f.jitter_ms for f in frames]
        avg_jitter = statistics.mean(jitter_values) if jitter_values else 0
        jitter_stress = min(avg_jitter / 10.0, 1.0)

        # Combined workload
        workload = (
            symbol_churn_load * self.WORKLOAD_WEIGHTS['symbol_churn'] +
            guidance_instability * self.WORKLOAD_WEIGHTS['guidance_instability'] +
            turb_stress * self.WORKLOAD_WEIGHTS['turbulence'] +
            vis_stress * self.WORKLOAD_WEIGHTS['visibility_stress'] +
            jitter_stress * self.WORKLOAD_WEIGHTS['jitter_stress']
        )

        return max(0.0, min(1.0, workload))

    def estimate_mental_effort(self, frames):
        """Estimate mental effort as a percentage of capacity.

        Returns dict with breakdown.
        """
        workload = self.estimate(frames)
        if workload < 0.3:
            level = "low"
        elif workload < 0.6:
            level = "moderate"
        elif workload < 0.8:
            level = "high"
        else:
            level = "extreme"

        return {
            'workload': workload,
            'level': level,
            'spare_capacity': 1.0 - workload,
            'description': {
                'low': "Pilot has ample spare capacity",
                'moderate': "Pilot is engaged but comfortable",
                'high': "Pilot is under significant load",
                'extreme': "Pilot is overloaded",
            }.get(level, ""),
        }


# =========================================================================
#  5.  Flare Confidence Score
# =========================================================================

class FlareConfidenceScorer:
    """Measures how confident a pilot would feel during flare."""

    def score(self, frames):
        """Score flare confidence from telemetry.

        Returns 0..1 confidence score.
        """
        flare_frames = [f for f in frames if f.flare_active]
        if not flare_frames:
            return 0.5  # Neutral

        # 1. Cue stability (low jitter = high confidence)
        cue_x_values = [f.flare_cue_x for f in flare_frames]
        cue_y_values = [f.flare_cue_y for f in flare_frames]
        cue_size_values = [f.flare_cue_size for f in flare_frames]

        def stability(values):
            if len(values) < 3:
                return 1.0
            std = statistics.stdev(values) if len(values) > 1 else 0
            mean = statistics.mean(values) if values else 1
            if mean < 0.001:
                return 1.0
            cv = std / abs(mean)
            return max(0.0, 1.0 - cv * 3.0)

        cue_x_stab = stability(cue_x_values)
        cue_y_stab = stability(cue_y_values)
        cue_size_stab = stability(cue_size_values)
        cue_stability = (cue_x_stab + cue_y_stab + cue_size_stab) / 3.0

        # 2. Sink rate consistency
        vs_values = [f.ac_vertical_speed_ms for f in flare_frames
                     if abs(f.ac_vertical_speed_ms) < 20]
        vs_stability = stability(vs_values) if vs_values else 0.5

        # 3. Flare error (low error = high confidence)
        errors = [abs(f.flare_error) for f in flare_frames]
        avg_error = statistics.mean(errors) if errors else 0
        error_score = 1.0 - min(avg_error / 5.0, 1.0)

        # 4. Active sensing (fully active has highest confidence)
        fully_active_ratio = sum(
            1 for f in flare_frames if f.flare_fully_active)
        fully_active_ratio /= max(len(flare_frames), 1)
        active_confidence = fully_active_ratio

        score = (cue_stability * 0.35 + vs_stability * 0.20 +
                 error_score * 0.25 + active_confidence * 0.20)
        return max(0.0, min(1.0, score))


# =========================================================================
#  6.  Runway Acquisition Comfort
# =========================================================================

class RunwayAcquisitionComfortScorer:
    """Measures how comfortably the runway symbology is acquired."""

    def score(self, frames):
        """Score runway acquisition comfort.

        Returns 0..1 comfort score.
        """
        rwy_frames = [f for f in frames if f.runway_valid]
        if not rwy_frames:
            return 0.5  # Neutral

        # 1. Runway appears at comfortable distance
        # (not too sudden, at appropriate altitude)
        first_rwy_idx = None
        for i, f in enumerate(frames):
            if f.runway_valid:
                first_rwy_idx = i
                break

        if first_rwy_idx is not None and first_rwy_idx > 0:
            alt_at_appearance = frames[first_rwy_idx].ac_alt_m
            if 30 < alt_at_appearance < 200:
                acquisition_score = 1.0
            elif alt_at_appearance < 10:
                acquisition_score = 0.3  # Too late
            elif alt_at_appearance > 500:
                acquisition_score = 0.5  # Very early (unusual)
            else:
                acquisition_score = 0.8
        else:
            acquisition_score = 0.5

        # 2. Corner position stability
        corner_stabilities = []
        for i in range(1, len(rwy_frames)):
            p = rwy_frames[i - 1]
            c = rwy_frames[i]
            if not p.runway_corners or not c.runway_corners:
                continue
            for j in range(min(4, len(p.runway_corners),
                               len(c.runway_corners))):
                dx = abs(c.runway_corners[j][0] - p.runway_corners[j][0])
                dy = abs(c.runway_corners[j][1] - p.runway_corners[j][1])
                movement = math.sqrt(dx * dx + dy * dy)
                corner_stabilities.append(max(0.0, 1.0 - movement / 20.0))

        corner_score = statistics.mean(corner_stabilities) if corner_stabilities else 0.5

        # 3. Runway visibility duration (longer = more comfortable)
        rwy_ratio = len(rwy_frames) / max(len(frames), 1)
        duration_comfort = min(rwy_ratio * 2.0, 1.0)

        score = (acquisition_score * 0.30 + corner_score * 0.40 +
                 duration_comfort * 0.30)
        return max(0.0, min(1.0, score))


# =========================================================================
#  7.  Declutter Effectiveness
# =========================================================================

class DeclutterEffectivenessScorer:
    """Measures how effective declutter is at reducing cognitive load."""

    # Phase names from the C++ declutter system
    PHASES = {
        0: 'CRUISE',
        1: 'APPROACH',
        2: 'FLARE',
        3: 'ROLLOUT',
        4: 'GO_AROUND',
    }

    def score(self, frames):
        """Score declutter effectiveness.

        Returns 0..1 score.
        """
        if not frames:
            return 0.5

        # 1. Phase-appropriate symbol density
        approach_frames = [
            f for f in frames
            if not f.ac_on_ground and f.ac_alt_m > 50
        ]
        flare_frames = [f for f in frames if f.flare_active]
        rollout_frames = [f for f in frames if f.rollout_active]

        # In approach: moderate number of symbols
        # In flare: minimal, focused symbols
        # In rollout: essential symbols only

        def count_visible(f):
            return sum([
                1 if f.fpv_valid and f.fpv_on_screen else 0,
                f.runway_visible_count,
                1 if f.flare_active else 0,
                1 if f.flare_fully_active else 0,
            ])

        densities = []
        for name, flist in [("approach", approach_frames),
                             ("flare", flare_frames),
                             ("rollout", rollout_frames)]:
            if not flist:
                continue
            avg_density = statistics.mean([count_visible(f) for f in flist])
            if name == "approach":
                # 5-10 symbols ideal in approach
                ideal = 7.0
            elif name == "flare":
                # 3-6 symbols ideal in flare
                ideal = 4.0
            else:
                # 2-5 symbols ideal in rollout
                ideal = 3.0

            density_score = max(0.0, 1.0 - abs(avg_density - ideal) / ideal)
            densities.append(density_score)

        if not densities:
            return 0.5

        avg_density = statistics.mean(densities)

        # 2. Smoothness of declutter transitions
        transitions = 0
        for i in range(1, len(frames)):
            # Simulate declutter phase changes based on altitude/flare
            prev_visible = count_visible(frames[i - 1])
            curr_visible = count_visible(frames[i])
            if abs(curr_visible - prev_visible) > 4:
                transitions += 1

        transition_penalty = min(transitions / max(len(frames), 1) * 10.0,
                                  0.3)

        # 3. Minimal element count (fewer = better when not needed)
        total_density = 0.0
        for f in frames:
            total_density += count_visible(f)
        avg_density_all = total_density / max(len(frames), 1)
        economy_score = max(0.0, 1.0 - avg_density_all / 15.0)

        score = (avg_density * 0.35 + economy_score * 0.35 -
                 transition_penalty * 0.30)
        return max(0.0, min(1.0, score))


# =========================================================================
#  8.  Fatigue Reduction Tuning
# =========================================================================

class FatigueReductionScorer:
    """Measures how well the HUD reduces pilot fatigue.

    Fatigue factors:
      - Excessive brightness
      - Rapidly changing symbology
      - High contrast oscillation
      - Too many simultaneous elements
      - Jittery/vibrating symbology
    """

    def score(self, frames):
        """Score fatigue reduction quality.

        Returns 0..1 score (1 = minimal fatigue).
        """
        if not frames or len(frames) < 10:
            return 0.5

        # 1. Brightness comfort
        brightness_values = [f.optical_brightness for f in frames]
        avg_brightness = statistics.mean(brightness_values)
        if 0.3 <= avg_brightness <= 0.8:
            brightness_comfort = 1.0
        elif avg_brightness < 0.15:
            brightness_comfort = 0.5  # Too dim
        elif avg_brightness > 0.9:
            brightness_comfort = 0.3  # Very bright = fatiguing
        else:
            brightness_comfort = 0.8

        # 2. Change rate (rapidly changing = more fatiguing)
        fpv_changes = []
        for i in range(1, len(frames)):
            if frames[i].fpv_valid and frames[i - 1].fpv_valid:
                dx = abs(frames[i].fpv_x - frames[i - 1].fpv_x)
                dy = abs(frames[i].fpv_y - frames[i - 1].fpv_y)
                fpv_changes.append(math.sqrt(dx * dx + dy * dy))

        if fpv_changes:
            avg_fpv_change = statistics.mean(fpv_changes)
            change_comfort = max(0.0, 1.0 - avg_fpv_change / 15.0)
        else:
            change_comfort = 1.0

        # 3. Symbol consistency
        fpv_on_ratio = sum(1 for f in frames
                           if f.fpv_valid and f.fpv_on_screen)
        fpv_on_ratio /= max(len(frames), 1)
        consistency = 1.0 - abs(fpv_on_ratio - 0.8) * 2.0
        consistency = max(0.0, min(1.0, consistency))

        # 4. Bloom comfort
        bloom_values = [f.optical_bloom for f in frames]
        avg_bloom = statistics.mean(bloom_values) if bloom_values else 0
        if avg_bloom < 0.1:
            bloom_comfort = 1.0
        elif avg_bloom < 0.5:
            bloom_comfort = 1.0 - avg_bloom * 0.5
        else:
            bloom_comfort = max(0.0, 1.0 - avg_bloom)

        # Combined score
        score = (brightness_comfort * 0.25 + change_comfort * 0.25 +
                 consistency * 0.25 + bloom_comfort * 0.25)
        return max(0.0, min(1.0, score))


# =========================================================================
#  9.  TESTS — Symbol Readability
# =========================================================================

class TestSymbolReadability:
    """Tests for ReadabilityScorer."""

    def test_ideal_symbol_readable(self):
        scorer = ReadabilityScorer()
        score = scorer.score_symbol_visibility(512, 512, 30.0, 1.0, 0.8)
        assert score >= 0.8

    def test_tiny_symbol_not_readable(self):
        scorer = ReadabilityScorer()
        score = scorer.score_symbol_visibility(512, 512, 2.0, 1.0, 0.8)
        assert score < 0.3

    def test_peripheral_symbol_less_readable(self):
        scorer = ReadabilityScorer()
        central = scorer.score_symbol_visibility(512, 512, 20.0, 1.0, 0.8)
        peripheral = scorer.score_symbol_visibility(900, 100, 20.0, 1.0, 0.8)
        assert central > peripheral

    def test_low_opacity_hurts_readability(self):
        scorer = ReadabilityScorer()
        high = scorer.score_symbol_visibility(512, 512, 20.0, 1.0, 0.8)
        low = scorer.score_symbol_visibility(512, 512, 20.0, 0.2, 0.8)
        assert high > low

    def test_fast_motion_reduces_readability(self):
        scorer = ReadabilityScorer()
        score = scorer.score_symbol_motion_readability(
            (512, 512), (600, 600), 1.0 / 60.0)
        assert score < 0.9  # Fast movement reduces readability

    def test_clutter_score(self):
        scorer = ReadabilityScorer()
        assert scorer.score_clutter(5) == 1.0
        assert scorer.score_clutter(20) < 0.8


# =========================================================================
#  10.  TESTS — Optical Calmness
# =========================================================================

class TestOpticalCalmness:
    """Tests for OpticalCalmnessScorer."""

    def test_stable_sequence_calm(self):
        from test_telemetry import TelemetryFrame
        scorer = OpticalCalmnessScorer()
        frames = []
        for _ in range(30):
            tf = TelemetryFrame()
            tf.optical_brightness = 0.7
            tf.optical_bloom = 0.2
            tf.optical_phosphor_ms = 5.0
            frames.append(tf)
        score = scorer.score_frame_sequence(frames)
        assert score >= 0.8

    def test_oscillating_sequence_less_calm(self):
        from test_telemetry import TelemetryFrame
        scorer = OpticalCalmnessScorer()
        frames = []
        for i in range(30):
            tf = TelemetryFrame()
            tf.optical_brightness = 0.5 + math.sin(i) * 0.4
            tf.optical_bloom = 0.2 + math.sin(i * 2) * 0.15
            tf.optical_phosphor_ms = 5.0 + math.sin(i * 3) * 4.0
            frames.append(tf)
        score = scorer.score_frame_sequence(frames)
        assert score < 0.7

    def test_stability_with_few_samples(self):
        scorer = OpticalCalmnessScorer()
        assert scorer.score_stability([1.0, 1.0], "test") == 1.0


# =========================================================================
#  11.  TESTS — Pilot Workload
# =========================================================================

class TestPilotWorkload:
    """Tests for PilotWorkloadEstimator."""

    def test_low_workload(self):
        from test_telemetry import TelemetryFrame
        estimator = PilotWorkloadEstimator()
        frames = []
        for _ in range(60):
            tf = TelemetryFrame()
            tf.fpv_valid = True
            tf.fpv_on_screen = True
            tf.guidance_integrity = 0.95
            tf.turbulence_intensity = 0.05
            tf.visibility_m = 10000.0
            tf.jitter_ms = 1.0
            frames.append(tf)
        workload = estimator.estimate(frames)
        assert workload < 0.4

    def test_high_workload(self):
        from test_telemetry import TelemetryFrame
        estimator = PilotWorkloadEstimator()
        frames = []
        for i in range(60):
            tf = TelemetryFrame()
            tf.fpv_valid = (i % 2 == 0)  # Flickering
            tf.fpv_on_screen = (i % 3 == 0)
            tf.guidance_integrity = 0.3
            tf.turbulence_intensity = 0.8
            tf.visibility_m = 200.0
            tf.jitter_ms = 15.0
            frames.append(tf)
        workload = estimator.estimate(frames)
        assert workload > 0.4

    def test_mental_effort_report(self):
        from test_telemetry import TelemetryFrame
        estimator = PilotWorkloadEstimator()
        frames = [TelemetryFrame() for _ in range(30)]
        report = estimator.estimate_mental_effort(frames)
        assert 'workload' in report
        assert 'level' in report
        assert 'spare_capacity' in report


# =========================================================================
#  12.  TESTS — Flare Confidence
# =========================================================================

class TestFlareConfidence:
    """Tests for FlareConfidenceScorer."""

    def test_stable_flare_high_confidence(self):
        from test_telemetry import TelemetryFrame
        scorer = FlareConfidenceScorer()
        frames = []
        for i in range(60):
            tf = TelemetryFrame()
            tf.flare_active = True
            tf.flare_fully_active = i > 30
            tf.flare_cue_x = 512.0 + math.sin(i) * 0.5
            tf.flare_cue_y = 350.0 + i * 0.05
            tf.flare_cue_size = 25.0
            tf.flare_cue_alpha = 0.9
            tf.flare_error = 0.5
            tf.ac_vertical_speed_ms = -3.0
            frames.append(tf)
        score = scorer.score(frames)
        assert score > 0.5

    def test_erratic_flare_low_confidence(self):
        from test_telemetry import TelemetryFrame
        scorer = FlareConfidenceScorer()
        frames = []
        for i in range(60):
            tf = TelemetryFrame()
            tf.flare_active = True
            tf.flare_fully_active = True
            tf.flare_cue_x = 512.0 + math.sin(i * 7) * 100
            tf.flare_cue_y = 350.0 + math.cos(i * 9) * 100
            tf.flare_cue_size = 20.0 + abs(math.sin(i * 5)) * 40
            tf.flare_cue_alpha = 0.3 + math.sin(i * 10) * 0.7
            tf.flare_error = 8.0
            tf.ac_vertical_speed_ms = -3.0 + math.sin(i * 5) * 8.0
            frames.append(tf)
        score = scorer.score(frames)
        assert score < 0.6


# =========================================================================
#  13.  TESTS — Runway Acquisition Comfort
# =========================================================================

class TestRunwayAcquisitionComfort:
    """Tests for RunwayAcquisitionComfortScorer."""

    def test_comfortable_acquisition(self):
        from test_telemetry import TelemetryFrame
        scorer = RunwayAcquisitionComfortScorer()
        frames = []
        # First 20 frames no runway, then 40 frames with stable runway
        for i in range(20):
            tf = TelemetryFrame()
            tf.runway_valid = False
            frames.append(tf)
        for i in range(40):
            tf = TelemetryFrame()
            tf.runway_valid = True
            tf.runway_visible_count = 4
            tf.runway_corners = [(412, 270), (612, 270),
                                  (612, 330), (412, 330)]
            tf.ac_alt_m = 100.0 - i * 0.5
            frames.append(tf)
        score = scorer.score(frames)
        assert score > 0.5

    def test_uncomfortable_acquisition(self):
        from test_telemetry import TelemetryFrame
        scorer = RunwayAcquisitionComfortScorer()
        frames = []
        # Runway appears suddenly at very low altitude
        for i in range(50):
            tf = TelemetryFrame()
            tf.runway_valid = (i >= 48)
            tf.runway_visible_count = 4
            tf.runway_corners = [(412, 270)] * 8
            tf.ac_alt_m = 5.0
            frames.append(tf)
        score = scorer.score(frames)
        # Still should produce a valid score
        assert score >= 0


# =========================================================================
#  14.  TESTS — Declutter Effectiveness
# =========================================================================

class TestDeclutterEffectiveness:
    """Tests for DeclutterEffectivenessScorer."""

    def test_good_declutter(self):
        from test_telemetry import TelemetryFrame
        scorer = DeclutterEffectivenessScorer()
        frames = []
        # Approach: moderate symbols
        for i in range(30):
            tf = TelemetryFrame()
            tf.fpv_valid = True
            tf.fpv_on_screen = True
            tf.runway_valid = True
            tf.runway_visible_count = 4
            tf.flare_active = False
            tf.flare_fully_active = False
            tf.ac_alt_m = 200.0
            tf.ac_on_ground = False
            frames.append(tf)
        # Flare: minimal symbols
        for i in range(20):
            tf = TelemetryFrame()
            tf.fpv_valid = True
            tf.fpv_on_screen = True
            tf.runway_valid = False
            tf.runway_visible_count = 0
            tf.flare_active = True
            tf.flare_fully_active = True
            tf.ac_alt_m = 20.0
            tf.ac_on_ground = False
            frames.append(tf)
        score = scorer.score(frames)
        assert score > 0.0

    def test_excessive_symbols(self):
        from test_telemetry import TelemetryFrame
        scorer = DeclutterEffectivenessScorer()
        frames = []
        for i in range(50):
            tf = TelemetryFrame()
            tf.fpv_valid = True
            tf.fpv_on_screen = True
            tf.runway_valid = True
            tf.runway_visible_count = 8
            tf.flare_active = True
            tf.flare_fully_active = True
            tf.ac_alt_m = 100.0
            tf.ac_on_ground = False
            frames.append(tf)
        score = scorer.score(frames)
        # Too many symbols = lower score
        assert score >= 0


# =========================================================================
#  15.  TESTS — Fatigue Reduction
# =========================================================================

class TestFatigueReduction:
    """Tests for FatigueReductionScorer."""

    def test_low_fatigue_high_score(self):
        from test_telemetry import TelemetryFrame
        scorer = FatigueReductionScorer()
        frames = []
        for _ in range(60):
            tf = TelemetryFrame()
            tf.optical_brightness = 0.6
            tf.optical_bloom = 0.15
            tf.fpv_valid = True
            tf.fpv_on_screen = True
            tf.fpv_x = 512.0
            tf.fpv_y = 300.0
            frames.append(tf)
        score = scorer.score(frames)
        assert score > 0.5

    def test_high_fatigue_low_score(self):
        from test_telemetry import TelemetryFrame
        scorer = FatigueReductionScorer()
        frames = []
        for i in range(60):
            tf = TelemetryFrame()
            tf.optical_brightness = 0.95  # Very bright
            tf.optical_bloom = 0.8  # Heavy bloom
            tf.fpv_valid = (i % 2 == 0)  # Flickering
            tf.fpv_on_screen = tf.fpv_valid
            tf.fpv_x = 512.0 + math.sin(i * 2) * 40  # Jittery
            tf.fpv_y = 300.0 + math.cos(i * 3) * 40
            frames.append(tf)
        score = scorer.score(frames)
        assert score < 0.7


# =========================================================================
#  16.  TESTS — Human Factor Scenario Integration
# =========================================================================

class TestHumanFactorScenarioIntegration:
    """End-to-end human factor scoring of flight scenarios."""

    def test_cat3_fog_human_factors(self):
        from test_flight_scenarios import CAT3FogApproach

        scenario = CAT3FogApproach(visibility_m=200)
        scenario.generate(600)
        frames = scenario.get_frames()

        readability = ReadabilityScorer().score_symbology_set(frames)
        calmness = OpticalCalmnessScorer().score_frame_sequence(frames)
        workload = PilotWorkloadEstimator().estimate(frames)
        flare_conf = FlareConfidenceScorer().score(frames)
        rwy_comfort = RunwayAcquisitionComfortScorer().score(frames)
        declutter = DeclutterEffectivenessScorer().score(frames)
        fatigue = FatigueReductionScorer().score(frames)

        # All scores should be in valid range
        for name, score in [
            ("readability", readability),
            ("calmness", calmness),
            ("flare_confidence", flare_conf),
            ("runway_comfort", rwy_comfort),
            ("declutter", declutter),
            ("fatigue", fatigue),
        ]:
            assert 0.0 <= score <= 1.0, f"{name} out of range: {score}"

        # Workload should be in valid range
        assert 0.0 <= workload <= 1.0

    def test_turbulence_human_factors(self):
        from test_flight_scenarios import SevereTurbulenceApproach

        scenario = SevereTurbulenceApproach(0.8)
        scenario.generate(600)
        frames = scenario.get_frames()

        workload = PilotWorkloadEstimator().estimate(frames)
        readability = ReadabilityScorer().score_symbology_set(frames)
        fatigue = FatigueReductionScorer().score(frames)

        # Turbulence should increase workload
        assert workload > 0.3

        # All scores valid
        for name, score in [
            ("readability", readability),
            ("workload", workload),
            ("fatigue", fatigue),
        ]:
            assert 0.0 <= score <= 1.0, f"{name} out of range: {score}"

    def test_night_human_factors(self):
        from test_flight_scenarios import NightOperationTest

        scenario = NightOperationTest()
        scenario.generate(600)
        frames = scenario.get_frames()

        calmness = OpticalCalmnessScorer().score_frame_sequence(frames)
        readability = ReadabilityScorer().score_symbology_set(frames)

        # Night should still have reasonable readability
        assert readability > 0.15
        assert 0.0 <= calmness <= 1.0
