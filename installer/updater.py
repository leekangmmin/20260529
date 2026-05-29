"""
Safe Update Management — Phase 4 Deployment Certification
==========================================================
Automatic aircraft update detection and safe migration.

Provides:
  · Aircraft update detection (version watching)
  · Automatic compatibility re-check
  · Migration patching between aircraft versions
  · Stale integration cleanup
  · Orphan file cleanup
  · Installer version migration
"""

import json
import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from . import __version__
from .aircraft_scanner import (
    AircraftPackage,
    AircraftType,
    IntegrationStatus,
    scan_community,
    check_version_compatibility,
    get_aircraft_compatibility_map,
)
from .healer import HealthChecker
from .patch_engine import (
    PatchEngine,
    LayoutPatcher,
    PanelCfgPatcher,
    FileCopier,
    BackupEngine,
    HGS_LAYOUT_ENTRIES,
)

logger = logging.getLogger("updater")


# =========================================================================
#  1.  Enums & Dataclasses
# =========================================================================

class UpdateAction(Enum):
    """Action to take for an aircraft update."""
    NONE = "none"                # No update needed
    REINSTALL = "reinstall"      # Full reinstall needed
    MIGRATE = "migrate"          # Migration patch available
    REPAIR = "repair"            # Minor repair needed
    REMOVE = "remove"            # Remove integration (incompatible)


@dataclass
class AircraftUpdate:
    """Describes an update event for an aircraft."""
    package_name: str
    aircraft_type: str
    old_version: str
    new_version: str
    detected_at: float = 0.0
    action: UpdateAction = UpdateAction.NONE
    requires_backup: bool = True
    migration_available: bool = False
    compatible: bool = True
    issues: List[str] = field(default_factory=list)


@dataclass
class UpdateResult:
    """Result of performing an update action."""
    aircraft_type: str
    action: UpdateAction
    success: bool
    old_version: str
    new_version: str
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    timestamp: float = 0.0


# =========================================================================
#  2.  Update Detection
# =========================================================================

class UpdateDetector:
    """
    Detects when aircraft packages have been updated.

    Compares current state against stored snapshots to identify:
      - Version changes (major/minor)
      - Structural changes (missing layout.json entries)
      - Panel.cfg changes (HGS entries removed)
    """

    def __init__(self, community_path: Optional[Path] = None):
        self.community_path = community_path
        self.health_checker = HealthChecker(community_path)
        self._update_history: List[AircraftUpdate] = []

    def detect_updates(self) -> List[AircraftUpdate]:
        """
        Scan all aircraft and detect any updates since last check.

        Returns:
            List of AircraftUpdate objects describing what changed.
        """
        if not self.community_path or not self.community_path.exists():
            logger.warning("Community path not available for update detection")
            return []

        packages = scan_community(self.community_path)
        updates: List[AircraftUpdate] = []

        for pkg in packages:
            update = self._check_aircraft_update(pkg)
            if update and update.action != UpdateAction.NONE:
                updates.append(update)
                self._update_history.append(update)
                logger.info(
                    f"Detected update for {pkg.aircraft_type.value}: "
                    f"{update.old_version} -> {update.new_version} [{update.action.value}]"
                )

        return updates

    def _check_aircraft_update(self, pkg: AircraftPackage) -> Optional[AircraftUpdate]:
        """
        Check a single aircraft for updates.

        Args:
            pkg: The aircraft package to check.

        Returns:
            AircraftUpdate if an update is detected, None otherwise.
        """
        snapshot_key = pkg.package_path.name
        snapshot = self.health_checker.state.aircraft_snapshots.get(snapshot_key, {})

        if not snapshot:
            # No previous snapshot — this is a new installation
            # Take a snapshot and return no update needed
            self.health_checker.take_snapshot(pkg)
            return None

        old_major = snapshot.get("version_major", 0)
        old_minor = snapshot.get("version_minor", 0)
        new_major = pkg.detected_version_major
        new_minor = pkg.detected_version_minor

        old_version = f"{old_major}.{old_minor}"
        new_version = f"{new_major}.{new_minor}"

        if old_version == new_version:
            # Version unchanged — check integration health
            if snapshot.get("hgs_integrated", False) and not pkg.hgs_integrated:
                # HGS entries were removed (likely by the game update)
                return AircraftUpdate(
                    package_name=pkg.package_path.name,
                    aircraft_type=pkg.aircraft_type.value,
                    old_version=old_version,
                    new_version=new_version,
                    detected_at=time.time(),
                    action=UpdateAction.REPAIR,
                    compatible=True,
                    issues=["HGS integration was removed, possibly by aircraft update"],
                )
            return None

        # Version changed
        compat_ok = check_version_compatibility(pkg)
        compat_map = get_aircraft_compatibility_map()
        info = compat_map.get(pkg.aircraft_type.value, {})
        expected_major = info.get("version_major", new_major)
        expected_minor = info.get("version_minor", new_minor)

        # Determine action
        if not compat_ok:
            action = UpdateAction.REMOVE if (new_major < expected_major) else UpdateAction.REINSTALL
        elif pkg.hgs_integrated:
            action = UpdateAction.MIGRATE
        else:
            action = UpdateAction.REINSTALL

        issues = []
        if not compat_ok:
            issues.append(
                f"Version {new_version} may not be compatible with HGS "
                f"(expected ~{expected_major}.{expected_minor})"
            )

        return AircraftUpdate(
            package_name=pkg.package_path.name,
            aircraft_type=pkg.aircraft_type.value,
            old_version=old_version,
            new_version=new_version,
            detected_at=time.time(),
            action=action,
            migration_available=(action == UpdateAction.MIGRATE),
            compatible=compat_ok,
            issues=issues,
        )

    def get_update_history(self) -> List[AircraftUpdate]:
        """Get the history of detected updates."""
        return list(self._update_history)


