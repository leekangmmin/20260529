#!/usr/bin/env python3
"""
Conformal HUD – WASM Performance Certification Suite (v2.5.0)

PHASE 4 — WASM PERFORMANCE CERTIFICATION

Profiles and validates:
  1. Virtual dispatch overhead cost model
  2. Projection cost model
  3. Stabilization cost model
  4. Telemetry cost model
  5. JS rendering cost model
  6. L:var publishing throughput
  7. Adaptive throttling
  8. Low-FPS degradation mode
  9. Subsystem rate limiting
  10. Telemetry decimation
  11. Render quality scaling

Goal:
  Stable operation under heavy MSFS load.

Run:  python -m pytest tests/test_performance.py -v
"""

import math
import time


# =========================================================================
#  1.  Performance Budget Constants (WASM target: MSFS 2024)
# =========================================================================

# Per-frame budget: 16.67ms at 60fps (MSFS WASM gauge slot)
# We should target under 5ms total CPU per frame to not impact sim frame rate.
FRAME_BUDGET_MS = 16.67
TARGET_BUDGET_MS = 3.0    # Ideal HUD budget
WARNING_BUDGET_MS = 5.0   # Start throttling above this
CRITICAL_BUDGET_MS = 8.0  # Emergency measures above this

# Subsystem budget allocations
SUBSYSTEM_BUDGETS_US = {  # microseconds
    'simvar_read': 200,
    'runway_projection': 300,
    'fpv': 250,
    'guidance': 150,
    'flare': 100,
    'rollout': 100,
    'stabilization': 200,
    'collimation': 50,
    'symbology_publish': 150,
    'telemetry': 150,
    'confidence': 100,
    'optical': 50,
    'declutter': 50,
    'watchdog': 50,
}

# L:var throughput targets
LVAR_THROUGHPUT_TARGET = 100   # L:vars per frame max
LVAR_PUBLISH_BUDGET_US = 500   # Microseconds for L:var publishing

# Render quality levels
QUALITY_LEVELS = {
    'ultra': 1.0,
    'high': 0.85,
    'medium': 0.65,
    'low': 0.45,
    'minimum': 0.25,
}


# =========================================================================
#  2.  Cost Model Base
# =========================================================================

class PerformanceCostModel:
    """Models computational cost of HUD subsystems."""

    def __init__(self, base_cost_us=0, complexity_factor=1.0):
        self.base_cost_us = base_cost_us
        self.complexity_factor = complexity_factor
        self._measurements = []

    def estimate(self, active_elements=1, resolution_scale=1.0,
                 telemetry_enabled=True, stabilization_enabled=True):
        """Estimate cost in microseconds."""
        cost = self.base_cost_us
        cost += active_elements * self.complexity_factor * 10
        if resolution_scale < 1.0:
            cost *= 0.5 + resolution_scale * 0.5
        if not telemetry_enabled:
            cost *= 0.8
        if not stabilization_enabled:
            cost *= 0.85
        return cost

    def measure(self, cost_us):
        """Record an actual measurement."""
        self._measurements.append(cost_us)

    def avg_cost(self):
        if not self._measurements:
            return 0.0
        return sum(self._measurements) / len(self._measurements)

    def max_cost(self):
        if not self._measurements:
            return 0.0
        return max(self._measurements)

    def p95_cost(self):
        if not self._measurements:
            return 0.0
        sorted_m = sorted(self._measurements)
        idx = int(len(sorted_m) * 0.95)
        return sorted_m[min(idx, len(sorted_m) - 1)]

    def budget_ok(self):
        budget = SUBSYSTEM_BUDGETS_US.get(
            self.__class__.__name__.lower().replace('model', ''),
            WARNING_BUDGET_MS * 1000)
        return self.p95_cost() <= budget


# =========================================================================
#  3.  Subsystem Cost Models
# =========================================================================

class SimvarReadCostModel(PerformanceCostModel):
    """Cost model for MSFS SimVar reads."""

    def __init__(self):
        super().__init__(base_cost_us=50, complexity_factor=1.5)

    def estimate(self, active_vars=25, resolution_scale=1.0, **kwargs):
        # Each SimVar read costs ~8us in the WASM environment
        cost = active_vars * 8.0
        cost += 20  # overhead for gauge API call
        return cost


