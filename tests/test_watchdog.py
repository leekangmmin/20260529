#!/usr/bin/env python3
"""
Conformal HUD – Real-Time Failure Detection & Watchdog Suite (v2.5.0)

PHASE 3 — REAL-TIME FAILURE DETECTION

Expands runtime watchdog systems:
  1. Stalled subsystem recovery detection
  2. Invalid projection detection
  3. NaN/INF propagation guards
  4. Unstable optics detection
  5. Invalid telemetry rejection
  6. Excessive jitter detection
  7. FPS collapse detection
  8. Emergency degraded mode

Goal:
  Subsystem failures should never silently corrupt the HUD.

Run:  python -m pytest tests/test_watchdog.py -v
"""

import math


# =========================================================================
#  1.  Watchdog state types
# =========================================================================

class WatchdogState:
    """Tracks health of a single HUD subsystem."""

    SUBSYSTEM_NAMES = [
        'FPV', 'GUIDANCE', 'RUNWAY', 'FLARE',
        'EVS', 'COLLIMATION', 'STABILIZATION', 'ADVANCED',
    ]

    def __init__(self):
        # Heartbeat tracking
        self.heartbeat_count = 0
        self.last_heartbeat = 0
        self.stalled_ticks = 0
        self.total_failures = 0

        # Subsystem health
        self.healthy = True
        self.degraded = False
        self.recovery_count = 0

        # Failure tracking
        self.consecutive_nan = 0
        self.consecutive_inf = 0
        self.consecutive_invalid = 0
        self.consecutive_jitter = 0
        self.fps_collapse_count = 0

        # Timing
        self.last_frame_ms = 0.0
        self.fps = 60.0
        self.fps_min = 60.0
        self.fps_max = 60.0

    def reset(self):
        self.__init__()


class WatchdogSystem:
    """Central watchdog monitoring all subsystems."""

    def __init__(self, tick_timeout=5, stall_threshold=10):
        self.subsystems = {}
        for name in WatchdogState.SUBSYSTEM_NAMES:
            self.subsystems[name] = WatchdogState()

        self.tick_timeout = tick_timeout
        self.stall_threshold = stall_threshold
        self.system_degraded = False
        self.emergency_mode = False
        self._failure_log = []

    def get(self, name):
        return self.subsystems.get(name)

    def heartbeat(self, name):
        """Record a heartbeat from a subsystem."""
        sub = self.subsystems.get(name)
        if sub is None:
            return
        if sub.last_heartbeat > 0:
            # Not stalled between heartbeats
            if sub.stalled_ticks > 0:
                sub.recovery_count += 1
            sub.stalled_ticks = 0
        sub.heartbeat_count += 1
        sub.last_heartbeat = sub.heartbeat_count

    def tick(self, name):
        """Advance one tick for a subsystem (check for stalls)."""
        sub = self.subsystems.get(name)
        if sub is None:
            return

        if not sub.healthy:
            # Already failed — check if this is a continued stall
            sub.stalled_ticks += 1
            sub.total_failures += 1

            # Attempt auto-recovery after excessive stalls
            if sub.stalled_ticks >= self.stall_threshold * 3:
                self._attempt_recovery(name)
            return False

        # Check if heartbeat has stalled
        sub.stalled_ticks += 1
        if sub.stalled_ticks >= self.stall_threshold:
            self._record_failure(name, 'stall')
            return False

        return True

    def _record_failure(self, name, failure_type):
        sub = self.subsystems.get(name)
        if sub is None:
            return
        sub.healthy = False
        sub.degraded = True
        sub.total_failures += 1
        self._failure_log.append((name, failure_type, sub.total_failures))

        # Check if system-wide degraded mode needed
        self._evaluate_system_health()

    def _attempt_recovery(self, name):
        sub = self.subsystems.get(name)
        if sub is None:
            return
        sub.reset()
        sub.recovery_count += 1
        sub.healthy = True
        self._failure_log.append((name, 'recovery', sub.recovery_count))
        self._evaluate_system_health()

    def _evaluate_system_health(self):
        """Evaluate overall system health and decide on degraded/emergency mode."""
        failed_count = sum(
            1 for s in self.subsystems.values() if not s.healthy)
        total = len(self.subsystems)

        # If more than half of subsystems failed → emergency mode
        if failed_count > total / 2:
            self.emergency_mode = True
            self.system_degraded = True
        elif failed_count > 0:
            self.system_degraded = True
            self.emergency_mode = False
        else:
            self.system_degraded = False
            self.emergency_mode = False

    def report(self):
        """Generate watchdog report."""
        lines = ["=== WATCHDOG SYSTEM REPORT ==="]
        lines.append(f"  System degraded: {self.system_degraded}")
        lines.append(f"  Emergency mode: {self.emergency_mode}")
        lines.append(f"  Total failures: {sum(s.total_failures
                     for s in self.subsystems.values())}")
        for name, sub in sorted(self.subsystems.items()):
            status = "OK" if sub.healthy else "FAIL"
            lines.append(f"  [{status}] {name}: "
                         f"heartbeats={sub.heartbeat_count} "
                         f"stalls={sub.stalled_ticks} "
                         f"failures={sub.total_failures} "
                         f"recoveries={sub.recovery_count}")
        lines.append("=" * 40)
        return "\n".join(lines)


# =========================================================================
#  2.  NaN/INF Propagation Guards
# =========================================================================

