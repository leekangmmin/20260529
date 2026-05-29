"""
Self-Healing Integration — Phase 4
===================================
Automatic detection and repair of HGS integration after aircraft updates.

Features:
  · Aircraft update detection (version changes)
  · Broken integration detection (missing entries)
  · Automatic repair
  · Compatibility validation
  · Migration between aircraft versions
"""

import json
import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .aircraft_scanner import (
    AircraftPackage,
    AircraftType,
    IntegrationStatus,
    scan_community,
    get_aircraft_compatibility_map,
    check_version_compatibility,
)
from .patch_engine import (
    PatchEngine,
    LayoutPatcher,
    PanelCfgPatcher,
    FileCopier,
    BackupEngine,
)

logger = logging.getLogger("healer")


# =========================================================================
#  1.  Health state tracking
# =========================================================================

@dataclass
class IntegrationHealth:
    """Tracks the integration health of a single aircraft."""
    package_name: str
    aircraft_type: str
    status: IntegrationStatus
    version_major: int
    version_minor: int
    expected_version_major: int
    expected_version_minor: int
    panel_integrated: bool = False
    layout_integrated: bool = False
    hgs_package_present: bool = False
    compatibility_ok: bool = False
    needs_repair: bool = False
    issues: List[str] = field(default_factory=list)
    last_checked: float = 0.0


@dataclass
class HealerState:
    """Persistent state for the self-healing system."""
    aircraft_snapshots: Dict[str, Dict] = field(default_factory=dict)
    last_scan_time: float = 0.0
    repair_history: List[Dict] = field(default_factory=list)


# =========================================================================
#  2.  Health Checker
# =========================================================================