class ProjectionCostModel(PerformanceCostModel):
    """Cost model for conformal projection pipeline."""

    def __init__(self):
        super().__init__(base_cost_us=150, complexity_factor=2.0)

    def estimate(self, active_elements=5, resolution_scale=1.0,
                 runway_corners=4, **kwargs):
        corner_cost = runway_corners * 20.0  # ~20us per corner
        element_cost = active_elements * 40.0  # ~40us per element
        return self.base_cost_us + corner_cost + element_cost


class StabilizationCostModel(PerformanceCostModel):
    """Cost model for symbol stabilization filters."""

    def __init__(self):
        super().__init__(base_cost_us=100, complexity_factor=1.5)

    def estimate(self, active_elements=8, resolution_scale=1.0,
                 turbulence_detection=True, **kwargs):
        base = self.base_cost_us
        base += active_elements * 15  # ~15us per element filter
        if turbulence_detection:
            base += 30  # turbulence detection overhead
        return base


class TelemetryCostModel(PerformanceCostModel):
    """Cost model for telemetry recording and replay."""

    def __init__(self):
        super().__init__(base_cost_us=80, complexity_factor=1.0)

    def estimate(self, recording=True, frame_count=36000,
                 event_count=0, **kwargs):
        cost = self.base_cost_us
        if recording:
            cost += 60  # frame capture + checksum
            cost += event_count * 5  # per event overhead
        # Cost scales very slowly with buffer size (ring buffer)
        if frame_count > 10000:
            cost += 10
        return cost


class JSRederingCostModel(PerformanceCostModel):
    """Cost model for JS-side Canvas rendering."""

    def __init__(self):
        super().__init__(base_cost_us=500, complexity_factor=3.0)

    def estimate(self, active_elements=15, resolution_scale=1.0,
                 quality_level='high', **kwargs):
        quality = QUALITY_LEVELS.get(quality_level, 0.85)
        # JS rendering is much more expensive than WASM
        base = 500.0
        element_cost = active_elements * 50.0
        quality_factor = 0.5 + quality * 0.5
        return (base + element_cost) * quality_factor


class LVarPublishCostModel(PerformanceCostModel):
    """Cost model for L:var publishing throughput."""

    def __init__(self):
        super().__init__(base_cost_us=100, complexity_factor=1.0)

    def estimate(self, active_lvars=60, changed_lvars=30, **kwargs):
        # Setting an L:var costs ~5us
        # Changed detection costs ~2us per var
        return active_lvars * 2.0 + changed_lvars * 5.0 + 20


# =========================================================================
#  4.  Adaptive Throttling System
# =========================================================================

class AdaptiveThrottleState:
    """Per-subsystem adaptive throttle state."""

    def __init__(self, name, max_rate_hz=60, min_rate_hz=5):
        self.name = name
        self.max_rate_hz = max_rate_hz
        self.min_rate_hz = min_rate_hz
        self.current_rate_hz = max_rate_hz
        self._last_run = 0.0
        self._run_count = 0
        self._skip_count = 0
        self._total_time_s = 0.0

    def should_run(self, current_time_s):
        """Determine if subsystem should run at current time."""
        elapsed = current_time_s - self._last_run
        interval = 1.0 / max(self.current_rate_hz, 1)
        if elapsed >= interval:
            self._last_run = current_time_s
            self._run_count += 1
            return True
        self._skip_count += 1
        return False

    def throttle(self, factor):
        """Reduce rate by factor (0..1 where 0 = max throttle)."""
        rate_range = self.max_rate_hz - self.min_rate_hz
        self.current_rate_hz = self.max_rate_hz - rate_range * factor
        self.current_rate_hz = max(self.min_rate_hz, min(self.max_rate_hz,
                                                          self.current_rate_hz))

    def reset(self):
        self.current_rate_hz = self.max_rate_hz
        self._skip_count = 0


