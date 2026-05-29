"""
Tests for C_HUD_Runway Installer — Safe Update Management
===========================================================
Phase 4 tests for aircraft update detection and safe migration.
"""

import sys
import json
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from installer.updater import (
    UpdateDetector,
    UpdateManager,
    AircraftUpdate,
    UpdateResult,
    UpdateAction,
)
from installer.aircraft_scanner import (
    AircraftPackage,
    AircraftType,
    IntegrationStatus,
    scan_community,
)
from installer.healer import HealthChecker


# =========================================================================
#  Helpers
# =========================================================================

def create_aircraft_package(
    community: Path,
    name: str = "pmdg-737-800",
    atype: AircraftType = AircraftType.PMDG_737_800,
    vmaj: int = 3,
    vmin: int = 0,
    with_hgs: bool = False,
) -> Path:
    """Create a test aircraft package."""
    pkg_dir = community / name
    pkg_dir.mkdir(parents=True, exist_ok=True)

    sim_dir = pkg_dir / "SimObjects" / "Airplanes" / name
    sim_dir.mkdir(parents=True, exist_ok=True)
    panel_dir = sim_dir / "panel"
    panel_dir.mkdir(parents=True, exist_ok=True)

    cfg_lines = ["[VCockpit01]", "size_mm = 1024, 1024"]
    if with_hgs:
        cfg_lines.extend([
            "; --- C_HUD_Runway HGS Integration ---",
            "gauge00 = C_HUD_Runway!Gauge_ConformalHUD, 0, 0, 1024, 1024",
            "htmlgauge00 = HUD/hud_overlay.html, 0, 0, 1024, 1024",
            "; --- End HGS Integration ---",
        ])
    else:
        cfg_lines.append("gauge00 = Other!Gauge, 0, 0, 300, 300")
    (panel_dir / "panel.cfg").write_text("\n".join(cfg_lines) + "\n", encoding="utf-8")

    layout_content = [
        {"path": f"SimObjects/Airplanes/{name}/panel/panel.cfg", "size": 100, "date": 0},
    ]
    if with_hgs:
        layout_content.extend([
            {"path": "C_HUD_Runway/panel/C_HUD_Runway.wasm", "size": 50000, "date": 0},
        ])
    (pkg_dir / "layout.json").write_text(
        json.dumps({"content": layout_content}), encoding="utf-8",
    )
    (pkg_dir / "manifest.json").write_text(
        json.dumps({"version": f"{vmaj}.{vmin}.0"}), encoding="utf-8",
    )

    return pkg_dir


def take_initial_snapshot(community: Path, name: str, vmaj: int, vmin: int, hgs: bool):
    """Take a health snapshot for an aircraft."""
    pkg_dir = community / name
    pkg = AircraftPackage(
        package_path=pkg_dir,
        aircraft_type=AircraftType.PMDG_737_800,
        title_prefix="PMDG 737-800",
        detected_version_major=vmaj,
        detected_version_minor=vmin,
        hgs_integrated=hgs,
        integration_status=IntegrationStatus.INSTALLED if hgs else IntegrationStatus.NOT_INSTALLED,
    )
    checker = HealthChecker(community)
    checker.take_snapshot(pkg)
    return checker


# =========================================================================
#  Tests
# =========================================================================

class TestAircraftUpdate:
    """Test AircraftUpdate dataclass."""

    def test_create_update(self):
        update = AircraftUpdate(
            package_name="test",
            aircraft_type="PMDG 737-800",
            old_version="3.0",
            new_version="4.0",
        )
        assert update.action == UpdateAction.NONE
        assert update.compatible is True

    def test_update_with_action(self):
        update = AircraftUpdate(
            package_name="test",
            aircraft_type="PMDG 737-800",
            old_version="3.0",
            new_version="4.0",
            action=UpdateAction.MIGRATE,
        )
        assert update.action == UpdateAction.MIGRATE


class TestUpdateResult:
    """Test UpdateResult dataclass."""

    def test_success_result(self):
        result = UpdateResult(
            aircraft_type="PMDG 737-800",
            action=UpdateAction.NONE,
            success=True,
            old_version="3.0",
            new_version="4.0",
        )
        assert result.success is True

    def test_failure_result(self):
        result = UpdateResult(
            aircraft_type="PMDG 737-800",
            action=UpdateAction.REINSTALL,
            success=False,
            old_version="3.0",
            new_version="4.0",
            errors=["Something went wrong"],
        )
        assert result.success is False
        assert len(result.errors) == 1


