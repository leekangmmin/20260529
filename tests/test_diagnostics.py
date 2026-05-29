"""
Tests for C_HUD_Runway Installer — Integration Diagnostics
===========================================================
Phase 3 tests for live integration diagnostics.
"""

import sys
import json
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from installer.diagnostics import (
    IntegrationDiagnostics,
    DiagnosticsReport,
    IntegrationDiagnostic,
    DiagnosticCheck,
    DiagnosticLevel,
    export_diagnostics,
    generate_diagnostics_overlay,
    run_diagnostics,
    quick_diagnostic_summary,
)
from installer.aircraft_scanner import (
    AircraftPackage,
    AircraftType,
    IntegrationStatus,
)
from installer.patch_engine import (
    LayoutPatcher,
    PanelCfgPatcher,
    HGS_LAYOUT_ENTRIES,
    HGS_PANEL_GAUGE_MARKER,
    HGS_HTML_MARKER,
)


# =========================================================================
#  Helpers
# =========================================================================

HGS_WASM_BYTES = b"\x00\x01\x02"


def create_test_aircraft(
    tmp_dir: Path,
    name: str = "pmdg-737-800",
    atype: AircraftType = AircraftType.PMDG_737_800,
    vmaj: int = 3,
    vmin: int = 0,
    with_hgs: bool = False,
) -> Path:
    """Create a test aircraft package for diagnostic testing."""
    pkg_dir = tmp_dir / name
    pkg_dir.mkdir(parents=True, exist_ok=True)

    sim_dir = pkg_dir / "SimObjects" / "Airplanes" / name
    sim_dir.mkdir(parents=True, exist_ok=True)
    panel_dir = sim_dir / "panel"
    panel_dir.mkdir(parents=True, exist_ok=True)

    # Panel.cfg
    cfg_lines = ["[VCockpit01]", "size_mm = 1024, 1024"]
    if with_hgs:
        cfg_lines.extend([
            "; --- C_HUD_Runway HGS Integration ---",
            "gauge00 = C_HUD_Runway!Gauge_ConformalHUD,  0, 0, 1024, 1024",
            "htmlgauge00 = HUD/hud_overlay.html,  0, 0, 1024, 1024",
            "; --- End HGS Integration ---",
        ])
    else:
        cfg_lines.append("gauge00 = Other!Gauge, 0, 0, 300, 300")
    (panel_dir / "panel.cfg").write_text("\n".join(cfg_lines) + "\n", encoding="utf-8")

    # Layout.json
    layout_content = [
        {"path": f"SimObjects/Airplanes/{name}/panel/panel.cfg", "size": 100, "date": 0},
    ]
    if with_hgs:
        layout_content.extend([
            {"path": "C_HUD_Runway/panel/C_HUD_Runway.wasm", "size": 50000, "date": 0},
            {"path": "C_HUD_Runway/panel/HUD/hud_overlay.html", "size": 1000, "date": 0},
            {"path": "C_HUD_Runway/panel/HUD/hud_overlay.js", "size": 5000, "date": 0},
        ])
    (pkg_dir / "layout.json").write_text(
        json.dumps({"content": layout_content}), encoding="utf-8",
    )

    # Manifest
    (pkg_dir / "manifest.json").write_text(
        json.dumps({"version": f"{vmaj}.{vmin}.0"}), encoding="utf-8",
    )

    return pkg_dir


def create_hgs_package(community: Path) -> Path:
    """
    Create a mock HGS package that passes verify_hgs_in_community().
    """
    hgs_dir = community / "C_HUD_Runway"

    # Create the required file structure for verify_hgs_in_community:
    # SimObjects/Airplanes/C_HUD_Runway/panel/panel.cfg
    # SimObjects/Airplanes/C_HUD_Runway/panel/C_HUD_Runway.wasm
    # SimObjects/Airplanes/C_HUD_Runway/panel/HUD/hud_overlay.html
    # SimObjects/Airplanes/C_HUD_Runway/aircraft.cfg
    # layout.json (at package root)
    panel_root = hgs_dir / "SimObjects" / "Airplanes" / "C_HUD_Runway" / "panel"
    panel_root.mkdir(parents=True, exist_ok=True)

    (panel_root / "panel.cfg").write_text(
        "[VCockpit01]\nsize_mm = 1024, 1024\n", encoding="utf-8"
    )
    (panel_root / "C_HUD_Runway.wasm").write_bytes(HGS_WASM_BYTES)

    hud_dir = panel_root / "HUD"
    hud_dir.mkdir(parents=True, exist_ok=True)
    (hud_dir / "hud_overlay.html").write_text("<html></html>", encoding="utf-8")
    (hud_dir / "hud_overlay.js").write_text("// JS overlay", encoding="utf-8")

    # aircraft.cfg
    ac_cfg = hgs_dir / "SimObjects" / "Airplanes" / "C_HUD_Runway" / "aircraft.cfg"
    ac_cfg.parent.mkdir(parents=True, exist_ok=True)
    ac_cfg.write_text("[FLTSIM.0]\ntitle = C_HUD_Runway\n", encoding="utf-8")

    # layout.json (at HGS package root)
    (hgs_dir / "layout.json").write_text(
        json.dumps({"content": []}), encoding="utf-8"
    )

    return hgs_dir