class NaNGuard:
    """Detects and prevents NaN/INF propagation through the system."""

    def __init__(self):
        self.nan_count = 0
        self.inf_count = 0
        self.corrected_count = 0
        self.last_valid_value = 0.0

    def check_value(self, value, context="unknown",
                    fallback=None, auto_correct=True):
        """Check a value for NaN/INF. Returns clean value."""
        if isinstance(value, bool):
            return value

        if isinstance(value, (int, float)):
            if math.isnan(value):
                self.nan_count += 1
                if auto_correct:
                    self.corrected_count += 1
                    return fallback if fallback is not None else self.last_valid_value
                return value
            if math.isinf(value):
                self.inf_count += 1
                if auto_correct:
                    self.corrected_count += 1
                    return fallback if fallback is not None else self.last_valid_value
                return value
            self.last_valid_value = value

        return value

    def check_frame(self, frame, context="frame"):
        """Check all numeric fields in a TelemetryFrame for NaN/INF.

        Returns (clean_frame, issues_found).
        """
        if frame is None:
            return None, ["null frame"]

        issues = []
        fields_to_check = [
            'ac_lat', 'ac_lon', 'ac_alt_m', 'ac_hdg_true',
            'ac_pitch_deg', 'ac_bank_deg',
            'ac_groundspeed_ms', 'ac_true_airspeed_ms',
            'ac_vertical_speed_ms', 'ac_track_deg_true',
            'ac_radio_alt_m', 'ac_accel_ms2',
            'fpv_x', 'fpv_y', 'fpv_pitch', 'fpv_drift',
            'flare_cue_x', 'flare_cue_y', 'flare_cue_size',
            'flare_cue_alpha', 'flare_rise', 'flare_error',
            'flare_vs_cmd',
            'rollout_steering', 'rollout_centerline_error',
            'rollout_confidence', 'rollout_nosewheel',
            'cat3_confidence', 'system_integrity',
            'turbulence_intensity', 'jitter_ms',
            'optical_brightness', 'optical_bloom',
            'optical_phosphor_ms',
            'ils_integrity', 'guidance_integrity',
            'visibility_m',
        ]

        for field in fields_to_check:
            val = getattr(frame, field, None)
            if val is not None and isinstance(val, (int, float)):
                cleaned = self.check_value(val, f"{context}/{field}")
                if cleaned != val:
                    setattr(frame, field, cleaned)
                    if math.isnan(val):
                        issues.append(f"{field}=NaN")
                    else:
                        issues.append(f"{field}=INF")

        return frame, issues

    def report(self):
        return {
            'nan_count': self.nan_count,
            'inf_count': self.inf_count,
            'corrected_count': self.corrected_count,
            'last_valid_value': self.last_valid_value,
        }


# =========================================================================
#  3.  Invalid Projection Detection
# =========================================================================

class ProjectionValidator:
    """Validates projection outputs for physical plausibility."""

    # Screen bounds with margin
    SCREEN_X_MIN = -500
    SCREEN_X_MAX = 2000
    SCREEN_Y_MIN = -500
    SCREEN_Y_MAX = 2000

    # Physical limits
    LAT_MIN = -90.0
    LAT_MAX = 90.0
    LON_MIN = -180.0
    LON_MAX = 180.0
    ALT_MIN = -1000.0
    ALT_MAX = 60000.0
    SPEED_MIN = 0.0
    SPEED_MAX = 500.0  # m/s
    VS_MAX = 200.0     # m/s
    ACCEL_MAX = 50.0   # m/s²
    HDG_MIN = 0.0
    HDG_MAX = 360.0
    PITCH_MIN = -90.0
    PITCH_MAX = 90.0
    BANK_MIN = -180.0
    BANK_MAX = 180.0

    def __init__(self):
        self.invalid_count = 0
        self.total_checked = 0

    def is_valid_position(self, lat, lon, alt_m):
        """Check if aircraft position is physically plausible."""
        self.total_checked += 1
        if not (self.LAT_MIN <= lat <= self.LAT_MAX):
            return False
        if not (self.LON_MIN <= lon <= self.LON_MAX):
            return False
        if not (self.ALT_MIN <= alt_m <= self.ALT_MAX):
            return False
        return True

    def is_valid_attitude(self, pitch_deg, bank_deg, hdg_true):
        """Check if attitude values are physically plausible."""
        self.total_checked += 1
        if not (self.PITCH_MIN <= pitch_deg <= self.PITCH_MAX):
            return False
        if not (self.BANK_MIN <= bank_deg <= self.BANK_MAX):
            return False
        if not (self.HDG_MIN <= hdg_true <= self.HDG_MAX):
            return False
        return True

    def is_valid_speed(self, groundspeed_ms, vert_speed_ms, accel_ms2):
        """Check if speed values are physically plausible."""
        self.total_checked += 1
        if not (self.SPEED_MIN <= groundspeed_ms <= self.SPEED_MAX):
            return False
        if abs(vert_speed_ms) > self.VS_MAX:
            return False
        if abs(accel_ms2) > self.ACCEL_MAX:
            return False
        return True

    def is_valid_screen_pos(self, x, y):
        """Check if a screen position is within plausible bounds."""
        self.total_checked += 1
        return (self.SCREEN_X_MIN <= x <= self.SCREEN_X_MAX and
                self.SCREEN_Y_MIN <= y <= self.SCREEN_Y_MAX)

    def is_valid_runway_corners(self, corners, visible_count):
        """Check if runway corner positions are plausible."""
        self.total_checked += 1
        if visible_count < 0 or visible_count > 8:
            return False
        if corners is None:
            return visible_count == 0
        for i in range(min(visible_count, len(corners))):
            cx, cy = corners[i] if isinstance(corners[i], tuple) else (0, 0)
            if not self.is_valid_screen_pos(cx, cy):
                return False
        return True

    def validate_frame(self, frame):
        """Comprehensive validation of all projection outputs.

        Returns (valid: bool, issues: list).
        """
        issues = []

        # Position
        if not self.is_valid_position(frame.ac_lat, frame.ac_lon,
                                       frame.ac_alt_m):
            issues.append("invalid_position")

        # Attitude
        if not self.is_valid_attitude(frame.ac_pitch_deg, frame.ac_bank_deg,
                                       frame.ac_hdg_true):
            issues.append("invalid_attitude")

        # Speed
        if not self.is_valid_speed(frame.ac_groundspeed_ms,
                                    frame.ac_vertical_speed_ms,
                                    frame.ac_accel_ms2):
            issues.append("invalid_speed")

        # Screen positions
        if frame.fpv_on_screen and frame.fpv_valid:
            if not self.is_valid_screen_pos(frame.fpv_x, frame.fpv_y):
                issues.append("fpv_off_screen")

        # Runway corners
        if frame.runway_valid:
            if not self.is_valid_runway_corners(frame.runway_corners,
                                                 frame.runway_visible_count):
                issues.append("invalid_runway_corners")

        if issues:
            self.invalid_count += 1

        return len(issues) == 0, issues

    def report(self):
        invalid_pct = (self.invalid_count / max(self.total_checked, 1)) * 100
        return {
            'invalid_count': self.invalid_count,
            'total_checked': self.total_checked,
            'invalid_pct': invalid_pct,
        }


