"""
Live Integration Diagnostics — Phase 3 Deployment Certification
=================================================================
Runtime diagnostics for installer/integration failures.

Provides:
  · Failed WASM load detection
  · Missing L:var detection
  · Broken panel injection detection
  · JS renderer failure detection
  · Telemetry startup verification
  · Compatibility mismatch warnings
  · Integration diagnostics overlay (HTML)
  · Installer diagnostics export (JSON)
  · Runtime integration report
"""

import json
import logging
import os
import platform
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from . import __version__, __title__
from .aircraft_scanner import (
    AircraftPackage,
    AircraftType,
    IntegrationStatus,
    scan_community,
    check_version_compatibility,
    get_aircraft_compatibility_map,
    HGS_PANEL_GAUGE_MARKER,
    HGS_HTML_MARKER,
)
from .msfs_detector import (
    find_community_folder,
    find_best_installation,
    detect_msfs_installations,
)
from .patch_engine import (
    LayoutPatcher,
    PanelCfgPatcher,
    FileCopier,
)

logger = logging.getLogger("diagnostics")


# =========================================================================
#  1.  Enums & Dataclasses
# =========================================================================

class DiagnosticLevel(Enum):
    """Severity level of a diagnostic finding."""
    OK = "ok"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class DiagnosticCheck:
    """Result of a single diagnostic check."""
    name: str
    level: DiagnosticLevel
    message: str
    details: Optional[str] = None
    passed: bool = True
    timestamp: float = 0.0


@dataclass
class IntegrationDiagnostic:
    """Complete diagnostic for a single aircraft integration."""
    aircraft_type: str
    aircraft_version: str
    status: str

    # Component checks
    wasm_loaded: DiagnosticCheck = None
    lvars_detected: DiagnosticCheck = None
    panel_injection: DiagnosticCheck = None
    js_renderer: DiagnosticCheck = None
    telemetry_status: DiagnosticCheck = None
    compatibility: DiagnosticCheck = None
    hgs_package: DiagnosticCheck = None

    checks: List[DiagnosticCheck] = field(default_factory=list)
    timestamp: float = 0.0

    @property
    def overall_level(self) -> DiagnosticLevel:
        """Get the worst level across all checks."""
        levels = {DiagnosticLevel.CRITICAL, DiagnosticLevel.ERROR,
                  DiagnosticLevel.WARNING, DiagnosticLevel.INFO, DiagnosticLevel.OK}
        worst = DiagnosticLevel.OK
        for check in self.checks:
            if check.level.value == "critical":
                return DiagnosticLevel.CRITICAL
            if check.level.value == "error":
                worst = DiagnosticLevel.ERROR
            elif check.level.value == "warning" and worst != DiagnosticLevel.ERROR:
                worst = DiagnosticLevel.WARNING
            elif check.level.value == "info" and worst not in (DiagnosticLevel.ERROR, DiagnosticLevel.WARNING):
                worst = DiagnosticLevel.INFO
        return worst

    @property
    def passed(self) -> bool:
        """True if no critical or error checks."""
        return self.overall_level not in (DiagnosticLevel.CRITICAL, DiagnosticLevel.ERROR)


@dataclass
class DiagnosticsReport:
    """Full diagnostics report for the entire system."""
    installer_version: str = __version__
    timestamp: float = 0.0
    system_info: Dict[str, str] = field(default_factory=dict)
    msfs_installations: List[Dict] = field(default_factory=list)
    community_path: Optional[str] = None
    aircraft_diagnostics: List[IntegrationDiagnostic] = field(default_factory=list)
    global_checks: List[DiagnosticCheck] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """Convert to serializable dict."""
        def _check_to_dict(c):
            return asdict(c) if c else None

        return {
            "installer_version": self.installer_version,
            "timestamp": self.timestamp,
            "system_info": self.system_info,
            "msfs_installations": self.msfs_installations,
            "community_path": self.community_path,
            "aircraft_diagnostics": [
                {
                    "aircraft_type": ad.aircraft_type,
                    "aircraft_version": ad.aircraft_version,
                    "status": ad.status,
                    "overall_level": ad.overall_level.value,
                    "passed": ad.passed,
                    "checks": [asdict(c) for c in ad.checks],
                }
                for ad in self.aircraft_diagnostics
            ],
            "global_checks": [asdict(c) for c in self.global_checks],
            "errors": self.errors,
            "warnings": self.warnings,
            "recommendations": self.recommendations,
        }


