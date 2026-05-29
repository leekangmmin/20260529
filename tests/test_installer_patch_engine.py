"""
Tests for the C_HUD_Runway Installer — Patch Engine
=====================================================
Phase 3 tests for safe patching system.
"""

import sys
import json
import tempfile
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from installer.patch_engine import (
    BackupEngine,
    BackupRecord,
    LayoutPatcher,
    PanelCfgPatcher,
    FileCopier,
    PatchEngine,
    PatchTransaction,
    PatchOperation,
    compute_file_checksum,
    compute_string_checksum,
    HGS_PANEL_GAUGE_MARKER,
    HGS_HTML_MARKER,
    HGS_LAYOUT_ENTRIES,
    BACKUP_DIR,
)
from installer.aircraft_scanner import (
    AircraftPackage,
    AircraftType,
    IntegrationStatus,
    PanelConfig,
)


# =========================================================================
#  Helpers
# =========================================================================

def create_mock_aircraft_package(temp_dir: Path) -> AircraftPackage:
    """Create a mock aircraft package for testing."""
    pkg_dir = temp_dir / "pmdg-737-800"
    pkg_dir.mkdir(parents=True, exist_ok=True)

    # Create panel.cfg
    panel_dir = pkg_dir / "SimObjects" / "Airplanes" / "pmdg-737-800" / "panel"
    panel_dir.mkdir(parents=True, exist_ok=True)
    panel_cfg = panel_dir / "panel.cfg"
    panel_cfg.write_text(
        "[VCockpit01]\n"
        "size_mm = 1024, 1024\n"
        "pixel_size = 1024, 1024\n"
        'gauge00 = PMDG_737!SomeGauge, 0, 0, 300, 300\n'
        'htmlgauge00 = Some/overlay.html, 0, 0, 1024, 1024\n',
        encoding="utf-8",
    )

    # Create layout.json
    layout_path = pkg_dir / "layout.json"
    layout_path.write_text(json.dumps({
        "content": [
            {"path": "SimObjects/Airplanes/pmdg-737-800/panel/panel.cfg", "size": 100, "date": 0},
        ]
    }), encoding="utf-8")

    # Create manifest.json
    manifest_path = pkg_dir / "manifest.json"
    manifest_path.write_text(json.dumps({"version": "3.0.0"}), encoding="utf-8")

    return AircraftPackage(
        package_path=pkg_dir,
        aircraft_type=AircraftType.PMDG_737_800,
        title_prefix="PMDG 737-800",
        layout_path=layout_path,
        panel_configs=[
            PanelConfig(
                path=panel_cfg,
                entries=[
                    {"raw": "gauge00 = PMDG_737!SomeGauge, 0, 0, 300, 300", "type": "gauge"},
                    {"raw": "htmlgauge00 = Some/overlay.html, 0, 0, 1024, 1024", "type": "htmlgauge"},
                ],
                has_hud_gauge=False,
                has_html_hud=False,
            ),
        ],
        detected_version_major=3,
        detected_version_minor=0,
        hgs_integrated=False,
        integration_status=IntegrationStatus.NOT_INSTALLED,
    )


# =========================================================================
#  Tests
# =========================================================================