# =========================================================================
#  4.  Unstable Optics Detection
# =========================================================================

class OpticsStabilityDetector:
    """Detects unstable or rapidly oscillating optical parameters."""

    def __init__(self):
        self.oscillation_count = 0
        self._brightness_history = []
        self._bloom_history = []
        self._phosphor_history = []
        self._max_history = 30

    def check(self, brightness, bloom, phosphor_ms):
        """Check optical parameters for instability.

        Returns (stable: bool, instability_score: float, details: str).
        """
        self._brightness_history.append(brightness)
        self._bloom_history.append(bloom)
        self._phosphor_history.append(phosphor_ms)

        if len(self._brightness_history) > self._max_history:
            self._brightness_history.pop(0)
            self._bloom_history.pop(0)
            self._phosphor_history.pop(0)

        if len(self._brightness_history) < 5:
            return True, 0.0, "warming_up"

        # Check for oscillation
        b_osc = self._detect_oscillation(self._brightness_history)
        bl_osc = self._detect_oscillation(self._bloom_history)
        p_osc = self._detect_oscillation(self._phosphor_history, 5.0)

        # Check for abrupt jumps
        b_jump = self._detect_abrupt_jump(self._brightness_history, 0.3)
        bl_jump = self._detect_abrupt_jump(self._bloom_history, 0.3)
        p_jump = self._detect_abrupt_jump(self._phosphor_history, 30.0)

        instability_score = max(b_osc, bl_osc, p_osc, b_jump, bl_jump, p_jump)
        instability_score = min(1.0, instability_score)

        if instability_score > 0.5:
            self.oscillation_count += 1

        details_parts = []
        if b_osc > 0.3:
            details_parts.append(f"brightness_oscillation={b_osc:.2f}")
        if bl_osc > 0.3:
            details_parts.append(f"bloom_oscillation={bl_osc:.2f}")
        if p_osc > 0.3:
            details_parts.append(f"phosphor_oscillation={p_osc:.2f}")
        if b_jump > 0.3:
            details_parts.append(f"brightness_jump={b_jump:.2f}")
        if bl_jump > 0.3:
            details_parts.append(f"bloom_jump={bl_jump:.2f}")
        if p_jump > 0.3:
            details_parts.append(f"phosphor_jump={p_jump:.2f}")

        stable = instability_score < 0.5
        return stable, instability_score, ", ".join(details_parts) or "stable"

    @staticmethod
    def _detect_oscillation(values, threshold=0.1):
        """Detect oscillation by counting sign changes in the derivative."""
        if len(values) < 5:
            return 0.0

        signs = []
        for i in range(1, len(values)):
            diff = values[i] - values[i - 1]
            if abs(diff) > threshold * 0.1:
                signs.append(1 if diff > 0 else -1)

        if len(signs) < 3:
            return 0.0

        # Count sign changes
        changes = sum(1 for i in range(1, len(signs)) if signs[i] != signs[i - 1])
        change_rate = changes / max(len(signs) - 1, 1)

        # Map to instability score
        return min(1.0, change_rate * 2.0)

    @staticmethod
    def _detect_abrupt_jump(values, jump_threshold):
        """Detect large single-frame jumps."""
        if len(values) < 3:
            return 0.0

        max_jump = 0.0
        for i in range(1, len(values)):
            jump = abs(values[i] - values[i - 1])
            if jump > jump_threshold:
                max_jump = max(max_jump, jump / jump_threshold)

        return min(1.0, max_jump * 0.5)


# =========================================================================
#  5.  Excessive Jitter Detection
# =========================================================================

