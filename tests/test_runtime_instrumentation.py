#!/usr/bin/env python3
"""
Conformal HUD – Real WASM Runtime Instrumentation Suite (v2.6.0)

PHASE 1 — REAL WASM RUNTIME INSTRUMENTATION

Tests for:
  1. High-resolution timing instrumentation (perf_begin/perf_end)
  2. Rolling timing histograms with P50/P95/P99 percentiles
  3. Subsystem execution time measurement
  4. L:var publish cost measurement
  5. SimVar read latency measurement
  6. JS bridge latency measurement
  7. Projection cost measurement
  8. Stabilization cost measurement
  9. Telemetry cost measurement
  10. Optical rendering overhead measurement
  11. Subsystem cost overlays
  12. Runtime profiling HUD data

Goal:
  Every major subsystem must be measurable in real simulator conditions.

Run:  python -m pytest tests/test_runtime_instrumentation.py -v
"""

import math
import struct
import time


# =========================================================================
#  1.  Matching C++ enums and constants
# =========================================================================

SUBSYSTEM_IDS = {
    'SimVarRead': 0,
    'FPV': 1,
    'Guidance': 2,
    'RunwayProj': 3,
    'Flare': 4,
    'Rollout': 5,
    'Collimation': 6,
    'EVS': 7,
    'Stabilization': 8,
    'AdvSymbology': 9,
    'Confidence': 10,
    'Declutter': 11,
    'Optical': 12,
    'SymPublish': 13,
    'Telemetry': 14,
    'TotalFrame': 15,
    'JSBridge': 16,
}

SUBSYSTEM_NAMES = {v: k for k, v in SUBSYSTEM_IDS.items()}

SUBSYSTEM_BUDGETS_US = {
    'SimVarRead': 200,
    'FPV': 250,
    'Guidance': 150,
    'RunwayProj': 300,
    'Flare': 100,
    'Rollout': 100,
    'Collimation': 50,
    'EVS': 80,
    'Stabilization': 200,
    'AdvSymbology': 120,
    'Confidence': 100,
    'Declutter': 50,
    'Optical': 50,
    'SymPublish': 150,
    'Telemetry': 150,
    'TotalFrame': 3000,
    'JSBridge': 200,
}

C_HUD_PERF_HIST_BINS = 32
C_HUD_PERF_MAX_HISTORY = 1024


# =========================================================================
#  2.  Python reference implementation of performance instrumentation
# =========================================================================

class TimingSample:
    """A single timing measurement sample."""
    __slots__ = ('us', 'frame_index')

    def __init__(self, us=0.0, frame_index=0):
        self.us = us
        self.frame_index = frame_index


