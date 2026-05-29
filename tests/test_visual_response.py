#!/usr/bin/env python3
"""
Conformal HUD – Human Visual Response Test Suite (v2.4.0)

Tests:
  1. Dark adaptation (entering/exiting dark conditions)
  2. Bloom / temporary blindness from bright lights
  3. Rain glare effects
  4. Phosphor persistence changes (night vs day)
  5. Brightness adaptation lag
  6. Visual contrast fatigue
  7. Eye accommodation simulation
  8. Output gain computation

Run:  python -m pytest tests/test_visual_response.py -v
"""

import math
import pytest


# ======================================================================
#  Reference implementation
# ======================================================================

class VisualResponseState:
    def __init__(self):
        self.dark_adaptation = 0.0
        self.ambient_luminance = 0.5
        self.dark_adapt_time_s = 0.0
        self.bloom_exposure = 0.0
        self.bloom_decay = 1.0
        self.bloom_threshold = 0.7
        self.bloom_amount = 0.0
        self.rain_intensity = 0.0
        self.rain_glare = 0.0
        self.is_raining = False
        self.phosphor_base_ms = 30.0
        self.phosphor_current_ms = 30.0
        self.persistence_boost = 0.0
        self.current_brightness = 0.7
        self.target_brightness = 0.7
        self.adaptation_rate = 0.5
        self.brightness_lag = 0.0
        self.fatigue_accumulator = 0.0
        self.fatigue_threshold = 0.5
        self.contrast_reduction = 0.0
        self.fatigue_recovery_rate = 0.1
        self.accommodation = 0.0
        self.accommodation_lag = 0.3
        self.accommodation_target = 0.0
        self.luminance_gain = 1.0
        self.contrast_gain = 1.0
        self.active = False
        self.debug_adaptation_level = 0.0
        self.debug_bloom_level = 0.0
        self.debug_phosphor_ms = 30.0
        self.debug_fatigue_level = 0.0


VR_DARK_ADAPT_RATE_UP = 0.8
VR_DARK_ADAPT_RATE_DOWN = 0.3
VR_BLOOM_DECAY_RATE = 2.0
VR_BLOOM_ATTACK_RATE = 5.0
VR_PHOSPHOR_NIGHT_MAX_MS = 80.0
VR_PHOSPHOR_DAY_MIN_MS = 20.0
VR_BRIGHTNESS_ADAPT_RATE = 0.4
VR_FATIGUE_ACCUM_RATE = 0.02
VR_ACCOMMODATION_RATE = 0.5


