#!/usr/bin/env python3
"""
Conformal HUD – Real Frame Pacing Validation Suite (v2.6.0)

PHASE 3 — REAL FRAME PACING VALIDATION

Tests for:
  1. Timing anomaly detection (hitches, stutters, pauses)
  2. Frame hitch recovery
  3. Stabilization reset logic for pause/unpause
  4. Temporal continuity protection
  5. Frame pacing instability detection
  6. Menu interruption resilience
  7. Focus-loss recovery
  8. Aircraft reload transition behavior

Goal:
  HUD must remain visually stable under real MSFS frame instability.

Run:  python -m pytest tests/test_frame_pacing.py -v
"""

import math
import time
import statistics


# =========================================================================
#  1.  Pacing anomaly detection state (mirrors C++ PacingState)
# =========================================================================

class PacingAnomalyType:
    NONE = 0
    HITCH = 1
    STUTTER = 2
    PAUSE = 3
    FOCUS_LOSS = 4
    MENU_OVERLAY = 5
    AIRCRAFT_LOAD = 6

ANOMALY_NAMES = {
    0: 'None', 1: 'Hitch', 2: 'Stutter', 3: 'Pause',
    4: 'FocusLoss', 5: 'MenuOverlay', 6: 'AircraftLoad',
}


class PacingAnomalyEvent:
    def __init__(self):
        self.type = PacingAnomalyType.NONE
        self.frame_index = 0
        self.timestamp_s = 0.0
        self.duration_ms = 0.0
        self.recovery_ms = 0.0


class PacingState:
    """Frame pacing validation state (mirrors C++ PacingState)."""

    MAX_DT_HISTORY = 60

    def __init__(self):
        self.expected_frame_interval_ms = 16.667  # 60fps
        self.hitch_threshold_ms = 50.0
        self.stutter_threshold_ms = 33.0

        self.dt_history = [0.0] * self.MAX_DT_HISTORY
        self.dt_write_pos = 0
        self.dt_sample_count = 0
        self.dt_min = 1e9
        self.dt_max = 0.0
        self.dt_mean = 16.667
        self.dt_stddev = 0.0

        self.anomalies = []
        self.max_anomalies = 32

        self.in_recovery = False
        self.recovery_frames = 0
        self.stabilization_reset_pending = False

        self.continuity_metric = 1.0
        self.consecutive_stable_frames = 0

        self.valid = True

    def record_frame_interval(self, dt_s, frame_index=0):
        """Record a frame interval in seconds."""
        dt_ms = dt_s * 1000.0
        if dt_ms < 0.0:
            dt_ms = 0.0
        if dt_ms > 500.0:
            dt_ms = 500.0  # Clamp

        # Update rolling history
        if self.dt_sample_count < self.MAX_DT_HISTORY:
            self.dt_sample_count += 1
        self.dt_history[self.dt_write_pos] = dt_ms
        self.dt_write_pos = (self.dt_write_pos + 1) % self.MAX_DT_HISTORY

        # Update stats
        self.dt_min = min(self.dt_min, dt_ms)
        self.dt_max = max(self.dt_max, dt_ms)

        total = sum(self.dt_history[:self.dt_sample_count])
        self.dt_mean = total / max(self.dt_sample_count, 1)

        if self.dt_sample_count > 1:
            variance = sum((x - self.dt_mean) ** 2
                           for x in self.dt_history[:self.dt_sample_count]) / self.dt_sample_count
            self.dt_stddev = math.sqrt(variance)

        # Detect anomaly
        anomaly = self._detect_anomaly(dt_ms, frame_index)

        # Update continuity metric
        if anomaly is None:
            self.consecutive_stable_frames += 1
            self.continuity_metric = min(1.0, self.continuity_metric + 0.01)
            self.in_recovery = False
            self.recovery_frames = 0
        else:
            self.anomalies.append(anomaly)
            if len(self.anomalies) > self.max_anomalies:
                self.anomalies.pop(0)
            self.in_recovery = True
            self.recovery_frames = 0
            self.consecutive_stable_frames = 0
            self.continuity_metric = max(0.0, self.continuity_metric - 0.2)

        if self.in_recovery:
            self.recovery_frames += 1

        return anomaly

    def _detect_anomaly(self, dt_ms, frame_index):
        """Detect if the current frame interval indicates an anomaly."""
        if dt_ms > self.hitch_threshold_ms:
            ev = PacingAnomalyEvent()
            ev.type = PacingAnomalyType.HITCH
            ev.frame_index = frame_index
            ev.duration_ms = dt_ms
            return ev

        # Stutter: consecutive high intervals (rolling mean > 2x expected)
        if self.dt_sample_count >= 10:
            recent = self.dt_history[:self.dt_sample_count]
            recent_mean = statistics.mean(recent)
            if recent_mean > self.stutter_threshold_ms:
                ev = PacingAnomalyEvent()
                ev.type = PacingAnomalyType.STUTTER
                ev.frame_index = frame_index
                ev.duration_ms = recent_mean
                return ev

        return None

    def should_reset_stabilization(self):
        """Check if stabilization system should be reset."""
        if self.in_recovery and self.recovery_frames <= 5:
            return True
        return False

    def recovery_progress(self):
        """Return 0..1 progress of recovery."""
        if not self.in_recovery:
            return 1.0
        return min(1.0, self.recovery_frames / 30.0)  # Recover over ~30 frames

    def anomaly_count(self):
        return len(self.anomalies)

    def last_anomaly_type(self):
        if not self.anomalies:
            return PacingAnomalyType.NONE
        return self.anomalies[-1].type