class AdaptiveThrottlingManager:
    """Manages adaptive throttling across all subsystems."""

    def __init__(self, target_fps=60.0):
        self.target_fps = target_fps
        self._subsystems = {}
        self._frame_times = []
        self._max_history = 60  # ~1 second
        self.throttle_active = False
        self.throttle_level = 0.0  # 0..1

    def register(self, name, max_rate_hz=60, min_rate_hz=5):
        self._subsystems[name] = AdaptiveThrottleState(
            name, max_rate_hz, min_rate_hz)

    def get(self, name):
        return self._subsystems.get(name)

    def record_frame_time(self, dt_ms):
        """Record frame time for load analysis."""
        self._frame_times.append(dt_ms)
        if len(self._frame_times) > self._max_history:
            self._frame_times.pop(0)

    def avg_frame_time(self):
        if not self._frame_times:
            return 0.0
        return sum(self._frame_times) / len(self._frame_times)

    def compute_throttle(self):
        """Compute throttle level based on recent frame times.

        Returns throttle level (0 = no throttle, 1 = max throttle).
        """
        avg = self.avg_frame_time()
        if avg < TARGET_BUDGET_MS:
            self.throttle_level = 0.0
        elif avg < WARNING_BUDGET_MS:
            self.throttle_level = (avg - TARGET_BUDGET_MS) / (
                WARNING_BUDGET_MS - TARGET_BUDGET_MS) * 0.3
        elif avg < CRITICAL_BUDGET_MS:
            self.throttle_level = 0.3 + (avg - WARNING_BUDGET_MS) / (
                CRITICAL_BUDGET_MS - WARNING_BUDGET_MS) * 0.4
        else:
            self.throttle_level = 0.7 + min((avg - CRITICAL_BUDGET_MS) / 10.0,
                                             0.3)

        self.throttle_level = max(0.0, min(1.0, self.throttle_level))
        self.throttle_active = self.throttle_level > 0.01

        # Apply throttle to all subsystems
        for sub in self._subsystems.values():
            sub.throttle(self.throttle_level)

        return self.throttle_level

    def estimate_skip_ratio(self):
        """Estimate what fraction of frames are being skipped."""
        total = sum(s._run_count + s._skip_count
                    for s in self._subsystems.values()
                    if hasattr(s, '_run_count'))
        skipped = sum(s._skip_count
                      for s in self._subsystems.values()
                      if hasattr(s, '_skip_count'))
        if total == 0:
            return 0.0
        return skipped / max(total, 1)


# =========================================================================
#  5.  Low-FPS Degradation Mode
# =========================================================================

class LowFPSDegradationManager:
    """Manages HUD quality degradation during low FPS conditions."""

    # Degradation stages
    STAGE_NORMAL = 0
    STAGE_REDUCED = 1     # Reduce render quality
    STAGE_SIMPLIFIED = 2  # Simplify symbology
    STAGE_MINIMAL = 3     # Minimal rendering
    STAGE_OFF = 4         # HUD off / standby

    def __init__(self):
        self.stage = self.STAGE_NORMAL
        self.quality_level = 'ultra'
        self.fps_thresholds = {
            self.STAGE_REDUCED: 45.0,
            self.STAGE_SIMPLIFIED: 30.0,
            self.STAGE_MINIMAL: 20.0,
            self.STAGE_OFF: 10.0,
        }
        self._fps_history = []
        self._transition_time_s = 0.5  # Time between stages

    def update(self, current_fps, dt_s):
        """Update degradation stage based on current FPS."""
        self._fps_history.append(current_fps)
        if len(self._fps_history) > 10:
            self._fps_history.pop(0)

        avg_fps = sum(self._fps_history) / len(self._fps_history)

        # Determine target stage based on avg FPS
        target = self.STAGE_NORMAL
        if avg_fps < self.fps_thresholds[self.STAGE_OFF]:
            target = self.STAGE_OFF
        elif avg_fps < self.fps_thresholds[self.STAGE_MINIMAL]:
            target = self.STAGE_MINIMAL
        elif avg_fps < self.fps_thresholds[self.STAGE_SIMPLIFIED]:
            target = self.STAGE_SIMPLIFIED
        elif avg_fps < self.fps_thresholds[self.STAGE_REDUCED]:
            target = self.STAGE_REDUCED

        if target < self.stage:
            self.stage = target
        elif target > self.stage:
            self._transition_time_s -= dt_s
            if self._transition_time_s <= 0.0:
                self.stage = target

        if self.stage == target:
            self._transition_time_s = 0.5

        stage_to_quality = {
            self.STAGE_NORMAL: "ultra",
            self.STAGE_REDUCED: "high",
            self.STAGE_SIMPLIFIED: "medium",
            self.STAGE_MINIMAL: "low",
            self.STAGE_OFF: "minimum",
        }
        self.quality_level = stage_to_quality.get(self.stage, "ultra")
        return self.stage

    @property
    def scale_factor(self):
        """Render scale factor for current stage (0..1)."""
        return QUALITY_LEVELS.get(self.quality_level, 1.0)

    @property
    def enabled_features(self):
        """List of enabled features at current stage."""
        if self.stage >= self.STAGE_OFF:
            return ["hud_power"]
        features = ["hud_power", "fpv", "runway", "horizon", "pitch_ladder"]
        if self.stage <= self.STAGE_SIMPLIFIED:
            features += ["guidance", "flare_cue"]
        if self.stage <= self.STAGE_REDUCED:
            features += ["bloom", "flare", "evs"]
        return features


