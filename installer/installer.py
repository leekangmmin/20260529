"""
C_HUD_Runway Installer — Main CLI Application
==============================================
Orchestrates the full installation, integration, and management of the
HGS/HUD system for MSFS aircraft.

Usage:
    python -m installer.installer [command] [options]

Commands:
    install      Install/repair HGS integration for all compatible aircraft
    uninstall    Remove HGS integration from all aircraft
    status       Show installation status
    scan         Scan Community folder for supported aircraft
    diag         Show diagnostic information
    repair       Repair broken integrations
    rollback     Roll back the last transaction
    gui          Launch the GUI application

Options:
    --community PATH   Specify Community folder path
    --verbose          Enable verbose logging
    --dry-run          Show what would be done without making changes
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

from . import __version__, __title__
from .msfs_detector import (
    detect_msfs_installations,
    find_community_folder,
    find_best_installation,
    get_diagnostics as get_msfs_diagnostics,
)
from .aircraft_scanner import (
    AircraftPackage,
    IntegrationStatus,
    scan_community,
    analyze_package_structure,
)
from .patch_engine import (
    PatchEngine,
    BackupEngine,
    FileCopier,
    LayoutPatcher,
    PanelCfgPatcher,
    BACKUP_DIR,
)
from .healer import SelfHealer, HealthChecker

logger = logging.getLogger("installer")


# =========================================================================
#  1.  Logging Setup
# =========================================================================

def setup_logging(verbose: bool = False, log_file: Optional[Path] = None):
    """Configure logging with both console and file handlers."""
    level = logging.DEBUG if verbose else logging.INFO

    # Root logger for our package
    installer_logger = logging.getLogger("installer")
    installer_logger.setLevel(level)

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(logging.Formatter(
        "%(levelname)s  %(message)s",
        datefmt="%H:%M:%S",
    ))
    installer_logger.addHandler(console)

    # File handler
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s  %(levelname)s  %(name)s  %(message)s",
        ))
        installer_logger.addHandler(file_handler)
        # Also set other loggers to file
        for name in ["msfs_detector", "aircraft_scanner", "patch_engine", "healer"]:
            logging.getLogger(name).setLevel(logging.DEBUG)
            logging.getLogger(name).addHandler(file_handler)

    return installer_logger


# =========================================================================
#  2.  Installer Core
# =========================================================================

class Installer:
    """
    Main installation orchestrator.

    Manages the end-to-end workflow:
      1. Detect MSFS installation
      2. Find Community folder
      3. Scan for supported aircraft
      4. Install/Repair/Uninstall
      5. Verify and report
    """

    def __init__(self, community_path: Optional[Path] = None, dry_run: bool = False):
        self.dry_run = dry_run
        self.community_path = community_path
        self.patch_engine = PatchEngine(community_path)
        self.backup_engine = BackupEngine()
        self.healer = SelfHealer(community_path)
        self.health_checker = HealthChecker(community_path)

        if community_path is None:
            # Auto-detect
            detected = find_community_folder()
            if detected:
                self.community_path = detected
                self.patch_engine.set_community_path(detected)
                self.healer.set_community_path(detected)
                self.health_checker.community_path = detected

    def ensure_community_path(self) -> bool:
        """Ensure we have a valid Community folder path."""
        if self.community_path and self.community_path.exists():
            return True

        # Try to detect
        detected = find_community_folder()
        if detected:
            self.community_path = detected
            self.patch_engine.set_community_path(detected)
            self.healer.set_community_path(detected)
            self.health_checker.community_path = detected
            logger.info(f"Auto-detected Community folder: {detected}")
            return True

        logger.error("Cannot find MSFS Community folder. Use --community to specify.")
        return False

    def scan(self) -> List[AircraftPackage]:
        """Scan the Community folder for supported aircraft."""
        if not self.ensure_community_path():
            return []

        logger.info(f"Scanning {self.community_path} for supported aircraft...")
        packages = scan_community(self.community_path)

        if not packages:
            logger.info("No supported aircraft packages found.")
        else:
            logger.info(f"Found {len(packages)} supported aircraft package(s).")

        return packages

    def install(self) -> Dict[str, bool]:
        """
        Full installation workflow.

        1. Copy HGS package to Community folder
        2. For each compatible aircraft:
           a. Create backup
           b. Patch layout.json
           c. Patch panel.cfg
           d. Verify
        3. Take snapshots for future health checks

        Returns:
            Dict mapping aircraft type -> success status.
        """
        if not self.ensure_community_path():
            return {}

        results: Dict[str, bool] = {}
        packages = self.scan()

        if not packages:
            logger.warning("No supported aircraft found to install.")
            return results

        # Step 1: Copy HGS package to Community folder
        logger.info("\nStep 1: Installing HGS package to Community folder...")
        if self.dry_run:
            logger.info("  [DRY RUN] Would copy HGS package")
        else:
            if FileCopier.copy_hgs_to_community(self.community_path):
                logger.info("  HGS package installed successfully.")
            else:
                logger.warning("  HGS package installation had issues (WASM may be missing).")

        # Step 2: Integrate with each aircraft
        logger.info(f"\nStep 2: Integrating with {len(packages)} aircraft...")
        for pkg in packages:
            logger.info(f"\n  Integrating with {pkg.aircraft_type.value}...")

            if self.dry_run:
                logger.info(f"    [DRY RUN] Would create backup and patch files")
                results[pkg.aircraft_type.value] = True
                continue

            success = self.patch_engine.install_hgs_to_aircraft(pkg)
            results[pkg.aircraft_type.value] = success

            if success:
                logger.info(f"    ✓ Integration successful")
            else:
                logger.error(f"    ✗ Integration failed")

        # Step 3: Take snapshots
        if not self.dry_run:
            for pkg in packages:
                self.health_checker.take_snapshot(pkg)

        # Summary
        logger.info("\n" + "=" * 50)
        logger.info("Installation Summary:")
        success_count = sum(1 for v in results.values() if v)
        logger.info(f"  {success_count}/{len(results)} aircraft integrated successfully")

        return results

    def uninstall(self) -> Dict[str, bool]:
        """
        Uninstall HGS integration from all aircraft.

        1. For each aircraft:
           a. Create backup
           b. Unpatch panel.cfg
           c. Unpatch layout.json
        2. Remove HGS package from Community folder

        Returns:
            Dict mapping aircraft type -> success status.
        """
        if not self.ensure_community_path():
            return {}

        results: Dict[str, bool] = {}
        packages = self.scan()

        if not packages:
            logger.info("No supported aircraft packages found.")
            return results

        logger.info(f"Uninstalling from {len(packages)} aircraft...")

        for pkg in packages:
            logger.info(f"\n  Removing integration from {pkg.aircraft_type.value}...")

            if self.dry_run:
                logger.info(f"    [DRY RUN] Would unpatch files")
                results[pkg.aircraft_type.value] = True
                continue

            success = self.patch_engine.uninstall_hgs_from_aircraft(pkg)
            results[pkg.aircraft_type.value] = success

            if success:
                logger.info(f"    ✓ Uninstall successful")
            else:
                logger.error(f"    ✗ Uninstall failed")

        # Remove HGS package
        if not self.dry_run:
            logger.info("\nRemoving HGS package from Community folder...")
            FileCopier.remove_hgs_from_community(self.community_path)

        # Summary
        logger.info("\n" + "=" * 50)
        logger.info("Uninstall Summary:")
        success_count = sum(1 for v in results.values() if v)
        logger.info(f"  {success_count}/{len(results)} aircraft cleaned successfully")

        return results

    def repair(self) -> Dict[str, bool]:
        """
        Repair broken HGS integrations.

        Scans all aircraft and re-patches any that need repair.

        Returns:
            Dict mapping aircraft type -> repair success status.
        """
        if not self.ensure_community_path():
            return {}

        logger.info("Checking for aircraft needing repair...")
        results = self.healer.repair_all()

        if not results:
            logger.info("All aircraft integrations are healthy. No repair needed.")
        else:
            fixed = sum(1 for v in results.values() if v)
            logger.info(f"\nRepair complete: {fixed}/{len(results)} repaired")

        return results

    def status(self) -> List[Dict]:
        """
        Show detailed installation status for all aircraft.

        Returns:
            List of status dictionaries.
        """
        if not self.ensure_community_path():
            return []

        health_list = self.health_checker.scan_all_health()

        if not health_list:
            logger.info("No supported aircraft found.")
            return []

        status_data = []
        for h in health_list:
            entry = {
                "aircraft": h.aircraft_type,
                "status": h.status.value,
                "version": f"{h.version_major}.{h.version_minor}",
                "expected_version": f"{h.expected_version_major}.{h.expected_version_minor}",
                "panel": h.panel_integrated,
                "layout": h.layout_integrated,
                "hgs_package": h.hgs_package_present,
                "compatible": h.compatibility_ok,
                "needs_repair": h.needs_repair,
                "issues": h.issues,
            }
            status_data.append(entry)

            # Print friendly output
            status_icon = "✓" if h.status == IntegrationStatus.INSTALLED else \
                         "⚠" if h.status == IntegrationStatus.NEEDS_REPAIR else "✗"
            logger.info(f"\n  {status_icon} {h.aircraft_type}")
            logger.info(f"     Status: {h.status.value}")
            logger.info(f"     Version: {h.version_major}.{h.version_minor}")
            logger.info(f"     Panel: {'✓' if h.panel_integrated else '✗'}")
            logger.info(f"     Layout: {'✓' if h.layout_integrated else '✗'}")
            logger.info(f"     HGS Package: {'✓' if h.hgs_package_present else '✗'}")
            if h.issues:
                for issue in h.issues:
                    logger.info(f"     ⚠ {issue}")

        return status_data

    def diag(self) -> Dict:
        """Get comprehensive diagnostic information."""
        diag = get_msfs_diagnostics()

        # Add HGS-specific info
        diag["installer_version"] = __version__
        diag["community_path"] = str(self.community_path) if self.community_path else None
        diag["dry_run"] = self.dry_run
        diag["backup_dir"] = str(BACKUP_DIR)
        diag["backup_dir_exists"] = BACKUP_DIR.exists()

        # Backup info
        backups = self.backup_engine.list_backups()
        diag["backup_count"] = len(backups)
        diag["backups"] = [
            {
                "id": b.id,
                "aircraft": b.aircraft_type,
                "date": b.timestamp_str,
                "files": b.file_count,
                "size": b.size_bytes,
            }
            for b in backups[:10]  # Last 10 backups
        ]

        # Health info
        try:
            health_list = self.health_checker.scan_all_health()
            diag["aircraft_health"] = [
                {
                    "type": h.aircraft_type,
                    "status": h.status.value,
                    "issues": h.issues,
                }
                for h in health_list
            ]
        except Exception as e:
            diag["aircraft_health_error"] = str(e)

        return diag

    def rollback(self) -> bool:
        """Roll back the last transaction."""
        if self.patch_engine.transaction is None:
            logger.info("No active transaction to roll back.")
            return False

        logger.info("Rolling back last transaction...")
        return self.patch_engine.rollback_transaction()


# =========================================================================
#  3.  CLI Entry Point
# =========================================================================

def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="c-hud-installer",
        description=f"{__title__} v{__version__}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m installer.installer install
  python -m installer.installer status --verbose
  python -m installer.installer repair
  python -m installer.installer uninstall
  python -m installer.installer gui
        """,
    )

    parser.add_argument(
        "command",
        choices=["install", "uninstall", "status", "scan", "diag", "repair", "rollback", "gui"],
        nargs="?",
        default="status",
        help="Operation to perform (default: status)",
    )

    parser.add_argument(
        "--community", "-c",
        type=str,
        help="Path to the MSFS Community folder",
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Show what would be done without making changes",
    )

    parser.add_argument(
        "--log-file",
        type=str,
        help="Path to log file",
    )

    return parser