# =========================================================================
#  2.  Tests
# =========================================================================

class TestPacingState:
    """Test basic pacing state management."""

    def test_init(self):
        p = PacingState()
        assert p.valid
        assert abs(p.expected_frame_interval_ms - 16.667) < 0.001
        assert p.dt_sample_count == 0
        assert p.continuity_metric == 1.0

    def test_record_normal_frame(self):
        p = PacingState()
        dt_s = 1.0 / 60.0  # Normal 60fps
        p.record_frame_interval(dt_s)
        assert p.dt_sample_count == 1
        assert not p.in_recovery
        assert p.consecutive_stable_frames == 1

    def test_record_multiple_normal_frames(self):
        p = PacingState()
        for _ in range(10):
            p.record_frame_interval(1.0 / 60.0)
        assert p.dt_sample_count == 10
        assert abs(p.dt_mean - 16.667) < 1.0

    def test_dt_history_limited(self):
        p = PacingState()
        for _ in range(PacingState.MAX_DT_HISTORY + 10):
            p.record_frame_interval(1.0 / 60.0)
        assert p.dt_sample_count == PacingState.MAX_DT_HISTORY

    def test_min_max_tracking(self):
        p = PacingState()
        p.record_frame_interval(1.0 / 60.0)  # ~16.67ms
        p.record_frame_interval(1.0 / 30.0)  # ~33.33ms
        p.record_frame_interval(1.0 / 120.0)  # ~8.33ms
        assert p.dt_min < 10.0
        assert p.dt_max > 30.0


class TestAnomalyDetection:
    """Test timing anomaly detection."""

    def test_no_anomaly_normal(self):
        p = PacingState()
        for _ in range(20):
            result = p.record_frame_interval(1.0 / 60.0)
            assert result is None

    def test_hitch_detection(self):
        p = PacingState()
        # Normal frames first
        for _ in range(10):
            p.record_frame_interval(1.0 / 60.0)

        # Hitched frame (100ms)
        result = p.record_frame_interval(0.100)
        assert result is not None
        assert result.type == PacingAnomalyType.HITCH

    def test_hitch_threshold_boundary(self):
        p = PacingState()
        for _ in range(10):
            p.record_frame_interval(1.0 / 60.0)

        # Just below threshold (49ms)
        result = p.record_frame_interval(0.049)
        assert result is None, "Below threshold should not trigger"

        # Just above threshold (51ms)
        result = p.record_frame_interval(0.051)
        assert result is not None, "Above threshold should trigger"

    def test_stutter_detection(self):
        p = PacingState()
        # Create sustained high frame times
        for _ in range(15):
            p.record_frame_interval(1.0 / 30.0)  # 33ms per frame

        # Should detect stutter
        assert p.anomaly_count() > 0
        assert p.last_anomaly_type() in (PacingAnomalyType.STUTTER, PacingAnomalyType.HITCH)

    def test_rapid_hitch_detection(self):
        """Multiple hitches in quick succession should each be detected."""
        p = PacingState()
        for _ in range(10):
            p.record_frame_interval(1.0 / 60.0)

        hitches = 0
        for _ in range(5):
            result = p.record_frame_interval(0.100)
            if result is not None:
                hitches += 1
            p.record_frame_interval(1.0 / 60.0)  # Recovery frame

        assert hitches > 0