class JitterDetector:
    """Detects excessive symbol jitter that degrades usability."""

    def __init__(self, threshold_px=10.0, window_size=30):
        self.threshold_px = threshold_px
        self.window_size = window_size
        self._fpv_jitter_history = []
        self._runway_jitter_history = []
        self._flare_jitter_history = []
        self.excessive_jitter_events = 0

    def check_fpv_jitter(self, prev_x, prev_y, curr_x, curr_y):
        """Check FPV jitter magnitude."""
        if prev_x is None or prev_y is None:
            return 0.0

        dx = abs(curr_x - prev_x)
        dy = abs(curr_y - prev_y)
        movement = math.sqrt(dx * dx + dy * dy)

        self._fpv_jitter_history.append(movement)
        if len(self._fpv_jitter_history) > self.window_size:
            self._fpv_jitter_history.pop(0)

        return movement

    def check_runway_jitter(self, prev_corners, curr_corners):
        """Check runway corner jitter."""
        if not prev_corners or not curr_corners:
            return 0.0

        max_movement = 0.0
        for (px, py), (cx, cy) in zip(prev_corners, curr_corners):
            dx = abs(cx - px)
            dy = abs(cy - py)
            movement = math.sqrt(dx * dx + dy * dy)
            max_movement = max(max_movement, movement)

        self._runway_jitter_history.append(max_movement)
        if len(self._runway_jitter_history) > self.window_size:
            self._runway_jitter_history.pop(0)

        return max_movement

    def check_flare_jitter(self, prev_x, prev_y, curr_x, curr_y):
        """Check flare cue jitter."""
        if prev_x is None or prev_y is None:
            return 0.0

        dx = abs(curr_x - prev_x)
        dy = abs(curr_y - prev_y)
        movement = math.sqrt(dx * dx + dy * dy)

        self._flare_jitter_history.append(movement)
        if len(self._flare_jitter_history) > self.window_size:
            self._flare_jitter_history.pop(0)

        return movement

    def is_jitter_excessive(self, history):
        """Check if jitter in a history window exceeds threshold."""
        if len(history) < 5:
            return False
        avg = sum(history[-5:]) / 5
        return avg > self.threshold_px

    def any_excessive_jitter(self):
        """Check if any element has excessive jitter."""
        fpv_excessive = self.is_jitter_excessive(self._fpv_jitter_history)
        rwy_excessive = self.is_jitter_excessive(self._runway_jitter_history)
        flare_excessive = self.is_jitter_excessive(self._flare_jitter_history)

        if fpv_excessive or rwy_excessive or flare_excessive:
            self.excessive_jitter_events += 1

        return fpv_excessive or rwy_excessive or flare_excessive

    def jitter_level(self):
        """Overall jitter level across all elements (0..1)."""
        all_jitter = (self._fpv_jitter_history +
                      self._runway_jitter_history +
                      self._flare_jitter_history)
        if not all_jitter:
            return 0.0
        avg = sum(all_jitter) / len(all_jitter)
        return min(1.0, avg / self.threshold_px)


# =========================================================================
#  6.  FPS Collapse Detection
# =========================================================================

class FPSCollapseDetector:
    """Detects severe FPS drops that could affect HUD usability."""

    TARGET_FPS = 60.0
    COLLAPSE_THRESHOLD = 20.0  # FPS below this = collapsed
    WARNING_THRESHOLD = 30.0   # FPS below this = warning

    def __init__(self):
        self._fps_history = []
        self._max_history = 60  # 1 second at 60fps
        self.collapse_events = 0
        self.warning_events = 0
        self.current_state = "normal"
        self.total_frames_dropped = 0

    def record_fps(self, fps):
        """Record current FPS and detect collapse."""
        self._fps_history.append(fps)
        if len(self._fps_history) > self._max_history:
            self._fps_history.pop(0)

        if fps < self.COLLAPSE_THRESHOLD:
            self.collapse_events += 1
            self.current_state = "collapsed"
            self.total_frames_dropped += int(self.TARGET_FPS / max(fps, 1))
            return "collapsed"
        elif fps < self.WARNING_THRESHOLD:
            self.warning_events += 1
            self.current_state = "warning"
            return "warning"
        else:
            self.current_state = "normal"
            return "normal"

    def is_collapsed(self):
        """Check if currently in FPS collapse."""
        return self.current_state == "collapsed"

    def is_degraded(self):
        """Check if FPS is in warning or collapse territory."""
        return self.current_state != "normal"

    def avg_fps(self, window=None):
        """Average FPS over recent window."""
        if not self._fps_history:
            return self.TARGET_FPS
        if window:
            return sum(self._fps_history[-window:]) / min(window,
                                                          len(self._fps_history))
        return sum(self._fps_history) / len(self._fps_history)

    def recovery_time(self):
        """Estimate time (seconds) to recover to target FPS."""
        if self.current_state != "collapsed":
            return 0.0
        # Rough estimate: 1 frame per frame at current FPS
        return 60.0 / max(self.avg_fps(5), 1.0)


# =========================================================================
#  7.  Emergency Degraded Mode
# =========================================================================

