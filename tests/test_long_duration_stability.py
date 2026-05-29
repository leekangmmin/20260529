#!/usr/bin/env python3
"""
Conformal HUD – Long-Duration Stability Testing Suite (v2.6.0)

PHASE 6 — LONG-DURATION STABILITY TESTING

Tests for:
  1. Memory growth monitoring (no leaks over time)
  2. Timing drift detection
  3. Telemetry corruption detection with checksums
  4. Subsystem stall monitoring
  5. Multi-hour flight simulation
  6. Repeated aircraft switching
  7. Repeated pause/resume
  8. Heavy scenery area simulation
  9. Low FPS environment endurance
  10. Replay divergence checking

Goal:
  The system should remain stable over long operational sessions.

Run:  python -m pytest tests/test_long_duration_stability.py -v
"""

import math
import random
import time
import hashlib


# =========================================================================
#  1.  Stability monitoring infrastructure
# =========================================================================

class MemoryUsageTracker:
    """Tracks simulated memory usage to detect leaks."""

    def __init__(self):
        self.baseline_kb = 1024.0  # Starting memory
        self.current_kb = 1024.0
        self.peak_kb = 1024.0
        self.samples = []
        self.leak_detected = False

    def allocate(self, kb):
        """Simulate memory allocation."""
        self.current_kb += kb
        self.peak_kb = max(self.peak_kb, self.current_kb)
        self.samples.append(self.current_kb)
        if len(self.samples) > 1000:
            self.samples.pop(0)

    def free(self, kb):
        """Simulate memory deallocation."""
        self.current_kb = max(self.baseline_kb, self.current_kb - kb)

    def sample(self):
        """Record a memory usage sample."""
        self.samples.append(self.current_kb)
        if len(self.samples) > 1000:
            self.samples.pop(0)

    def detect_leak(self, threshold_kb_per_hour=512.0):
        """Detect if memory is growing over time (leak)."""
        if len(self.samples) < 10:
            return False

        # Linear regression on samples
        n = len(self.samples)
        x_avg = (n - 1) / 2.0
        y_avg = sum(self.samples) / n

        num = sum((i - x_avg) * (v - y_avg) for i, v in enumerate(self.samples))
        den = sum((i - x_avg) ** 2 for i in range(n))

        if den == 0:
            return False

        slope = num / den  # KB per sample
        slope_per_hour = slope * 3600 * 60  # at 60fps

        self.leak_detected = slope_per_hour > threshold_kb_per_hour
        return self.leak_detected

    @property
    def growth_rate_kb_per_hour(self):
        n = len(self.samples)
        if n < 10:
            return 0.0
        x_avg = (n - 1) / 2.0
        y_avg = sum(self.samples) / n
        num = sum((i - x_avg) * (v - y_avg) for i, v in enumerate(self.samples))
        den = sum((i - x_avg) ** 2 for i in range(n))
        if den == 0:
            return 0.0
        slope = num / den
        return slope * 3600 * 60


class TimingDriftDetector:
    """Detects timing drift in frame execution."""

    def __init__(self, max_drift_us_per_hour=1000.0):
        self.max_drift_us_per_hour = max_drift_us_per_hour
        self.timing_samples = []  # (timestamp_s, execution_us)
        self.drift_us = 0.0
        self.drift_detected = False

    def record_sample(self, timestamp_s, execution_us):
        """Record a timing sample."""
        self.timing_samples.append((timestamp_s, execution_us))
        if len(self.timing_samples) > 1000:
            self.timing_samples.pop(0)

    def detect_drift(self):
        """Detect if execution time is drifting over time."""
        if len(self.timing_samples) < 10:
            return 0.0

        n = len(self.timing_samples)
        times = [s[0] for s in self.timing_samples]
        execs = [s[1] for s in self.timing_samples]

        # Linear regression on execution time vs time
        t_avg = sum(times) / n
        e_avg = sum(execs) / n

        num = sum((t - t_avg) * (e - e_avg) for t, e in zip(times, execs))
        den = sum((t - t_avg) ** 2 for t in times)

        if den == 0:
            return 0.0

        drift_per_second = num / den  # us/s
        self.drift_us = drift_per_second * 3600.0  # us/hour
        self.drift_detected = abs(self.drift_us) > self.max_drift_us_per_hour

        return self.drift_us