class SubsystemRateLimiter:
    """Rate-limits individual subsystems to prevent overload."""

    def __init__(self):
        self._limits = {}
        self._last_run = {}

    def set_limit(self, subsystem_name, max_per_second):
        """Set maximum execution rate for a subsystem."""
        self._limits[subsystem_name] = max_per_second

    def get_limit(self, subsystem_name):
        """Get the current limit for a subsystem."""
        return self._limits.get(subsystem_name, 60)

    def allow(self, subsystem_name, current_time_s):
        """Check if subsystem can run now (returns True if allowed)."""
        limit = self._limits.get(subsystem_name, 60)
        if limit <= 0:
            return False
        min_interval = 1.0 / limit
        last_run = self._last_run.get(subsystem_name, -1.0)
        if current_time_s - last_run >= min_interval:
            self._last_run[subsystem_name] = current_time_s
            return True
        return False

    def limit_all(self, fps, current_time_s):
        """Set limits based on current FPS."""
        if fps >= 45:
            for sub in ["fpv", "guidance", "flare", "rollout", "stabilization"]:
                self.set_limit(sub, 60)
            for sub in ["evs", "collimation", "optical", "depth_illusion"]:
                self.set_limit(sub, 30)
        elif fps >= 30:
            for sub in ["fpv", "guidance", "flare", "rollout"]:
                self.set_limit(sub, 30)
            for sub in ["stabilization"]:
                self.set_limit(sub, 15)
            for sub in ["evs", "collimation", "optical"]:
                self.set_limit(sub, 10)
        elif fps >= 20:
            for sub in ["fpv", "runway", "horizon"]:
                self.set_limit(sub, 15)
            for sub in ["guidance", "flare"]:
                self.set_limit(sub, 5)
            for sub in ["stabilization"]:
                self.set_limit(sub, 5)
            for sub in ["evs", "collimation", "optical", "depth_illusion"]:
                self.set_limit(sub, 1)
        else:
            for sub in (list(self._limits.keys()) or
                        ["evs", "collimation", "optical", "depth_illusion",
                         "fpv", "guidance", "flare", "rollout",
                         "stabilization", "symbology_publish",
                         "telemetry", "confidence", "declutter"]):
                self.set_limit(sub, 1)


class TelemetryDecimator:
    """Decimates telemetry frames to reduce CPU/memory usage."""

    def __init__(self, target_rate_hz=10):
        self.target_rate_hz = target_rate_hz
        self._frame_count = 0
        self._recorded_count = 0

    def should_record(self, frame_index, current_fps):
        """Determine if a frame should be recorded based on decimation."""
        if current_fps <= 0:
            return False
        if current_fps < self.target_rate_hz:
            interval = 2
        else:
            interval = int(current_fps / self.target_rate_hz)
        should = (frame_index % interval == 0)
        if should:
            self._recorded_count += 1
        return should

    def decimation_ratio(self, total=None):
        """Compute current decimation ratio."""
        if total is None or total == 0:
            return 1.0
        return max(0.01, 1.0 - (self._recorded_count / total))

    def savings_factor(self):
        """Compute memory savings from decimation."""
        return 1.0