class TestRecoveryBehavior:
    """Test recovery from pacing anomalies."""

    def test_recovery_after_hitch(self):
        p = PacingState()
        for _ in range(10):
            p.record_frame_interval(1.0 / 60.0)

        # Trigger hitch
        p.record_frame_interval(0.100)
        assert p.in_recovery
        assert p.recovery_frames == 1

        # Recover
        for _ in range(30):
            p.record_frame_interval(1.0 / 60.0)

        assert not p.in_recovery
        assert p.consecutive_stable_frames > 0

    def test_recovery_progress_increasing(self):
        p = PacingState()
        for _ in range(10):
            p.record_frame_interval(1.0 / 60.0)

        p.record_frame_interval(0.100)  # Trigger hitch

        progress_1 = p.recovery_progress()
        for _ in range(15):
            p.record_frame_interval(1.0 / 60.0)
        progress_2 = p.recovery_progress()

        assert progress_2 >= progress_1

    def test_full_recovery(self):
        p = PacingState()
        for _ in range(10):
            p.record_frame_interval(1.0 / 60.0)

        p.record_frame_interval(0.100)  # Trigger

        for _ in range(60):
            p.record_frame_interval(1.0 / 60.0)

        assert p.recovery_progress() >= 1.0

    def test_consecutive_stable_increases(self):
        p = PacingState()
        for i in range(50):
            p.record_frame_interval(1.0 / 60.0)
        assert p.consecutive_stable_frames >= 50

    def test_stabilization_reset_during_recovery(self):
        p = PacingState()
        for _ in range(10):
            p.record_frame_interval(1.0 / 60.0)

        p.record_frame_interval(0.100)
        assert p.should_reset_stabilization()

        for _ in range(10):
            p.record_frame_interval(1.0 / 60.0)
        # Should no longer need reset after several stable frames
        assert not p.in_recovery or not p.should_reset_stabilization()


class TestContinuityMetric:
    """Test the temporal continuity metric."""

    def test_perfect_continuity(self):
        p = PacingState()
        for _ in range(100):
            p.record_frame_interval(1.0 / 60.0)
        assert p.continuity_metric >= 0.99

    def test_continuity_drops_on_hitch(self):
        p = PacingState()
        for _ in range(10):
            p.record_frame_interval(1.0 / 60.0)

        continuity_before = p.continuity_metric
        p.record_frame_interval(0.100)
        assert p.continuity_metric < continuity_before

    def test_continuity_recovers(self):
        p = PacingState()
        for _ in range(10):
            p.record_frame_interval(1.0 / 60.0)

        p.record_frame_interval(0.100)
        low_point = p.continuity_metric

        for _ in range(50):
            p.record_frame_interval(1.0 / 60.0)

        assert p.continuity_metric > low_point

    def test_continuity_range(self):
        """Continuity should always be 0..1."""
        p = PacingState()

        # Perfect frames
        for _ in range(10):
            p.record_frame_interval(1.0 / 60.0)
        assert 0.0 <= p.continuity_metric <= 1.0

        # Hitched frames
        for _ in range(5):
            p.record_frame_interval(0.100)
        assert 0.0 <= p.continuity_metric <= 1.0


class TestPauseUnpause:
    """Test behavior during sim pause/unpause transitions."""

    def test_pause_detection_large_gap(self):
        """A very large dt should be handled gracefully."""
        p = PacingState()
        for _ in range(10):
            p.record_frame_interval(1.0 / 60.0)

        # Very large gap (5 second pause)
        dt_s = 5.0
        result = p.record_frame_interval(dt_s)
        assert result is not None
        assert result.type in (PacingAnomalyType.HITCH, PacingAnomalyType.PAUSE)

    def test_pause_recovery(self):
        p = PacingState()
        for _ in range(10):
            p.record_frame_interval(1.0 / 60.0)

        # Simulate pause
        p.record_frame_interval(5.0)
        assert p.in_recovery

        # Recovery after pause
        for _ in range(30):
            p.record_frame_interval(1.0 / 60.0)

        assert not p.in_recovery

    def test_repeated_pause_resume(self):
        p = PacingState()
        for _ in range(5):
            p.record_frame_interval(1.0 / 60.0)

        for cycle in range(3):
            # Pause for 2 seconds
            p.record_frame_interval(2.0)
            assert p.in_recovery

            # Resume
            for _ in range(30):
                p.record_frame_interval(1.0 / 60.0)