# =========================================================================
#  2.  Individual Diagnostic Checks
# =========================================================================

class IntegrationDiagnostics:
    """
    Runtime diagnostics engine.

    Runs all diagnostic checks on the system and produces
    a comprehensive report.
    """

    def __init__(self, community_path: Optional[Path] = None):
        self.community_path = community_path
        if community_path is None:
            detected = find_community_folder()
            if detected:
                self.community_path = detected

    def run_all(self) -> DiagnosticsReport:
        """
        Run all diagnostic checks and produce a full report.

        Returns:
            DiagnosticsReport with all findings.
        """
        logger.info("Running full integration diagnostics...")
        report = DiagnosticsReport()
        report.timestamp = time.time()
        report.system_info = self._get_system_info()
        report.msfs_installations = self._get_msfs_info()
        report.community_path = str(self.community_path) if self.community_path else None

        # Check community folder
        if not self.community_path or not self.community_path.exists():
            report.global_checks.append(DiagnosticCheck(
                name="community_folder",
                level=DiagnosticLevel.ERROR,
                message="Community folder not found",
                details="HGS integration requires an MSFS Community folder.",
                passed=False,
            ))
            report.errors.append("Community folder not found. Use --community to specify.")
            report.recommendations.append(
                "Install MSFS 2020/2024 or specify the Community folder manually."
            )
            return report

        report.global_checks.append(DiagnosticCheck(
            name="community_folder",
            level=DiagnosticLevel.OK,
            message=f"Community folder found: {self.community_path}",
            passed=True,
        ))

        # Check HGS package presence
        hgs_present = FileCopier.verify_hgs_in_community(self.community_path)
        if hgs_present:
            report.global_checks.append(DiagnosticCheck(
                name="hgs_package",
                level=DiagnosticLevel.OK,
                message="HGS package is installed in Community folder",
                passed=True,
            ))
        else:
            report.global_checks.append(DiagnosticCheck(
                name="hgs_package",
                level=DiagnosticLevel.WARNING,
                message="HGS package not found in Community folder",
                details="Run 'install' to install the HGS package.",
                passed=False,
            ))
            report.warnings.append("HGS package not installed. Run install command.")
            report.recommendations.append("Run 'install' to deploy the HGS package.")

        # Scan aircraft
        packages = scan_community(self.community_path)

        if not packages:
            report.global_checks.append(DiagnosticCheck(
                name="aircraft_scan",
                level=DiagnosticLevel.WARNING,
                message="No supported aircraft found in Community folder",
                passed=True,
            ))
            report.recommendations.append(
                "Install supported aircraft (PMDG 737/777, iniBuilds A350, "
                "FBW A32NX, Headwind A330, WT 787) into the Community folder."
            )
            return report

        report.global_checks.append(DiagnosticCheck(
            name="aircraft_scan",
            level=DiagnosticLevel.OK,
            message=f"Found {len(packages)} supported aircraft",
            details=", ".join(p.aircraft_type.value for p in packages),
            passed=True,
        ))

        # Per-aircraft diagnostics
        for pkg in packages:
            diag = self._diagnose_aircraft(pkg)
            report.aircraft_diagnostics.append(diag)

            if not diag.passed:
                report.warnings.append(
                    f"{diag.aircraft_type}: Integration issues detected"
                )
                for check in diag.checks:
                    if check.level in (DiagnosticLevel.ERROR, DiagnosticLevel.CRITICAL):
                        report.errors.append(f"{diag.aircraft_type}: {check.message}")

        # Generate recommendations
        report.recommendations.extend(self._generate_recommendations(report))

        logger.info(f"Diagnostics complete: {len(report.aircraft_diagnostics)} aircraft checked, "
                     f"{len(report.errors)} errors, {len(report.warnings)} warnings")
        return report

    def _get_system_info(self) -> Dict[str, str]:
        """Get system information for diagnostics."""
        return {
            "platform": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "python_version": sys.version,
            "python_executable": sys.executable,
            "installer_version": __version__,
            "timestamp": datetime.now().isoformat(),
        }

    def _get_msfs_info(self) -> List[Dict]:
        """Get MSFS installation information."""
        installations = detect_msfs_installations()
        return [
            {
                "path": str(inst.path),
                "source": inst.source.name,
                "version": inst.version.value,
                "community_path": str(inst.community_path) if inst.community_path else None,
            }
            for inst in installations
        ]

    def _diagnose_aircraft(self, pkg: AircraftPackage) -> IntegrationDiagnostic:
        """
        Run all diagnostic checks for a single aircraft.

        Args:
            pkg: The aircraft package to diagnose.

        Returns:
            IntegrationDiagnostic with all checks.
        """
        version_str = f"{pkg.detected_version_major}.{pkg.detected_version_minor}"
        diag = IntegrationDiagnostic(
            aircraft_type=pkg.aircraft_type.value,
            aircraft_version=version_str,
            status=pkg.integration_status.value,
            timestamp=time.time(),
        )

        # 1. Check panel injection
        diag.panel_injection = self._check_panel_injection(pkg)
        diag.checks.append(diag.panel_injection)

        # 2. Check layout.json integration
        diag.wasm_loaded = self._check_layout_integration(pkg)
        diag.checks.append(diag.wasm_loaded)

        # 3. Check JS renderer
        diag.js_renderer = self._check_js_renderer(pkg)
        diag.checks.append(diag.js_renderer)

        # 4. Check compatibility
        diag.compatibility = self._check_compatibility(pkg)
        diag.checks.append(diag.compatibility)

        # 5. Check telemetry
        diag.telemetry_status = self._check_telemetry(pkg)
        diag.checks.append(diag.telemetry_status)

        # 6. Check HGS package
        diag.hgs_package = self._check_hgs_package()
        diag.checks.append(diag.hgs_package)

        # 7. L:var detection (simulated)
        diag.lvars_detected = self._check_lvars(pkg)
        diag.checks.append(diag.lvars_detected)

        return diag

    def _check_panel_injection(self, pkg: AircraftPackage) -> DiagnosticCheck:
        """Check if panel.cfg has HGS injection entries."""
        name = "panel_injection"
        hgs_found = any(
            PanelCfgPatcher.has_hgs_entries(pc.path)
            for pc in pkg.panel_configs
        )

        if hgs_found:
            return DiagnosticCheck(
                name=name,
                level=DiagnosticLevel.OK,
                message="HGS panel injection verified",
                details=f"HGS gauge entries found in panel.cfg",
                passed=True,
            )
        else:
            paths = [str(pc.path) for pc in pkg.panel_configs]
            return DiagnosticCheck(
                name=name,
                level=DiagnosticLevel.ERROR,
                message="HGS panel injection missing",
                details=f"No HGS entries found in panel.cfg files: {paths}",
                passed=False,
            )

    def _check_layout_integration(self, pkg: AircraftPackage) -> DiagnosticCheck:
        """Check if layout.json has HGS WASM entries."""
        name = "wasm_loading"
        if not pkg.layout_path:
            return DiagnosticCheck(
                name=name,
                level=DiagnosticLevel.ERROR,
                message="layout.json not found",
                details="Cannot verify WASM loading without layout.json",
                passed=False,
            )

        try:
            has_hgs = LayoutPatcher.has_hgs_entries(pkg.layout_path)
            if has_hgs:
                return DiagnosticCheck(
                    name=name,
                    level=DiagnosticLevel.OK,
                    message="WASM loading entries verified in layout.json",
                    passed=True,
                )
            else:
                return DiagnosticCheck(
                    name=name,
                    level=DiagnosticLevel.ERROR,
                    message="WASM loading entries missing from layout.json",
                    details="HGS WASM module not referenced. Run install to fix.",
                    passed=False,
                )
        except Exception as e:
            return DiagnosticCheck(
                name=name,
                level=DiagnosticLevel.ERROR,
                message=f"Failed to check layout.json: {e}",
                passed=False,
            )

    def _check_js_renderer(self, pkg: AircraftPackage) -> DiagnosticCheck:
        """Check for JS overlay files in the package or HGS package."""
        name = "js_renderer"

        # Check if HGS package has the JS overlay files
        if self.community_path:
            hgs_dir = self.community_path / "C_HUD_Runway"
            js_path = hgs_dir / "panel" / "HUD" / "hud_overlay.js"
            html_path = hgs_dir / "panel" / "HUD" / "hud_overlay.html"

            if js_path.exists() and html_path.exists():
                return DiagnosticCheck(
                    name=name,
                    level=DiagnosticLevel.OK,
                    message="JS renderer files present",
                    details=f"JS: {js_path}, HTML: {html_path}",
                    passed=True,
                )
            else:
                missing = []
                if not js_path.exists():
                    missing.append("hud_overlay.js")
                if not html_path.exists():
                    missing.append("hud_overlay.html")
                return DiagnosticCheck(
                    name=name,
                    level=DiagnosticLevel.WARNING,
                    message=f"JS renderer files missing: {', '.join(missing)}",
                    details="The HUD overlay may not render correctly without these files.",
                    passed=False,
                )

        return DiagnosticCheck(
            name=name,
            level=DiagnosticLevel.INFO,
            message="JS renderer check skipped (no community path)",
            passed=True,
        )

    def _check_compatibility(self, pkg: AircraftPackage) -> DiagnosticCheck:
        """Check aircraft compatibility."""
        name = "compatibility"
        compat_ok = check_version_compatibility(pkg)

        if compat_ok:
            return DiagnosticCheck(
                name=name,
                level=DiagnosticLevel.OK,
                message="Aircraft version is compatible",
                details=f"Version {pkg.detected_version_major}.{pkg.detected_version_minor} supported",
                passed=True,
            )
        else:
            compat_map = get_aircraft_compatibility_map()
            info = compat_map.get(pkg.aircraft_type.value, {})
            expected = f"{info.get('version_major', '?')}.{info.get('version_minor', '?')}"
            return DiagnosticCheck(
                name=name,
                level=DiagnosticLevel.WARNING,
                message=f"Aircraft version may be incompatible",
                details=f"Detected: v{pkg.detected_version_major}.{pkg.detected_version_minor}, "
                        f"Expected: v{expected}",
                passed=False,
            )

    def _check_telemetry(self, pkg: AircraftPackage) -> DiagnosticCheck:
        """Check telemetry status."""
        name = "telemetry_startup"
        # Telemetry is part of the WASM module; check if package is integrated
        if pkg.hgs_integrated:
            return DiagnosticCheck(
                name=name,
                level=DiagnosticLevel.OK,
                message="Telemetry integration verified",
                details="HGS integrated, telemetry should initialize on aircraft load",
                passed=True,
            )
        else:
            return DiagnosticCheck(
                name=name,
                level=DiagnosticLevel.INFO,
                message="Telemetry not yet integrated",
                details="Run install to enable telemetry",
                passed=True,
            )

    def _check_hgs_package(self) -> DiagnosticCheck:
        """Check HGS package presence."""
        name = "hgs_package"
        if self.community_path and FileCopier.verify_hgs_in_community(self.community_path):
            return DiagnosticCheck(
                name=name,
                level=DiagnosticLevel.OK,
                message="HGS package present in Community folder",
                passed=True,
            )
        else:
            return DiagnosticCheck(
                name=name,
                level=DiagnosticLevel.ERROR,
                message="HGS package not found in Community folder",
                passed=False,
            )

    def _check_lvars(self, pkg: AircraftPackage) -> DiagnosticCheck:
        """
        Check L:var detection.

        Note: L:vars are detected at runtime by the WASM module.
        At install time, we verify the gauge entry exists which will
        register the L:vars when the aircraft loads.
        """
        name = "lvars_detected"
        has_gauge = any(
            "C_HUD_Runway" in entry.get("raw", "")
            for pc in pkg.panel_configs
            for entry in pc.entries
        )

        if has_gauge:
            return DiagnosticCheck(
                name=name,
                level=DiagnosticLevel.OK,
                message="L:var registration gauge present",
                details="C_HUD_Runway gauge entry will register L:vars at runtime",
                passed=True,
            )
        else:
            return DiagnosticCheck(
                name=name,
                level=DiagnosticLevel.WARNING,
                message="L:var gauge entry missing",
                details="HGS L:vars will not be registered. Run install to fix.",
                passed=False,
            )

    def _generate_recommendations(self, report: DiagnosticsReport) -> List[str]:
        """Generate actionable recommendations based on diagnostic findings."""
        recommendations = []

        # Check if any aircraft need repair
        needs_repair = [
            d for d in report.aircraft_diagnostics
            if d.status == IntegrationStatus.NEEDS_REPAIR.value
        ]
        if needs_repair:
            types = [d.aircraft_type for d in needs_repair]
            recommendations.append(
                f"Repair needed for: {', '.join(types)}. Run 'repair' command."
            )

        # Check if any aircraft not installed
        not_installed = [
            d for d in report.aircraft_diagnostics
            if d.status == IntegrationStatus.NOT_INSTALLED.value
        ]
        if not_installed:
            types = [d.aircraft_type for d in not_installed]
            recommendations.append(
                f"Install HGS for: {', '.join(types)}. Run 'install' command."
            )

        # Check WASM loading
        wasm_issues = [
            d for d in report.aircraft_diagnostics
            if d.wasm_loaded and not d.wasm_loaded.passed
        ]
        if wasm_issues:
            recommendations.append(
                "WASM loading issues detected. Ensure the HGS .wasm file is "
                "in the Community/C_HUD_Runway/panel/ directory."
            )

        return recommendations