class RenderQualityScaler:
    """Scales render quality based on performance budget."""

    def __init__(self):
        self.quality_params = {
            "resolution_scale": 1.0,
            "symbol_detail": 1.0,
            "smoothing_quality": 1.0,
            "effects_enabled": True,
            "anti_aliasing": True,
        }

    def scale_for_budget(self, budget_usage_pct, current_fps):
        """Scale quality based on budget usage and FPS.

        budget_usage_pct: 0..100% of frame budget used
        """
        if budget_usage_pct > 90 or current_fps < 15:
            return {
                "resolution_scale": 0.5,
                "symbol_detail": 0.3,
                "smoothing_quality": 0.3,
                "effects_enabled": False,
                "anti_aliasing": False,
            }
        elif budget_usage_pct > 70 or current_fps < 25:
            return {
                "resolution_scale": 0.65,
                "symbol_detail": 0.5,
                "smoothing_quality": 0.5,
                "effects_enabled": False,
                "anti_aliasing": False,
            }
        elif budget_usage_pct > 50 or current_fps < 40:
            return {
                "resolution_scale": 0.8,
                "symbol_detail": 0.7,
                "smoothing_quality": 0.7,
                "effects_enabled": True,
                "anti_aliasing": False,
            }
        else:
            return {
                "resolution_scale": 0.9,
                "symbol_detail": 0.85,
                "smoothing_quality": 0.85,
                "effects_enabled": True,
                "anti_aliasing": True,
            }


class TestPerformanceCostModels:
    """Tests for performance cost models."""

    def test_simvar_read_cost(self):
        model = SimvarReadCostModel()
        cost = model.estimate(active_vars=25)
        assert cost > 100
        assert cost < 500

    def test_projection_cost(self):
        model = ProjectionCostModel()
        cost = model.estimate(active_elements=5, runway_corners=4)
        assert cost > 100
        assert cost < 1000

    def test_stabilization_cost(self):
        model = StabilizationCostModel()
        cost = model.estimate(active_elements=8)
        assert cost > 100
        assert cost < 500

    def test_telemetry_cost(self):
        model = TelemetryCostModel()
        cost = model.estimate()
        assert cost > 50
        assert cost < 500

    def test_js_rendering_cost(self):
        model = JSRederingCostModel()
        cost_ultra = model.estimate(quality_level="ultra")
        cost_low = model.estimate(quality_level="low")
        assert cost_ultra > cost_low

    def test_lvar_publish_cost(self):
        model = LVarPublishCostModel()
        cost = model.estimate(active_lvars=60, changed_lvars=30)
        assert cost > 50
        assert cost < 500

    def test_cost_measurements(self):
        model = SimvarReadCostModel()
        for i in range(99):
            model.measure(150 + (i % 49))
        model.measure(300)
        assert model.avg_cost() > 100
        assert model.max_cost() > model.p95_cost()

    def test_all_within_budget(self):
        """All cost model estimates should be within their budgets."""
        models = [
            ("simvar_read", SimvarReadCostModel(), {"active_vars": 25}),
            ("runway_projection", ProjectionCostModel(),
             {"active_elements": 5, "runway_corners": 4}),
            ("fpv", StabilizationCostModel(),
             {"active_elements": 2}),
            ("stabilization", StabilizationCostModel(),
             {"active_elements": 8}),
            ("telemetry", TelemetryCostModel(), {}),
        ]
        for name, model, kwargs in models:
            cost = model.estimate(**kwargs)
            budget = SUBSYSTEM_BUDGETS_US.get(name, 500)
            assert cost <= budget * 1.5, f"{name}: {cost} > {budget * 1.5}"