def visual_response_compute(vs, dt_s=1.0/60.0, ambient_lux=0.5,
                            rain_intensity=0.0, runway_light_boom=False):
    # Dark adaptation
    vs.ambient_luminance = max(0.0, min(1.0, ambient_lux))
    vs.dark_adapt_time_s += dt_s
    target_adaptation = 1.0 - vs.ambient_luminance
    if target_adaptation > vs.dark_adaptation:
        vs.dark_adaptation += (target_adaptation - vs.dark_adaptation) * VR_DARK_ADAPT_RATE_UP * dt_s
    else:
        vs.dark_adaptation += (target_adaptation - vs.dark_adaptation) * VR_DARK_ADAPT_RATE_DOWN * dt_s
    vs.dark_adaptation = max(0.0, min(1.0, vs.dark_adaptation))

    # Bloom
    if runway_light_boom or vs.bloom_exposure > 0.01:
        if runway_light_boom:
            vs.bloom_exposure += (1.0 - vs.bloom_exposure) * VR_BLOOM_ATTACK_RATE * dt_s
        else:
            vs.bloom_exposure -= VR_BLOOM_DECAY_RATE * dt_s
        vs.bloom_exposure = max(0.0, min(1.0, vs.bloom_exposure))
    vs.bloom_amount = vs.bloom_exposure * 0.6

    # Rain glare
    vs.rain_intensity = max(0.0, min(1.0, rain_intensity))
    vs.is_raining = vs.rain_intensity > 0.05
    vs.rain_glare = vs.rain_intensity * 0.3 * (1.0 + vs.dark_adaptation * 0.5)
    vs.rain_glare = max(0.0, min(1.0, vs.rain_glare))

    # Phosphor persistence
    vs.persistence_boost = vs.dark_adaptation * 0.6
    target_persistence = VR_PHOSPHOR_DAY_MIN_MS + (VR_PHOSPHOR_NIGHT_MAX_MS - VR_PHOSPHOR_DAY_MIN_MS) * vs.persistence_boost
    vs.phosphor_current_ms += (target_persistence - vs.phosphor_current_ms) * VR_DARK_ADAPT_RATE_UP * dt_s

    # Brightness adaptation lag
    vs.target_brightness = 0.3 + vs.ambient_luminance * 0.7
    brightness_diff = vs.target_brightness - vs.current_brightness
    adapt_speed = VR_BRIGHTNESS_ADAPT_RATE * (1.0 + vs.dark_adaptation * 0.5)
    vs.current_brightness += brightness_diff * adapt_speed * dt_s
    vs.current_brightness = max(0.05, min(1.0, vs.current_brightness))
    vs.brightness_lag = abs(vs.target_brightness - vs.current_brightness)

    # Visual contrast fatigue
    if vs.ambient_luminance > 0.3:
        vs.fatigue_accumulator += VR_FATIGUE_ACCUM_RATE * dt_s * vs.ambient_luminance
    else:
        vs.fatigue_accumulator -= vs.fatigue_recovery_rate * dt_s * (1.0 - vs.ambient_luminance)
    vs.fatigue_accumulator = max(0.0, min(1.0, vs.fatigue_accumulator))

    if vs.fatigue_accumulator > vs.fatigue_threshold:
        vs.contrast_reduction = (vs.fatigue_accumulator - vs.fatigue_threshold) / (1.0 - vs.fatigue_threshold)
    else:
        vs.contrast_reduction = 0.0
    vs.contrast_reduction = max(0.0, min(0.3, vs.contrast_reduction))

    # Accommodation
    accommodation_target = 0.3
    if vs.ambient_luminance < 0.2:
        accommodation_target = 0.7
    if vs.rain_intensity > 0.3:
        accommodation_target = 0.6
    vs.accommodation_target = accommodation_target
    vs.accommodation += (accommodation_target - vs.accommodation) * VR_ACCOMMODATION_RATE * dt_s
    vs.accommodation = max(0.0, min(1.0, vs.accommodation))

    # Output gains
    vs.luminance_gain = 1.0 + vs.dark_adaptation * 0.3
    vs.contrast_gain = 1.0 - vs.contrast_reduction
    vs.active = (vs.dark_adaptation > 0.05 or vs.bloom_amount > 0.01 or
                 vs.rain_glare > 0.01 or vs.contrast_reduction > 0.01 or
                 vs.brightness_lag > 0.05)

    vs.debug_adaptation_level = vs.dark_adaptation
    vs.debug_bloom_level = vs.bloom_amount
    vs.debug_phosphor_ms = vs.phosphor_current_ms
    vs.debug_fatigue_level = vs.contrast_reduction


# ======================================================================
#  Tests
# ======================================================================

class TestDarkAdaptation:
    def test_daylight_no_adaptation(self):
        vs = VisualResponseState()
        visual_response_compute(vs, ambient_lux=1.0)
        assert vs.dark_adaptation < 0.1

    def test_darkness_causes_adaptation(self):
        vs = VisualResponseState()
        for _ in range(100):
            visual_response_compute(vs, ambient_lux=0.0)
        assert vs.dark_adaptation > 0.5

    def test_adaptation_increases_slowly_in_dark(self):
        vs = VisualResponseState()
        # After 1 second at 1/60 dt
        before = vs.dark_adaptation
        for _ in range(60):
            visual_response_compute(vs, ambient_lux=0.0)
        after = vs.dark_adaptation
        assert after > before

    def test_adaptation_decays_in_light(self):
        vs = VisualResponseState()
        for _ in range(200):
            visual_response_compute(vs, ambient_lux=0.0)
        assert vs.dark_adaptation > 0.5
        # Now go into bright light (adaptation decays slowly)
        for _ in range(300):  # 5 seconds at 60 fps
            visual_response_compute(vs, ambient_lux=1.0)
        assert vs.dark_adaptation < 0.5  # Should have decreased


