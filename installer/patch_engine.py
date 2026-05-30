"""
Safe Patching System — Phase 3
===============================
Core patching engine for injecting HGS/HUD integration files into aircraft packages.

Features:
  · Automatic backup creation (zip snapshots)
  · Manifest snapshots for rollback
  · Reversible patching (every patch has an undo)
  · Integrity verification (SHA-256 checksums)
  · layout.json regeneration
  · panel.cfg patch insertion
  · Duplicate patch prevention
  · Never overwrites user files without backup
"""

import hashlib
import json
import logging
import os
import shutil
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from zipfile import ZipFile, ZIP_DEFLATED

from .aircraft_scanner import (
    AircraftPackage,
    PanelConfig,
    IntegrationStatus,
    HGS_PANEL_GAUGE_MARKER,
    HGS_HTML_MARKER,
)

logger = logging.getLogger("patch_engine")


# =========================================================================
#  1.  Constants
# =========================================================================

# Backup directory (inside the installer working directory)
BACKUP_DIR = Path(__file__).resolve().parent / "backups"

# The files we inject into aircraft packages
HGS_WASM_FILE = "C_HUD_Runway.wasm"
HGS_HTML_FILE = "HUD/hud_overlay.html"
HGS_JS_FILE = "HUD/hud_overlay.js"
HGS_PANEL_DIR = "panel/HUD"

# The panel.cfg entries we inject
HGS_PANEL_GAUGE_LINE = f"gauge00 = {HGS_PANEL_GAUGE_MARKER},  0, 0, 1024, 1024"
HGS_HTML_GAUGE_LINE = f"htmlgauge00 = {HGS_HTML_MARKER},  0, 0, 1024, 1024"

# Marker comments we add to track our patches
PATCH_MARKER_START = "; --- C_HUD_Runway HGS Integration ---"
PATCH_MARKER_END = "; --- End HGS Integration ---"

# Layout.json entries we add
HGS_LAYOUT_ENTRIES = [
    {"path": "SimObjects/Airplanes/C_HUD_Runway/panel/panel.cfg", "size": 0, "date": 0},
    {"path": "SimObjects/Airplanes/C_HUD_Runway/panel/C_HUD_Runway.wasm", "size": 0, "date": 0},
    {"path": "SimObjects/Airplanes/C_HUD_Runway/panel/HUD/hud_overlay.html", "size": 0, "date": 0},
    {"path": "SimObjects/Airplanes/C_HUD_Runway/panel/HUD/hud_overlay.js", "size": 0, "date": 0},
    {"path": "SimObjects/Airplanes/C_HUD_Runway/aircraft.cfg", "size": 0, "date": 0},
    {"path": "SimObjects/Airplanes/C_HUD_Runway/model/C_HUD_Runway.xml", "size": 0, "date": 0},
    {"path": "SimObjects/Airplanes/C_HUD_Runway/model/C_HUD_Runway.bin", "size": 0, "date": 0},
    {"path": "SimObjects/Airplanes/C_HUD_Runway/texture/texture.cfg", "size": 0, "date": 0},
    {"path": "SimObjects/Airplanes/C_HUD_Runway/texture/HUD_Overlay.png", "size": 0, "date": 0},
]


# =========================================================================
#  2.  Dataclasses
# =========================================================================

@dataclass
class BackupRecord:
    """Records a single backup operation."""
    id: str                          # Unique backup ID (timestamp-based)
    aircraft_package: str             # Name of the aircraft package
    aircraft_type: str                # Aircraft type string
    timestamp: float                  # When the backup was created
    backup_path: str                  # Path to the backup zip
    file_count: int = 0              # Number of files backed up
    size_bytes: int = 0              # Total size of backup
    checksum: str = ""               # SHA-256 of the backup archive
    reason: str = "pre_patch"        # Why the backup was created

    @property
    def timestamp_str(self) -> str:
        return datetime.fromtimestamp(self.timestamp).isoformat()


@dataclass
class PatchOperation:
    """Describes a single patch operation (atomic)."""
    operation_id: str
    aircraft_package: str
    patch_type: str                   # "panel_cfg" or "layout_json" or "file_copy"
    target_path: str                  # File being patched
    backup_id: str                    # Associated backup
    status: str = "pending"          # pending, applied, rolled_back, failed
    checksum_before: str = ""
    checksum_after: str = ""
    timestamp: float = 0.0
    error: Optional[str] = None