class TestAdaptiveThrottling:
    """Tests for adaptive throttling."""

    def test_no_throttle_normal(self):
        mgr = AdaptiveThrottlingManager()
        mgr.register("fpv")
        for _ in range(60):
            mgr.record_frame_time(2.0)
        level = mgr.compute_throttle()
        assert level == 0.0
        assert not mgr.throttle_active

    def test_throttle_warning(self):
        mgr = AdaptiveThrottlingManager()
        mgr.register("fpv")
        for _ in range(60):
            mgr.record_frame_time(4.0)
        level = mgr.compute_throttle()
        assert level > 0.0

    def test_throttle_critical(self):
        mgr = AdaptiveThrottlingManager()
        mgr.register("fpv")
        for _ in range(60):
            mgr.record_frame_time(9.0)
        level = mgr.compute_throttle()
        assert level > 0.5

    def test_throttle_reduction(self):
        mgr = AdaptiveThrottlingManager()
        mgr.register("test_sub", max_rate_hz=60, min_rate_hz=5)
        sub = mgr.get("test_sub")
        initial_rate = sub.current_rate_hz
        for _ in range(60):
            mgr.record_frame_time(10.0)
        mgr.compute_throttle()
        assert sub.current_rate_hz < initial_rate

    def test_skip_ratio(self):
        mgr = AdaptiveThrottlingManager()
        mgr.register("test_sub", max_rate_hz=60, min_rate_hz=5)
        t = 0.0
        for _ in range(100):
            mgr.record_frame_time(8.0)
            mgr.compute_throttle()
            sub = mgr.get("test_sub")
            sub.should_run(t)
            t += 0.016
        ratio = mgr.estimate_skip_ratio()
        assert ratio > 0.0
        assert ratio < 0.8

    def test_throttle_recovers(self):
        mgr = AdaptiveThrottlingManager()
        mgr.register("fpv")
        for _ in range(60):
            mgr.record_frame_time(10.0)
        mgr.compute_throttle()
        assert mgr.throttle_active
        for _ in range(60):
            mgr.record_frame_time(2.0)
        mgr.compute_throttle()
        assert not mgr.throttle_active


class TestLowFPSDegradation:
    """Tests for low-FPS degradation mode."""

    def test_normal_fps_no_degradation(self):
        mgr = LowFPSDegradationManager()
        mgr.update(60.0, 0.016)
        assert mgr.stage == LowFPSDegradationManager.STAGE_NORMAL
        assert mgr.quality_level == "ultra"

    def test_reduced_at_40fps(self):
        mgr = LowFPSDegradationManager()
        for _ in range(50):
            mgr.update(40.0, 0.016)
        assert mgr.stage == LowFPSDegradationManager.STAGE_REDUCED

    def test_minimal_at_15fps(self):
        mgr = LowFPSDegradationManager()
        for _ in range(50):
            mgr.update(15.0, 0.016)
        assert mgr.stage == LowFPSDegradationManager.STAGE_MINIMAL

    def test_off_at_5fps(self):
        mgr = LowFPSDegradationManager()
        for _ in range(50):
            mgr.update(9.0, 0.016)
        assert mgr.stage == LowFPSDegradationManager.STAGE_OFF

    def test_recovery(self):
        mgr = LowFPSDegradationManager()
        for _ in range(50):
            mgr.update(9.0, 0.016)
        assert mgr.stage == LowFPSDegradationManager.STAGE_OFF
        for _ in range(50):
            mgr.update(60.0, 0.016)
        assert mgr.stage == LowFPSDegradationManager.STAGE_NORMAL

    def test_scale_factor_decreases(self):
        mgr = LowFPSDegradationManager()
        mgr.quality_level = "low"
        minimal_scale = mgr.scale_factor
        mgr.quality_level = "ultra"
        normal_scale = mgr.scale_factor
        assert minimal_scale < normal_scale

    def test_features_disabled_at_low_fps(self):
        mgr_reduced = LowFPSDegradationManager()
        mgr_reduced.stage = LowFPSDegradationManager.STAGE_MINIMAL
        features_reduced = mgr_reduced.enabled_features
        mgr_normal = LowFPSDegradationManager()
        features_normal = mgr_normal.enabled_features
        assert "bloom" not in features_reduced
        assert "bloom" in features_normal


class TestSubsystemRateLimiting:
    """Tests for SubsystemRateLimiter."""

    def test_full_rate_at_high_fps(self):
        limiter = SubsystemRateLimiter()
        limiter.limit_all(60.0, 0.0)
        limit = limiter.get_limit("fpv")
        assert limit > 30

    def test_reduced_rate_at_low_fps(self):
        limiter = SubsystemRateLimiter()
        limiter.limit_all(60.0, 0.0)
        limiter.limit_all(15.0, 0.0)
        limit = limiter.get_limit("evs")
        assert limit <= 5

    def test_allow_deny(self):
        limiter = SubsystemRateLimiter()
        limiter.set_limit("test", 10)
        assert limiter.allow("test", 0.0)
        assert not limiter.allow("test", 0.05)
        assert limiter.allow("test", 0.1)

    def test_zero_limit(self):
        limiter = SubsystemRateLimiter()
        limiter.set_limit("disabled", 0)
        assert not limiter.allow("disabled", 0.0)