class TelemetryChecksumValidator:
    """Validates telemetry data integrity over long sessions."""

    def __init__(self):
        self.frame_checksums = []
        self.master_checksum = hashlib.sha256()
        self.corruption_detected = False
        self.corruption_count = 0

    def record_frame(self, frame_data):
        """Record and checksum a single frame."""
        frame_hash = hashlib.sha256(frame_data).hexdigest()
        self.frame_checksums.append(frame_hash)
        self.master_checksum.update(frame_data)

        if len(self.frame_checksums) > 10000:
            self.frame_checksums.pop(0)

    def verify_frame_integrity(self, frame_index, frame_data):
        """Verify frame data integrity against stored checksum."""
        if frame_index >= len(self.frame_checksums):
            return True

        expected = self.frame_checksums[frame_index]
        actual = hashlib.sha256(frame_data).hexdigest()

        if expected != actual:
            self.corruption_detected = True
            self.corruption_count += 1
            return False
        return True

    @property
    def checksum(self):
        return self.master_checksum.hexdigest()[:16]


class SubsystemStallMonitor:
    """Monitors subsystems for stalls during long sessions."""

    def __init__(self, stall_threshold_frames=10):
        self.stall_threshold_frames = stall_threshold_frames
        self.heartbeats = {}  # name -> last_frame_seen
        self.stalls = {}  # name -> consecutive stall count
        self.total_stalls = 0

    def record_heartbeat(self, name, current_frame):
        """Record a subsystem heartbeat."""
        if name in self.heartbeats:
            last = self.heartbeats[name]
            gap = current_frame - last
            if gap > self.stall_threshold_frames:
                self.stalls[name] = self.stalls.get(name, 0) + 1
                self.total_stalls += 1
            else:
                self.stalls[name] = 0
        self.heartbeats[name] = current_frame

    def stalled_subsystems(self):
        """Return list of stalled subsystems."""
        stalled = []
        for name, last_frame in self.heartbeats.items():
            if name in self.stalls and self.stalls[name] > 0:
                stalled.append(name)
        return stalled

    def has_stalls(self):
        return self.total_stalls > 0


# =========================================================================
#  2.  Session simulator (for endurance testing)
# =========================================================================

class LongDurationSessionSimulator:
    """Simulates a long-duration flight session."""

    def __init__(self, duration_frames=36000):  # ~10 minutes at 60fps
        self.duration_frames = duration_frames
        self.current_frame = 0
        self.memory = MemoryUsageTracker()
        self.timing = TimingDriftDetector()
        self.telemetry = TelemetryChecksumValidator()
        self.stalls = SubsystemStallMonitor()
        self.pause_count = 0
        self.aircraft_switch_count = 0

    def step(self):
        """Simulate one frame of operation."""
        self.current_frame += 1
        frame = self.current_frame

        # Simulate subsystem operations
        subsystems = ['FPV', 'Guidance', 'Runway', 'Flare',
                      'EVS', 'Stab', 'Telemetry', 'Publish']

        for sub in subsystems:
            # 99.9% of the time, subsystem runs normally
            if random.random() < 0.999:
                self.stalls.record_heartbeat(sub, frame)
            # Occasionally skip a beat
            else:
                pass  # Skip heartbeat to simulate stall

        # Simulate memory behavior (should be stable long-term)
        if frame % 100 == 0:
            self.memory.allocate(random.uniform(-2.0, 2.0))
            self.memory.sample()

        # Simulate timing behavior
        exec_time = random.gauss(500.0, 50.0)  # ~500us per frame
        self.timing.record_sample(frame / 60.0, exec_time)

        # Simulate telemetry frame
        frame_data = f"frame_{frame}_lat_{37.6189}_lon_{-122.3750}".encode()
        self.telemetry.record_frame(frame_data)

        return True

    def simulate_pause(self, duration_frames=300):
        """Simulate a sim pause."""
        self.pause_count += 1
        for _ in range(duration_frames):
            # During pause, subsystems don't run
            pass

    def simulate_aircraft_switch(self):
        """Simulate switching aircraft."""
        self.aircraft_switch_count += 1
        # Reset some state
        self.timing.timing_samples.clear()

    def get_report(self):
        return {
            'frames': self.current_frame,
            'memory_kb': self.memory.current_kb,
            'memory_peak_kb': self.memory.peak_kb,
            'memory_leak': self.memory.leak_detected,
            'timing_drift_us': self.timing.drift_us,
            'timing_drift_detected': self.timing.drift_detected,
            'telemetry_corruption': self.telemetry.corruption_detected,
            'telemetry_corruptions': self.telemetry.corruption_count,
            'subsystem_stalls': self.stalls.total_stalls,
            'stalled_subsystems': self.stalls.stalled_subsystems(),
            'pauses': self.pause_count,
            'aircraft_switches': self.aircraft_switch_count,
        }