class EmergencyDegradedMode:
    """Manages the system's emergency degraded mode behavior."""

    # Degradation levels
    LEVEL_NORMAL = 0
    LEVEL_CAUTION = 1   # Some subsystems degraded
    LEVEL_WARNING = 2   # Multiple subsystems degraded
    LEVEL_EMERGENCY = 3 # Critical failure

    def __init__(self):
        self.level = self.LEVEL_NORMAL
        self.triggered_by = []
        self.degradation_start_time = 0.0
        self.total_time_in_emergency = 0.0

        # What to degrade
        self.disable_bloom = False
        self.disable_evs = False
        self.disable_advanced_symbology = False
        self.reduce_fpv_alpha = False
        self.simplify_runway = False
        self.hide_guidance = False
        self.force_solid_rendering = False

    def evaluate(self, watchdog, fps_detector, jitter_detector):
        """Evaluate system state and set degradation level.

        Returns current level.
        """
        self.triggered_by = []

        # Check for emergency conditions
        if watchdog.emergency_mode:
            self.level = self.LEVEL_EMERGENCY
            self.triggered_by.append("watchdog_emergency")

        if fps_detector.is_collapsed():
            self.level = max(self.level, self.LEVEL_EMERGENCY)
            self.triggered_by.append("fps_collapse")

        # Check for warning conditions
        if fps_detector.is_degraded():
            self.level = max(self.level, self.LEVEL_WARNING)
            self.triggered_by.append("fps_degraded")

        if jitter_detector.any_excessive_jitter():
            self.level = max(self.level, self.LEVEL_WARNING)
            self.triggered_by.append("excessive_jitter")

        if watchdog.system_degraded:
            self.level = max(self.level, self.LEVEL_CAUTION)
            self.triggered_by.append("subsystem_degraded")

        # Apply degradation actions based on level
        self._apply_degradation()

        return self.level

    def _apply_degradation(self):
        """Apply degradation actions for current level."""
        if self.level >= self.LEVEL_EMERGENCY:
            self.disable_bloom = True
            self.disable_evs = True
            self.disable_advanced_symbology = True
            self.reduce_fpv_alpha = True
            self.simplify_runway = True
            self.hide_guidance = True
            self.force_solid_rendering = True
        elif self.level >= self.LEVEL_WARNING:
            self.disable_bloom = True
            self.disable_evs = True
            self.disable_advanced_symbology = True
            self.reduce_fpv_alpha = True
            self.simplify_runway = False
            self.hide_guidance = False
            self.force_solid_rendering = False
        elif self.level >= self.LEVEL_CAUTION:
            self.disable_bloom = True
            self.disable_evs = False
            self.disable_advanced_symbology = False
            self.reduce_fpv_alpha = False
            self.simplify_runway = False
            self.hide_guidance = False
            self.force_solid_rendering = False
        else:
            self.disable_bloom = False
            self.disable_evs = False
            self.disable_advanced_symbology = False
            self.reduce_fpv_alpha = False
            self.simplify_runway = False
            self.hide_guidance = False
            self.force_solid_rendering = False

    def recovery_check(self):
        """Check if system can recover from degraded mode."""
        if self.level == self.LEVEL_EMERGENCY:
            # Must have been in emergency for at least some time
            return False
        if self.level >= self.LEVEL_WARNING:
            # Can attempt partial recovery
            return True
        return True


# =========================================================================
#  8.  Invalid Telemetry Rejection
# =========================================================================

class TelemetryRejectionFilter:
    """Rejects invalid or corrupted telemetry frames."""

    def __init__(self):
        self.rejected_count = 0
        self.accepted_count = 0
        self.rejection_reasons = {}

    def accept_frame(self, frame):
        """Check if a frame should be accepted.

        Returns (accepted: bool, reason: str).
        """
        self.accepted_count += 1

        # Null check
        if frame is None:
            self._reject("null_frame")
            return False, "null_frame"

        # NaN/Inf checks on critical fields
        critical_fields = [
            ('ac_lat', -90, 90), ('ac_lon', -180, 180),
            ('ac_alt_m', -1000, 60000),
            ('ac_hdg_true', 0, 360),
            ('ac_pitch_deg', -90, 90),
            ('ac_bank_deg', -180, 180),
        ]

        for field_name, min_val, max_val in critical_fields:
            val = getattr(frame, field_name, None)
            if val is None:
                self._reject(f"missing_{field_name}")
                return False, f"missing_{field_name}"
            if isinstance(val, float):
                if math.isnan(val):
                    self._reject(f"{field_name}_nan")
                    return False, f"{field_name}_nan"
                if math.isinf(val):
                    self._reject(f"{field_name}_inf")
                    return False, f"{field_name}_inf"
                if val < min_val or val > max_val:
                    self._reject(f"{field_name}_out_of_range")
                    return False, f"{field_name}_out_of_range"

        # Frame index consistency
        if hasattr(frame, 'frame_index') and frame.frame_index < 0:
            self._reject("negative_frame_index")
            return False, "negative_frame_index"

        return True, "accepted"

    def _reject(self, reason):
        self.rejected_count += 1
        self.rejection_reasons[reason] = self.rejection_reasons.get(reason, 0) + 1

    def acceptance_rate(self):
        total = self.accepted_count + self.rejected_count
        if total == 0:
            return 1.0
        return self.accepted_count / max(total, 1)


# =========================================================================
#  9.  TESTS — Watchdog System
# =========================================================================