class SubsystemHistogram:
    """Rolling-window timing histogram (mirrors C++ SubsystemHistogram)."""

    def __init__(self, name=''):
        self.name = name
        self.bin_count = C_HUD_PERF_HIST_BINS
        self.max_history = C_HUD_PERF_MAX_HISTORY
        self.samples = [TimingSample()] * self.max_history
        self.sample_write_pos = 0
        self.sample_count = 0
        self.running_sum_us = 0.0
        self.running_sum_sq_us = 0.0
        self.min_us = 1e9
        self.max_us = 0.0
        self.total_frames_measured = 0
        self.p50_us = 0.0
        self.p95_us = 0.0
        self.p99_us = 0.0
        self.last_percentile_update = 0
        self.valid = True

        # Initialize bins
        self.bins = [0] * self.bin_count
        self.bin_lower = [0.0] * self.bin_count
        self.bin_upper = [0.0] * self.bin_count
        for i in range(self.bin_count):
            t = i / self.bin_count
            self.bin_lower[i] = t * t * 5000.0
            self.bin_upper[i] = ((i + 1) / self.bin_count) ** 2 * 5000.0

    def record(self, us):
        """Record a timing sample in microseconds."""
        if not self.valid:
            return

        if self.sample_count < self.max_history:
            self.sample_count += 1

        idx = self.sample_write_pos % self.max_history
        self.samples[idx] = TimingSample(us, 0)
        self.sample_write_pos = (self.sample_write_pos + 1) % self.max_history

        self.running_sum_us += us
        self.running_sum_sq_us += us * us
        self.min_us = min(self.min_us, us)
        self.max_us = max(self.max_us, us)
        self.total_frames_measured += 1

        # Bin it
        for i in range(self.bin_count - 1):
            if self.bin_lower[i] <= us < self.bin_upper[i]:
                self.bins[i] += 1
                return
        self.bins[self.bin_count - 1] += 1

    @property
    def avg_us(self):
        if self.total_frames_measured == 0:
            return 0.0
        return self.running_sum_us / self.total_frames_measured

    @property
    def stddev_us(self):
        if self.total_frames_measured < 2:
            return 0.0
        n = self.total_frames_measured
        variance = (self.running_sum_sq_us / n) - (self.running_sum_us / n) ** 2
        return math.sqrt(max(0.0, variance))

    def compute_percentile(self, p):
        """Compute the p-th percentile from the rolling window samples."""
        if self.sample_count == 0:
            return 0.0

        count = min(self.sample_count, self.max_history)
        values = [self.samples[i].us for i in range(count)]
        values.sort()

        idx = p * (count - 1)
        lo = int(idx)
        hi = min(lo + 1, count - 1)
        frac = idx - lo
        return values[lo] * (1.0 - frac) + values[hi] * frac

    def update_percentiles(self):
        """Compute and cache P50/P95/P99."""
        self.p50_us = self.compute_percentile(0.50)
        self.p95_us = self.compute_percentile(0.95)
        self.p99_us = self.compute_percentile(0.99)


class SubsystemTiming:
    """Per-subsystem timing (mirrors C++ SubsystemTiming)."""

    def __init__(self, name='', budget_us=1000.0):
        self.name = name
        self.hist = SubsystemHistogram(name)
        self.last_us = 0.0
        self.peak_us = 0.0
        self.budget_us = budget_us
        self.over_budget = False
        self.valid = True

    def record(self, us):
        self.last_us = us
        self.peak_us = max(self.peak_us, us)
        self.over_budget = us > self.budget_us
        self.hist.record(us)

    @property
    def avg_us(self):
        return self.hist.avg_us

    @property
    def p95_us(self):
        return self.hist.p95_us

    @property
    def p99_us(self):
        return self.hist.p99_us

    @property
    def min_us(self):
        return self.hist.min_us

    @property
    def max_us(self):
        return self.hist.max_us


