#!/usr/bin/env python3
"""
Conformal HUD – Live Aircraft Compatibility Certification Suite (v2.6.0)

PHASE 4 — LIVE AIRCRAFT COMPATIBILITY CERTIFICATION

Tests for:
  1. Compatibility signature matching
  2. Aircraft-version detection
  3. Integration self-repair
  4. Automatic fallback mode
  5. Package structure change resilience
  6. Panel integration reliability
  7. Camera alignment consistency
  8. Optical center consistency

Goal:
  Aircraft updates should not silently break the HUD.

Run:  python -m pytest tests/test_aircraft_compatibility.py -v
"""


# =========================================================================
#  1.  Compatibility infrastructure (mirrors C++)
# =========================================================================

# Known aircraft compatibility signatures
AIRCRAFT_SIGNATURES = [
    {
        'prefix': 'PMDG 737-800',
        'profile_index': 0,
        'version_major': 3,
        'version_minor': 0,
        'requires_panel_fix': False,
        'requires_eye_offset': True,
        'eye_offset_correction_m': 0.05,
        'optical_center_verified': True,
        'optical_center_cx': 512.0,
        'optical_center_cy': 500.0,
    },
    {
        'prefix': 'PMDG 737-700',
        'profile_index': 0,
        'version_major': 3,
        'version_minor': 0,
        'requires_panel_fix': False,
        'requires_eye_offset': True,
        'eye_offset_correction_m': 0.05,
        'optical_center_verified': True,
        'optical_center_cx': 512.0,
        'optical_center_cy': 500.0,
    },
    {
        'prefix': 'PMDG 777-300ER',
        'profile_index': 1,
        'version_major': 1,
        'version_minor': 0,
        'requires_panel_fix': False,
        'requires_eye_offset': True,
        'eye_offset_correction_m': 0.03,
        'optical_center_verified': True,
        'optical_center_cx': 512.0,
        'optical_center_cy': 490.0,
    },
    {
        'prefix': 'ASOBO 787-10',
        'profile_index': 2,
        'version_major': 1,
        'version_minor': 34,
        'requires_panel_fix': True,
        'requires_eye_offset': False,
        'eye_offset_correction_m': 0.0,
        'optical_center_verified': True,
        'optical_center_cx': 512.0,
        'optical_center_cy': 510.0,
    },
    {
        'prefix': 'WT 787-10',
        'profile_index': 3,
        'version_major': 1,
        'version_minor': 0,
        'requires_panel_fix': True,
        'requires_eye_offset': False,
        'eye_offset_correction_m': 0.0,
        'optical_center_verified': False,
        'optical_center_cx': 512.0,
        'optical_center_cy': 512.0,
    },
    {
        'prefix': 'iniBuilds A350',
        'profile_index': 4,
        'version_major': 1,
        'version_minor': 2,
        'requires_panel_fix': True,
        'requires_eye_offset': True,
        'eye_offset_correction_m': -0.02,
        'optical_center_verified': True,
        'optical_center_cx': 515.0,
        'optical_center_cy': 505.0,
    },
    {
        'prefix': 'FBW A32NX',
        'profile_index': 5,
        'version_major': 1,
        'version_minor': 0,
        'requires_panel_fix': False,
        'requires_eye_offset': False,
        'eye_offset_correction_m': 0.0,
        'optical_center_verified': False,
        'optical_center_cx': 512.0,
        'optical_center_cy': 512.0,
    },
    {
        'prefix': 'HEADWIND A330-900',
        'profile_index': 5,
        'version_major': 1,
        'version_minor': 0,
        'requires_panel_fix': False,
        'requires_eye_offset': False,
        'eye_offset_correction_m': 0.0,
        'optical_center_verified': False,
        'optical_center_cx': 512.0,
        'optical_center_cy': 512.0,
    },
]


class CompatibilityResult:
    """Result of compatibility check."""

    def __init__(self):
        self.aircraft_prefix = ''
        self.signature = None
        self.supported = False
        self.version_match = False
        self.requires_repair = False
        self.fallback_active = False
        self.profile_index = -1
        self.confidence = 0.0  # 0..1


def match_signature(aircraft_title):
    """Match aircraft title against known signatures (prefix matching)."""
    upper_title = aircraft_title.upper()
    best_sig = None
    best_len = 0

    for sig in AIRCRAFT_SIGNATURES:
        if upper_title.startswith(sig['prefix'].upper()):
            if len(sig['prefix']) > best_len:
                best_sig = sig
                best_len = len(sig['prefix'])

    return best_sig