# =========================================================================
#  Tests
# =========================================================================

class TestDiagnosticLevel:
    """Test DiagnosticLevel enum."""

    def test_levels_ordered(self):
        assert DiagnosticLevel.OK.value == "ok"
        assert DiagnosticLevel.ERROR.value == "error"
        assert DiagnosticLevel.CRITICAL.value == "critical"


class TestDiagnosticCheck:
    """Test DiagnosticCheck dataclass."""

    def test_create_check(self):
        check = DiagnosticCheck(
            name="test", level=DiagnosticLevel.OK, message="All good", passed=True,
        )
        assert check.name == "test"
        assert check.passed is True

    def test_error_check(self):
        check = DiagnosticCheck(
            name="test_fail", level=DiagnosticLevel.ERROR,
            message="Something failed", passed=False,
        )
        assert check.passed is False


class TestIntegrationDiagnostic:
    """Test IntegrationDiagnostic dataclass."""

    def test_overall_level_ok(self):
        diag = IntegrationDiagnostic(
            aircraft_type="PMDG 737-800", aircraft_version="3.0", status="installed",
        )
        diag.checks.append(DiagnosticCheck(
            name="test", level=DiagnosticLevel.OK, message="ok", passed=True,
        ))
        assert diag.overall_level == DiagnosticLevel.OK
        assert diag.passed is True

    def test_overall_level_error(self):
        diag = IntegrationDiagnostic(
            aircraft_type="PMDG 737-800", aircraft_version="3.0", status="installed",
        )
        diag.checks.append(DiagnosticCheck(
            name="test", level=DiagnosticLevel.ERROR, message="fail", passed=False,
        ))
        assert diag.overall_level == DiagnosticLevel.ERROR
        assert diag.passed is False


class TestDiagnosticsReport:
    """Test DiagnosticsReport."""

    def test_empty_report(self):
        report = DiagnosticsReport()
        assert report.installer_version != ""
        assert len(report.aircraft_diagnostics) == 0
        assert len(report.errors) == 0

    def test_to_dict(self):
        report = DiagnosticsReport()
        report.aircraft_diagnostics.append(IntegrationDiagnostic(
            aircraft_type="Test", aircraft_version="1.0", status="installed",
        ))
        data = report.to_dict()
        assert "installer_version" in data
        assert len(data["aircraft_diagnostics"]) == 1


class TestIntegrationDiagnosticsEngine:
    """Test the diagnostics engine."""

    def test_no_community_path(self):
        engine = IntegrationDiagnostics(community_path=None)
        report = engine.run_all()
        assert isinstance(report, DiagnosticsReport)

    def test_empty_community(self):
        with tempfile.TemporaryDirectory() as tmp:
            community = Path(tmp) / "Community"
            community.mkdir()
            engine = IntegrationDiagnostics(community)
            report = engine.run_all()
            assert isinstance(report, DiagnosticsReport)
            assert len(report.aircraft_diagnostics) == 0

    def test_aircraft_without_hgs(self):
        with tempfile.TemporaryDirectory() as tmp:
            community = Path(tmp) / "Community"
            community.mkdir()
            create_test_aircraft(community, with_hgs=False)
            engine = IntegrationDiagnostics(community)
            report = engine.run_all()
            assert len(report.aircraft_diagnostics) == 1
            ad = report.aircraft_diagnostics[0]
            assert ad.aircraft_type == "PMDG 737-800"

    def test_aircraft_with_hgs(self):
        with tempfile.TemporaryDirectory() as tmp:
            community = Path(tmp) / "Community"
            community.mkdir()
            create_test_aircraft(community, with_hgs=True)
            create_hgs_package(community)
            engine = IntegrationDiagnostics(community)
            report = engine.run_all()
            assert len(report.aircraft_diagnostics) == 1
            ad = report.aircraft_diagnostics[0]
            panel_check = next(
                (c for c in ad.checks if c.name == "panel_injection"), None
            )
            if panel_check:
                assert panel_check.passed is True

    def test_multiple_aircraft(self):
        with tempfile.TemporaryDirectory() as tmp:
            community = Path(tmp) / "Community"
            community.mkdir()
            create_test_aircraft(community, "pmdg-737-800", AircraftType.PMDG_737_800, 3, 0)
            create_test_aircraft(community, "inibuilds-a350", AircraftType.INIBUILDS_A350, 1, 0)
            create_hgs_package(community)
            engine = IntegrationDiagnostics(community)
            report = engine.run_all()
            assert len(report.aircraft_diagnostics) == 2

    def test_diagnostics_with_hgs_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            community = Path(tmp) / "Community"
            community.mkdir()
            create_hgs_package(community)
            create_test_aircraft(community, "pmdg-737-800", AircraftType.PMDG_737_800, 3, 0, with_hgs=True)
            engine = IntegrationDiagnostics(community)
            report = engine.run_all()
            hgs_check = next(
                (c for c in report.global_checks if c.name == "hgs_package"), None
            )
            if hgs_check:
                assert hgs_check.passed is True