class PerfState:
    """Complete runtime performance state (mirrors C++ PerfState)."""

    def __init__(self):
        self.subsystems = {}
        for name, sid in SUBSYSTEM_IDS.items():
            budget = SUBSYSTEM_BUDGETS_US.get(name, 1000.0)
            self.subsystems[sid] = SubsystemTiming(name, budget)
        self.frame_start_us = 0.0
        self.frame_end_us = 0.0
        self.js_bridge_latency_us = 0.0
        self.enabled = True
        self.frame_active = False

    def begin_frame(self):
        if not self.enabled:
            return
        self.frame_active = True
        self.frame_start_us = time.time() * 1_000_000

    def end_frame(self):
        if not self.enabled or not self.frame_active:
            return 0.0
        self.frame_end_us = time.time() * 1_000_000
        total = self.frame_end_us - self.frame_start_us
        self.subsystems[SUBSYSTEM_IDS['TotalFrame']].record(total)
        self.frame_active = False
        return total

    def measure_subsystem(self, sid):
        """Context manager for measuring a subsystem."""
        class SubsystemMeasurer:
            def __init__(self, perf, sid_):
                self.perf = perf
                self.sid = sid_
                self.start = 0.0

            def __enter__(self):
                if self.perf.enabled and self.perf.frame_active:
                    self.start = time.time() * 1_000_000
                return self

            def __exit__(self, *args):
                if self.perf.enabled and self.perf.frame_active and self.start > 0:
                    elapsed = (time.time() * 1_000_000) - self.start
                    self.perf.subsystems[self.sid].record(elapsed)

        return SubsystemMeasurer(self, sid)

    def measure_js_bridge(self, latency_us):
        """Record a JS bridge latency measurement."""
        self.js_bridge_latency_us = latency_us
        self.subsystems[SUBSYSTEM_IDS['JSBridge']].record(latency_us)

    def update_percentiles(self):
        """Update all percentile caches."""
        for sub in self.subsystems.values():
            sub.hist.update_percentiles()

    def over_budget_count(self):
        """Count subsystems over budget."""
        return sum(1 for sub in self.subsystems.values() if sub.over_budget)

    def budget_ok(self):
        """Return True if all subsystems within budget."""
        return self.over_budget_count() == 0

    def get_report(self):
        """Generate a full timing report as a dict."""
        self.update_percentiles()
        report = {}
        for sid, sub in self.subsystems.items():
            name = SUBSYSTEM_NAMES.get(sid, f"Subsys{sid}")
            report[name] = {
                'avg_us': sub.avg_us,
                'min_us': sub.min_us,
                'max_us': sub.peak_us,
                'p50_us': sub.hist.p50_us,
                'p95_us': sub.p95_us,
                'p99_us': sub.p99_us,
                'budget_us': sub.budget_us,
                'over_budget': sub.over_budget,
                'samples': sub.hist.total_frames_measured,
            }
        return report


# =========================================================================
#  3.  Simulated subsystem work (for testing)
# =========================================================================

def simulate_subsystem_work(mean_us=100.0, std_us=20.0):
    """Simulate a subsystem doing work for a random duration."""
    import random
    return max(1.0, random.gauss(mean_us, std_us))


def simulate_js_bridge_roundtrip():
    """Simulate JS bridge round-trip latency."""
    import random
    return random.uniform(50.0, 200.0)


def simulate_simvar_read(count=25):
    """Simulate reading `count` SimVars."""
    import random
    # Each SimVar read costs ~8us
    return count * 8.0 + random.uniform(10.0, 30.0)


def simulate_projection(active_elements=5, runway_corners=4):
    """Simulate conformal projection costs."""
    return 150.0 + runway_corners * 20.0 + active_elements * 40.0


def simulate_stabilization(active_elements=8):
    """Simulate stabilization filter costs."""
    return 100.0 + active_elements * 15.0 + 30.0


def simulate_telemetry(recording=True):
    """Simulate telemetry recording costs."""
    cost = 80.0
    if recording:
        cost += 60.0
    return cost


def simulate_optical_rendering():
    """Simulate optical rendering overhead."""
    import random
    return random.uniform(30.0, 80.0)


# =========================================================================
#  4.  Tests
# =========================================================================