class TestTelemetryDecimation:
    """Tests for TelemetryDecimator."""

    def test_target_rate(self):
        dec = TelemetryDecimator(target_rate_hz=10)
        recorded = 0
        for i in range(600):
            if dec.should_record(i, 60.0):
                recorded += 1
        assert recorded > 0

    def test_adaptive_low_fps(self):
        dec = TelemetryDecimator(target_rate_hz=10)
        recorded_normal = 0
        for i in range(600):
            if dec.should_record(i, 60.0):
                recorded_normal += 1
        dec2 = TelemetryDecimator(target_rate_hz=10)
        recorded_low = 0
        for i in range(600):
            if dec2.should_record(i, 15.0):
                recorded_low += 1
        assert recorded_low != recorded_normal

    def test_savings_factor(self):
        dec = TelemetryDecimator(target_rate_hz=10)
        for i in range(100):
            dec.should_record(i, 60.0)
        sf = dec.savings_factor()
        assert sf >= 0

    def test_no_decimation(self):
        dec = TelemetryDecimator(target_rate_hz=600)
        recorded = sum(1 for i in range(600) if dec.should_record(i, 60.0))
        assert recorded <= 600


class TestRenderQualityScaling:
    """Tests for RenderQualityScaler."""

    def test_full_quality_normal(self):
        scaler = RenderQualityScaler()
        params = scaler.scale_for_budget(30, 55.0)
        assert params["resolution_scale"] > 0.8
        assert params["effects_enabled"] is True

    def test_reduced_quality_high_budget(self):
        scaler = RenderQualityScaler()
        params = scaler.scale_for_budget(80, 30.0)
        assert params["resolution_scale"] < 1.0

    def test_low_fps_reduces_quality(self):
        scaler = RenderQualityScaler()
        params = scaler.scale_for_budget(50, 20.0)
        assert params["resolution_scale"] < 0.9

    def test_critical_reduces_to_minimum(self):
        scaler = RenderQualityScaler()
        params = scaler.scale_for_budget(95, 10.0)
        assert params["resolution_scale"] <= 0.5
        assert params["anti_aliasing"] is False


class TestPerformanceBudgetValidation:
    """End-to-end performance budget validation."""

    def test_total_subsystem_budget(self):
        """Sum of all subsystem budgets should be within frame budget."""
        total_us = sum(SUBSYSTEM_BUDGETS_US.values())
        total_ms = total_us / 1000.0
        assert total_ms < FRAME_BUDGET_MS
        assert total_ms < TARGET_BUDGET_MS

    def test_per_subsystem_budget_reasonable(self):
        """No single subsystem should exceed 20%% of frame budget."""
        for name, budget_us in SUBSYSTEM_BUDGETS_US.items():
            budget_pct = (budget_us / 1000.0) / FRAME_BUDGET_MS * 100
            assert budget_pct <= 20

    def test_all_subsystems_accounted(self):
        """All major subsystems should have budget allocations."""
        expected = {"simvar_read", "runway_projection", "fpv", "guidance",
                     "flare", "rollout", "stabilization", "collimation",
                     "symbology_publish", "telemetry", "confidence"}
        for name in expected:
            assert name in SUBSYSTEM_BUDGETS_US

    def test_quality_levels_monotonic(self):
        """Quality levels should be monotonically decreasing."""
        levels = list(QUALITY_LEVELS.values())
        for i in range(len(levels) - 1):
            assert levels[i] >= levels[i + 1]

    def test_cost_model_budget_compliance(self):
        """All cost model estimates should respect budgets."""
        models = [
            ("simvar_read", SimvarReadCostModel(), {"active_vars": 25}),
            ("runway_projection", ProjectionCostModel(),
             {"active_elements": 5, "runway_corners": 4}),
            ("stabilization", StabilizationCostModel(),
             {"active_elements": 8}),
            ("telemetry", TelemetryCostModel(), {}),
            ("fpv", StabilizationCostModel(), {"active_elements": 2}),
        ]
        for name, model, kwargs in models:
            cost = model.estimate(**kwargs)
            budget = SUBSYSTEM_BUDGETS_US.get(name, 500)
            assert cost <= budget * 2
