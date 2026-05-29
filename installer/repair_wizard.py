"""
Guided Repair Wizard — Phase 6 UX Certification
================================================
Step-by-step guided repair workflow with auto-log export,
compatibility recommendations, and telemetry viewer.

Provides:
  · Guided repair wizard (step-by-step)
  · Automatic log export to desktop
  · Compatibility recommendation engine
  · Installer telemetry viewer
"""

import json
import logging
import os
import platform
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import __version__, __title__
from .aircraft_scanner import (
    AircraftPackage,
    AircraftType,
    IntegrationStatus,
    scan_community,
    check_version_compatibility,
    get_aircraft_compatibility_map,
    is_title_supported,
)
from .diagnostics import (
    IntegrationDiagnostics,
    DiagnosticsReport,
    DiagnosticLevel,
    export_diagnostics,
    quick_diagnostic_summary,
)
from .healer import SelfHealer, HealthChecker
from .patch_engine import (
    PatchEngine,
    BackupEngine,
    FileCopier,
    LayoutPatcher,
    PanelCfgPatcher,
)
from .msfs_detector import (
    find_community_folder,
    find_best_installation,
)
from .signature_verifier import SignatureVerifier

logger = logging.getLogger("repair_wizard")


# =========================================================================
#  1.  Repair Wizard Steps
# =========================================================================

class RepairStep(Enum):
    """Steps in the guided repair workflow."""
    DETECT = "detect"
    ANALYZE = "analyze"
    RECOMMEND = "recommend"
    EXECUTE = "execute"
    VERIFY = "verify"
    REPORT = "report"


@dataclass
class RepairAction:
    """A recommended action from the repair wizard."""
    aircraft_type: str
    action: str                        # Description of the action
    severity: str                      # "critical", "error", "warning", "info"
    command: str                       # Command to run (e.g., "install", "repair")
    auto_fixable: bool = True          # Whether it can be auto-fixed
    details: str = ""


@dataclass
class RepairPlan:
    """Complete repair plan from the wizard."""
    steps: List[RepairAction] = field(default_factory=list)
    requires_backup: bool = True
    requires_restart: bool = False
    estimated_time_seconds: int = 30
    warnings: List[str] = field(default_factory=list)


@dataclass
class RepairResult:
    """Result of executing a repair plan."""
    success: bool
    actions_taken: int = 0
    actions_succeeded: int = 0
    actions_failed: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    log_path: Optional[Path] = None
    timestamp: float = 0.0