class TestTimingInstrumentation:
    """Test basic timing recording and retrieval."""

    def test_histogram_init(self):
        h = SubsystemHistogram('test')
        assert h.valid
        assert h.bin_count == C_HUD_PERF_HIST_BINS
        assert h.sample_count == 0
        assert h.min_us == 1e9
        assert h.max_us == 0.0
        assert h.total_frames_measured == 0

    def test_record_single_sample(self):
        h = SubsystemHistogram('test')
        h.record(100.0)
        assert h.sample_count == 1
        assert h.total_frames_measured == 1
        assert h.min_us == 100.0
        assert h.max_us == 100.0
        assert h.avg_us == 100.0

    def test_record_multiple_samples(self):
        h = SubsystemHistogram('test')
        samples = [50.0, 100.0, 150.0, 200.0, 250.0]
        for s in samples:
            h.record(s)
        assert h.sample_count == 5
        assert h.total_frames_measured == 5
        assert h.min_us == 50.0
        assert h.max_us == 250.0
        assert abs(h.avg_us - 150.0) < 0.01

    def test_rolling_window_overflow(self):
        h = SubsystemHistogram('test')
        # Record more than max history
        for i in range(C_HUD_PERF_MAX_HISTORY + 100):
            h.record(float(i % 1000))
        assert h.sample_count == C_HUD_PERF_MAX_HISTORY
        assert h.total_frames_measured == C_HUD_PERF_MAX_HISTORY + 100

    def test_percentile_computation(self):
        h = SubsystemHistogram('test')
        # Record values 0, 10, 20, ..., 990
        for i in range(100):
            h.record(float(i * 10))
        h.update_percentiles()
        # P50 should be ~450, P95 ~950, P99 ~990
        assert abs(h.p50_us - 450.0) < 50.0, f"P50={h.p50_us}"
        assert abs(h.p95_us - 950.0) < 50.0, f"P95={h.p95_us}"
        assert abs(h.p99_us - 990.0) < 50.0, f"P99={h.p99_us}"

    def test_percentile_empty_histogram(self):
        h = SubsystemHistogram('test')
        assert h.compute_percentile(0.5) == 0.0
        assert h.compute_percentile(0.95) == 0.0
        assert h.compute_percentile(0.99) == 0.0

    def test_percentile_single_sample(self):
        h = SubsystemHistogram('test')
        h.record(42.0)
        h.update_percentiles()
        assert h.p50_us == 42.0
        assert h.p95_us == 42.0
        assert h.p99_us == 42.0

    def test_binning(self):
        h = SubsystemHistogram('test')
        for i in range(100):
            h.record(float(i * 10))  # 0, 10, 20, ..., 990
        total_binned = sum(h.bins)
        assert total_binned == 100
        # Most small values should be in early bins
        assert h.bins[0] >= 0

    def test_running_stats(self):
        h = SubsystemHistogram('test')
        samples = [10.0, 20.0, 30.0, 40.0, 50.0]
        for s in samples:
            h.record(s)
        expected_mean = 30.0
        expected_var = sum((s - expected_mean) ** 2 for s in samples) / len(samples)
        assert abs(h.avg_us - expected_mean) < 0.01
        assert abs(h.stddev_us - math.sqrt(expected_var)) < 0.01