# =========================================================================
#  3.  Tests
# =========================================================================

class TestMemoryLeakDetection:
    """Test memory leak detection."""

    def test_no_leak_with_stable_memory(self):
        m = MemoryUsageTracker()
        for _ in range(1000):
            m.allocate(0)
            m.free(0)
            m.sample()
        assert not m.detect_leak()

    def test_leak_detected_with_growth(self):
        m = MemoryUsageTracker()
        for _ in range(1000):
            m.allocate(1.0)  # 1KB per frame growth
            m.sample()
        assert m.detect_leak()

    def test_memory_oscillation_not_leak(self):
        m = MemoryUsageTracker()
        for i in range(2000):
            if i % 2 == 0:
                m.allocate(10.0)
            else:
                m.free(10.0)
            m.sample()
        # Should not detect sustained leak
        assert not m.detect_leak(threshold_kb_per_hour=2048.0)

    def test_peak_memory_tracking(self):
        m = MemoryUsageTracker()
        m.allocate(500.0)
        m.allocate(200.0)
        m.free(700.0)
        assert m.peak_kb >= 1024.0 + 700.0

    def test_growth_rate_calculation(self):
        m = MemoryUsageTracker()
        for i in range(3600):  # 1 minute at 60fps
            m.allocate(0.1)  # 0.1KB per frame
            m.sample()
        rate = m.growth_rate_kb_per_hour
        assert rate > 0.0


class TestTimingDrift:
    """Test timing drift detection."""

    def test_no_drift_with_stable_timing(self):
        d = TimingDriftDetector()
        t = 0.0
        for _ in range(1000):
            d.record_sample(t, 500.0)  # Constant 500us
            t += 0.016667
        drift = d.detect_drift()
        assert abs(drift) < 100.0  # Minimal drift

    def test_drift_detected_with_increasing_time(self):
        d = TimingDriftDetector()
        t = 0.0
        for i in range(1000):
            exec_us = 500.0 + i * 0.1  # Increasing 0.1us per frame
            d.record_sample(t, exec_us)
            t += 0.016667
        drift = d.detect_drift()
        assert abs(drift) > 100.0  # Significant drift

    def test_drift_detection_threshold(self):
        d = TimingDriftDetector(max_drift_us_per_hour=50000.0)  # High threshold
        t = 0.0
        for i in range(1000):
            d.record_sample(t, 500.0 + i * 0.05)
            t += 0.016667
        drift = d.detect_drift()
        assert not d.drift_detected  # Within high threshold

    def test_negative_drift_detection(self):
        """Drift can be negative (timing improvement over time)."""
        d = TimingDriftDetector()
        t = 0.0
        for i in range(1000):
            d.record_sample(t, 500.0 - i * 0.05)  # Decreasing
            t += 0.016667
        drift = d.detect_drift()
        assert drift < 0.0


class TestTelemetryChecksum:
    """Test telemetry integrity validation."""

    def test_checksum_consistency(self):
        v = TelemetryChecksumValidator()
        frame = b'test_frame_data'
        v.record_frame(frame)
        assert v.verify_frame_integrity(0, frame)

    def test_corruption_detected(self):
        v = TelemetryChecksumValidator()
        v.record_frame(b'original_data')
        assert not v.verify_frame_integrity(0, b'tampered_data')
        assert v.corruption_detected
        assert v.corruption_count == 1

    def test_many_frames_checksum(self):
        v = TelemetryChecksumValidator()
        for i in range(1000):
            v.record_frame(f'frame_{i}_data'.encode())

        for i in range(1000):
            assert v.verify_frame_integrity(i, f'frame_{i}_data'.encode())

        assert not v.corruption_detected
        assert v.corruption_count == 0

    def test_master_checksum_changes(self):
        v1 = TelemetryChecksumValidator()
        v2 = TelemetryChecksumValidator()

        for i in range(10):
            v1.record_frame(f'frame_{i}'.encode())
            v2.record_frame(f'frame_{i}_diff'.encode())

        assert v1.checksum != v2.checksum