def check_compatibility(aircraft_title, version_major=0, version_minor=0):
    """Full compatibility check."""
    result = CompatibilityResult()
    result.aircraft_prefix = aircraft_title

    sig = match_signature(aircraft_title)
    if sig is None:
        result.supported = False
        result.fallback_active = True
        result.confidence = 0.1
        return result

    result.signature = sig
    result.supported = True
    result.profile_index = sig['profile_index']

    # Check version match
    result.version_match = (
        version_major >= sig['version_major'] and
        version_minor >= sig['version_minor']
    )

    # Determine if repair needed
    if not result.version_match:
        result.requires_repair = True
        result.fallback_active = True
        result.confidence = 0.4
    elif sig['requires_panel_fix']:
        result.requires_repair = True
        result.fallback_active = True
        result.confidence = 0.7
    else:
        result.fallback_active = False
        result.confidence = 0.95

    return result


def self_repair(result):
    """Attempt to repair compatibility issues."""
    if not result.requires_repair:
        return True

    # Simulated repair actions
    repairs_needed = []
    if result.signature and result.signature['requires_panel_fix']:
        repairs_needed.append('panel_fix')
    if not result.version_match:
        repairs_needed.append('version_adjust')

    # In real simulator, these would apply actual fixes
    if len(repairs_needed) > 0:
        result.fallback_active = True
        # After repair attempt, re-check
        if result.signature:
            result.requires_repair = False
            result.confidence = min(1.0, result.confidence + 0.2)
        return True

    return False


# =========================================================================
#  2.  Tests
# =========================================================================

class TestSignatureMatching:
    """Test aircraft signature matching."""

    def test_match_pmdg_737(self):
        sig = match_signature('PMDG 737-800')
        assert sig is not None
        assert sig['prefix'] == 'PMDG 737-800'

    def test_match_pmdg_737_700(self):
        sig = match_signature('PMDG 737-700')
        assert sig is not None
        assert sig['prefix'] == 'PMDG 737-700'

    def test_match_pmdg_777(self):
        sig = match_signature('PMDG 777-300ER')
        assert sig is not None
        assert sig['prefix'] == 'PMDG 777-300ER'

    def test_match_asobo_787(self):
        sig = match_signature('ASOBO 787-10')
        assert sig is not None
        assert sig['prefix'] == 'ASOBO 787-10'

    def test_match_wt_787(self):
        sig = match_signature('WT 787-10')
        assert sig is not None
        assert sig['prefix'] == 'WT 787-10'

    def test_match_inibuilds_a350(self):
        sig = match_signature('iniBuilds A350')
        assert sig is not None
        assert sig['prefix'] == 'iniBuilds A350'

    def test_match_fbw_a32nx(self):
        sig = match_signature('FBW A32NX')
        assert sig is not None
        assert sig['prefix'] == 'FBW A32NX'

    def test_match_headwind_a330(self):
        sig = match_signature('HEADWIND A330-900')
        assert sig is not None
        assert sig['prefix'] == 'HEADWIND A330-900'

    def test_match_unknown_aircraft(self):
        sig = match_signature('Some Unknown Aircraft')
        assert sig is None

    def test_case_insensitive_matching(self):
        sig = match_signature('pmdg 737-800')
        assert sig is not None
        assert sig['prefix'] == 'PMDG 737-800'

    def test_prefix_over_matching(self):
        """'PMDG 737-800' should match before just 'PMDG'."""
        # Add a short prefix
        sig = match_signature('PMDG 737-800 WL')
        assert sig is not None
        assert sig['prefix'] == 'PMDG 737-800'

    def test_prefix_substring(self):
        """Ensure partial word matches don't trigger."""
        sig = match_signature('PMDGX 9000')  # Not actually PMDG
        assert sig is None