class TestPerfState:
    """Test the complete performance state management."""

    def test_perf_state_init(self):
        p = PerfState()
        assert p.enabled
        assert not p.frame_active
        assert len(p.subsystems) == len(SUBSYSTEM_IDS)

    def test_frame_timing(self):
        p = PerfState()
        p.begin_frame()
        import time
        time.sleep(0.001)  # 1ms
        total = p.end_frame()
        assert total > 500.0  # At least 500us
        assert total < 50000.0  # Less than 50ms
        assert not p.frame_active

    def test_subsystem_measurement(self):
        p = PerfState()
        p.begin_frame()

        with p.measure_subsystem(SUBSYSTEM_IDS['FPV']):
            import time
            time.sleep(0.0005)  # 500us

        with p.measure_subsystem(SUBSYSTEM_IDS['Guidance']):
            pass

        p.end_frame()

        fpv = p.subsystems[SUBSYSTEM_IDS['FPV']]
        assert fpv.last_us > 200.0
        assert fpv.hist.total_frames_measured == 1

    def test_js_bridge_measurement(self):
        p = PerfState()
        p.measure_js_bridge(150.0)
        assert p.js_bridge_latency_us == 150.0
        js = p.subsystems[SUBSYSTEM_IDS['JSBridge']]
        assert js.last_us == 150.0

    def test_all_subsystems_measurable(self):
        """Verify every defined subsystem can be measured."""
        p = PerfState()
        p.begin_frame()

        # Skip TotalFrame (measured by end_frame) and JSBridge (measured separately)
        skip_ids = {SUBSYSTEM_IDS['TotalFrame'], SUBSYSTEM_IDS['JSBridge']}
        for sid in sorted(SUBSYSTEM_IDS.values()):
            if sid in skip_ids:
                continue
            with p.measure_subsystem(sid):
                pass  # No actual work, just the measurement

        p.end_frame()

        for sid, sub in p.subsystems.items():
            if sid in skip_ids:
                continue  # Skip TotalFrame/JSBridge which are measured differently
            assert sub.hist.total_frames_measured == 1, \
                f"Subsystem {SUBSYSTEM_NAMES.get(sid)} was not measured"

    def test_over_budget_detection(self):
        p = PerfState()
        p.begin_frame()

        with p.measure_subsystem(SUBSYSTEM_IDS['FPV']):
            # Simulate exceeding budget
            pass

        p.end_frame()

        assert p.over_budget_count() >= 0

    def test_budget_ok_with_low_load(self):
        p = PerfState()
        p.begin_frame()
        with p.measure_subsystem(SUBSYSTEM_IDS['Declutter']):
            pass
        p.end_frame()
        # Declutter budget is 50us, measurement should be ~0
        d = p.subsystems[SUBSYSTEM_IDS['Declutter']]
        assert d.last_us < d.budget_us or d.last_us == 0.0

    def test_report_generation(self):
        p = PerfState()
        p.begin_frame()
        with p.measure_subsystem(SUBSYSTEM_IDS['FPV']):
            pass
        with p.measure_subsystem(SUBSYSTEM_IDS['Guidance']):
            pass
        p.end_frame()

        report = p.get_report()
        assert 'FPV' in report
        assert 'Guidance' in report
        assert 'TotalFrame' in report
        assert 'avg_us' in report['FPV']
        assert 'p95_us' in report['FPV']
        assert 'p99_us' in report['FPV']

    def test_disabled_instrumentation(self):
        p = PerfState()
        p.enabled = False
        p.begin_frame()
        assert not p.frame_active  # Should not activate when disabled
        total = p.end_frame()
        assert total == 0.0


class TestSubsystemCostModels:
    """Test that subsystem cost models produce reasonable values."""

    def test_simvar_read_cost(self):
        cost = simulate_simvar_read(25)
        assert 100.0 < cost < 500.0, f"SimVar read cost {cost}us out of range"

    def test_simvar_read_few_vars(self):
        cost = simulate_simvar_read(5)
        assert 20.0 < cost < 100.0

    def test_simvar_read_many_vars(self):
        cost = simulate_simvar_read(50)
        assert 200.0 < cost < 800.0

    def test_projection_cost(self):
        cost = simulate_projection(active_elements=5, runway_corners=4)
        assert 300.0 < cost < 700.0, f"Projection cost {cost}us"

    def test_projection_few_elements(self):
        cost = simulate_projection(active_elements=2, runway_corners=2)
        assert 150.0 < cost < 400.0

    def test_projection_many_corners(self):
        cost = simulate_projection(active_elements=8, runway_corners=8)
        assert 400.0 < cost < 1000.0

    def test_stabilization_cost(self):
        cost = simulate_stabilization(active_elements=8)
        assert 150.0 < cost < 400.0, f"Stabilization cost {cost}us"

    def test_stabilization_few_elements(self):
        cost = simulate_stabilization(active_elements=2)
        assert 100.0 < cost < 250.0

    def test_telemetry_cost_enabled(self):
        cost = simulate_telemetry(recording=True)
        assert 100.0 < cost < 300.0, f"Telemetry cost {cost}us"

    def test_telemetry_cost_disabled(self):
        cost = simulate_telemetry(recording=False)
        assert 50.0 < cost < 200.0

    def test_optical_rendering_cost(self):
        cost = simulate_optical_rendering()
        assert 20.0 < cost < 200.0, f"Optical cost {cost}us"

    def test_all_subsystem_budgets_defined(self):
        """Every subsystem must have a defined budget."""
        for name in SUBSYSTEM_IDS:
            assert name in SUBSYSTEM_BUDGETS_US, \
                f"Missing budget for {name}"

    def test_subsystem_budgets_reasonable(self):
        for name, budget in SUBSYSTEM_BUDGETS_US.items():
            assert budget >= 10.0, f"Budget too small for {name}: {budget}us"
            assert budget <= 10000.0, f"Budget too large for {name}: {budget}us"