class TestWatchdogSystem:
    """Tests for WatchdogSystem."""

    def test_initial_state(self):
        wd = WatchdogSystem()
        assert wd.system_degraded is False
        assert wd.emergency_mode is False
        for name in WatchdogState.SUBSYSTEM_NAMES:
            sub = wd.get(name)
            assert sub is not None
            assert sub.healthy is True

    def test_heartbeat_keeps_alive(self):
        wd = WatchdogSystem(stall_threshold=5)
        for _ in range(10):
            wd.heartbeat('FPV')
            result = wd.tick('FPV')
            assert result is True

    def test_stall_detection(self):
        wd = WatchdogSystem(stall_threshold=5)
        wd.heartbeat('FPV')
        for _ in range(4):
            wd.tick('FPV')
        sub = wd.get('FPV')
        assert sub.healthy is True
        # One more tick without heartbeat = stall
        result = wd.tick('FPV')
        assert result is False  # stalled
        assert sub.healthy is False

    def test_auto_recovery(self):
        wd = WatchdogSystem(stall_threshold=3)
        wd.heartbeat('GUIDANCE')
        # Stall it
        for _ in range(10):
            wd.tick('GUIDANCE')
        sub = wd.get('GUIDANCE')
        # Should have triggered auto-recovery after 3*3=9 ticks
        assert sub.recovery_count > 0 or sub.healthy is True

    def test_emergency_mode(self):
        wd = WatchdogSystem(stall_threshold=2)
        # Stall more than half of subsystems (need 2 ticks with stall_threshold=2)
        for name in ['FPV', 'GUIDANCE', 'RUNWAY', 'FLARE', 'EVS']:
            wd.tick(name)  # first tick
            wd.tick(name)  # second tick triggers stall
        assert wd.emergency_mode is True

    def test_no_false_emergency(self):
        wd = WatchdogSystem(stall_threshold=5)
        for name in ['FPV', 'GUIDANCE']:
            wd.tick(name)
        assert wd.emergency_mode is False

    def test_report_format(self):
        wd = WatchdogSystem()
        report = wd.report()
        assert "WATCHDOG" in report
        assert "OK" in report

    def test_recovery_logging(self):
        wd = WatchdogSystem(stall_threshold=2)
        wd.heartbeat('FLARE')
        wd.tick('FLARE')
        wd.tick('FLARE')
        # Should be stalled
        wd._attempt_recovery('FLARE')
        sub = wd.get('FLARE')
        assert sub.recovery_count > 0
        assert sub.healthy is True


# =========================================================================
#  10.  TESTS — NaN/INF Guards
# =========================================================================

class TestNaNGuard:
    """Tests for NaNGuard."""

    def test_nan_detection(self):
        guard = NaNGuard()
        result = guard.check_value(float('nan'), "test")
        assert result == 0.0  # Falls back to last_valid (0)

    def test_inf_detection(self):
        guard = NaNGuard()
        result = guard.check_value(float('inf'), "test")
        assert result == 0.0

    def test_valid_value_passes(self):
        guard = NaNGuard()
        result = guard.check_value(42.0, "test")
        assert result == 42.0

    def test_last_valid_used_for_nan(self):
        guard = NaNGuard()
        guard.check_value(100.0, "test")
        result = guard.check_value(float('nan'), "test")
        assert result == 100.0

    def test_bool_passthrough(self):
        guard = NaNGuard()
        assert guard.check_value(True, "test") is True
        assert guard.check_value(False, "test") is False

    def test_negative_inf_detection(self):
        guard = NaNGuard()
        result = guard.check_value(float('-inf'), "test")
        assert result == 0.0

    def test_stats_counting(self):
        guard = NaNGuard()
        guard.check_value(float('nan'), "test")
        guard.check_value(float('inf'), "test")
        guard.check_value(float('nan'), "test")
        report = guard.report()
        assert report['nan_count'] == 2
        assert report['inf_count'] == 1
        assert report['corrected_count'] == 3


# =========================================================================
#  11.  TESTS — Projection Validator
# =========================================================================

class TestProjectionValidator:
    """Tests for ProjectionValidator."""

    def test_valid_position(self):
        pv = ProjectionValidator()
        assert pv.is_valid_position(51.4775, -0.4614, 300.0) is True

    def test_invalid_latitude(self):
        pv = ProjectionValidator()
        assert pv.is_valid_position(100.0, 0.0, 300.0) is False
        assert pv.is_valid_position(-100.0, 0.0, 300.0) is False

    def test_invalid_longitude(self):
        pv = ProjectionValidator()
        assert pv.is_valid_position(51.0, 200.0, 300.0) is False
        assert pv.is_valid_position(51.0, -200.0, 300.0) is False

    def test_invalid_altitude(self):
        pv = ProjectionValidator()
        assert pv.is_valid_position(51.0, 0.0, 100000.0) is False

    def test_valid_attitude(self):
        pv = ProjectionValidator()
        assert pv.is_valid_attitude(2.5, 5.0, 270.0) is True

    def test_invalid_pitch(self):
        pv = ProjectionValidator()
        assert pv.is_valid_attitude(95.0, 0.0, 270.0) is False

    def test_valid_screen_pos(self):
        pv = ProjectionValidator()
        assert pv.is_valid_screen_pos(512.0, 400.0) is True
        assert pv.is_valid_screen_pos(-1000.0, 400.0) is False


# =========================================================================
#  12.  TESTS — Optics Stability Detector
# =========================================================================

class TestOpticsStabilityDetector:
    """Tests for OpticsStabilityDetector."""

    def test_stable_optics(self):
        detector = OpticsStabilityDetector()
        for _ in range(10):
            stable, score, _ = detector.check(0.8, 0.2, 5.0)
        assert stable is True
        assert score < 0.5

    def test_oscillating_brightness(self):
        detector = OpticsStabilityDetector()
        for i in range(20):
            stable, score, _ = detector.check(
                0.5 + math.sin(i * 0.5) * 0.4, 0.2, 5.0)
        assert stable is False or detector.oscillation_count > 0

    def test_abrupt_jump(self):
        detector = OpticsStabilityDetector()
        for _ in range(10):
            detector.check(0.8, 0.2, 5.0)
        # Abrupt change
        stable, score, details = detector.check(0.1, 0.2, 5.0)
        # Should detect brightness jump
        assert "jump" in details or score > 0.3

    def test_warm_up_period(self):
        detector = OpticsStabilityDetector()
        stable, score, details = detector.check(0.8, 0.2, 5.0)
        assert stable is True  # Warm-up period always returns stable


# =========================================================================
#  13.  TESTS — Jitter Detection
# =========================================================================

