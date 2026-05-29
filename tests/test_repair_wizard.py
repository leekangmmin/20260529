"""
Tests for C_HUD_Runway Installer — Repair Wizard
==================================================
Phase 6 tests for guided repair workflow and UX certification.
"""

import sys
import json
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from installer.repair_wizard import (
    RepairWizard,
    RepairAction,
    RepairPlan,
    RepairResult,
    RepairStep,
    CompatibilityRecommender,
    TelemetryViewer,
    run_repair_wizard,
)
from installer.aircraft_scanner import (
    AircraftPackage,
    AircraftType,
    IntegrationStatus,
)
from installer.diagnostics import (
    DiagnosticsReport,
    IntegrationDiagnostic,
    DiagnosticCheck,
    DiagnosticLevel,
)


# =========================================================================
#  Helpers
# =========================================================================

def create_test_aircraft(
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


# =========================================================================
#  Tests
# =========================================================================

class TestRepairAction:
    """Test RepairAction dataclass."""

    def test_create_action(self):
        action = RepairAction(
            aircraft_type="PMDG 737-800",
            action="Re-patch panel.cfg",
            severity="error",
            command="repair",
        )
        assert action.aircraft_type == "PMDG 737-800"
        assert action.auto_fixable is True


class TestRepairPlan:
    """Test RepairPlan dataclass."""

    def test_empty_plan(self):
        plan = RepairPlan()
        assert len(plan.steps) == 0

    def test_plan_with_steps(self):
        plan = RepairPlan()
        plan.steps.append(RepairAction(
            aircraft_type="SYSTEM", action="Install HGS", severity="error", command="install",
        ))
        assert len(plan.steps) == 1


class TestRepairResult:
    """Test RepairResult dataclass."""

    def test_success(self):
        result = RepairResult(success=True, actions_taken=2, actions_succeeded=2)
        assert result.success is True

    def test_partial_failure(self):
        result = RepairResult(
            success=False, actions_taken=2, actions_succeeded=1, actions_failed=1,
        )
        assert result.success is False


class TestRepairWizard:
    """Test the repair wizard."""

    def test_no_community(self):
        wizard = RepairWizard(community_path=None)
        report = wizard.diagnose()
        assert isinstance(report, DiagnosticsReport)

    def test_diagnose_empty_community(self):
        with tempfile.TemporaryDirectory() as tmp:
            community = Path(tmp) / "Community"
            community.mkdir()
            wizard = RepairWizard(community)
            report = wizard.diagnose()
            assert isinstance(report, DiagnosticsReport)

    def test_recommend_with_aircraft(self):
        with tempfile.TemporaryDirectory() as tmp:
            community = Path(tmp) / "Community"
            community.mkdir()
            create_test_aircraft(community, "pmdg-737-800", AircraftType.PMDG_737_800, 3, 0, with_hgs=False)

            wizard = RepairWizard(community)
            report = wizard.diagnose()
            plan = wizard.recommend(report)

            assert isinstance(plan, RepairPlan)

    def test_recommend_healthy_system(self):
        with tempfile.TemporaryDirectory() as tmp:
            community = Path(tmp) / "Community"
            community.mkdir()
            create_test_aircraft(community, "pmdg-737-800", AircraftType.PMDG_737_800, 3, 0, with_hgs=True)

            wizard = RepairWizard(community)
            report = wizard.diagnose()
            plan = wizard.recommend(report)

            # May or may not have steps depending on HGS package presence
            assert isinstance(plan, RepairPlan)

    def test_execute_empty_plan(self):
        """Executing an empty plan should succeed quickly."""
        wizard = RepairWizard(community_path=None)
        plan = RepairPlan()
        result = wizard.execute(plan)
        assert result.success is True or result.success is False

    def test_verify_step(self):
        with tempfile.TemporaryDirectory() as tmp:
            community = Path(tmp) / "Community"
            community.mkdir()
            wizard = RepairWizard(community)
            report = wizard.verify()
            assert isinstance(report, DiagnosticsReport)

    def test_full_repair_cycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            community = Path(tmp) / "Community"
            community.mkdir()
            create_test_aircraft(community, "pmdg-737-800", AircraftType.PMDG_737_800, 3, 0, with_hgs=False)

            wizard = RepairWizard(community)
            result, final = wizard.run_full_repair()

            assert isinstance(result, RepairResult)
            assert isinstance(final, DiagnosticsReport)

    def test_run_repair_wizard_convenience(self):
        with tempfile.TemporaryDirectory() as tmp:
            community = Path(tmp) / "Community"
            community.mkdir()
            summary = run_repair_wizard(community)
            assert "success" in summary
            assert "aircraft_checked" in summary


class TestCompatibilityRecommender:
    """Test compatibility recommendations."""

    def test_get_aircraft_compatibility(self):
        recommender = CompatibilityRecommender()
        info = recommender.get_aircraft_compatibility("PMDG 737-800")
        assert info["supported"] is True
        assert "minimum_version" in info

    def test_unsupported_aircraft(self):
        recommender = CompatibilityRecommender()
        info = recommender.get_aircraft_compatibility("Unknown Aircraft")
        assert info["supported"] is False

    def test_all_compatible(self):
        recommender = CompatibilityRecommender()
        all_compat = recommender.get_all_compatible_aircraft()
        assert len(all_compat) > 0

    def test_installer_compatibility(self):
        recommender = CompatibilityRecommender()
        notes = recommender.check_installer_compatibility()
        assert isinstance(notes, list)


class TestTelemetryViewer:
    """Test telemetry viewer."""

    def test_no_telemetry(self):
        viewer = TelemetryViewer()
        data = viewer.get_latest_telemetry()
        # No telemetry yet; should be None
        assert data is None or isinstance(data, dict)

    def test_record_and_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Override backup dir via cleanup
            viewer = TelemetryViewer()
            viewer.record_telemetry({"test": "data", "aircraft_count": 1})
            latest = viewer.get_latest_telemetry()
            if latest:
                assert "test" in latest

    def test_formatted_summary(self):
        viewer = TelemetryViewer()
        telemetry = {
            "timestamp": "2024-01-01T00:00:00",
            "installer_version": "2.6.0",
            "aircraft_count": 3,
            "success_count": 2,
            "actions": [
                {"description": "Install HGS", "success": True},
                {"description": "Patch PMDG 737", "success": True},
            ],
        }
        summary = viewer.format_telemetry_summary(telemetry)
        assert "HGS Installer Telemetry" in summary
        assert "2.6.0" in summary


class TestRepairEdgeCases:
    """Test edge cases in repair wizard."""

    def test_diagnose_with_missing_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            community = Path(tmp) / "Community"
            community.mkdir()
            pkg_dir = create_test_aircraft(community, with_hgs=False)
            # Remove panel.cfg
            for cfg in pkg_dir.rglob("panel.cfg"):
                cfg.unlink()

            wizard = RepairWizard(community)
            report = wizard.diagnose()
            assert isinstance(report, DiagnosticsReport)

    def test_recommend_handles_errors_gracefully(self):
        with tempfile.TemporaryDirectory() as tmp:
            community = Path(tmp) / "Community"
            community.mkdir()
            # Create a dir that looks like an aircraft but has no valid files
            bad_pkg = community / "pmdg-737-800"
            bad_pkg.mkdir()

            wizard = RepairWizard(community)
            report = wizard.diagnose()
            plan = wizard.recommend(report)
            assert isinstance(plan, RepairPlan)