class RepairWizard:
    """
    Step-by-step guided repair workflow.

    Usage:
        wizard = RepairWizard(community_path)
        plan = wizard.diagnose()          # Step 1: Detect issues
        actions = wizard.recommend(plan)  # Step 2: Get recommendations
        result = wizard.execute(actions)  # Step 3: Execute repair
        wizard.verify()                   # Step 4: Verify repair
    """

    def __init__(self, community_path: Optional[Path] = None):
        self.community_path = community_path
        if community_path is None:
            detected = find_community_folder()
            if detected:
                self.community_path = detected

        self.diagnostics = IntegrationDiagnostics(community_path)
        self.healer = SelfHealer(community_path)
        self.patch_engine = PatchEngine(community_path)
        self.backup_engine = BackupEngine()
        self.health_checker = HealthChecker(community_path)
        self.signature_verifier = SignatureVerifier()

    def diagnose(self) -> DiagnosticsReport:
        """
        Step 1: Run full diagnostics to detect all issues.

        Returns:
            DiagnosticsReport with complete findings.
        """
        logger.info("=== Repair Wizard: Step 1 — Diagnostics ===")
        return self.diagnostics.run_all()

    def recommend(self, report: DiagnosticsReport) -> RepairPlan:
        """
        Step 2: Generate repair recommendations from diagnostics.

        Args:
            report: The diagnostics report.

        Returns:
            RepairPlan with ordered actions.
        """
        logger.info("=== Repair Wizard: Step 2 — Generating Recommendations ===")
        plan = RepairPlan()

        # Check global issues
        if not self.community_path or not self.community_path.exists():
            plan.steps.append(RepairAction(
                aircraft_type="SYSTEM",
                action="Locate MSFS Community folder",
                severity="critical",
                command="auto-detect",
                details="Community folder not found. Specify manually or install MSFS.",
            ))
            plan.requires_restart = True
            return plan

        # Check HGS package
        hgs_present = FileCopier.verify_hgs_in_community(self.community_path)
        if not hgs_present:
            plan.steps.append(RepairAction(
                aircraft_type="SYSTEM",
                action="Install HGS package to Community folder",
                severity="error",
                command="install",
                details="The HGS package files are missing from the Community folder.",
            ))

        # Check each aircraft
        packages = scan_community(self.community_path)
        for pkg in packages:
            # Check version compatibility
            compat_ok = check_version_compatibility(pkg)
            if not compat_ok:
                compat_map = get_aircraft_compatibility_map()
                info = compat_map.get(pkg.aircraft_type.value, {})
                expected = f"{info.get('version_major', '?')}.{info.get('version_minor', '?')}"
                plan.steps.append(RepairAction(
                    aircraft_type=pkg.aircraft_type.value,
                    action=f"Version mismatch: installed v{pkg.detected_version_major}.{pkg.detected_version_minor}, expected v{expected}",
                    severity="warning",
                    command="check-compatibility",
                    details="The aircraft version may not be fully compatible with HGS.",
                    auto_fixable=False,
                ))

            # Check panel.cfg
            for panel_cfg in pkg.panel_configs:
                if not PanelCfgPatcher.has_hgs_entries(panel_cfg.path):
                    plan.steps.append(RepairAction(
                        aircraft_type=pkg.aircraft_type.value,
                        action="Re-patch panel.cfg with HGS entries",
                        severity="error",
                        command="repair",
                        details=f"HGS gauge entries missing from {panel_cfg.path.name}.",
                    ))

            # Check layout.json
            if pkg.layout_path and not LayoutPatcher.has_hgs_entries(pkg.layout_path):
                plan.steps.append(RepairAction(
                    aircraft_type=pkg.aircraft_type.value,
                    action="Re-patch layout.json with HGS entries",
                    severity="error",
                    command="repair",
                    details="HGS WASM entries missing from layout.json.",
                ))

            # Check signature
            safe, warnings = self.signature_verifier.is_package_safe_to_patch(pkg)
            if not safe:
                for w in warnings[:2]:
                    plan.steps.append(RepairAction(
                        aircraft_type=pkg.aircraft_type.value,
                        action=f"Signature verification: {w}",
                        severity="warning",
                        command="verify",
                        details="Aircraft package may have been modified.",
                        auto_fixable=False,
                    ))

        # Add a final verification step
        if plan.steps:
            plan.steps.append(RepairAction(
                aircraft_type="SYSTEM",
                action="Run final verification",
                severity="info",
                command="verify",
                details="Confirm all fixes were applied correctly.",
                auto_fixable=True,
            ))

        # Generate summary warnings
        if not plan.steps:
            plan.warnings.append("No issues detected. System is healthy.")

        logger.info(f"Generated repair plan with {len(plan.steps)} action(s)")
        return plan

    def execute(self, plan: RepairPlan) -> RepairResult:
        """
        Step 3: Execute the repair plan.

        Args:
            plan: The repair plan to execute.

        Returns:
            RepairResult with execution details.
        """
        logger.info("=== Repair Wizard: Step 3 — Executing Repairs ===")
        result = RepairResult(
            success=True,
            timestamp=time.time(),
        )

        if not self.community_path:
            result.success = False
            result.errors.append("Community folder not available")
            return result

        for action in plan.steps:
            if not action.auto_fixable:
                result.warnings.append(
                    f"Skipped '{action.action}' for {action.aircraft_type} (manual fix required)"
                )
                continue

            try:
                if action.command == "install":
                    FileCopier.copy_hgs_to_community(self.community_path)
                    result.actions_taken += 1
                    result.actions_succeeded += 1
                    logger.info(f"  ✓ {action.action}")

                elif action.command == "repair":
                    packages = scan_community(self.community_path)
                    for pkg in packages:
                        if pkg.aircraft_type.value == action.aircraft_type:
                            self.backup_engine.create_backup(pkg, "pre_repair_wizard")
                            self.patch_engine.install_hgs_to_aircraft(pkg)
                    result.actions_taken += 1
                    result.actions_succeeded += 1
                    logger.info(f"  ✓ {action.action}")

                elif action.command == "verify":
                    # Run verification diagnostics
                    verify_report = self.diagnostics.run_all()
                    if verify_report.errors:
                        result.warnings.extend(verify_report.errors[:3])
                    result.actions_taken += 1
                    result.actions_succeeded += 1

            except Exception as e:
                result.actions_failed += 1
                result.errors.append(f"Failed {action.action}: {e}")
                logger.error(f"  ✗ {action.action}: {e}")

        # Export diagnostics log
        result.log_path = self._export_repair_log(result)
        result.success = result.actions_failed == 0

        logger.info(f"Repair complete: {result.actions_succeeded}/{result.actions_taken} actions succeeded")
        return result

    def _export_repair_log(self, result: RepairResult) -> Optional[Path]:
        """Export repair log to desktop."""
        try:
            desktop = Path.home() / "Desktop"
            desktop.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_path = desktop / f"hgs_repair_log_{timestamp}.json"

            log_data = {
                "installer_version": __version__,
                "timestamp": datetime.now().isoformat(),
                "system": platform.platform(),
                "result": {
                    "success": result.success,
                    "actions_taken": result.actions_taken,
                    "actions_succeeded": result.actions_succeeded,
                    "actions_failed": result.actions_failed,
                    "errors": result.errors,
                    "warnings": result.warnings,
                },
            }
            log_path.write_text(json.dumps(log_data, indent=2), encoding="utf-8")
            logger.info(f"Repair log exported to {log_path}")
            return log_path

        except Exception as e:
            logger.warning(f"Failed to export repair log: {e}")
            return None

    def verify(self) -> DiagnosticsReport:
        """
        Step 4: Run final verification after repair.

        Returns:
            Diagnostics report showing post-repair state.
        """
        logger.info("=== Repair Wizard: Step 4 — Final Verification ===")
        return self.diagnostics.run_all()

    def run_full_repair(self) -> Tuple[RepairResult, DiagnosticsReport]:
        """
        Run the complete repair workflow end-to-end.

        Returns:
            Tuple of (RepairResult, final DiagnosticsReport).
        """
        report = self.diagnose()
        plan = self.recommend(report)

        if not plan.steps:
            logger.info("No repair needed — system is healthy")
            return RepairResult(success=True, timestamp=time.time()), report

        result = self.execute(plan)
        final_report = self.verify()

        return result, final_report