class TestJitterDetector:
    """Tests for JitterDetector."""

    def test_low_jitter(self):
        detector = JitterDetector(threshold_px=10.0)
        for i in range(30):
            detector.check_fpv_jitter(512.0, 300.0,
                                      512.0 + math.sin(i) * 0.5,
                                      300.0 + math.cos(i) * 0.5)
        assert detector.any_excessive_jitter() is False

    def test_high_jitter(self):
        detector = JitterDetector(threshold_px=10.0)
        for i in range(30):
            detector.check_fpv_jitter(512.0, 300.0,
                                      512.0 + math.sin(i) * 20,
                                      300.0 + math.cos(i) * 20)
        assert detector.any_excessive_jitter() is True

    def test_runway_jitter(self):
        detector = JitterDetector(threshold_px=10.0)
        corner = [(412, 270), (612, 270), (612, 330), (412, 330),
                  (0, 0), (0, 0), (0, 0), (0, 0)]
        jittery_corner = [(412 + int(15 * math.sin(i)), 270) for i in range(8)]

        for _ in range(30):
            movement = detector.check_runway_jitter(corner, jittery_corner)
        assert detector.any_excessive_jitter() is True

    def test_jitter_level_scale(self):
        detector = JitterDetector(threshold_px=10.0)
        # No jitter
        for _ in range(30):
            detector.check_fpv_jitter(512.0, 300.0, 512.0, 300.0)
        low_level = detector.jitter_level()

        # High jitter
        detector2 = JitterDetector(threshold_px=10.0)
        for i in range(30):
            detector2.check_fpv_jitter(512.0, 300.0,
                                       512.0 + math.sin(i) * 50,
                                       300.0 + math.cos(i) * 50)
        high_level = detector2.jitter_level()
        assert high_level >= low_level


# =========================================================================
#  14.  TESTS — FPS Collapse Detection
# =========================================================================

class TestFPSCollapseDetector:
    """Tests for FPSCollapseDetector."""

    def test_normal_fps(self):
        detector = FPSCollapseDetector()
        for _ in range(10):
            state = detector.record_fps(60.0)
        assert detector.is_collapsed() is False
        assert detector.is_degraded() is False

    def test_collapse_detection(self):
        detector = FPSCollapseDetector()
        for _ in range(10):
            detector.record_fps(60.0)
        state = detector.record_fps(5.0)
        assert state == "collapsed"
        assert detector.is_collapsed() is True

    def test_warning_detection(self):
        detector = FPSCollapseDetector()
        for _ in range(10):
            detector.record_fps(60.0)
        state = detector.record_fps(25.0)
        assert state == "warning"
        assert detector.is_degraded() is True

    def test_recovery(self):
        detector = FPSCollapseDetector()
        detector.record_fps(5.0)
        assert detector.is_collapsed() is True
        for _ in range(5):
            detector.record_fps(60.0)
        assert detector.is_collapsed() is False

    def test_collapse_counting(self):
        detector = FPSCollapseDetector()
        detector.record_fps(5.0)
        detector.record_fps(3.0)
        assert detector.collapse_events == 2

    def test_avg_fps(self):
        detector = FPSCollapseDetector()
        for fps in [60, 60, 30, 30, 60]:
            detector.record_fps(fps)
        assert 40 <= detector.avg_fps() <= 60


# =========================================================================
#  15.  TESTS — Emergency Degraded Mode
# =========================================================================

class TestEmergencyDegradedMode:
    """Tests for EmergencyDegradedMode."""

    def test_normal_level(self):
        wd = WatchdogSystem()
        fps = FPSCollapseDetector()
        jd = JitterDetector()
        edm = EmergencyDegradedMode()
        level = edm.evaluate(wd, fps, jd)
        assert level == EmergencyDegradedMode.LEVEL_NORMAL

    def test_emergency_on_collapse(self):
        wd = WatchdogSystem()
        fps = FPSCollapseDetector()
        fps.record_fps(5.0)
        jd = JitterDetector()
        edm = EmergencyDegradedMode()
        level = edm.evaluate(wd, fps, jd)
        assert level == EmergencyDegradedMode.LEVEL_EMERGENCY

    def test_emergency_disables_features(self):
        edm = EmergencyDegradedMode()
        edm.level = EmergencyDegradedMode.LEVEL_EMERGENCY
        edm._apply_degradation()
        assert edm.disable_bloom is True
        assert edm.disable_evs is True
        assert edm.disable_advanced_symbology is True
        assert edm.simplify_runway is True

    def test_caution_limits_degradation(self):
        edm = EmergencyDegradedMode()
        edm.level = EmergencyDegradedMode.LEVEL_CAUTION
        edm._apply_degradation()
        assert edm.disable_bloom is True
        assert edm.disable_evs is False  # EVS kept
        assert edm.hide_guidance is False  # Guidance kept

    def test_recovery_check(self):
        edm = EmergencyDegradedMode()
        edm.level = EmergencyDegradedMode.LEVEL_WARNING
        assert edm.recovery_check() is True
        edm.level = EmergencyDegradedMode.LEVEL_EMERGENCY
        assert edm.recovery_check() is False  # Must wait


# =========================================================================
#  16.  TESTS — Telemetry Rejection Filter
# =========================================================================