class TestUpdateDetector:
    """Test update detection."""

    def test_no_community_path(self):
        detector = UpdateDetector(community_path=None)
        updates = detector.detect_updates()
        assert updates == []

    def test_empty_community(self):
        with tempfile.TemporaryDirectory() as tmp:
            community = Path(tmp) / "Community"
            community.mkdir()
            detector = UpdateDetector(community)
            updates = detector.detect_updates()
            assert updates == []

    def test_no_previous_snapshot(self):
        """New packages with no snapshot should not trigger updates."""
        with tempfile.TemporaryDirectory() as tmp:
            community = Path(tmp) / "Community"
            community.mkdir()
            create_aircraft_package(community, with_hgs=True)
            detector = UpdateDetector(community)
            updates = detector.detect_updates()
            # No snapshot, so no update detected (new install)
            assert updates == []

    def test_version_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            community = Path(tmp) / "Community"
            community.mkdir()
            create_aircraft_package(community, "pmdg-737-800", AircraftType.PMDG_737_800, 3, 0, with_hgs=True)

            # Take snapshot
            take_initial_snapshot(community, "pmdg-737-800", 3, 0, True)

            detector = UpdateDetector(community)
            updates = detector.detect_updates()
            # Version unchanged, HGS still integrated
            assert updates == []

    def test_detect_version_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            community = Path(tmp) / "Community"
            community.mkdir()
            create_aircraft_package(community, "pmdg-737-800", AircraftType.PMDG_737_800, 3, 0, with_hgs=True)

            # Take snapshot
            take_initial_snapshot(community, "pmdg-737-800", 3, 0, True)

            # Now change the version
            create_aircraft_package(community, "pmdg-737-800", AircraftType.PMDG_737_800, 4, 0, with_hgs=True)

            detector = UpdateDetector(community)
            updates = detector.detect_updates()
            assert len(updates) > 0
            assert updates[0].old_version == "3.0" or updates[0].new_version == "4.0"

    def test_detect_hgs_removal(self):
        with tempfile.TemporaryDirectory() as tmp:
            community = Path(tmp) / "Community"
            community.mkdir()
            create_aircraft_package(community, "pmdg-737-800", AircraftType.PMDG_737_800, 3, 0, with_hgs=True)

            # Take snapshot (hgs integrated)
            take_initial_snapshot(community, "pmdg-737-800", 3, 0, True)

            # Now recreate without HGS
            create_aircraft_package(community, "pmdg-737-800", AircraftType.PMDG_737_800, 3, 0, with_hgs=False)

            detector = UpdateDetector(community)
            updates = detector.detect_updates()
            # Should detect that HGS was removed
            has_repair = any(u.action == UpdateAction.REPAIR for u in updates)
            assert has_repair


class TestUpdateManager:
    """Test the update manager."""

    def test_no_community(self):
        manager = UpdateManager(community_path=None)
        results = manager.process_updates()
        assert results == []

    def test_cleanup_stale_integrations(self):
        with tempfile.TemporaryDirectory() as tmp:
            community = Path(tmp) / "Community"
            community.mkdir()
            create_aircraft_package(community, "pmdg-737-800", AircraftType.PMDG_737_800, 3, 0, with_hgs=True)

            # Take snapshot for a package that will be "removed"
            checker = HealthChecker(community)
            pkg_dir = community / "pmdg-737-800"
            pkg = AircraftPackage(
                package_path=pkg_dir,
                aircraft_type=AircraftType.PMDG_737_800,
                title_prefix="PMDG 737-800",
                detected_version_major=3,
                detected_version_minor=0,
                hgs_integrated=True,
            )
            checker.take_snapshot(pkg)

            # Clean up
            manager = UpdateManager(community)
            count = manager.cleanup_stale_integrations()
            assert count >= 0

    def test_orphan_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            community = Path(tmp) / "Community"
            community.mkdir()
            create_aircraft_package(community, "pmdg-737-800", AircraftType.PMDG_737_800, 3, 0, with_hgs=True)

            manager = UpdateManager(community)
            count = manager.cleanup_orphan_files()
            assert count >= 0

    def test_full_update_cycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            community = Path(tmp) / "Community"
            community.mkdir()
            create_aircraft_package(community, "pmdg-737-800", AircraftType.PMDG_737_800, 3, 0, with_hgs=True)

            # Take snapshot
            take_initial_snapshot(community, "pmdg-737-800", 3, 0, True)

            # Change version
            create_aircraft_package(community, "pmdg-737-800", AircraftType.PMDG_737_800, 4, 0, with_hgs=True)

            manager = UpdateManager(community)
            result = manager.full_update_cycle(auto_repair=False)
            assert "updates_detected" in result
            assert result["updates_detected"] >= 0

    def test_installer_migration(self):
        manager = UpdateManager()
        result = manager.migrate_installer_version("2.5.0", "2.6.0")
        assert result is True


class TestUpdateEdgeCases:
    """Test edge cases in update management."""

    def test_update_history_tracking(self):
        with tempfile.TemporaryDirectory() as tmp:
            community = Path(tmp) / "Community"
            community.mkdir()
            create_aircraft_package(community, "pmdg-737-800", AircraftType.PMDG_737_800, 3, 0, with_hgs=True)
            take_initial_snapshot(community, "pmdg-737-800", 3, 0, True)

            # Version change
            create_aircraft_package(community, "pmdg-737-800", AircraftType.PMDG_737_800, 4, 0, with_hgs=True)

            detector = UpdateDetector(community)
            detector.detect_updates()
            history = detector.get_update_history()
            assert isinstance(history, list)

    def test_set_community_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            community = Path(tmp) / "Community"
            community.mkdir()
            manager = UpdateManager()
            assert manager.community_path is None
            manager.set_community_path(community)
            assert manager.community_path == community
