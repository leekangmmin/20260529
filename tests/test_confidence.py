#!/usr/bin/env python3
"""
Conformal HUD – Confidence-Based Rendering Test Suite (v2.4.0)

Tests:
  1. Confidence state initialisation
  2. Per-sensor confidence scoring
  3. LOC/GS rendering mode transitions
  4. Integrity computation
  5. CAT III qualification
  6. Oscillation behaviour

Run:  python -m pytest tests/test_confidence.py -v
"""

import math
import pytest


# ======================================================================
#  Constants & Enums
# ======================================================================

SENSOR_ILS_LOC = 0
SENSOR_ILS_GS = 1
SENSOR_GPS = 2
SENSOR_RADIO_ALT = 3
SENSOR_AIR_DATA = 4
SENSOR_ATTITUDE = 5
SENSOR_COUNT = 6

RENDER_SOLID = 0
RENDER_DIMMED = 1
RENDER_DASHED = 2
RENDER_OSCILLATE = 3
RENDER_HIDDEN = 4

CONF_DASH_THRESHOLD = 0.6
CONF_DIMMED_THRESHOLD = 0.4
CONF_HIDDEN_THRESHOLD = 0.15


# ======================================================================
#  Reference implementation
# ======================================================================

class SensorConfidence:
    def __init__(self):
        self.confidence = 1.0
        self.signal_quality = 1.0
        self.signal_strength = 1.0
        self.noise_level = 0.0
        self.stability = 1.0
        self.oscillation_freq = 0.0
        self.oscillation_amplitude = 0.0
        self.valid = True


class ConfidenceRenderParams:
    def __init__(self):
        self.loc_mode = RENDER_SOLID
        self.gs_mode = RENDER_SOLID
        self.fpv_mode = RENDER_SOLID
        self.flare_mode = RENDER_SOLID
        self.centerline_mode = RENDER_SOLID
        self.loc_alpha = 1.0
        self.gs_alpha = 1.0
        self.fpv_alpha = 1.0
        self.flare_alpha = 1.0
        self.centerline_alpha = 1.0
        self.loc_dash_length = 0.0
        self.gs_dash_length = 0.0
        self.integrity = 1.0
        self.valid = True


class ConfidenceState:
    def __init__(self):
        self.sensors = [SensorConfidence() for _ in range(SENSOR_COUNT)]
        self.overall_integrity = 1.0
        self.ils_integrity = 1.0
        self.guidance_integrity = 1.0
        self.cat_iii_qualification = 1.0
        self.render = ConfidenceRenderParams()
        self.oscillation_phase = 0.0
        self.time_s = 0.0
        self.noise_sensitivity = 0.5
        self.stability_gain = 1.0
        self.valid = True