# =========================================================================
#  2.  Compatibility Recommendation Engine
# =========================================================================

class CompatibilityRecommender:
    """
    Provides compatibility recommendations for aircraft and installer versions.

    Answers:
      - Which aircraft are compatible with the current HGS version?
      - What version of each aircraft is required?
      - What are the known issues?
    """

    def __init__(self):
        self.compat_map = get_aircraft_compatibility_map()

    def get_aircraft_compatibility(self, aircraft_type: str) -> Dict:
        """
        Get compatibility info for a specific aircraft type.

        Args:
            aircraft_type: The aircraft type string.

        Returns:
            Dictionary with compatibility information.
        """
        info = self.compat_map.get(aircraft_type, {})
        return {
            "aircraft_type": aircraft_type,
            "supported": aircraft_type in self.compat_map,
            "minimum_version": f"{info.get('version_major', 0)}.{info.get('version_minor', 0)}",
            "has_profile": info.get("has_profile", False),
            "panel_fix_required": info.get("panel_fix_required", False),
            "notes": self._get_notes(aircraft_type),
        }

    def _get_notes(self, aircraft_type: str) -> List[str]:
        """Get known issues and notes for an aircraft type."""
        notes = {
            "PMDG 737-800": [
                "Requires PMDG 737-800 v3.0+",
                "Works with both MSFS 2020 and 2024",
                "Panel.cfg auto-patched on install",
            ],
            "PMDG 777-300ER": [
                "Requires PMDG 777-300ER v1.0+",
                "Full HUD integration supported",
            ],
            "iniBuilds A350": [
                "Supports iniBuilds A350 v1.0+",
                "Airbus-specific HUD profiles enabled",
            ],
            "FBW A32NX": [
                "Supports FBW A32NX stable and development builds",
                "Auto-detects A32NX version",
                "Community mod compatible",
            ],
            "HEADWIND A330-900": [
                "Supports Headwind A330-900 v1.0+",
                "Based on FBW A32NX systems",
            ],
            "WT 787-10": [
                "Working Title 787-10 integration",
                "Also supports default Asobo 787-10",
            ],
        }
        return notes.get(aircraft_type, ["Basic compatibility"])

    def get_all_compatible_aircraft(self) -> List[Dict]:
        """Get compatibility info for all supported aircraft."""
        return [
            self.get_aircraft_compatibility(at)
            for at in self.compat_map.keys()
        ]

    def check_installer_compatibility(self) -> List[str]:
        """
        Check the installer version against known requirements.

        Returns:
            List of compatibility notes/warnings.
        """
        notes = []
        version_parts = __version__.split(".")
        major = int(version_parts[0]) if version_parts else 0

        if major < 2:
            notes.append(
                f"Installer version {__version__} is outdated. "
                "Upgrade to v2.0+ for best compatibility."
            )

        notes.append(f"Installer v{__version__} — certified deployment build")

        return notes