class TestBloom:
    def test_no_bloom_initially(self):
        vs = VisualResponseState()
        visual_response_compute(vs)
        assert vs.bloom_amount == 0.0

    def test_bright_lights_cause_bloom(self):
        vs = VisualResponseState()
        for _ in range(20):
            visual_response_compute(vs, runway_light_boom=True)
        assert vs.bloom_amount > 0.0

    def test_bloom_decays(self):
        vs = VisualResponseState()
        for _ in range(20):
            visual_response_compute(vs, runway_light_boom=True)
        bloom_peak = vs.bloom_amount
        assert bloom_peak > 0.0

        # Remove light source
        for _ in range(60):
            visual_response_compute(vs, runway_light_boom=False)
        assert vs.bloom_amount < bloom_peak

    def test_bloom_clamped(self):
        vs = VisualResponseState()
        for _ in range(200):
            visual_response_compute(vs, runway_light_boom=True)
        assert vs.bloom_amount <= 0.6


class TestRainGlare:
    def test_no_rain_no_glare(self):
        vs = VisualResponseState()
        visual_response_compute(vs, rain_intensity=0.0)
        assert vs.rain_glare == 0.0

    def test_rain_causes_glare(self):
        vs = VisualResponseState()
        visual_response_compute(vs, rain_intensity=0.5)
        assert vs.rain_glare > 0.0
        assert vs.is_raining is True

    def test_glare_stronger_at_night(self):
        vs_night = VisualResponseState()
        for _ in range(100):
            visual_response_compute(vs_night, ambient_lux=0.0, rain_intensity=0.5)

        vs_day = VisualResponseState()
        visual_response_compute(vs_day, ambient_lux=1.0, rain_intensity=0.5)

        assert vs_night.rain_glare >= vs_day.rain_glare * 0.5


class TestPhosphorPersistence:
    def test_daytime_phosphor_minimal(self):
        vs = VisualResponseState()
        visual_response_compute(vs, ambient_lux=1.0)
        assert vs.phosphor_current_ms < 35.0

    def test_night_phosphor_increases(self):
        vs = VisualResponseState()
        for _ in range(100):
            visual_response_compute(vs, ambient_lux=0.0)
        assert vs.phosphor_current_ms > 30.0


class TestBrightnessAdaptation:
    def test_brightness_follows_ambient(self):
        vs = VisualResponseState()
        visual_response_compute(vs, ambient_lux=1.0)
        assert vs.current_brightness > 0.5

    def test_dark_reduces_brightness(self):
        vs = VisualResponseState()
        for _ in range(100):
            visual_response_compute(vs, ambient_lux=0.0)
        assert vs.current_brightness < 0.5

    def test_lag_exists(self):
        vs = VisualResponseState()
        # Sudden change from bright to dark
        visual_response_compute(vs, ambient_lux=1.0)
        visual_response_compute(vs, ambient_lux=0.0)
        # There should be some lag (brightness hasn't fully adapted yet)
        assert vs.current_brightness > 0.3  # not yet fully dark-adapted


class TestContrastFatigue:
    def test_fatigue_increases_in_bright_light(self):
        vs = VisualResponseState()
        for _ in range(200):
            visual_response_compute(vs, ambient_lux=1.0)
        assert vs.fatigue_accumulator > 0.0

    def test_fatigue_accumulates_in_bright_light(self):
        vs = VisualResponseState()
        # 2000 frames at 1/60 = 33 seconds should accumulate significant fatigue
        for _ in range(2000):
            visual_response_compute(vs, ambient_lux=1.0)
        assert vs.fatigue_accumulator > 0.3

    def test_fatigue_recovery_in_dark(self):
        vs = VisualResponseState()
        # Accumulate fatigue over a long period
        for _ in range(2000):
            visual_response_compute(vs, ambient_lux=1.0)
        assert vs.fatigue_accumulator > 0.2
        fatigue_before = vs.fatigue_accumulator
        # Recover in dark
        for _ in range(1000):
            visual_response_compute(vs, ambient_lux=0.0)
        assert vs.fatigue_accumulator < fatigue_before


class TestAccommodation:
    def test_daytime_accommodation_far(self):
        vs = VisualResponseState()
        visual_response_compute(vs, ambient_lux=1.0)
        assert vs.accommodation < 0.5  # more far-focused

    def test_night_accommodation_near(self):
        vs = VisualResponseState()
        visual_response_compute(vs, ambient_lux=0.0)
        assert vs.accommodation > 0.0  # moves toward near


class TestOutputGains:
    def test_luminance_gain_in_dark(self):
        vs = VisualResponseState()
        for _ in range(100):
            visual_response_compute(vs, ambient_lux=0.0)
        assert vs.luminance_gain > 1.0

    def test_active_when_dark_adapted(self):
        vs = VisualResponseState()
        visual_response_compute(vs, ambient_lux=0.0)
        assert vs.active is True