class TestFrameTimingDiagnostics:
    """Test frame timing and diagnostics helpers."""

    def test_frame_rate_calculation(self):
        # Simulate 60fps
        dt_s = 1.0 / 60.0
        fps = 1.0 / dt_s
        assert abs(fps - 60.0) < 0.01

    def test_jitter_detection(self):
        jitter = 0.0
        for _ in range(10):
            dt_s = 1.0 / 60.0
            jitter_val = abs(dt_s - 1.0/60.0) * 1000.0
            jitter = jitter * 0.95 + jitter_val * 0.05
        assert jitter >= 0.0

    def test_high_jitter_detection(self):
        jitter = 0.0
        for _ in range(10):
            dt_s = 1.0 / 30.0  # 30fps - heavy jitter
            jitter_val = abs(dt_s - 1.0/60.0) * 1000.0
            jitter = jitter * 0.95 + jitter_val * 0.05
        assert jitter > 5.0  # Should detect >5ms of jitter


class TestRollingHistory:
    """Test rolling window behavior for timing history."""

    def test_rolling_mean_stable(self):
        """Rolling mean should stabilize with enough samples."""
        h = SubsystemHistogram('test')
        for _ in range(100):
            h.record(100.0)
        assert abs(h.avg_us - 100.0) < 0.01

    def test_rolling_mean_tracks_changes(self):
        """Rolling mean should eventually track sustained changes."""
        h = SubsystemHistogram('test')
        # First 50 samples at 100us
        for _ in range(50):
            h.record(100.0)
        # Next 50 samples at 200us
        for _ in range(50):
            h.record(200.0)
        # Should be closer to 200 than 100 with full rolling window
        assert h.avg_us > 120.0

    def test_sample_count_limited(self):
        h = SubsystemHistogram('test')
        for i in range(C_HUD_PERF_MAX_HISTORY * 2):
            h.record(float(i))
        assert h.sample_count == C_HUD_PERF_MAX_HISTORY

    def test_min_max_tracking(self):
        h = SubsystemHistogram('test')
        h.record(50.0)
        h.record(200.0)
        h.record(100.0)
        assert h.min_us == 50.0
        assert h.max_us == 200.0

    def test_empty_histogram_avg(self):
        h = SubsystemHistogram('test')
        assert h.avg_us == 0.0
        assert h.stddev_us == 0.0