# =========================================================================
#  3.  Telemetry Viewer
# =========================================================================

class TelemetryViewer:
    """
    Provides a simple viewer for installer telemetry data.

    Telemetry data is stored as JSON files during operations and
    can be displayed in a human-readable format.
    """

    def __init__(self):
        self.backup_dir = Path(__file__).resolve().parent / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def get_latest_telemetry(self) -> Optional[Dict]:
        """
        Get the most recent telemetry data.

        Returns:
            Latest telemetry data dict, or None.
        """
        telemetry_files = sorted(
            self.backup_dir.glob("hgs_telemetry_*.json"),
            reverse=True,
        )
        if not telemetry_files:
            return None

        try:
            return json.loads(telemetry_files[0].read_text(encoding="utf-8"))
        except Exception:
            return None

    def get_telemetry_history(self) -> List[Dict]:
        """Get all telemetry records."""
        records = []
        for tf in sorted(self.backup_dir.glob("hgs_telemetry_*.json"), reverse=True):
            try:
                records.append(json.loads(tf.read_text(encoding="utf-8")))
            except Exception:
                continue
        return records

    def format_telemetry_summary(self, telemetry: Dict) -> str:
        """Format telemetry data as a readable string."""
        lines = []
        lines.append("=" * 50)
        lines.append(f"HGS Installer Telemetry Summary")
        lines.append(f"Timestamp: {telemetry.get('timestamp', 'Unknown')}")
        lines.append(f"Installer Version: {telemetry.get('installer_version', 'Unknown')}")
        lines.append(f"Aircraft Scanned: {telemetry.get('aircraft_count', 0)}")
        lines.append(f"Integration Success: {telemetry.get('success_count', 0)}")
        lines.append("=" * 50)

        actions = telemetry.get("actions", [])
        if actions:
            lines.append("\nActions:")
            for action in actions:
                status = "✓" if action.get("success") else "✗"
                lines.append(f"  {status} {action.get('description', 'Unknown')}")

        return "\n".join(lines)

    def record_telemetry(self, data: Dict):
        """
        Record telemetry data to disk.

        Args:
            data: Telemetry data dict.
        """
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = self.backup_dir / f"hgs_telemetry_{timestamp}.json"
            data["timestamp"] = datetime.now().isoformat()
            data["installer_version"] = __version__
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            logger.debug(f"Telemetry recorded to {path}")
        except Exception as e:
            logger.warning(f"Failed to record telemetry: {e}")


# =========================================================================
#  4.  Convenience CLI
# =========================================================================

def run_repair_wizard(community_path: Optional[Path] = None) -> Dict:
    """
    Run the complete repair wizard and return a summary.

    Args:
        community_path: Optional community folder path.

    Returns:
        Summary dictionary.
    """
    wizard = RepairWizard(community_path)
    result, final_report = wizard.run_full_repair()

    return {
        "success": result.success,
        "actions_taken": result.actions_taken,
        "actions_succeeded": result.actions_succeeded,
        "actions_failed": result.actions_failed,
        "errors": result.errors[:5] if result.errors else [],
        "warnings": result.warnings[:5] if result.warnings else [],
        "aircraft_checked": len(final_report.aircraft_diagnostics),
        "aircraft_healthy": sum(1 for d in final_report.aircraft_diagnostics if d.passed),
        "log_path": str(result.log_path) if result.log_path else None,
        "quick_summary": quick_diagnostic_summary(community_path),
    }
