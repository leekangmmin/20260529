"""
Tests for the C_HUD_Runway Installer — Self-Healing
=====================================================
Phase 4 tests for self-healing integration.
"""

import sys
import json
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from installer.healer import (
    HealthChecker,
    SelfHealer,
    IntegrationHealth,
)
from installer.aircraft_scanner import (
    AircraftPackage,
    AircraftType,
    IntegrationStatus,
)


# =========================================================================
#  Tests
# =========================================================================

class TestHealthChecker:
    """Test health checker functionality."""

    def test_health_check_no_community(self):
        checker = HealthChecker(community_path=None)
        results = checker.scan_all_health()
        assert results == []

    def test_health_check_empty_community(self):
        with tempfile.TemporaryDirectory() as tmp:
            community = Path(tmp) / "Community"
            community.mkdir()
            checker = HealthChecker(community)
            results = checker.scan_all_health()
            assert results == []

    def test_take_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = AircraftPackage(
                package_path=Path(tmp) / "test",
                aircraft_type=AircraftType.PMDG_737_800,
                title_prefix="PMDG 737-800",
                detected_version_major=3,
                detected_version_minor=0,
                hgs_integrated=True,
                integration_status=IntegrationStatus.INSTALLED,
            )
            checker = HealthChecker(Path(tmp))
            checker.take_snapshot(pkg)

            assert pkg.package_path.name in checker.state.aircraft_snapshots
            snapshot = checker.state.aircraft_snapshots[pkg.package_path.name]
            assert snapshot["version_major"] == 3
            assert snapshot["hgs_integrated"] is True

    def test_detect_version_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            community = Path(tmp) / "Community"
            community.mkdir()

            pkg = AircraftPackage(
                package_path=community / "test",
                aircraft_type=AircraftType.PMDG_737_800,
                title_prefix="PMDG 737-800",
                detected_version_major=3,
                detected_version_minor=0,
            )

            checker = HealthChecker(community)
            # Take snapshot with version 3.0
            checker.take_snapshot(pkg)

            # Change version and check health
            pkg.detected_version_major = 4
            pkg.detected_version_minor = 0
            health = checker.check_health(pkg)

            assert health.needs_repair  # Version changed
            assert len(health.issues) > 0

    def test_needs_repair_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            community = Path(tmp) / "Community"
            community.mkdir()

            checker = HealthChecker(community)
            result = checker.get_aircraft_needing_repair()
            assert isinstance(result, list)


class TestSelfHealer:
    """Test self-healer functionality."""

    def test_healer_init(self):
        healer = SelfHealer()
        assert healer is not None
        assert healer.repair_count == 0

    def test_healer_no_community(self):
        healer = SelfHealer()
        results = healer.repair_all()
        assert results == {}

    def test_repair_history(self):
        healer = SelfHealer()
        history = healer.get_repair_history()
        assert isinstance(history, list)