class HealthChecker:
    """
    Monitors aircraft package health and detects integration issues.

    Periodically checks:
      - Whether the aircraft has been updated (version change)
      - Whether HGS entries are still present in panel.cfg
      - Whether HGS entries are still present in layout.json
      - Whether the HGS package is still in the Community folder
    """

    def __init__(self, community_path: Optional[Path] = None):
        self.community_path = community_path
        self.state = HealerState()
        self._load_state()

    def _state_path(self) -> Path:
        """Path to the persistent state file."""
        state_dir = Path(__file__).resolve().parent / "backups"
        state_dir.mkdir(parents=True, exist_ok=True)
        return state_dir / "healer_state.json"

    def _load_state(self):
        """Load persistent state from disk."""
        path = self._state_path()
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self.state.aircraft_snapshots = data.get("aircraft_snapshots", {})
                self.state.last_scan_time = data.get("last_scan_time", 0.0)
                self.state.repair_history = data.get("repair_history", [])
                logger.debug(f"Loaded healer state with {len(self.state.aircraft_snapshots)} snapshots")
            except (json.JSONDecodeError, Exception) as e:
                logger.warning(f"Failed to load healer state: {e}")

    def _save_state(self):
        """Save persistent state to disk."""
        path = self._state_path()
        try:
            data = {
                "aircraft_snapshots": self.state.aircraft_snapshots,
                "last_scan_time": self.state.last_scan_time,
                "repair_history": self.state.repair_history,
            }
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to save healer state: {e}")

    def take_snapshot(self, pkg: AircraftPackage):
        """Record a snapshot of the aircraft package state for future comparison."""
        snapshot_key = pkg.package_path.name
        self.state.aircraft_snapshots[snapshot_key] = {
            "package_name": pkg.package_path.name,
            "aircraft_type": pkg.aircraft_type.value,
            "version_major": pkg.detected_version_major,
            "version_minor": pkg.detected_version_minor,
            "hgs_integrated": pkg.hgs_integrated,
            "integration_status": pkg.integration_status.value,
            "timestamp": time.time(),
        }
        self._save_state()
        logger.debug(f"Took snapshot of {snapshot_key}")

    def check_health(self, pkg: AircraftPackage) -> IntegrationHealth:
        """
        Perform a health check on a single aircraft package.

        Compares current state against the last known snapshot to detect changes.

        Args:
            pkg: The aircraft package to check.

        Returns:
            IntegrationHealth object describing the health state.
        """
        snapshot_key = pkg.package_path.name
        snapshot = self.state.aircraft_snapshots.get(snapshot_key, {})

        issues: List[str] = []
        needs_repair = False

        # Check 1: Version change detection
        version_changed = False
        if snapshot:
            old_major = snapshot.get("version_major", 0)
            old_minor = snapshot.get("version_minor", 0)
            if (old_major != pkg.detected_version_major or
                old_minor != pkg.detected_version_minor):
                issues.append(
                    f"Aircraft version changed: {old_major}.{old_minor} -> "
                    f"{pkg.detected_version_major}.{pkg.detected_version_minor}"
                )
                version_changed = True

        # Check 2: Compatibility check
        compat_map = get_aircraft_compatibility_map()
        compat_info = compat_map.get(pkg.aircraft_type.value, {})
        expected_major = compat_info.get("version_major", 0)
        expected_minor = compat_info.get("version_minor", 0)
        compatibility_ok = check_version_compatibility(pkg)
        if not compatibility_ok:
            issues.append(
                f"Version {pkg.detected_version_major}.{pkg.detected_version_minor} "
                f"below expected {expected_major}.{expected_minor}"
            )

        # Check 3: Panel.cfg integration
        panel_integrated = any(
            PanelCfgPatcher.has_hgs_entries(pc.path)
            for pc in pkg.panel_configs
        )
        if not panel_integrated and snapshot.get("hgs_integrated", False):
            issues.append("HGS entries missing from panel.cfg (removed by aircraft update?)")
            needs_repair = True

        # Check 4: Layout.json integration
        layout_integrated = False
        if pkg.layout_path:
            layout_integrated = LayoutPatcher.has_hgs_entries(pkg.layout_path)
            if not layout_integrated and snapshot.get("hgs_integrated", False):
                issues.append("HGS entries missing from layout.json (removed by aircraft update?)")
                needs_repair = True

        # Check 5: HGS package presence
        hgs_package_present = False
        if self.community_path:
            hgs_package_present = FileCopier.verify_hgs_in_community(self.community_path)

        # Determine overall status
        if version_changed or needs_repair:
            final_status = IntegrationStatus.NEEDS_REPAIR
        elif panel_integrated and layout_integrated and hgs_package_present:
            final_status = IntegrationStatus.INSTALLED
        else:
            final_status = IntegrationStatus.NOT_INSTALLED

        health = IntegrationHealth(
            package_name=pkg.package_path.name,
            aircraft_type=pkg.aircraft_type.value,
            status=final_status,
            version_major=pkg.detected_version_major,
            version_minor=pkg.detected_version_minor,
            expected_version_major=expected_major,
            expected_version_minor=expected_minor,
            panel_integrated=panel_integrated,
            layout_integrated=layout_integrated,
            hgs_package_present=hgs_package_present,
            compatibility_ok=compatibility_ok,
            needs_repair=needs_repair or version_changed,
            issues=issues,
            last_checked=time.time(),
        )

        return health

    def scan_all_health(self) -> List[IntegrationHealth]:
        """Check health of all aircraft packages in the Community folder."""
        if self.community_path is None:
            logger.warning("Community path not set")
            return []

        packages = scan_community(self.community_path)
        results = []

        for pkg in packages:
            health = self.check_health(pkg)
            results.append(health)
            # Update snapshot
            self.take_snapshot(pkg)

        self.state.last_scan_time = time.time()
        self._save_state()

        return results

    def get_aircraft_needing_repair(self) -> List[IntegrationHealth]:
        """Get a list of aircraft that need repair."""
        health_list = self.scan_all_health()
        return [h for h in health_list if h.needs_repair]


# =========================================================================
#  3.  Self-Healer
# =========================================================================