# =========================================================================
#  3.  Update Manager
# =========================================================================

class UpdateManager:
    """
    Manages the end-to-end update workflow.

    Handles:
      - Update detection
      - Automatic compatibility re-check
      - Migration patching
      - Stale integration cleanup
      - Orphan file cleanup
    """

    def __init__(self, community_path: Optional[Path] = None):
        self.community_path = community_path
        self.detector = UpdateDetector(community_path)
        self.patch_engine = PatchEngine(community_path)
        self.backup_engine = BackupEngine()
        self.health_checker = HealthChecker(community_path)

    def set_community_path(self, path: Path):
        """Set the community folder path."""
        self.community_path = path
        self.detector.community_path = path
        self.detector.health_checker.community_path = path
        self.patch_engine.set_community_path(path)
        self.health_checker.community_path = path

    def process_updates(self, auto_repair: bool = False) -> List[UpdateResult]:
        """
        Detect and process all aircraft updates.

        Args:
            auto_repair: If True, automatically repair/migrate updated aircraft.

        Returns:
            List of UpdateResult for each processed update.
        """
        updates = self.detector.detect_updates()
        results: List[UpdateResult] = []

        for update in updates:
            if auto_repair and update.action in (
                UpdateAction.REPAIR, UpdateAction.MIGRATE, UpdateAction.REINSTALL
            ):
                result = self._process_update(update)
                results.append(result)
            else:
                results.append(UpdateResult(
                    aircraft_type=update.aircraft_type,
                    action=update.action,
                    success=True,  # No action needed
                    old_version=update.old_version,
                    new_version=update.new_version,
                    warnings=update.issues,
                ))

        return results

    def _process_update(self, update: AircraftUpdate) -> UpdateResult:
        """
        Process a single aircraft update.

        Args:
            update: The update to process.

        Returns:
            UpdateResult indicating success/failure.
        """
        logger.info(f"Processing update for {update.aircraft_type}: {update.action.value}")

        result = UpdateResult(
            aircraft_type=update.aircraft_type,
            action=update.action,
            success=False,
            old_version=update.old_version,
            new_version=update.new_version,
            timestamp=time.time(),
        )

        try:
            if update.action == UpdateAction.REPAIR:
                # Re-patch panel.cfg and layout.json
                packages = scan_community(self.community_path)
                pkg = next(
                    (p for p in packages if p.aircraft_type.value == update.aircraft_type),
                    None
                )
                if pkg:
                    # Create backup
                    self.backup_engine.create_backup(pkg, "pre_update_repair")

                    # Re-patch
                    for panel_cfg in pkg.panel_configs:
                        if not PanelCfgPatcher.has_hgs_entries(panel_cfg.path):
                            PanelCfgPatcher.patch_panel(panel_cfg.path)

                    if pkg.layout_path and not LayoutPatcher.has_hgs_entries(pkg.layout_path):
                        LayoutPatcher.patch_layout(pkg.layout_path)

                    # Ensure HGS package present
                    if self.community_path and not FileCopier.verify_hgs_in_community(self.community_path):
                        FileCopier.copy_hgs_to_community(self.community_path)

                    # Update snapshot
                    self.health_checker.take_snapshot(pkg)
                    result.success = True

            elif update.action == UpdateAction.MIGRATE:
                # Migration: re-apply patches (aircraft structure may have changed)
                packages = scan_community(self.community_path)
                pkg = next(
                    (p for p in packages if p.aircraft_type.value == update.aircraft_type),
                    None
                )
                if pkg:
                    self.backup_engine.create_backup(pkg, "pre_migration")
                    success = self.patch_engine.install_hgs_to_aircraft(pkg)
                    if success:
                        self.health_checker.take_snapshot(pkg)
                    result.success = success

            elif update.action == UpdateAction.REINSTALL:
                # Full reinstall
                packages = scan_community(self.community_path)
                pkg = next(
                    (p for p in packages if p.aircraft_type.value == update.aircraft_type),
                    None
                )
                if pkg:
                    self.backup_engine.create_backup(pkg, "pre_reinstall")
                    # Remove old integration first
                    self.patch_engine.uninstall_hgs_from_aircraft(pkg)
                    # Re-install
                    success = self.patch_engine.install_hgs_to_aircraft(pkg)
                    if success:
                        self.health_checker.take_snapshot(pkg)
                    result.success = success

            elif update.action == UpdateAction.REMOVE:
                # Remove integration (incompatible version)
                packages = scan_community(self.community_path)
                pkg = next(
                    (p for p in packages if p.aircraft_type.value == update.aircraft_type),
                    None
                )
                if pkg:
                    self.backup_engine.create_backup(pkg, "pre_remove_incompatible")
                    self.patch_engine.uninstall_hgs_from_aircraft(pkg)
                    result.success = True
                    result.warnings.append(
                        f"HGS integration removed due to incompatible version "
                        f"{update.new_version}"
                    )

        except Exception as e:
            result.errors.append(str(e))
            logger.error(f"Failed to process update for {update.aircraft_type}: {e}")

        return result

    def cleanup_stale_integrations(self) -> int:
        """
        Remove stale HGS integration entries from aircraft that no longer exist.

        Scans layout.json and panel.cfg files for HGS entries and removes them
        from aircraft packages that no longer have HGS installed or whose
        packages have been removed.

        Returns:
            Number of stale integrations cleaned up.
        """
        if not self.community_path:
            return 0

        cleanups = 0

        # Scan all packages
        packages = scan_community(self.community_path)
        active_package_names = {p.package_path.name for p in packages}

        # Check backup records for packages that no longer exist
        from .patch_engine import BACKUP_DIR
        backup_dir = BACKUP_DIR
        if backup_dir.exists():
            manifest_path = backup_dir / "backup_manifest.json"
            if manifest_path.exists():
                try:
                    records = json.loads(manifest_path.read_text(encoding="utf-8"))
                    for record in records:
                        pkg_name = record.get("aircraft_package", "")
                        if pkg_name and pkg_name not in active_package_names:
                            # This package has been removed — clean up its snapshot
                            if pkg_name in self.health_checker.state.aircraft_snapshots:
                                del self.health_checker.state.aircraft_snapshots[pkg_name]
                                cleanups += 1
                                logger.info(f"Cleaned up snapshot for removed package: {pkg_name}")
                except Exception as e:
                    logger.warning(f"Failed to clean up stale integrations: {e}")

        if cleanups > 0:
            self.health_checker._save_state()

        return cleanups

    def cleanup_orphan_files(self) -> int:
        """
        Remove orphaned HGS files that are not referenced by any layout.json.

        Scans the Community folder for HGS-related files that don't belong
        to any current integration and removes them.

        Returns:
            Number of orphaned files removed.
        """
        if not self.community_path:
            return 0

        cleanups = 0
        hgs_package_dir = self.community_path / "C_HUD_Runway"

        if not hgs_package_dir.exists():
            return 0

        # Files that are part of the HGS package itself (not orphans)
        hgs_core_files = {
            "layout.json",
            "panel.cfg",
        }

        try:
            for file_path in hgs_package_dir.rglob("*"):
                if not file_path.is_file():
                    continue

                rel_path = file_path.relative_to(hgs_package_dir)

                # Skip core HGS files
                if rel_path.name in hgs_core_files:
                    continue

                # Check if file is referenced in any layout.json
                is_referenced = False
                for pkg_dir in self.community_path.iterdir():
                    if not pkg_dir.is_dir() or pkg_dir.name == "C_HUD_Runway":
                        continue
                    layout_path = pkg_dir / "layout.json"
                    if layout_path.exists():
                        try:
                            data = json.loads(layout_path.read_text(encoding="utf-8"))
                            entries = data.get("content", data if isinstance(data, list) else [])
                            for entry in entries:
                                entry_path = entry.get("path", "") if isinstance(entry, dict) else ""
                                if str(rel_path) in entry_path:
                                    is_referenced = True
                                    break
                        except Exception:
                            pass

                if not is_referenced:
                    # Check if it's a known HGS file (these are expected)
                    path_str = str(rel_path)
                    if any(
                        path_str.startswith(prefix)
                        for prefix in ["SimObjects/", "panel/", "texture/", "model/"]
                    ):
                        continue  # These are structural, not orphaned

                    # This file is orphaned
                    try:
                        file_path.unlink()
                        cleanups += 1
                        logger.debug(f"Removed orphaned file: {rel_path}")
                    except OSError as e:
                        logger.warning(f"Failed to remove orphaned file {rel_path}: {e}")

        except Exception as e:
            logger.warning(f"Orphan cleanup error: {e}")

        if cleanups > 0:
            logger.info(f"Cleaned up {cleanups} orphaned file(s)")

        return cleanups

    def migrate_installer_version(self, from_version: str, to_version: str) -> bool:
        """
        Handle installer self-version migration.

        Performs any necessary data migrations when the installer
        itself is updated.

        Args:
            from_version: Previous installer version.
            to_version: New installer version.

        Returns:
            True if migration was successful.
        """
        logger.info(f"Migrating installer from v{from_version} to v{to_version}")

        try:
            # Currently no data format migrations needed.
            # Future versions can add migration steps here.

            # Update the version in state files
            state_dir = Path(__file__).resolve().parent / "backups"
            if state_dir.exists():
                # Update any state files that embed version info
                for state_file in state_dir.glob("*.json"):
                    try:
                        data = json.loads(state_file.read_text(encoding="utf-8"))
                        if "installer_version" in data:
                            data["installer_version"] = to_version
                            state_file.write_text(
                                json.dumps(data, indent=2), encoding="utf-8"
                            )
                    except Exception:
                        pass

            logger.info(f"Installer migration v{from_version} -> v{to_version} complete")
            return True

        except Exception as e:
            logger.error(f"Installer migration failed: {e}")
            return False

    def full_update_cycle(self, auto_repair: bool = True) -> Dict:
        """
        Run a complete update cycle: detect, repair, and clean up.

        Args:
            auto_repair: Whether to automatically apply repairs.

        Returns:
            Summary dictionary with results.
        """
        results = {
            "updates_detected": 0,
            "updates_processed": 0,
            "updates_succeeded": 0,
            "updates_failed": 0,
            "stale_cleanups": 0,
            "orphan_cleanups": 0,
            "warnings": [],
            "errors": [],
        }

        # Step 1: Detect and process updates
        update_results = self.process_updates(auto_repair=auto_repair)
        results["updates_detected"] = len(update_results)

        for ur in update_results:
            if ur.success:
                results["updates_processed"] += 1
                results["updates_succeeded"] += 1
            else:
                results["updates_failed"] += 1
                results["errors"].append(
                    f"Failed to process {ur.aircraft_type}: {ur.errors}"
                )

        # Step 2: Clean stale integrations
        stale_count = self.cleanup_stale_integrations()
        results["stale_cleanups"] = stale_count

        # Step 3: Clean orphan files
        orphan_count = self.cleanup_orphan_files()
        results["orphan_cleanups"] = orphan_count

        return results