def main():
    """Main entry point for the installer CLI."""
    parser = build_parser()
    args = parser.parse_args()

    # Set up logging
    log_path = Path(args.log_file) if args.log_file else \
               Path(__file__).resolve().parent / "installer.log"
    setup_logging(args.verbose, log_path)

    # Determine community path
    community_path = Path(args.community) if args.community else None

    # Create installer
    installer = Installer(community_path=community_path, dry_run=args.dry_run)

    # Execute command
    if args.command == "install":
        logger.info(f"{__title__} v{__version__}")
        logger.info("=" * 50)
        results = installer.install()
        if not results:
            sys.exit(1)

    elif args.command == "uninstall":
        logger.info(f"{__title__} v{__version__}")
        logger.info("=" * 50)
        results = installer.uninstall()
        if not results:
            sys.exit(1)

    elif args.command == "status":
        logger.info(f"{__title__} v{__version__} — Status")
        logger.info("=" * 50)
        status_data = installer.status()
        if not status_data and not installer.ensure_community_path():
            sys.exit(1)

    elif args.command == "scan":
        logger.info(f"{__title__} v{__version__} — Scan")
        logger.info("=" * 50)
        packages = installer.scan()
        if packages:
            for pkg in packages:
                analysis = analyze_package_structure(pkg)
                logger.info(f"\n  {pkg.aircraft_type.value}")
                logger.info(f"     Path: {pkg.package_path.name}")
                logger.info(f"     Layout: {analysis['layout_format']}")
                logger.info(f"     Entries: {analysis['total_entries']}")
                logger.info(f"     Panel CFGs: {analysis['panel_config_count']}")
                logger.info(f"     HGS: {analysis['integration_status']}")

    elif args.command == "diag":
        logger.info(f"{__title__} v{__version__} — Diagnostics")
        logger.info("=" * 50)
        diag = installer.diag()
        print(json.dumps(diag, indent=2, default=str))

    elif args.command == "repair":
        logger.info(f"{__title__} v{__version__} — Repair")
        logger.info("=" * 50)
        results = installer.repair()
        if not results:
            # Check if any aircraft need repair
            health_list = installer.health_checker.scan_all_health()
            needs_repair = [h for h in health_list if h.needs_repair]
            if not needs_repair:
                logger.info("All aircraft are healthy.")

    elif args.command == "rollback":
        logger.info(f"{__title__} v{__version__} — Rollback")
        logger.info("=" * 50)
        installer.rollback()

    elif args.command == "gui":
        logger.info("Launching GUI...")
        try:
            from .gui.app import run_gui
            run_gui(community_path=community_path)
        except ImportError as e:
            logger.error(f"Cannot launch GUI: {e}")
            logger.info("Install tkinter or use CLI commands instead.")
            sys.exit(1)


if __name__ == "__main__":
    main()