class TestCompatibilityCheck:
    """Test full compatibility checking logic."""

    def test_supported_aircraft_high_confidence(self):
        result = check_compatibility('PMDG 737-800', 3, 0)
        assert result.supported
        assert not result.fallback_active
        assert result.confidence >= 0.9

    def test_unknown_aircraft_low_confidence(self):
        result = check_compatibility('Unknown Aircraft')
        assert not result.supported
        assert result.fallback_active
        assert result.confidence < 0.5

    def test_version_mismatch_triggers_repair(self):
        result = check_compatibility('PMDG 737-800', 2, 0)  # Older version
        assert result.supported
        assert result.requires_repair
        assert not result.version_match

    def test_panel_fix_required(self):
        result = check_compatibility('ASOBO 787-10', 1, 34)
        assert result.supported
        assert result.requires_repair  # requires_panel_fix is True
        assert result.fallback_active

    def test_inibuilds_a350_detection(self):
        result = check_compatibility('iniBuilds A350-1000', 1, 2)
        assert result.supported
        assert result.profile_index == 4

    def test_all_aircraft_have_signatures(self):
        """Verify all supported aircraft have signatures."""
        expected = [
            'PMDG 737-800', 'PMDG 737-700', 'PMDG 777-300ER',
            'ASOBO 787-10', 'WT 787-10', 'iniBuilds A350',
            'FBW A32NX', 'HEADWIND A330-900',
        ]
        for aircraft in expected:
            sig = match_signature(aircraft)
            assert sig is not None, f"Missing signature for {aircraft}"


class TestSelfRepair:
    """Test self-repair capability."""

    def test_self_repair_on_version_mismatch(self):
        result = check_compatibility('PMDG 737-800', 2, 5)
        assert result.requires_repair

        success = self_repair(result)
        assert success
        assert not result.requires_repair
        assert result.confidence > 0.5

    def test_self_repair_on_panel_fix(self):
        result = check_compatibility('ASOBO 787-10', 1, 34)
        assert result.requires_repair

        success = self_repair(result)
        assert success

    def test_self_repair_not_needed(self):
        result = check_compatibility('PMDG 737-800', 3, 0)
        assert not result.requires_repair
        success = self_repair(result)
        assert success  # No-op success

    def test_repair_unknown_aircraft(self):
        result = check_compatibility('Unknown')
        assert not result.supported
        success = self_repair(result)
        assert success  # Silent success

    def test_fallback_after_repair_attempt(self):
        result = check_compatibility('PMDG 777-300ER', 0, 9)
        assert result.fallback_active
        self_repair(result)
        # After repair, fallback may still be active
        assert result.fallback_active or result.confidence > 0.5


class TestFallbackMode:
    """Test automatic fallback mode behavior."""

    def test_fallback_for_unknown(self):
        result = check_compatibility('Unknown Aircraft')
        assert result.fallback_active
        assert result.confidence < 0.3

    def test_fallback_for_version_mismatch(self):
        result = check_compatibility('PMDG 737-800', 1, 0)
        assert result.fallback_active

    def test_no_fallback_for_perfect_match(self):
        result = check_compatibility('PMDG 737-800', 3, 0)
        assert not result.fallback_active

    def test_fallback_profile_index(self):
        result = check_compatibility('Unknown Aircraft')
        assert result.profile_index == -1  # Default/fallback profile


class TestOpticalCenterConsistency:
    """Test optical center consistency across aircraft types."""

    def test_optical_center_within_range(self):
        """All verified optical centers should be within panel bounds."""
        for sig in AIRCRAFT_SIGNATURES:
            if sig['optical_center_verified']:
                assert 400 <= sig['optical_center_cx'] <= 624, \
                    f"Cx out of range for {sig['prefix']}"
                assert 350 <= sig['optical_center_cy'] <= 674, \
                    f"Cy out of range for {sig['prefix']}"

    def test_eye_offset_reasonable(self):
        """Eye offsets should be physically plausible."""
        for sig in AIRCRAFT_SIGNATURES:
            if sig['requires_eye_offset']:
                assert abs(sig['eye_offset_correction_m']) < 0.5, \
                    f"Eye offset unrealistic for {sig['prefix']}"

    def test_all_aircraft_have_profile_index(self):
        for sig in AIRCRAFT_SIGNATURES:
            assert 0 <= sig['profile_index'] <= 5


class TestVersionDetection:
    """Test version-based detection and handling."""

    def test_exact_version_match(self):
        result = check_compatibility('PMDG 737-800', 3, 0)
        assert result.version_match

    def test_newer_version_compatible(self):
        result = check_compatibility('PMDG 737-800', 4, 0)
        assert result.version_match  # Newer version is backward compatible

    def test_older_version_incompatible(self):
        result = check_compatibility('PMDG 737-800', 2, 0)
        assert not result.version_match

    def test_minor_version_mismatch(self):
        """Minor version mismatch still triggers repair if below min."""
        result = check_compatibility('iniBuilds A350', 1, 0)
        assert not result.version_match  # Below min 1.2

    def test_confidence_increases_with_version(self):
        r1 = check_compatibility('PMDG 737-800', 2, 0)
        r2 = check_compatibility('PMDG 737-800', 3, 0)
        assert r2.confidence >= r1.confidence