class TestTelemetryRejectionFilter:
    """Tests for TelemetryRejectionFilter."""

    def test_accept_valid_frame(self):
        from test_telemetry import TelemetryFrame
        filt = TelemetryRejectionFilter()
        tf = TelemetryFrame()
        tf.ac_lat = 51.4775
        tf.ac_lon = -0.4614
        tf.ac_alt_m = 300.0
        tf.ac_hdg_true = 270.0
        tf.ac_pitch_deg = -2.5
        tf.ac_bank_deg = 0.0
        accepted, _ = filt.accept_frame(tf)
        assert accepted is True

    def test_reject_nan(self):
        from test_telemetry import TelemetryFrame
        filt = TelemetryRejectionFilter()
        tf = TelemetryFrame()
        tf.ac_lat = float('nan')
        accepted, reason = filt.accept_frame(tf)
        assert accepted is False
        assert 'nan' in reason

    def test_reject_inf(self):
        from test_telemetry import TelemetryFrame
        filt = TelemetryRejectionFilter()
        tf = TelemetryFrame()
        tf.ac_lat = float('inf')
        accepted, _ = filt.accept_frame(tf)
        assert accepted is False

    def test_reject_out_of_range(self):
        from test_telemetry import TelemetryFrame
        filt = TelemetryRejectionFilter()
        tf = TelemetryFrame()
        tf.ac_lat = 100.0  # Invalid
        accepted, _ = filt.accept_frame(tf)
        assert accepted is False

    def test_reject_null(self):
        filt = TelemetryRejectionFilter()
        accepted, _ = filt.accept_frame(None)
        assert accepted is False

    def test_acceptance_rate(self):
        filt = TelemetryRejectionFilter()
        from test_telemetry import TelemetryFrame

        for _ in range(80):
            tf = TelemetryFrame()
            tf.ac_lat = 51.4775
            tf.ac_lon = -0.4614
            filt.accept_frame(tf)

        for _ in range(20):
            tf = TelemetryFrame()
            tf.ac_lat = float('nan')
            filt.accept_frame(tf)

        rate = filt.acceptance_rate()
        assert abs(rate - 0.8) < 0.05

    def test_rejection_reasons_tracked(self):
        from test_telemetry import TelemetryFrame
        filt = TelemetryRejectionFilter()
        tf = TelemetryFrame()
        tf.ac_lat = float('nan')
        filt.accept_frame(tf)
        tf2 = TelemetryFrame()
        tf2.ac_lat = float('inf')
        filt.accept_frame(tf2)
        assert 'ac_lat_nan' in filt.rejection_reasons
        assert 'ac_lat_inf' in filt.rejection_reasons


# =========================================================================
#  17.  TESTS — Integrated Watchdog Pipeline
# =========================================================================

class TestIntegratedWatchdogPipeline:
    """End-to-end watchdog pipeline test."""

    def test_full_watchdog_pipeline(self):
        """Watchdog + NaN guard + Jitter + FPS + Emergency Mode."""
        from test_telemetry import generate_test_approach

        frames = generate_test_approach(600).frames

        wd = WatchdogSystem(stall_threshold=10)
        nan_guard = NaNGuard()
        proj_validator = ProjectionValidator()
        optics_detector = OpticsStabilityDetector()
        jitter_detector = JitterDetector()
        fps_detector = FPSCollapseDetector()
        reject_filter = TelemetryRejectionFilter()
        edm = EmergencyDegradedMode()

        # Run pipeline
        prev_fpv = (None, None)
        for i, frame in enumerate(frames):
            # 1. Reject invalid telemetry
            accepted, reason = reject_filter.accept_frame(frame)
            if not accepted:
                continue

            # 2. NaN guard
            _, issues = nan_guard.check_frame(frame)

            # 3. Validate projection
            valid, proj_issues = proj_validator.validate_frame(frame)

            # 4. Check optics stability
            optics_detector.check(
                frame.optical_brightness,
                frame.optical_bloom,
                frame.optical_phosphor_ms)

            # 5. Track jitter
            if frame.fpv_valid:
                movement = jitter_detector.check_fpv_jitter(
                    prev_fpv[0], prev_fpv[1], frame.fpv_x, frame.fpv_y)
                prev_fpv = (frame.fpv_x, frame.fpv_y)

            # 6. Record FPS
            fps_detector.record_fps(60.0)

            # 7. Heartbeats
            wd.heartbeat('FPV')
            wd.heartbeat('GUIDANCE')
            wd.tick('FPV')
            wd.tick('GUIDANCE')

        # 8. Evaluate emergency mode
        level = edm.evaluate(wd, fps_detector, jitter_detector)

        # Normal operation with 60fps should be fine
        assert edm.level <= EmergencyDegradedMode.LEVEL_NORMAL
        assert reject_filter.acceptance_rate() > 0.95
        assert fps_detector.is_collapsed() is False

    def test_watchdog_recovers_from_stall(self):
        """Watchdog should detect and recover from subsystem stalls."""
        wd = WatchdogSystem(stall_threshold=3)
        wd.heartbeat('FPV')

        # Stall FPV
        for _ in range(5):
            wd.tick('FPV')

        sub = wd.get('FPV')
        assert sub.healthy is False or sub.stalled_ticks > 0

        # Resume heartbeats
        wd.heartbeat('FPV')
        if not sub.healthy:
            wd._attempt_recovery('FPV')
            assert wd.get('FPV').healthy is True

    def test_nan_propagation_blocked(self):
        """NaN should never propagate past the guard."""
        guard = NaNGuard()
        from test_telemetry import TelemetryFrame, generate_test_approach

        frames = generate_test_approach(100).frames
        frames[50].ac_lat = float('nan')
        frames[50].ac_lon = float('nan')

        for i, frame in enumerate(frames):
            cleaned, issues = guard.check_frame(frame)
            if i == 50:
                assert 'ac_lat' in str(issues) or len(issues) > 0
                # Cleaned frame should not have NaN
                assert not math.isnan(cleaned.ac_lat)
                assert not math.isnan(cleaned.ac_lon)