@dataclass
class PatchTransaction:
    """A transaction comprising multiple patch operations."""
    transaction_id: str
    aircraft_package: str
    operations: List[PatchOperation] = field(default_factory=list)
    status: str = "open"             # open, committed, rolled_back, failed
    created_at: float = 0.0
    committed_at: Optional[float] = None
    error: Optional[str] = None


# =========================================================================
#  3.  Checksum utilities
# =========================================================================

def compute_file_checksum(path: Path) -> str:
    """Compute SHA-256 checksum of a file."""
    hasher = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except (OSError, IOError) as e:
        logger.warning(f"Failed to compute checksum for {path}: {e}")
        return ""


def compute_string_checksum(content: str) -> str:
    """Compute SHA-256 checksum of a string."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


# =========================================================================
#  4.  Backup Engine
# =========================================================================

class BackupEngine:
    """
    Creates and manages backup archives of aircraft packages before patching.

    Backups are stored as ZIP files in the installer/backups directory.
    """

    def __init__(self, backup_dir: Path = BACKUP_DIR):
        self.backup_dir = backup_dir
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self._records: List[BackupRecord] = []
        self._load_records()

    def _load_records(self):
        """Load existing backup records from the manifest file."""
        manifest_path = self.backup_dir / "backup_manifest.json"
        if manifest_path.exists():
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                for item in data:
                    self._records.append(BackupRecord(**item))
            except (json.JSONDecodeError, Exception) as e:
                logger.warning(f"Failed to load backup manifest: {e}")

    def _save_records(self):
        """Save backup records to the manifest file."""
        manifest_path = self.backup_dir / "backup_manifest.json"
        try:
            data = [asdict(r) for r in self._records]
            manifest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to save backup manifest: {e}")

    def create_backup(self, pkg: AircraftPackage, reason: str = "pre_patch") -> Optional[BackupRecord]:
        """
        Create a full backup of an aircraft package.

        Args:
            pkg: The aircraft package to back up.
            reason: Reason for the backup.

        Returns:
            BackupRecord on success, None on failure.
        """
        backup_id = f"bk_{int(time.time())}_{pkg.package_path.name[:20]}"
        backup_filename = f"{backup_id}.zip"
        backup_path = self.backup_dir / backup_filename

        logger.info(f"Creating backup: {backup_id} for {pkg.aircraft_type.value}")

        try:
            # Create the zip archive
            file_count = 0
            total_size = 0

            with ZipFile(backup_path, "w", ZIP_DEFLATED) as zf:
                package_root = pkg.package_path
                for file_path in package_root.rglob("*"):
                    if file_path.is_file():
                        # Calculate relative path for archive
                        rel_path = str(file_path.relative_to(package_root))
                        zf.write(file_path, rel_path)
                        file_count += 1
                        total_size += file_path.stat().st_size

            # Compute checksum
            checksum = compute_file_checksum(backup_path)

            record = BackupRecord(
                id=backup_id,
                aircraft_package=pkg.package_path.name,
                aircraft_type=pkg.aircraft_type.value,
                timestamp=time.time(),
                backup_path=str(backup_path),
                file_count=file_count,
                size_bytes=total_size,
                checksum=checksum,
                reason=reason,
            )

            self._records.append(record)
            self._save_records()
            logger.info(f"Backup created: {backup_path} ({file_count} files, {total_size} bytes)")
            return record

        except Exception as e:
            logger.error(f"Failed to create backup for {pkg.package_path.name}: {e}")
            # Clean up partial zip
            if backup_path.exists():
                try:
                    backup_path.unlink()
                except OSError:
                    pass
            return None

    def restore_backup(self, record: BackupRecord) -> bool:
        """
        Restore an aircraft package from a backup.

        Args:
            record: The backup record to restore from.

        Returns:
            True if restoration was successful.
        """
        backup_path = Path(record.backup_path)
        if not backup_path.exists():
            logger.error(f"Backup file not found: {backup_path}")
            return False

        # Verify checksum
        current_checksum = compute_file_checksum(backup_path)
        if current_checksum != record.checksum:
            logger.error(f"Backup checksum mismatch! Expected {record.checksum}, got {current_checksum}")
            return False

        logger.info(f"Restoring from backup: {record.id}")

        try:
            # Determine the target directory (the aircraft package)
            # The backup contains relative paths from the package root
            # We need to find the package by name
            target_dir = None
            for candidate in Path(record.backup_path).parent.parent.parent.rglob(record.aircraft_package):
                if candidate.is_dir() and candidate.name == record.aircraft_package:
                    target_dir = candidate
                    break

            if target_dir is None:
                logger.error(f"Cannot find target directory for {record.aircraft_package}")
                return False

            # Extract the backup
            with ZipFile(backup_path, "r") as zf:
                zf.extractall(target_dir)

            logger.info(f"Restored {record.aircraft_package} from backup")
            return True

        except Exception as e:
            logger.error(f"Failed to restore backup: {e}")
            return False

    def get_backup_for_package(self, package_name: str) -> Optional[BackupRecord]:
        """Get the most recent backup for a given package."""
        matching = [r for r in self._records if r.aircraft_package == package_name]
        if not matching:
            return None
        return max(matching, key=lambda r: r.timestamp)

    def list_backups(self) -> List[BackupRecord]:
        """List all available backups."""
        return sorted(self._records, key=lambda r: r.timestamp, reverse=True)

    def cleanup_old_backups(self, max_age_days: int = 30):
        """Remove backups older than the specified age."""
        now = time.time()
        cutoff = now - (max_age_days * 86400)
        kept = []
        for record in self._records:
            if record.timestamp < cutoff:
                try:
                    Path(record.backup_path).unlink(missing_ok=True)
                except OSError:
                    pass
            else:
                kept.append(record)
        self._records = kept
        self._save_records()


# =========================================================================
#  5.  Layout JSON patcher
# =========================================================================

class LayoutPatcher:
    """
    Handles patching of layout.json files.

    Adds HGS entries to the layout and removes them during rollback.
    """

    @staticmethod
    def patch_layout(layout_path: Path) -> bool:
        """
        Add HGS entries to a layout.json file.

        Args:
            layout_path: Path to the layout.json file.

        Returns:
            True if patching was successful.
        """
        if not layout_path.exists():
            logger.error(f"layout.json not found: {layout_path}")
            return False

        try:
            data = json.loads(layout_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error(f"Failed to parse {layout_path}: {e}")
            return False

        # Determine the content list
        if isinstance(data, dict) and "content" in data:
            content = data["content"]
        elif isinstance(data, list):
            content = data
        else:
            logger.error(f"Unknown layout.json format at {layout_path}")
            return False

        # Add missing HGS entries
        added = 0
        existing_paths = {entry.get("path", "") for entry in content}

        for hgs_entry in HGS_LAYOUT_ENTRIES:
            if hgs_entry["path"] not in existing_paths:
                content.append(hgs_entry)
                existing_paths.add(hgs_entry["path"])
                added += 1

        if added == 0:
            logger.info(f"All HGS entries already present in {layout_path}")
            return True

        # Write back
        try:
            if isinstance(data, dict):
                data["content"] = content
                layout_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            else:
                layout_path.write_text(json.dumps(content, indent=2), encoding="utf-8")
            logger.info(f"Added {added} HGS entries to {layout_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to write {layout_path}: {e}")
            return False

    @staticmethod
    def unpatch_layout(layout_path: Path) -> bool:
        """
        Remove HGS entries from a layout.json file.

        Args:
            layout_path: Path to the layout.json file.

        Returns:
            True if unpatching was successful.
        """
        if not layout_path.exists():
            logger.warning(f"layout.json not found for unpatch: {layout_path}")
            return False

        try:
            data = json.loads(layout_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error(f"Failed to parse {layout_path}: {e}")
            return False

        # Get the list of HGS entry paths
        hgs_paths = {e["path"] for e in HGS_LAYOUT_ENTRIES}

        if isinstance(data, dict) and "content" in data:
            original_count = len(data["content"])
            data["content"] = [e for e in data["content"] if e.get("path", "") not in hgs_paths]
            removed = original_count - len(data["content"])
            if removed > 0:
                layout_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
                logger.info(f"Removed {removed} HGS entries from {layout_path}")
            return True
        elif isinstance(data, list):
            original_count = len(data)
            data = [e for e in data if e.get("path", "") not in hgs_paths]
            removed = original_count - len(data)
            if removed > 0:
                layout_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
                logger.info(f"Removed {removed} HGS entries from {layout_path}")
            return True
        else:
            logger.error(f"Unknown layout.json format at {layout_path}")
            return False

    @staticmethod
    def has_hgs_entries(layout_path: Path) -> bool:
        """Check if layout.json already contains HGS entries."""
        if not layout_path.exists():
            return False
        try:
            data = json.loads(layout_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return False

        if isinstance(data, dict) and "content" in data:
            content = data["content"]
        elif isinstance(data, list):
            content = data
        else:
            return False

        hgs_paths = {e["path"] for e in HGS_LAYOUT_ENTRIES}
        return any(e.get("path", "") in hgs_paths for e in content)


# =========================================================================
#  6.  Panel CFG patcher
# =========================================================================

class PanelCfgPatcher:
    """
    Handles patching of panel.cfg files.

    Injects HGS gauge and HTML entries while preserving existing content.
    """

    @staticmethod
    def patch_panel(panel_cfg_path: Path) -> bool:
        """
        Add HGS gauge entries to a panel.cfg file.

        Args:
            panel_cfg_path: Path to the panel.cfg file.

        Returns:
            True if patching was successful.
        """
        if not panel_cfg_path.exists():
            logger.error(f"panel.cfg not found: {panel_cfg_path}")
            return False

        try:
            content = panel_cfg_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            logger.error(f"Failed to read {panel_cfg_path}: {e}")
            return False

        # Check if already patched
        if PATCH_MARKER_START in content:
            logger.info(f"panel.cfg already has HGS integration at {panel_cfg_path}")
            return True

        # Check for existing HGS gauge entries (without our markers)
        if HGS_PANEL_GAUGE_MARKER in content:
            logger.info(f"panel.cfg already contains HGS gauge at {panel_cfg_path}")
            return True

        # Find the insertion point: after [VCockpit01] section or the last gauge entry
        lines = content.splitlines()
        insertion_index = len(lines)

        # Find the VCockpit section
        vcockpit_section = None
        last_gauge_line = None
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("[VCockpit"):
                vcockpit_section = i
            if stripped.startswith("gauge") or stripped.startswith("htmlgauge"):
                last_gauge_line = i

        if vcockpit_section is None:
            logger.warning(f"No [VCockpit] section found in {panel_cfg_path}, appending at end")
        elif last_gauge_line is not None:
            insertion_index = last_gauge_line + 1

        # Build the HGS patch block
        patch_block = [
            "",
            PATCH_MARKER_START,
            "",
            f"; ---- C++ WASM gauge (Conformal HUD)",
            HGS_PANEL_GAUGE_LINE,
            "",
            f"; ---- HTML/JS Canvas overlay (Conformal HUD)",
            HGS_HTML_GAUGE_LINE,
            "",
            PATCH_MARKER_END,
            "",
        ]

        # Insert the patch block
        new_lines = lines[:insertion_index] + patch_block + lines[insertion_index:]
        new_content = "\n".join(new_lines)

        # Write back
        try:
            panel_cfg_path.write_text(new_content, encoding="utf-8")
            logger.info(f"Patched panel.cfg at {panel_cfg_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to write {panel_cfg_path}: {e}")
            return False

    @staticmethod
    def unpatch_panel(panel_cfg_path: Path) -> bool:
        """
        Remove HGS gauge entries from a panel.cfg file.

        Args:
            panel_cfg_path: Path to the panel.cfg file.

        Returns:
            True if unpatching was successful.
        """
        if not panel_cfg_path.exists():
            logger.warning(f"panel.cfg not found for unpatch: {panel_cfg_path}")
            return True  # Already clean

        try:
            content = panel_cfg_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            logger.error(f"Failed to read {panel_cfg_path}: {e}")
            return False

        # Remove our marked block
        if PATCH_MARKER_START in content and PATCH_MARKER_END in content:
            # Remove everything between and including markers
            pattern_start = content.find(PATCH_MARKER_START)
            pattern_end = content.find(PATCH_MARKER_END) + len(PATCH_MARKER_END)
            if pattern_start >= 0 and pattern_end > pattern_start:
                new_content = content[:pattern_start] + content[pattern_end:]
        elif HGS_PANEL_GAUGE_MARKER in content:
            # Remove the line containing our gauge marker
            lines = content.splitlines()
            new_lines = [
                line for line in lines
                if HGS_PANEL_GAUGE_MARKER not in line
                and HGS_HTML_MARKER not in line
            ]
            new_content = "\n".join(new_lines)
        else:
            logger.info(f"No HGS entries found in {panel_cfg_path}")
            return True

        try:
            panel_cfg_path.write_text(new_content, encoding="utf-8")
            logger.info(f"Unpatched panel.cfg at {panel_cfg_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to write {panel_cfg_path}: {e}")
            return False

    @staticmethod
    def has_hgs_entries(panel_cfg_path: Path) -> bool:
        """Check if panel.cfg already contains HGS entries."""
        if not panel_cfg_path.exists():
            return False
        try:
            content = panel_cfg_path.read_text(encoding="utf-8", errors="ignore")
            return PATCH_MARKER_START in content or HGS_PANEL_GAUGE_MARKER in content
        except Exception:
            return False


# =========================================================================
#  7.  File Copier (HGS WASM + assets)
# =========================================================================

class FileCopier:
    """
    Copies HGS runtime files into the aircraft package or Community folder.

    Handles:
      - Copying C_HUD_Runway.wasm
      - Copying HUD overlay HTML/JS files
      - Creating necessary directory structure
      - Verifying file integrity after copy
    """

    @staticmethod
    def get_hgs_source_dir() -> Optional[Path]:
        """
        Get the directory containing the HGS source files to deploy.

        This searches relative to the installer location.
        """
        # First check relative to this file
        installer_dir = Path(__file__).resolve().parent.parent

        # Check for build output
        for candidate in [
            installer_dir / "build" / "C_HUD_Runway.wasm",
            installer_dir / "panel" / "C_HUD_Runway.wasm",
            installer_dir / "C_HUD_Runway.wasm",
        ]:
            if candidate.exists() and candidate.suffix == ".wasm":
                return candidate.parent

        return None

    @staticmethod
    def copy_hgs_to_community(community_path: Path) -> bool:
        """
        Copy the HGS package to the Community folder.

        This creates the full package structure at:
        Community/C_HUD_Runway/SimObjects/Airplanes/C_HUD_Runway/...

        Args:
            community_path: Path to the MSFS Community folder.

        Returns:
            True if copy was successful.
        """
        # Define the package structure
        package_root = community_path / "C_HUD_Runway"
        sim_root = package_root / "SimObjects" / "Airplanes" / "C_HUD_Runway"

        try:
            # Create directories
            sim_root.mkdir(parents=True, exist_ok=True)
            (sim_root / "panel" / "HUD").mkdir(parents=True, exist_ok=True)
            (sim_root / "model").mkdir(parents=True, exist_ok=True)
            (sim_root / "texture").mkdir(parents=True, exist_ok=True)

            # Find source files
            installer_dir = Path(__file__).resolve().parent.parent

            # Copy WASM (from build dir)
            wasm_sources = [
                installer_dir / "build" / "C_HUD_Runway.wasm",
                installer_dir / "panel" / "C_HUD_Runway.wasm",
                installer_dir / "C_HUD_Runway.wasm",
            ]

            wasm_copied = False
            for src in wasm_sources:
                if src.exists():
                    shutil.copy2(src, sim_root / "panel" / "C_HUD_Runway.wasm")
                    wasm_copied = True
                    logger.info(f"Copied WASM: {src}")
                    break

            if not wasm_copied:
                # The WASM is the HUD engine — without it nothing renders. Fail
                # loudly instead of silently producing a broken, empty package.
                logger.error(
                    "C_HUD_Runway.wasm not found in any of: "
                    f"{[str(s) for s in wasm_sources]}. "
                    "The compiled WASM gauge must be present before installing."
                )
                return False

            # Copy HTML/JS overlay files (these live under panel/HUD/, not panel/)
            overlay_src_dir = installer_dir / "panel" / "HUD"
            overlay_files = ["hud_overlay.html", "hud_overlay.js", "conformal_renderer.js"]
            missing_overlay = []
            for fname in overlay_files:
                src = overlay_src_dir / fname
                if src.exists():
                    shutil.copy2(src, sim_root / "panel" / "HUD" / fname)
                    logger.info(f"Copied overlay: {fname}")
                else:
                    missing_overlay.append(fname)

            if missing_overlay:
                logger.error(
                    f"Missing overlay file(s) in {overlay_src_dir}: {missing_overlay}. "
                    "HUD overlay would not render. Aborting."
                )
                return False

            # Copy panel.cfg from our template
            panel_cfg_src = installer_dir / "panel.cfg"
            if panel_cfg_src.exists():
                shutil.copy2(panel_cfg_src, sim_root / "panel" / "panel.cfg")

            # Create aircraft.cfg
            aircraft_cfg = sim_root / "aircraft.cfg"
            if not aircraft_cfg.exists():
                aircraft_cfg.write_text(
                    "[FLTSIM.0]\n"
                    "title = C_HUD_Runway\n"
                    "model = \n"
                    "panel = \n"
                    "sound = \n"
                    "texture = \n"
                    "kb_checklists =\n"
                    "kb_reference =\n"
                    "atc_id = N701CG\n"
                    "atc_airline = Conformal\n"
                    "atc_flight_number = 1\n"
                    "atc_heavy = 0\n"
                    "atc_type = HGS\n"
                    "atc_model =\n"
                    "atc_parking_types = GATE,RAMP\n"
                    "atc_id_color = 0xFFFF0000\n"
                    "description = Conformal HUD Runway Guidance System\n"
                    "\n",
                    encoding="utf-8",
                )

            # Create texture.cfg
            texture_cfg = sim_root / "texture" / "texture.cfg"
            if not texture_cfg.exists():
                texture_cfg.write_text(
                    "[fltsim]\n"
                    "fallback.1=..\n"
                    "\n",
                    encoding="utf-8",
                )

            # Create layout.json for the HGS package.
            # Build it from the files that ACTUALLY exist on disk so MSFS package
            # integrity verification doesn't reject the package for phantom entries
            # (previously it referenced model/*.bin and texture/*.png that were
            # never created).
            layout_path = package_root / "layout.json"
            content_entries = []
            for f in sorted(package_root.rglob("*")):
                if f.is_file() and f.name != "layout.json":
                    rel = f.relative_to(package_root).as_posix()
                    stat = f.stat()
                    content_entries.append({
                        "path": rel,
                        "size": stat.st_size,
                        "date": int(stat.st_mtime * 1e7) + 116444736000000000,  # FILETIME
                    })
            layout_content = {"content": content_entries}
            layout_path.write_text(json.dumps(layout_content, indent=2), encoding="utf-8")

            logger.info(f"Copied HGS package to {package_root}")
            return True

        except Exception as e:
            logger.error(f"Failed to copy HGS package to Community: {e}")
            return False

    @staticmethod
    def remove_hgs_from_community(community_path: Path) -> bool:
        """
        Remove the HGS package from the Community folder.

        Args:
            community_path: Path to the MSFS Community folder.

        Returns:
            True if removal was successful.
        """
        package_root = community_path / "C_HUD_Runway"
        if not package_root.exists():
            logger.info(f"HGS package not found at {package_root}")
            return True

        try:
            shutil.rmtree(package_root)
            logger.info(f"Removed HGS package from {package_root}")
            return True
        except Exception as e:
            logger.error(f"Failed to remove HGS package: {e}")
            return False

    @staticmethod
    def verify_hgs_in_community(community_path: Path) -> bool:
        """Verify that the HGS package is correctly installed in the Community folder."""
        package_root = community_path / "C_HUD_Runway"
        required_files = [
            "SimObjects/Airplanes/C_HUD_Runway/panel/panel.cfg",
            "SimObjects/Airplanes/C_HUD_Runway/panel/C_HUD_Runway.wasm",
            "SimObjects/Airplanes/C_HUD_Runway/panel/HUD/hud_overlay.html",
            "SimObjects/Airplanes/C_HUD_Runway/aircraft.cfg",
        ]

        for rel_path in required_files:
            if not (package_root / rel_path).exists():
                logger.warning(f"Missing required file: {rel_path}")
                return False

        # Check layout.json
        layout_path = package_root / "layout.json"
        if not layout_path.exists():
            logger.warning("Missing layout.json in HGS package")
            return False

        return True


# =========================================================================
#  8.  Patch Engine (orchestrator)
# =========================================================================

class PatchEngine:
    """
    Main patching orchestrator.

    Coordinates backup creation, file patching, and transaction management
    to provide safe and reversible aircraft integration.
    """

    def __init__(self, community_path: Optional[Path] = None):
        self.community_path = community_path
        self.backup_engine = BackupEngine()
        self.transaction: Optional[PatchTransaction] = None

    def set_community_path(self, path: Path):
        """Set the Community folder path."""
        self.community_path = path

    def install_hgs_to_aircraft(self, pkg: AircraftPackage) -> bool:
        """
        Install HGS integration into a single aircraft package.

        This is the main entry point for integration.

        Steps:
          1. Create backup
          2. Copy HGS package to Community folder (if not already there)
          3. Patch aircraft layout.json
          4. Patch aircraft panel.cfg
          5. Verify integration
          6. Commit transaction

        Args:
            pkg: The aircraft package to integrate with.

        Returns:
            True if installation was successful.
        """
        if self.community_path is None:
            logger.error("Community path not set. Call set_community_path() first.")
            return False

        # Start transaction
        transaction_id = f"txn_{int(time.time())}"
        self.transaction = PatchTransaction(
            transaction_id=transaction_id,
            aircraft_package=pkg.package_path.name,
            created_at=time.time(),
        )

        try:
            # Step 1: Create backup
            logger.info(f"Step 1: Creating backup of {pkg.aircraft_type.value}")
            backup = self.backup_engine.create_backup(pkg, "pre_install")
            if backup is None:
                self.transaction.status = "failed"
                self.transaction.error = "Backup creation failed"
                return False

            # Step 2: Copy HGS package to Community
            logger.info(f"Step 2: Copying HGS package to Community folder")
            if not FileCopier.copy_hgs_to_community(self.community_path):
                self.transaction.status = "failed"
                self.transaction.error = "Failed to copy HGS package"
                return False

            op2 = PatchOperation(
                operation_id=f"{transaction_id}_copy",
                aircraft_package=pkg.package_path.name,
                patch_type="file_copy",
                target_path=str(self.community_path / "C_HUD_Runway"),
                backup_id=backup.id,
                status="applied",
                timestamp=time.time(),
            )
            self.transaction.operations.append(op2)

            # Step 3: Patch aircraft layout.json
            logger.info(f"Step 3: Patching layout.json")
            if pkg.layout_path:
                checksum_before = compute_file_checksum(pkg.layout_path)
                if LayoutPatcher.patch_layout(pkg.layout_path):
                    checksum_after = compute_file_checksum(pkg.layout_path)
                    op3 = PatchOperation(
                        operation_id=f"{transaction_id}_layout",
                        aircraft_package=pkg.package_path.name,
                        patch_type="layout_json",
                        target_path=str(pkg.layout_path),
                        backup_id=backup.id,
                        status="applied",
                        checksum_before=checksum_before,
                        checksum_after=checksum_after,
                        timestamp=time.time(),
                    )
                    self.transaction.operations.append(op3)

            # Step 4: Patch aircraft panel.cfg
            logger.info(f"Step 4: Patching panel.cfg")
            for panel_cfg in pkg.panel_configs:
                checksum_before = compute_file_checksum(panel_cfg.path)
                if PanelCfgPatcher.patch_panel(panel_cfg.path):
                    checksum_after = compute_file_checksum(panel_cfg.path)
                    op4 = PatchOperation(
                        operation_id=f"{transaction_id}_panel",
                        aircraft_package=pkg.package_path.name,
                        patch_type="panel_cfg",
                        target_path=str(panel_cfg.path),
                        backup_id=backup.id,
                        status="applied",
                        checksum_before=checksum_before,
                        checksum_after=checksum_after,
                        timestamp=time.time(),
                    )
                    self.transaction.operations.append(op4)

            # Step 5: Verify
            logger.info(f"Step 5: Verifying integration")
            verification = self.verify_integration(pkg)
            if not verification["success"]:
                logger.warning(f"Integration verification had issues: {verification['issues']}")

            # Step 6: Commit
            self.transaction.status = "committed"
            self.transaction.committed_at = time.time()
            logger.info(f"Installation complete for {pkg.aircraft_type.value}")
            return True

        except Exception as e:
            logger.error(f"Installation failed: {e}")
            if self.transaction:
                self.transaction.status = "failed"
                self.transaction.error = str(e)
            return False

    def uninstall_hgs_from_aircraft(self, pkg: AircraftPackage) -> bool:
        """
        Uninstall HGS integration from a single aircraft package.

        Steps:
          1. Create backup (just in case)
          2. Unpatch panel.cfg
          3. Unpatch layout.json
          4. Verify removal

        Args:
            pkg: The aircraft package to uninstall from.

        Returns:
            True if uninstallation was successful.
        """
        try:
            # Step 1: Create backup
            logger.info(f"Creating pre-uninstall backup of {pkg.aircraft_type.value}")
            self.backup_engine.create_backup(pkg, "pre_uninstall")

            # Step 2: Unpatch panel.cfg
            for panel_cfg in pkg.panel_configs:
                if not PanelCfgPatcher.unpatch_panel(panel_cfg.path):
                    logger.warning(f"Failed to unpanel.cfg at {panel_cfg.path}")

            # Step 3: Unpatch layout.json
            if pkg.layout_path:
                if not LayoutPatcher.unpatch_layout(pkg.layout_path):
                    logger.warning(f"Failed to unpatch layout.json at {pkg.layout_path}")

            # Step 4: Remove HGS package
            if self.community_path:
                FileCopier.remove_hgs_from_community(self.community_path)

            logger.info(f"Uninstall complete for {pkg.aircraft_type.value}")
            return True

        except Exception as e:
            logger.error(f"Uninstall failed: {e}")
            return False

    def verify_integration(self, pkg: AircraftPackage) -> Dict:
        """Verify that HGS integration is correctly installed."""
        issues = []
        success = True

        # Check panel.cfg integration
        for panel_cfg in pkg.panel_configs:
            if not PanelCfgPatcher.has_hgs_entries(panel_cfg.path):
                issues.append(f"Missing HGS entries in {panel_cfg.path}")
                success = False

        # Check layout.json integration
        if pkg.layout_path and not LayoutPatcher.has_hgs_entries(pkg.layout_path):
            issues.append(f"Missing HGS entries in {pkg.layout_path}")
            success = False

        # Check HGS package in Community
        if self.community_path and not FileCopier.verify_hgs_in_community(self.community_path):
            issues.append("HGS package missing or incomplete in Community folder")
            success = False

        return {
            "success": success,
            "issues": issues,
            "aircraft": pkg.aircraft_type.value,
        }

    def rollback_transaction(self) -> bool:
        """Roll back the current transaction."""
        if self.transaction is None:
            logger.warning("No active transaction to rollback")
            return False

        logging.info(f"Rolling back transaction: {self.transaction.transaction_id}")

        try:
            # Reverse operations in reverse order
            for op in reversed(self.transaction.operations):
                if op.patch_type == "panel_cfg":
                    PanelCfgPatcher.unpatch_panel(Path(op.target_path))
                elif op.patch_type == "layout_json":
                    LayoutPatcher.unpatch_layout(Path(op.target_path))

            # Restore from backup
            backup = self.backup_engine.get_backup_for_package(
                self.transaction.aircraft_package
            )
            if backup:
                self.backup_engine.restore_backup(backup)

            self.transaction.status = "rolled_back"
            logger.info("Transaction rolled back successfully")
            return True

        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            self.transaction.status = "failed"
            self.transaction.error = f"Rollback failed: {e}"
            return False


# =========================================================================
#  CLI entry point
# =========================================================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Patch Engine Test")
    print("=" * 60)
    print(f"Backup directory: {BACKUP_DIR}")
    print(f"Engine ready.")