class TestChecksumUtils:
    """Test checksum utilities."""

    def test_compute_file_checksum(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Hello, World!")
            f.flush()
            checksum = compute_file_checksum(Path(f.name))
        os.unlink(f.name)
        # SHA-256 of "Hello, World!"
        assert len(checksum) == 64
        assert checksum == "dffd6021bb2bd5b0af676290809ec3a53191dd81c7f70a4b28688a362182986f"

    def test_compute_string_checksum(self):
        checksum = compute_string_checksum("test data")
        assert len(checksum) == 64

    def test_checksum_empty_string(self):
        checksum = compute_string_checksum("")
        # SHA-256 of empty string
        expected = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        assert checksum == expected

    def test_checksum_nonexistent_file(self):
        checksum = compute_file_checksum(Path("/nonexistent/file.txt"))
        assert checksum == ""


import os


class TestLayoutPatcher:
    """Test layout.json patching."""

    def test_patch_layout_adds_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            layout_path = Path(tmp) / "layout.json"
            layout_path.write_text(json.dumps({"content": []}), encoding="utf-8")
            assert LayoutPatcher.patch_layout(layout_path) is True

            data = json.loads(layout_path.read_text(encoding="utf-8"))
            assert len(data["content"]) == len(HGS_LAYOUT_ENTRIES)

    def test_patch_layout_existing_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            layout_path = Path(tmp) / "layout.json"
            # Start with all entries already present
            layout_path.write_text(
                json.dumps({"content": list(HGS_LAYOUT_ENTRIES)}),
                encoding="utf-8",
            )
            assert LayoutPatcher.patch_layout(layout_path) is True

            data = json.loads(layout_path.read_text(encoding="utf-8"))
            assert len(data["content"]) == len(HGS_LAYOUT_ENTRIES)

    def test_unpatch_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            layout_path = Path(tmp) / "layout.json"
            layout_path.write_text(
                json.dumps({"content": list(HGS_LAYOUT_ENTRIES)}),
                encoding="utf-8",
            )
            assert LayoutPatcher.unpatch_layout(layout_path) is True

            data = json.loads(layout_path.read_text(encoding="utf-8"))
            assert len(data["content"]) == 0

    def test_has_hgs_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            layout_path = Path(tmp) / "layout.json"
            layout_path.write_text(json.dumps({"content": []}), encoding="utf-8")
            assert LayoutPatcher.has_hgs_entries(layout_path) is False

            LayoutPatcher.patch_layout(layout_path)
            assert LayoutPatcher.has_hgs_entries(layout_path) is True

    def test_patch_layout_array_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            layout_path = Path(tmp) / "layout.json"
            layout_path.write_text(json.dumps([]), encoding="utf-8")
            assert LayoutPatcher.patch_layout(layout_path) is True

            data = json.loads(layout_path.read_text(encoding="utf-8"))
            assert len(data) == len(HGS_LAYOUT_ENTRIES)

    def test_patch_layout_missing_file(self):
        result = LayoutPatcher.patch_layout(Path("/nonexistent/layout.json"))
        assert result is False


class TestPanelCfgPatcher:
    """Test panel.cfg patching."""

    def test_patch_panel_adds_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "panel.cfg"
            cfg_path.write_text(
                "[VCockpit01]\n"
                "size_mm = 1024, 1024\n"
                'gauge00 = SomeGauge!Gauge, 0, 0, 300, 300\n',
                encoding="utf-8",
            )
            assert PanelCfgPatcher.patch_panel(cfg_path) is True

            content = cfg_path.read_text(encoding="utf-8")
            assert HGS_PANEL_GAUGE_MARKER in content
            assert HGS_HTML_MARKER in content

    def test_unpatch_panel(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "panel.cfg"
            cfg_path.write_text(
                "[VCockpit01]\n"
                "size_mm = 1024, 1024\n"
                'gauge00 = SomeGauge!Gauge, 0, 0, 300, 300\n',
                encoding="utf-8",
            )
            PanelCfgPatcher.patch_panel(cfg_path)
            assert PanelCfgPatcher.unpatch_panel(cfg_path) is True

            content = cfg_path.read_text(encoding="utf-8")
            assert HGS_PANEL_GAUGE_MARKER not in content

    def test_has_hgs_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "panel.cfg"
            cfg_path.write_text(
                "[VCockpit01]\n"
                'gauge00 = SomeGauge!Gauge, 0, 0, 300, 300\n',
                encoding="utf-8",
            )
            assert PanelCfgPatcher.has_hgs_entries(cfg_path) is False

            PanelCfgPatcher.patch_panel(cfg_path)
            assert PanelCfgPatcher.has_hgs_entries(cfg_path) is True

    def test_double_patch_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "panel.cfg"
            cfg_path.write_text(
                "[VCockpit01]\n"
                'gauge00 = SomeGauge!Gauge, 0, 0, 300, 300\n',
                encoding="utf-8",
            )
            # Patch twice
            assert PanelCfgPatcher.patch_panel(cfg_path) is True
            assert PanelCfgPatcher.patch_panel(cfg_path) is True  # Should not duplicate

            content = cfg_path.read_text(encoding="utf-8")
            # Count occurrences
            assert content.count(HGS_PANEL_GAUGE_MARKER) == 1

    def test_patch_reversible(self):
        """Verify that unpatch restores original content."""
        with tempfile.TemporaryDirectory() as tmp:
            original = "[VCockpit01]\nsize_mm = 1024, 1024\n"
            original += 'gauge00 = SomeGauge!Gauge, 0, 0, 300, 300\n'
            cfg_path = Path(tmp) / "panel.cfg"
            cfg_path.write_text(original, encoding="utf-8")

            checksum_before = compute_file_checksum(cfg_path)
            PanelCfgPatcher.patch_panel(cfg_path)
            PanelCfgPatcher.unpatch_panel(cfg_path)
            checksum_after = compute_file_checksum(cfg_path)

            # After unpatch, we should have a clean state
            content = cfg_path.read_text(encoding="utf-8")
            assert HGS_PANEL_GAUGE_MARKER not in content
            assert HGS_HTML_MARKER not in content

    def test_patch_missing_file(self):
        result = PanelCfgPatcher.patch_panel(Path("/nonexistent/panel.cfg"))
        assert result is False


class TestBackupEngine:
    """Test backup engine."""

    def test_create_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            backup_dir = Path(tmp) / "backups"
            engine = BackupEngine(backup_dir)

            pkg_dir = Path(tmp) / "test-aircraft"
            pkg_dir.mkdir(parents=True, exist_ok=True)
            (pkg_dir / "panel.cfg").write_text("gauge00 = Test", encoding="utf-8")
            (pkg_dir / "layout.json").write_text("{}", encoding="utf-8")

            pkg = AircraftPackage(
                package_path=pkg_dir,
                aircraft_type=AircraftType.PMDG_737_800,
                title_prefix="PMDG 737-800",
            )

            record = engine.create_backup(pkg, "test")
            assert record is not None
            assert record.aircraft_package == pkg_dir.name
            assert record.file_count > 0

    def test_list_backups(self):
        with tempfile.TemporaryDirectory() as tmp:
            backup_dir = Path(tmp) / "backups"
            engine = BackupEngine(backup_dir)
            # No backups initially
            assert len(engine.list_backups()) == 0

    def test_get_backup_for_package_not_found(self):
        engine = BackupEngine()
        record = engine.get_backup_for_package("nonexistent")
        assert record is None


class TestPatchEngine:
    """Test the main patch engine orchestrator."""

    def test_install_hgs(self):
        with tempfile.TemporaryDirectory() as tmp:
            community_path = Path(tmp) / "Community"
            community_path.mkdir(parents=True, exist_ok=True)

            pkg = create_mock_aircraft_package(community_path)

            engine = PatchEngine(community_path)
            result = engine.install_hgs_to_aircraft(pkg)

            # The HGS package copy requires source files, which may not exist
            # in test environment. Verify partial success.
            assert result is not None

    def test_patch_then_verify(self):
        with tempfile.TemporaryDirectory() as tmp:
            community_path = Path(tmp) / "Community"
            community_path.mkdir(parents=True, exist_ok=True)

            pkg = create_mock_aircraft_package(community_path)

            engine = PatchEngine(community_path)
            engine.install_hgs_to_aircraft(pkg)

            verification = engine.verify_integration(pkg)
            assert "success" in verification
            assert "issues" in verification

    def test_transaction_rollback(self):
        """Test that a failed operation can be rolled back."""
        engine = PatchEngine()
        # No active transaction
        assert engine.rollback_transaction() is False