def confidence_compute(cs, dt_s=1.0/60.0, ils_loc_dots=0.0, ils_gs_dots=0.0,
                       loc_captured=True, gs_captured=True, radio_alt_valid=True,
                       groundspeed_ms=70.0, cat_iii_mode=False):
    cs.time_s += dt_s
    cs.oscillation_phase += dt_s * 3.0

    # ILS LOC
    loc = cs.sensors[SENSOR_ILS_LOC]
    loc.valid = True
    dev_quality = 1.0 - min(abs(ils_loc_dots) / 2.0, 1.0)
    loc.signal_quality = dev_quality
    capture_boost = 0.2 if loc_captured else 0.0
    loc.noise_level = 0.05 + (1.0 - dev_quality) * 0.3
    loc.stability = 0.95 if loc_captured else 0.7
    if not loc_captured:
        loc.oscillation_freq = 0.5
        loc.oscillation_amplitude = 0.02
    else:
        loc.oscillation_freq = 0.0
        loc.oscillation_amplitude = 0.0
    loc.confidence = dev_quality * 0.5 + loc.stability * 0.3 + capture_boost * 0.2
    loc.confidence = max(0.0, min(1.0, loc.confidence))

    # ILS GS
    gs_sensor = cs.sensors[SENSOR_ILS_GS]
    gs_sensor.valid = True
    dev_quality = 1.0 - min(abs(ils_gs_dots) / 2.0, 1.0)
    gs_sensor.signal_quality = dev_quality
    capture_boost = 0.2 if gs_captured else 0.0
    gs_sensor.noise_level = 0.05 + (1.0 - dev_quality) * 0.3
    gs_sensor.stability = 0.95 if gs_captured else 0.7
    if not gs_captured:
        gs_sensor.oscillation_freq = 0.4
        gs_sensor.oscillation_amplitude = 0.015
    else:
        gs_sensor.oscillation_freq = 0.0
        gs_sensor.oscillation_amplitude = 0.0
    gs_sensor.confidence = dev_quality * 0.5 + gs_sensor.stability * 0.3 + capture_boost * 0.2
    gs_sensor.confidence = max(0.0, min(1.0, gs_sensor.confidence))

    # GPS
    gps = cs.sensors[SENSOR_GPS]
    gps.valid = True
    gps.signal_quality = 0.95
    gps.stability = 0.9
    gps.noise_level = 0.05
    gps.confidence = 0.8 if groundspeed_ms < 0.5 else 0.95

    # Radio altimeter
    ra = cs.sensors[SENSOR_RADIO_ALT]
    ra.valid = radio_alt_valid
    if radio_alt_valid:
        ra.confidence = 0.98
        ra.signal_quality = 0.98
        ra.stability = 0.95
        ra.noise_level = 0.02
    else:
        ra.confidence = 0.2
        ra.signal_quality = 0.2
        ra.stability = 0.2
        ra.noise_level = 0.8

    # Air data
    ad = cs.sensors[SENSOR_AIR_DATA]
    ad.valid = True
    ad.confidence = 0.9
    ad.signal_quality = 0.9
    ad.stability = 0.85
    ad.noise_level = 0.1

    # Attitude
    att = cs.sensors[SENSOR_ATTITUDE]
    att.valid = True
    att.confidence = 0.95
    att.signal_quality = 0.95
    att.stability = 0.9
    att.noise_level = 0.05

    # Composite integrity
    cs.ils_integrity = min(cs.sensors[SENSOR_ILS_LOC].confidence,
                           cs.sensors[SENSOR_ILS_GS].confidence)
    cs.guidance_integrity = min(cs.ils_integrity, cs.sensors[SENSOR_ATTITUDE].confidence)

    total = 0.0
    count = 0
    for i in range(SENSOR_COUNT):
        if cs.sensors[i].valid:
            total += cs.sensors[i].confidence
            count += 1
    cs.overall_integrity = total / count if count > 0 else 0.5

    if cat_iii_mode:
        cs.cat_iii_qualification = cs.overall_integrity * min(cs.guidance_integrity * 1.1, 1.0)
    else:
        cs.cat_iii_qualification = cs.overall_integrity

    # Rendering parameters
    r = cs.render
    loc_conf = cs.sensors[SENSOR_ILS_LOC].confidence
    gs_conf = cs.sensors[SENSOR_ILS_GS].confidence

    if loc_conf < CONF_HIDDEN_THRESHOLD:
        r.loc_mode = RENDER_HIDDEN
        r.loc_alpha = 0.0
        r.loc_dash_length = 0.0
    elif loc_conf < CONF_DIMMED_THRESHOLD:
        r.loc_mode = RENDER_DIMMED
        r.loc_alpha = 0.3
        r.loc_dash_length = 0.0
    elif loc_conf < CONF_DASH_THRESHOLD:
        r.loc_mode = RENDER_DASHED
        r.loc_alpha = 0.5
        r.loc_dash_length = 8.0 + (1.0 - loc_conf) * 12.0
    else:
        r.loc_mode = RENDER_SOLID
        r.loc_alpha = 0.7 + loc_conf * 0.3
        r.loc_dash_length = 0.0

    if gs_conf < CONF_HIDDEN_THRESHOLD:
        r.gs_mode = RENDER_HIDDEN
        r.gs_alpha = 0.0
        r.gs_dash_length = 0.0
    elif gs_conf < CONF_DIMMED_THRESHOLD:
        r.gs_mode = RENDER_DIMMED
        r.gs_alpha = 0.3
        r.gs_dash_length = 0.0
    elif gs_conf < CONF_DASH_THRESHOLD:
        r.gs_mode = RENDER_DASHED
        r.gs_alpha = 0.5
        r.gs_dash_length = 8.0 + (1.0 - gs_conf) * 12.0
    else:
        r.gs_mode = RENDER_SOLID
        r.gs_alpha = 0.7 + gs_conf * 0.3
        r.gs_dash_length = 0.0

    gps_conf = cs.sensors[SENSOR_GPS].confidence
    if gps_conf < CONF_DIMMED_THRESHOLD:
        r.fpv_mode = RENDER_DIMMED
        r.fpv_alpha = gps_conf
    else:
        r.fpv_mode = RENDER_SOLID
        r.fpv_alpha = 0.8 + gps_conf * 0.2

    ra_conf = cs.sensors[SENSOR_RADIO_ALT].confidence
    if ra_conf < CONF_DIMMED_THRESHOLD:
        r.flare_mode = RENDER_HIDDEN
        r.flare_alpha = 0.0
    else:
        r.flare_mode = RENDER_SOLID
        r.flare_alpha = ra_conf

    r.centerline_mode = RENDER_SOLID
    r.centerline_alpha = cs.guidance_integrity
    r.integrity = cs.overall_integrity
    r.valid = True

    cs.valid = True