class SelfHealer:
    """
    Automatically repairs HGS integration after aircraft updates.

    Detects:
      - Aircraft updates that removed HGS panel entries
      - Layout.json that was regenerated without HGS entries
      - Community folder changes

    Performs:
      - Re-patching of panel.cfg
      - Re-patching of layout.json
      - Verification after repair
    """

    def __init__(self, community_path: Optional[Path] = None):
        self.community_path = community_path
        self.health_checker = HealthChecker(community_path)
        self.patch_engine = PatchEngine(community_path)
        self.backup_engine = BackupEngine()
        self.repair_count = 0

    def set_community_path(self, path: Path):
        """Set the Community folder path."""
        self.community_path = path
        self.health_checker.community_path = path
        self.patch_engine.set_community_path(path)

    def repair_aircraft(self, pkg: AircraftPackage) -> bool:
        """
        Attempt to repair HGS integration for a single aircraft.

        Args:
            pkg: The aircraft package to repair.

        Returns:
            True if repair was successful.
        """
        logger.info(f"Attempting repair for {pkg.aircraft_type.value}")

        try:
            # Create backup before repair
            self.backup_engine.create_backup(pkg, "pre_repair")

            # Re-patch panel.cfg
            for panel_cfg in pkg.panel_configs:
                if not PanelCfgPatcher.has_hgs_entries(panel_cfg.path):
                    PanelCfgPatcher.patch_panel(panel_cfg.path)
                    logger.info(f"  Re-patched panel.cfg at {panel_cfg.path}")

            # Re-patch layout.json
            if pkg.layout_path:
                if not LayoutPatcher.has_hgs_entries(pkg.layout_path):
                    LayoutPatcher.patch_layout(pkg.layout_path)
                    logger.info(f"  Re-patched layout.json")

            # Ensure HGS package is present
            if self.community_path and not FileCopier.verify_hgs_in_community(self.community_path):
                FileCopier.copy_hgs_to_community(self.community_path)
                logger.info(f"  Re-copied HGS package")

            # Verify
            health = self.health_checker.check_health(pkg)
            if not health.needs_repair:
                logger.info(f"  Repair successful for {pkg.aircraft_type.value}")
                self.repair_count += 1

                # Record repair
                self.health_checker.state.repair_history.append({
                    "timestamp": time.time(),
                    "aircraft": pkg.aircraft_type.value,
                    "package": pkg.package_path.name,
                    "version": f"{pkg.detected_version_major}.{pkg.detected_version_minor}",
                    "success": True,
                })
                self.health_checker._save_state()
                return True
            else:
                logger.warning(f"  Repair may be incomplete for {pkg.aircraft_type.value}: {health.issues}")
                return False

        except Exception as e:
            logger.error(f"Repair failed for {pkg.aircraft_type.value}: {e}")
            self.health_checker.state.repair_history.append({
                "timestamp": time.time(),
                "aircraft": pkg.aircraft_type.value,
                "package": pkg.package_path.name,
                "success": False,
                "error": str(e),
            })
            self.health_checker._save_state()
            return False

    def repair_all(self) -> Dict[str, bool]:
        """
        Repair all aircraft that need it.

        Returns:
            Dictionary mapping aircraft type to repair success status.
        """
        if self.community_path is None:
            logger.warning("Community path not set")
            return {}

        from .aircraft_scanner import scan_community
        packages = scan_community(self.community_path)
        results = {}

        for pkg in packages:
            health = self.health_checker.check_health(pkg)
            if health.needs_repair:
                results[pkg.aircraft_type.value] = self.repair_aircraft(pkg)

        return results

    def get_repair_history(self) -> List[Dict]:
        """Get the repair history."""
        return list(self.health_checker.state.repair_history)


# =========================================================================
#  CLI entry point
# =========================================================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Self-Healing Integration - Diagnostics")
    print("=" * 60)

    from .aircraft_scanner import scan_community
    from .msfs_detector import find_community_folder

    community = find_community_folder()
    if community:
        print(f"Community folder: {community}")
        healer = SelfHealer(community)
        health_list = healer.health_checker.scan_all_health()

        print(f"\nHealth report for {len(health_list)} aircraft:")
        for h in health_list:
            status = "✓" if h.status == IntegrationStatus.INSTALLED else \
                     "⚠" if h.status == IntegrationStatus.NEEDS_REPAIR else "✗"
            print(f"\n  {status} {h.aircraft_type}")
            print(f"     Status: {h.status.value}")
            print(f"     Version: {h.version_major}.{h.version_minor} (expected {h.expected_version_major}.{h.expected_version_minor})")
            print(f"     Panel: {'✓' if h.panel_integrated else '✗'}  Layout: {'✓' if h.layout_integrated else '✗'}  HGS: {'✓' if h.hgs_package_present else '✗'}")
            if h.issues:
                for issue in h.issues:
                    print(f"     Issue: {issue}")
    else:
        print("Could not find Community folder.")