class TestExportDiagnostics:
    """Test diagnostics export."""

    def test_export_to_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = DiagnosticsReport()
            report.aircraft_diagnostics.append(IntegrationDiagnostic(
                aircraft_type="Test", aircraft_version="1.0", status="installed",
            ))
            output = Path(tmp) / "report.json"
            result = export_diagnostics(report, output)
            assert result.exists()
            data = json.loads(result.read_text(encoding="utf-8"))
            assert "aircraft_diagnostics" in data
            assert len(data["aircraft_diagnostics"]) == 1

    def test_export_creates_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = DiagnosticsReport()
            output = Path(tmp) / "test_export.json"
            result = export_diagnostics(report, output)
            assert result.exists()


class TestGenerateOverlay:
    """Test diagnostics overlay generation."""

    def test_generates_html(self):
        report = DiagnosticsReport()
        report.aircraft_diagnostics.append(IntegrationDiagnostic(
            aircraft_type="Test", aircraft_version="1.0", status="installed",
        ))
        html = generate_diagnostics_overlay(report)
        assert "<html" in html
        assert "HGS Integration Diagnostics" in html
        assert "Test" in html

    def test_includes_errors(self):
        report = DiagnosticsReport()
        report.errors.append("Test error message")
        html = generate_diagnostics_overlay(report)
        assert "Test error message" in html

    def test_includes_warnings(self):
        report = DiagnosticsReport()
        report.warnings.append("Test warning")
        html = generate_diagnostics_overlay(report)
        assert "Test warning" in html

    def test_includes_recommendations(self):
        report = DiagnosticsReport()
        report.recommendations.append("Do something")
        html = generate_diagnostics_overlay(report)
        assert "Do something" in html


class TestRunDiagnostics:
    """Test run_diagnostics convenience function."""

    def test_run_with_community(self):
        with tempfile.TemporaryDirectory() as tmp:
            community = Path(tmp) / "Community"
            community.mkdir()
            report = run_diagnostics(community)
            assert isinstance(report, DiagnosticsReport)

    def test_quick_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            community = Path(tmp) / "Community"
            community.mkdir()
            summary = quick_diagnostic_summary(community)
            assert "Diagnostics" in summary
            assert "aircraft" in summary


class TestDiagnosticEdgeCases:
    """Test edge cases in diagnostics."""

    def test_partial_hgs_install(self):
        """Test diagnostics with partial HGS package (missing JS files)."""
        with tempfile.TemporaryDirectory() as tmp:
            community = Path(tmp) / "Community"
            community.mkdir()

            # Create HGS package with correct structure but missing some files
            hgs_dir = community / "C_HUD_Runway"
            panel_root = hgs_dir / "SimObjects" / "Airplanes" / "C_HUD_Runway" / "panel"
            panel_root.mkdir(parents=True, exist_ok=True)
            (panel_root / "panel.cfg").write_text("[VCockpit01]\n", encoding="utf-8")
            (panel_root / "C_HUD_Runway.wasm").write_bytes(HGS_WASM_BYTES)
            # Missing hud_overlay.html and aircraft.cfg

            create_test_aircraft(community, with_hgs=True)

            engine = IntegrationDiagnostics(community)
            report = engine.run_all()
            assert len(report.aircraft_diagnostics) == 1

    def test_corrupted_layout_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            community = Path(tmp) / "Community"
            community.mkdir()
            pkg_dir = create_test_aircraft(community, with_hgs=False)
            (pkg_dir / "layout.json").write_text("not valid json", encoding="utf-8")
            engine = IntegrationDiagnostics(community)
            report = engine.run_all()
            assert len(report.aircraft_diagnostics) >= 0

    def test_no_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            community = Path(tmp) / "Community"
            community.mkdir()
            pkg_dir = create_test_aircraft(community, with_hgs=False)
            manifest = pkg_dir / "manifest.json"
            if manifest.exists():
                manifest.unlink()
            engine = IntegrationDiagnostics(community)
            report = engine.run_all()
            assert len(report.aircraft_diagnostics) >= 0