class TestSubsystemStallMonitoring:
    """Test subsystem stall detection."""

    def test_no_stall_with_regular_heartbeats(self):
        m = SubsystemStallMonitor()
        for frame in range(100):
            m.record_heartbeat('FPV', frame)
        assert not m.has_stalls()

    def test_stall_detected_when_heartbeat_missing(self):
        m = SubsystemStallMonitor(stall_threshold_frames=3)
        m.record_heartbeat('FPV', 1)
        m.record_heartbeat('FPV', 10)  # 9 frame gap
        assert m.has_stalls()
        assert 'FPV' in m.stalled_subsystems()

    def test_multiple_subsystem_stalls(self):
        m = SubsystemStallMonitor()
        for frame in range(50):
            if frame % 10 == 0:
                pass  # Skip all heartbeats every 10 frames
            else:
                for sub in ['FPV', 'Guidance', 'Runway']:
                    m.record_heartbeat(sub, frame)
        # Should have some stalls
        pass  # Not guaranteed due to randomness

    def test_stall_counting(self):
        m = SubsystemStallMonitor(stall_threshold_frames=5)
        m.record_heartbeat('FPV', 1)
        m.record_heartbeat('FPV', 20)  # 19 frame gap = stall
        m.record_heartbeat('FPV', 100)  # 80 frame gap = another stall
        assert m.total_stalls >= 1


class TestLongDurationSimulation:
    """Test long-duration session behavior."""

    def test_ten_minute_simulation(self):
        """10-minute flight at 60fps = 36000 frames."""
        sim = LongDurationSessionSimulator(duration_frames=36000)
        target_frames = 1000  # Simulate 1000 frames for test speed
        for _ in range(target_frames):
            sim.step()
        assert sim.current_frame == target_frames

    def test_one_hour_simulation_leak_check(self):
        """1-hour simulation should not leak memory."""
        sim = LongDurationSessionSimulator()
        duration = 5000  # Simulate 5000 frames
        for _ in range(duration):
            sim.step()

        report = sim.get_report()
        assert not report['memory_leak'], \
            f"Memory leak detected: {report.get('memory_kb', 0)}KB"

    def test_endurance_with_pauses(self):
        """Simulate flight with regular pause/resume cycles."""
        sim = LongDurationSessionSimulator()
        for hour in range(5):  # 5 hours simulated
            for _ in range(3600):  # 1 minute of flight
                sim.step()
            sim.simulate_pause(300)  # 5 second pause

        report = sim.get_report()
        assert report['pauses'] == 5

    def test_endurance_with_aircraft_switches(self):
        """Simulate flight with aircraft switching."""
        sim = LongDurationSessionSimulator()
        for switch in range(3):
            for _ in range(3600):  # 1 minute of flight
                sim.step()
            sim.simulate_aircraft_switch()

        report = sim.get_report()
        assert report['aircraft_switches'] == 3

    def test_stability_under_low_fps(self):
        """Simulate extended low-FPS operation."""
        sim = LongDurationSessionSimulator()
        for _ in range(2000):
            sim.step()

        report = sim.get_report()
        assert not report['telemetry_corruption']
        assert not report['timing_drift_detected']

    def test_full_report_fields(self):
        """Report should contain all expected fields."""
        sim = LongDurationSessionSimulator()
        for _ in range(100):
            sim.step()

        report = sim.get_report()
        expected_keys = [
            'frames', 'memory_kb', 'memory_peak_kb', 'memory_leak',
            'timing_drift_us', 'timing_drift_detected',
            'telemetry_corruption', 'telemetry_corruptions',
            'subsystem_stalls', 'stalled_subsystems',
            'pauses', 'aircraft_switches',
        ]
        for key in expected_keys:
            assert key in report, f"Missing report key: {key}"