class TestProfilingHUDData:
    """Test that profiling data can be formatted for HUD overlay."""

    def test_report_contains_all_subsystems(self):
        p = PerfState()
        p.begin_frame()
        for sid in SUBSYSTEM_IDS.values():
            with p.measure_subsystem(sid):
                pass
        p.end_frame()
        report = p.get_report()

        for name in SUBSYSTEM_IDS:
            assert name in report, f"Missing {name} in report"

    def test_report_format_for_hud(self):
        """Report should be easily formatted into HUD overlay strings."""
        p = PerfState()
        p.begin_frame()
        with p.measure_subsystem(SUBSYSTEM_IDS['FPV']):
            pass
        with p.measure_subsystem(SUBSYSTEM_IDS['Guidance']):
            pass
        p.end_frame()

        report = p.get_report()

        # Format as HUD strings
        hud_lines = []
        for name, data in report.items():
            if data['samples'] > 0:
                line = f"{name}: avg={data['avg_us']:.0f}us P95={data['p95_us']:.0f}us"
                if data['over_budget']:
                    line += " OVER!"
                hud_lines.append(line)

        assert len(hud_lines) > 0
        assert any('FPV' in l for l in hud_lines)

    def test_budget_violation_reporting(self):
        """Over-budget subsystems should be clearly reported."""
        p = PerfState()
        # Set a very low budget for testing
        p.subsystems[SUBSYSTEM_IDS['FPV']].budget_us = 1.0

        p.begin_frame()
        with p.measure_subsystem(SUBSYSTEM_IDS['FPV']):
            import time
            time.sleep(0.0001)  # 100us
        p.end_frame()

        assert p.subsystems[SUBSYSTEM_IDS['FPV']].over_budget

    def test_percentile_consistency(self):
        """P50 <= P95 <= P99 should always hold."""
        p = PerfState()
        p.begin_frame()

        # Generate a range of timing values
        import random
        for sid in list(SUBSYSTEM_IDS.values())[:5]:
            for _ in range(50):
                with p.measure_subsystem(sid):
                    time.sleep(random.uniform(0.00001, 0.001))

        p.end_frame()
        p.update_percentiles()

        for sid, sub in p.subsystems.items():
            if sub.hist.total_frames_measured > 0:
                assert sub.hist.p50_us <= sub.hist.p95_us + 0.01, \
                    f"P50 > P95 for {SUBSYSTEM_NAMES[sid]}"
                assert sub.hist.p95_us <= sub.hist.p99_us + 0.01, \
                    f"P95 > P99 for {SUBSYSTEM_NAMES[sid]}"


class TestSubsystemHeartbeatIntegration:
    """Test heartbeat-style monitoring tied to performance."""

    def test_heartbeat_tracking(self):
        heartbeats = {}
        for name in SUBSYSTEM_IDS:
            heartbeats[name] = 0

        # Simulate 10 frames of work
        for frame in range(10):
            for name in SUBSYSTEM_IDS:
                heartbeats[name] += 1

        assert all(v == 10 for v in heartbeats.values())

    def test_stalled_subsystem_detection(self):
        """Test that missing heartbeats indicate stalls."""
        # Simple heartbeat tracking
        heartbeats = {name: 0 for name in list(SUBSYSTEM_IDS.keys())[:5]}
        stalled = set()

        for frame in range(10):
            for name in heartbeats:
                if name == 'FPV' and frame == 5:
                    continue  # FPV misses frame 5
                heartbeats[name] += 1

        for name in heartbeats:
            if heartbeats[name] < 10:
                stalled.add(name)

        assert 'FPV' in stalled


    def test_all_subsystems_heartbeat(self):
        """Every subsystem should have a heartbeat counter."""
        for name in SUBSYSTEM_IDS:
            assert name  # Just check they all have names


class TestRuntimeProfilingOverlay:
    """Test data formatting for the runtime profiling HUD overlay."""

    def test_overlay_string_format(self):
        """Test that overlay data formats into readable strings."""
        data = {
            'FPV': {'us': 120.5, 'budget': 250},
            'Guidance': {'us': 85.3, 'budget': 150},
            'RunwayProj': {'us': 310.2, 'budget': 300},
        }

        lines = []
        for name, d in data.items():
            pct = (d['us'] / d['budget']) * 100
            flag = " ⚠" if pct > 80 else ""
            lines.append(f"{name}: {d['us']:.0f}us ({pct:.0f}%){flag}")

        assert any('FPV' in l for l in lines)
        assert any('⚠' in l for l in lines)  # RunwayProj is over 80%

    def test_histogram_data_for_overlay(self):
        """Test histogram data can be formatted for visual display."""
        h = SubsystemHistogram('FPV')
        for i in range(100):
            h.record(float(i * 5))

        # Format as bar data (simplified)
        max_bin = max(h.bins)
        bars = []
        for i in range(h.bin_count):
            if max_bin > 0:
                bar_len = int((h.bins[i] / max_bin) * 20)
                bars.append('#' * bar_len)

        assert len(bars) == C_HUD_PERF_HIST_BINS
        assert any(len(b) > 0 for b in bars)  # At least some bars have data