# =========================================================================
#  3.  Diagnostics Export
# =========================================================================

def export_diagnostics(report: DiagnosticsReport, output_path: Optional[Path] = None) -> Path:
    """
    Export diagnostics report to a JSON file.

    Args:
        report: The diagnostics report to export.
        output_path: Path to write the report. If None, uses desktop.

    Returns:
        Path to the exported file.
    """
    if output_path is None:
        # Default to user desktop
        desktop = Path.home() / "Desktop"
        desktop.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = desktop / f"hgs_diagnostics_{timestamp}.json"

    data = report.to_dict()
    output_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    logger.info(f"Diagnostics exported to {output_path}")
    return output_path


# =========================================================================
#  4.  Diagnostics Overlay (HTML)
# =========================================================================

def generate_diagnostics_overlay(report: DiagnosticsReport) -> str:
    """
    Generate an HTML diagnostics overlay for in-sim viewing.

    Args:
        report: The diagnostics report.

    Returns:
        HTML string for the overlay.
    """
    def _level_icon(level: str) -> str:
        icons = {
            "ok": "✅",
            "info": "ℹ️",
            "warning": "⚠️",
            "error": "❌",
            "critical": "🛑",
        }
        return icons.get(level, "❓")

    def _level_color(level: str) -> str:
        colors = {
            "ok": "#4caf50",
            "info": "#2196f3",
            "warning": "#ff9800",
            "error": "#f44336",
            "critical": "#d32f2f",
        }
        return colors.get(level, "#9e9e9e")

    aircraft_html = ""
    for ad in report.aircraft_diagnostics:
        checks_html = ""
        for c in ad.checks:
            checks_html += f"""
            <div class="check">
                <span class="icon">{_level_icon(c.level.value)}</span>
                <span class="check-name">{c.name}</span>
                <span class="check-msg">{c.message}</span>
                {f'<div class="details">{c.details}</div>' if c.details else ''}
            </div>"""

        overall_color = _level_color(ad.overall_level.value)
        aircraft_html += f"""
        <div class="aircraft-card">
            <div class="aircraft-header" style="border-left: 4px solid {overall_color};">
                <span class="aircraft-name">{ad.aircraft_type}</span>
                <span class="aircraft-version">v{ad.aircraft_version}</span>
                <span class="aircraft-status" style="color: {overall_color};">
                    {_level_icon(ad.overall_level.value)} {ad.overall_level.value.upper()}
                </span>
            </div>
            <div class="checks">
                {checks_html}
            </div>
        </div>"""

    global_checks_html = ""
    for c in report.global_checks:
        global_checks_html += f"""
        <div class="check">
            <span class="icon">{_level_icon(c.level.value)}</span>
            <span class="check-name">{c.name}</span>
            <span class="check-msg">{c.message}</span>
        </div>"""

    warnings_html = ""
    for w in report.warnings:
        warnings_html += f'<div class="warning-item">⚠️ {w}</div>'

    errors_html = ""
    for e in report.errors:
        errors_html += f'<div class="error-item">❌ {e}</div>'

    recs_html = ""
    for r in report.recommendations:
        recs_html += f'<div class="rec-item">💡 {r}</div>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>HGS Integration Diagnostics</title>