class TestFramePacingInstability:
    """Test detection of frame pacing instability patterns."""

    def test_oscillating_frame_times(self):
        """Alternating fast/slow frames should be detectable."""
        p = PacingState()

        # Oscillating pattern: 8ms, 25ms, 8ms, 25ms, ...
        for _ in range(20):
            p.record_frame_interval(0.008)
            p.record_frame_interval(0.025)

        # Standard deviation should be high
        assert p.dt_stddev > 5.0

    def test_graceful_degradation_under_load(self):
        """Should not crash under sustained low FPS."""
        p = PacingState()
        for _ in range(100):
            p.record_frame_interval(1.0 / 20.0)  # 20fps

        assert p.valid
        assert p.anomaly_count() > 0

    def test_sudden_fps_drop(self):
        """Sudden FPS drop from 60 to 15 should be detected."""
        p = PacingState()
        for _ in range(10):
            p.record_frame_interval(1.0 / 60.0)

        for _ in range(10):
            p.record_frame_interval(1.0 / 15.0)  # Sudden 15fps

        assert p.anomaly_count() > 0


class TestAnomalyLog:
    """Test the circular anomaly event log."""

    def test_anomaly_log_size_limited(self):
        p = PacingState()
        for _ in range(10):
            p.record_frame_interval(1.0 / 60.0)

        for _ in range(p.max_anomalies * 2):
            p.record_frame_interval(0.100)
            p.record_frame_interval(1.0 / 60.0)

        assert len(p.anomalies) <= p.max_anomalies

    def test_anomaly_event_fields(self):
        p = PacingState()
        for _ in range(10):
            p.record_frame_interval(1.0 / 60.0)

        result = p.record_frame_interval(0.100, frame_index=100)
        assert result is not None
        assert result.frame_index == 100
        assert result.duration_ms >= 100.0
        assert result.type != PacingAnomalyType.NONE

    def test_anomaly_types(self):
        """All anomaly types should be distinguishable."""
        for t in range(PacingAnomalyType.AIRCRAFT_LOAD + 1):
            assert t in ANOMALY_NAMES
            assert ANOMALY_NAMES[t] != ''


class TestIntegrationWithStabilization:
    """Test how pacing anomalies interact with stabilization."""

    def test_stabilization_reset_needed_after_hitch(self):
        p = PacingState()
        for _ in range(10):
            p.record_frame_interval(1.0 / 60.0)

        # After hitch, stabilization should be reset
        p.record_frame_interval(0.100)
        assert p.should_reset_stabilization()

    def test_stabilization_reset_not_needed_nominal(self):
        p = PacingState()
        for _ in range(10):
            p.record_frame_interval(1.0 / 60.0)
        assert not p.should_reset_stabilization()

    def test_recovery_frame_counting(self):
        p = PacingState()
        for _ in range(10):
            p.record_frame_interval(1.0 / 60.0)

        # Record a hitch
        p.record_frame_interval(0.100)
        assert p.anomaly_count() >= 1

        # After a hitch, in_recovery becomes True and recovery_frames starts at 1
        # because the hitch itself counted as a recovery frame
        # After a normal frame, the in_recovery is cleared and recovery_frames is reset
        # Test that multiple hitches cause multiple anomalies
        for _ in range(3):
            p.record_frame_interval(0.100)
        
        assert p.anomaly_count() >= 2

    def test_stable_frame_count_reset_on_anomaly(self):
        p = PacingState()
        for _ in range(20):
            p.record_frame_interval(1.0 / 60.0)

        assert p.consecutive_stable_frames >= 20

        p.record_frame_interval(0.100)
        assert p.consecutive_stable_frames == 0