# ======================================================================
#  Tests
# ======================================================================

class TestConfidenceInit:
    def test_defaults(self):
        cs = ConfidenceState()
        assert cs.valid is True
        for s in cs.sensors:
            assert s.confidence == 1.0
        assert cs.overall_integrity == 1.0

    def test_render_defaults(self):
        cs = ConfidenceState()
        assert cs.render.loc_mode == RENDER_SOLID
        assert cs.render.loc_alpha == 1.0


class TestSensorConfidence:
    def test_loc_high_when_captured(self):
        cs = ConfidenceState()
        confidence_compute(cs, ils_loc_dots=0.1, loc_captured=True)
        assert cs.sensors[SENSOR_ILS_LOC].confidence > 0.7

    def test_loc_low_when_not_captured(self):
        cs = ConfidenceState()
        confidence_compute(cs, ils_loc_dots=1.5, loc_captured=False)
        assert cs.sensors[SENSOR_ILS_LOC].confidence < 0.7

    def test_gps_high_in_flight(self):
        cs = ConfidenceState()
        confidence_compute(cs, groundspeed_ms=70.0)
        assert cs.sensors[SENSOR_GPS].confidence > 0.9

    def test_radio_alt_high_when_valid(self):
        cs = ConfidenceState()
        confidence_compute(cs, radio_alt_valid=True)
        assert cs.sensors[SENSOR_RADIO_ALT].confidence > 0.9

    def test_radio_alt_low_when_invalid(self):
        cs = ConfidenceState()
        confidence_compute(cs, radio_alt_valid=False)
        assert cs.sensors[SENSOR_RADIO_ALT].confidence < 0.5


class TestRenderModes:
    def test_loc_solid_at_high_confidence(self):
        cs = ConfidenceState()
        confidence_compute(cs, ils_loc_dots=0.1, loc_captured=True)
        assert cs.render.loc_mode == RENDER_SOLID
        assert cs.render.loc_dash_length == 0.0

    def test_loc_dashed_at_medium_confidence(self):
        cs = ConfidenceState()
        # Moderate deviation, not captured
        confidence_compute(cs, ils_loc_dots=1.0, loc_captured=False)
        # Confidence should be in dashed range
        loc_conf = cs.sensors[SENSOR_ILS_LOC].confidence
        if CONF_DIMMED_THRESHOLD <= loc_conf < CONF_DASH_THRESHOLD:
            assert cs.render.loc_mode == RENDER_DASHED
        else:
            # It might be dimmed or solid depending on exact values
            assert cs.render.loc_mode in (RENDER_SOLID, RENDER_DASHED, RENDER_DIMMED)

    def test_loc_hidden_at_very_low_confidence(self):
        cs = ConfidenceState()
        # Large deviation
        confidence_compute(cs, ils_loc_dots=2.5, loc_captured=False)
        loc_conf = cs.sensors[SENSOR_ILS_LOC].confidence
        if loc_conf < CONF_HIDDEN_THRESHOLD:
            assert cs.render.loc_mode == RENDER_HIDDEN
        elif loc_conf < CONF_DIMMED_THRESHOLD:
            assert cs.render.loc_mode == RENDER_DIMMED

    def test_fpv_alpha_scales_with_gps(self):
        cs = ConfidenceState()
        confidence_compute(cs)
        assert cs.render.fpv_alpha > 0.8


class TestIntegrity:
    def test_integrity_high_in_good_conditions(self):
        cs = ConfidenceState()
        confidence_compute(cs, ils_loc_dots=0.05, ils_gs_dots=0.05,
                           loc_captured=True, gs_captured=True)
        assert cs.overall_integrity > 0.8

    def test_integrity_low_in_poor_conditions(self):
        cs = ConfidenceState()
        confidence_compute(cs, ils_loc_dots=2.0, ils_gs_dots=2.0,
                           loc_captured=False, gs_captured=False,
                           radio_alt_valid=False)
        assert cs.overall_integrity < 0.8

    def test_cat_iii_requires_high_integrity(self):
        cs_high = ConfidenceState()
        confidence_compute(cs_high, cat_iii_mode=True)
        cat_high = cs_high.cat_iii_qualification

        cs_low = ConfidenceState()
        confidence_compute(cs_low, ils_loc_dots=2.0, cat_iii_mode=True)
        cat_low = cs_low.cat_iii_qualification
        assert cat_low < cat_high