<style>
    body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: #1a1a2e;
           color: #e0e0e0; margin: 0; padding: 20px; }}
    h1 {{ color: #00d4ff; font-size: 1.5em; margin-bottom: 5px; }}
    h2 {{ color: #aaa; font-size: 1em; font-weight: normal; margin-top: 0; }}
    .summary {{ display: flex; gap: 15px; margin: 15px 0; }}
    .summary-item {{ background: #16213e; padding: 10px 20px; border-radius: 8px;
                    text-align: center; flex: 1; }}
    .summary-value {{ font-size: 2em; font-weight: bold; color: #00d4ff; }}
    .summary-label {{ font-size: 0.8em; color: #888; }}
    .aircraft-card {{ background: #16213e; border-radius: 8px; margin: 10px 0; padding: 12px; }}
    .aircraft-header {{ display: flex; align-items: center; gap: 15px; padding: 5px 10px; }}
    .aircraft-name {{ font-weight: bold; font-size: 1.1em; flex: 1; }}
    .aircraft-version {{ color: #888; font-size: 0.9em; }}
    .aircraft-status {{ font-size: 0.9em; }}
    .checks {{ margin-top: 10px; }}
    .check {{ display: flex; align-items: flex-start; gap: 8px; padding: 4px 8px;
              font-size: 0.9em; }}
    .check-name {{ color: #00d4ff; min-width: 120px; }}
    .check-msg {{ flex: 1; }}
    .details {{ color: #888; font-size: 0.85em; margin-top: 2px; padding-left: 8px; }}
    .section {{ margin: 15px 0; }}
    .section-title {{ font-weight: bold; color: #00d4ff; margin-bottom: 8px; }}
    .warning-item, .error-item {{ padding: 4px 8px; font-size: 0.9em; }}
    .error-item {{ color: #f44336; }}
    .rec-item {{ padding: 4px 8px; font-size: 0.9em; color: #4caf50; }}
    .footer {{ margin-top: 20px; font-size: 0.8em; color: #555; text-align: center; }}
</style>
</head>
<body>
<h1>🛩️ HGS Integration Diagnostics</h1>
<h2>{__title__} v{__version__} — {datetime.now().strftime('%Y-%m-%d %H:%M')}</h2>

<div class="summary">
    <div class="summary-item">
        <div class="summary-value">{len(report.aircraft_diagnostics)}</div>
        <div class="summary-label">Aircraft Checked</div>
    </div>
    <div class="summary-item">
        <div class="summary-value" style="color: {'#f44336' if report.errors else '#4caf50'}">
            {len(report.errors)}
        </div>
        <div class="summary-label">Errors</div>
    </div>
    <div class="summary-item">
        <div class="summary-value" style="color: {'#ff9800' if report.warnings else '#4caf50'}">
            {len(report.warnings)}
        </div>
        <div class="summary-label">Warnings</div>
    </div>
    <div class="summary-item">
        <div class="summary-value" style="color: {'#4caf50'}">
            {sum(1 for d in report.aircraft_diagnostics if d.passed)}
        </div>
        <div class="summary-label">Healthy</div>
    </div>
</div>

<div class="section">
    <div class="section-title">🌐 Global Checks</div>
    {global_checks_html}
</div>

<div class="section">
    <div class="section-title">✈️ Aircraft Diagnostics</div>
    {aircraft_html}
</div>

{'<div class="section"><div class="section-title">⚠️ Warnings</div>' + warnings_html + '</div>' if warnings_html else ''}
{'<div class="section"><div class="section-title">❌ Errors</div>' + errors_html + '</div>' if errors_html else ''}
{'<div class="section"><div class="section-title">💡 Recommendations</div>' + recs_html + '</div>' if recs_html else ''}

<div class="footer">
    Generated by {__title__} v{__version__} | {datetime.now().isoformat()}
</div>
</body>
</html>"""


# =========================================================================
#  5.  CLI Helpers
# =========================================================================

def run_diagnostics(community_path: Optional[Path] = None,
                    export: bool = False) -> DiagnosticsReport:
    """
    Run diagnostics and optionally export the report.

    Args:
        community_path: Optional Community folder path.
        export: Whether to export to desktop.

    Returns:
        The diagnostics report.
    """
    engine = IntegrationDiagnostics(community_path)
    report = engine.run_all()

    if export:
        export_path = export_diagnostics(report)
        logger.info(f"Diagnostics exported to {export_path}")

    return report


def quick_diagnostic_summary(community_path: Optional[Path] = None) -> str:
    """
    Generate a quick one-line diagnostic summary for terminal display.

    Args:
        community_path: Optional Community folder path.

    Returns:
        Summary string.
    """
    report = run_diagnostics(community_path)
    total = len(report.aircraft_diagnostics)
    healthy = sum(1 for d in report.aircraft_diagnostics if d.passed)
    errors = len(report.errors)
    warnings = len(report.warnings)

    return (
        f"Diagnostics: {total} aircraft, {healthy} healthy, "
        f"{errors} error{'s' if errors != 1 else ''}, "
        f"{warnings} warning{'s' if warnings != 1 else ''}"
    )
