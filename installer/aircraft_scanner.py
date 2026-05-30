"""
Aircraft Package Scanner — Phase 2
===================================
Scans the MSFS Community folder for supported aircraft packages.

Detects:
  · PMDG 737-800 / 737-700
  · PMDG 777-300ER
  · WT/Asobo 787-10
  · iniBuilds A350
  · FBW A32NX
  · Headwind A330-900

For each detected aircraft, the scanner identifies:
  · Installed version (from manifest or layout.json)
  · Package structure (layout.json format)
  · panel.cfg location(s)
  · Existing HUD integrations
  · Unsupported or modified installs
"""

import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger("aircraft_scanner")


# =========================================================================
#  1.  Enums & Dataclasses
# =========================================================================

class AircraftType(Enum):
    """Supported aircraft types."""
    PMDG_737_800 = "PMDG 737-800"
    PMDG_737_700 = "PMDG 737-700"
    PMDG_777_300ER = "PMDG 777-300ER"
    ASOBO_787_10 = "ASOBO 787-10"
    WT_787_10 = "WT 787-10"
    INIBUILDS_A350 = "iniBuilds A350"
    FBW_A32NX = "FBW A32NX"
    FBW_A380 = "FBW A380"
    FENIX_A320 = "FENIX A320"
    HEADWIND_A330_900 = "HEADWIND A330-900"

    @classmethod
    def from_prefix(cls, prefix: str) -> Optional["AircraftType"]:
        """Match an aircraft type from a title prefix (case-insensitive)."""
        mapping = {
            "PMDG 737-800": cls.PMDG_737_800,
            "PMDG 737-700": cls.PMDG_737_700,
            "PMDG 777-300ER": cls.PMDG_777_300ER,
            "ASOBO 787-10": cls.ASOBO_787_10,
            "WT 787-10": cls.WT_787_10,
            "INIBUILDS A350": cls.INIBUILDS_A350,
            "FBW A32NX": cls.FBW_A32NX,
            "FBW A380": cls.FBW_A380,
            "FENIX A320": cls.FENIX_A320,
            "HEADWIND A330-900": cls.HEADWIND_A330_900,
        }
        upper = prefix.upper().strip()
        for key, atype in mapping.items():
            if upper.startswith(key.upper()):
                return atype
        return None


class IntegrationStatus(Enum):
    """Status of HGS/HUD integration for an aircraft."""
    NOT_INSTALLED = "not_installed"
    INSTALLED = "installed"
    NEEDS_REPAIR = "needs_repair"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"


@dataclass
class LayoutEntry:
    """A single entry in a layout.json file."""
    path: str
    size: int
    date: int

    @classmethod
    def from_dict(cls, d: dict) -> "LayoutEntry":
        return cls(
            path=d.get("path", ""),
            size=d.get("size", 0),
            date=d.get("date", 0),
        )


@dataclass
class PanelConfig:
    """Information about an aircraft's panel configuration."""
    path: Path
    entries: List[Dict] = field(default_factory=list)
    has_hud_gauge: bool = False
    has_html_hud: bool = False
    wasm_gauge_name: Optional[str] = None


@dataclass
class AircraftPackage:
    """Describes a scanned aircraft package."""
    package_path: Path              # Root of the aircraft package in Community
    aircraft_type: AircraftType     # Identified type
    title_prefix: str               # Matched title prefix
    layout_path: Optional[Path] = None  # Path to layout.json (None if not found)
    layout_entries: List[LayoutEntry] = field(default_factory=list)
    panel_configs: List[PanelConfig] = field(default_factory=list)
    manifest_version: str = "0.0.0"  # Version from manifest.json if available
    detected_version_major: int = 0
    detected_version_minor: int = 0
    hgs_integrated: bool = False     # Whether HGS panel entries exist
    integration_status: IntegrationStatus = IntegrationStatus.NOT_INSTALLED
    is_modified: bool = False        # Detected as modified from original
    is_official: bool = False        # Located in Official (OneStore) folder — not Community
    is_official_backed_up: bool = False  # Backed up before patching (mandatory for official)
    errors: List[str] = field(default_factory=list)

    @property
    def is_supported(self) -> bool:
        """Whether this aircraft is officially supported by the HGS system."""
        return True  # All scanned types are supported


# =========================================================================
#  2.  Known package identifiers
# =========================================================================

# Patterns used to identify aircraft packages in the Community folder
# NOTE: matching is performed against the *Community folder name*, which for
# most real packages uses ICAO/vendor codes rather than the marketing name:
#   PMDG 737-800  ->  pmdg-aircraft-738       PMDG 777-300ER -> pmdg-aircraft-77w
#   FBW A32NX     ->  flybywire-aircraft-a320-neo (note: "a320", NOT "a32nx")
#   FBW A380      ->  flybywire-aircraft-a380-842
#   Fenix A320    ->  fenix-a320 / fnx-320-airbus
#   iniBuilds A350->  inibuilds-aircraft-a350 Headwind A330 -> headwindsim-aircraft-a330-900
# Order matters: most specific patterns first.
AIRCRAFT_PACKAGE_PATTERNS = [
    # PMDG 737  (738 = -800, 737/736 = -700, ICAO codes in folder names)
    (re.compile(r'pmdg.*73[78].*800', re.IGNORECASE), AircraftType.PMDG_737_800),
    (re.compile(r'pmdg.*73[67].*700', re.IGNORECASE), AircraftType.PMDG_737_700),
    (re.compile(r'pmdg.*738', re.IGNORECASE), AircraftType.PMDG_737_800),
    (re.compile(r'pmdg.*736', re.IGNORECASE), AircraftType.PMDG_737_700),
    (re.compile(r'pmdg.*737', re.IGNORECASE), AircraftType.PMDG_737_800),  # fallback
    # PMDG 777  (77w = 777-300ER)
    (re.compile(r'pmdg.*777.*300', re.IGNORECASE), AircraftType.PMDG_777_300ER),
    (re.compile(r'pmdg.*77w', re.IGNORECASE), AircraftType.PMDG_777_300ER),
    (re.compile(r'pmdg.*777', re.IGNORECASE), AircraftType.PMDG_777_300ER),  # fallback
    # Boeing 787
    (re.compile(r'asobo.*787', re.IGNORECASE), AircraftType.ASOBO_787_10),
    (re.compile(r'wt.*787', re.IGNORECASE), AircraftType.WT_787_10),
    (re.compile(r'787.*10', re.IGNORECASE), AircraftType.ASOBO_787_10),  # fallback
    # iniBuilds A350
    (re.compile(r'inibuilds.*a350', re.IGNORECASE), AircraftType.INIBUILDS_A350),
    (re.compile(r'a350', re.IGNORECASE), AircraftType.INIBUILDS_A350),
    # FBW A380  (must come before generic a380/a32nx so A380 wins)
    (re.compile(r'flybywire.*a380', re.IGNORECASE), AircraftType.FBW_A380),
    (re.compile(r'fbw.*a380', re.IGNORECASE), AircraftType.FBW_A380),
    (re.compile(r'a380', re.IGNORECASE), AircraftType.FBW_A380),
    # FBW A32NX  (real folder is "flybywire-aircraft-a320-neo": matches a320, not a32nx)
    (re.compile(r'flybywire.*a32(0|nx)', re.IGNORECASE), AircraftType.FBW_A32NX),
    (re.compile(r'fbw.*a32(0|nx)', re.IGNORECASE), AircraftType.FBW_A32NX),
    (re.compile(r'a32nx', re.IGNORECASE), AircraftType.FBW_A32NX),
    # Fenix A320  (fenix-a320 / fnx-320-airbus)
    (re.compile(r'fenix.*a?320', re.IGNORECASE), AircraftType.FENIX_A320),
    (re.compile(r'fnx.*320', re.IGNORECASE), AircraftType.FENIX_A320),
    # Headwind A330
    (re.compile(r'headwind.*a330', re.IGNORECASE), AircraftType.HEADWIND_A330_900),
    (re.compile(r'a330.*900', re.IGNORECASE), AircraftType.HEADWIND_A330_900),
]

# Known SimObjects paths for supported aircraft
AIRCRAFT_SIMOBJECT_PATHS = {
    AircraftType.PMDG_737_800: ["SimObjects/Airplanes/PMDG 737-800"],
    AircraftType.PMDG_737_700: ["SimObjects/Airplanes/PMDG 737-700"],
    AircraftType.PMDG_777_300ER: ["SimObjects/Airplanes/PMDG 777-300ER"],
    AircraftType.ASOBO_787_10: ["SimObjects/Airplanes/Asobo_787_10", "SimObjects/Airplanes/ASOBO_787_10"],
    AircraftType.WT_787_10: ["SimObjects/Airplanes/WT_787_10"],
    AircraftType.INIBUILDS_A350: ["SimObjects/Airplanes/iniBuilds_A350"],
    AircraftType.FBW_A32NX: ["SimObjects/Airplanes/FlyByWire_A320_NEO", "SimObjects/Airplanes/FBW_A32NX"],
    AircraftType.FBW_A380: ["SimObjects/Airplanes/FlyByWire_A380_842", "SimObjects/Airplanes/FBW_A380"],
    AircraftType.FENIX_A320: ["SimObjects/Airplanes/FNX-320-AIRBUS", "SimObjects/Airplanes/Fenix_A320"],
    AircraftType.HEADWIND_A330_900: ["SimObjects/Airplanes/Headwind_A330_900"],
}

# The panel.cfg entry we look for to confirm our HGS integration
HGS_PANEL_GAUGE_MARKER = "C_HUD_Runway!Gauge_ConformalHUD"
HGS_HTML_MARKER = "HUD/hud_overlay.html"


# =========================================================================
#  3.  Scanner implementation
# =========================================================================

def scan_community(community_path: Path) -> List[AircraftPackage]:
    """
    Scan the Community folder for supported aircraft packages.

    Args:
        community_path: Path to the MSFS Community folder.

    Returns:
        List of detected AircraftPackage objects.
    """
    if not community_path.exists():
        logger.warning(f"Community folder does not exist: {community_path}")
        return []

    logger.info(f"Scanning Community folder: {community_path}")
    packages: List[AircraftPackage] = []
    seen_packages: Set[str] = set()

    try:
        entries = sorted(community_path.iterdir())
    except PermissionError as e:
        logger.error(f"Permission denied scanning {community_path}: {e}")
        return []

    for entry in entries:
        # A single inaccessible/read-only entry must not abort the whole scan.
        try:
            if not entry.is_dir():
                continue
        except (PermissionError, OSError) as e:
            logger.warning(f"Skipping inaccessible entry {entry}: {e}")
            continue
        if entry.name.startswith("."):
            continue

        try:
            pkg = _scan_single_package(entry)
        except (PermissionError, OSError) as e:
            logger.warning(f"Skipping unreadable package {entry}: {e}")
            continue
        if pkg is not None:
            # Deduplicate by package path
            key = str(pkg.package_path.resolve())
            if key not in seen_packages:
                seen_packages.add(key)
                packages.append(pkg)
                logger.info(f"  Detected: {pkg.aircraft_type.value} @ {entry.name}")
            else:
                logger.debug(f"  Skipping duplicate: {entry.name}")

    logger.info(f"Scan complete. Found {len(packages)} supported aircraft package(s).")
    return packages


def scan_official(official_path: Path) -> List[AircraftPackage]:
    """
    Scan the MSFS Official (OneStore) folder for supported aircraft packages.

    Official packages (e.g. asobo-aircraft-787-10 from the base sim) live under
    Official/OneStore/... or Official/Steam/... rather than Community/.
    Patching these carries extra risk because they are base-sim files — the
    function tags each detected package with ``is_official=True`` and issues
    a warning.

    The scanner reuses the same ``_scan_single_package()`` logic used by
    ``scan_community()`` — only the root path differs.

    Args:
        official_path: Path to the MSFS Official folder (e.g.
                       ``Official/OneStore`` or ``Official/Steam``).

    Returns:
        List of detected AircraftPackage objects flagged as official.
    """
    if not official_path.exists():
        logger.warning(f"Official folder does not exist: {official_path}")
        return []

    logger.info(f"Scanning Official folder: {official_path}")
    packages: List[AircraftPackage] = []
    seen_packages: Set[str] = set()

    # Official packages are organised under sub-directories (OneStore, Steam, etc.)
    # Each sub-directory contains publisher/aircraft folders.
    try:
        entries = sorted(official_path.iterdir())
    except PermissionError as e:
        logger.error(f"Permission denied scanning {official_path}: {e}")
        return []

    for entry in entries:
        try:
            if not entry.is_dir():
                continue
        except (PermissionError, OSError) as e:
            logger.warning(f"Skipping inaccessible entry {entry}: {e}")
            continue
        if entry.name.startswith("."):
            continue

        # Official store may have nested publisher directories (e.g. "asobo/aircraft-787-10")
        # or flat aircraft folder names.  Try both.
        try:
            sub_entries = sorted(entry.iterdir())
        except (PermissionError, OSError):
            # Try this entry itself as a package directory
            pkg = _scan_single_package(entry)
            if pkg is not None:
                pkg.is_official = True
                key = str(pkg.package_path.resolve())
                if key not in seen_packages:
                    seen_packages.add(key)
                    packages.append(pkg)
                    logger.info(f"  Detected (official): {pkg.aircraft_type.value} @ {entry.name}")
            continue

        # Check if sub-entries are aircraft packages
        found_any = False
        for sub in sub_entries:
            try:
                if not sub.is_dir() or sub.name.startswith("."):
                    continue
            except (PermissionError, OSError):
                continue

            pkg = _scan_single_package(sub)
            if pkg is not None:
                pkg.is_official = True
                key = str(pkg.package_path.resolve())
                if key not in seen_packages:
                    seen_packages.add(key)
                    packages.append(pkg)
                    logger.info(f"  Detected (official): {pkg.aircraft_type.value} @ {sub.name}")
                    found_any = True

        # If no sub-directory matched, try the entry directory itself
        if not found_any:
            pkg = _scan_single_package(entry)
            if pkg is not None:
                pkg.is_official = True
                key = str(pkg.package_path.resolve())
                if key not in seen_packages:
                    seen_packages.add(key)
                    packages.append(pkg)
                    logger.info(f"  Detected (official): {pkg.aircraft_type.value} @ {entry.name}")

    if packages:
        logger.warning(
            f"Found {len(packages)} official aircraft package(s) — "
            "patching base-sim files is risky. Backups are REQUIRED."
        )

    logger.info(f"Official scan complete. Found {len(packages)} supported aircraft package(s).")
    return packages



def _scan_single_package(package_dir: Path) -> Optional[AircraftPackage]:
    """Scan a single directory to determine if it's a supported aircraft package."""
    # Identify the aircraft type from the directory name
    aircraft_type = _identify_aircraft_type(package_dir.name)
    if aircraft_type is None:
        return None

    title_prefix = aircraft_type.value
    layout_path = package_dir / "layout.json"
    layout_entries: List[LayoutEntry] = []
    panel_configs: List[PanelConfig] = []
    errors: List[str] = []

    # Parse layout.json
    if layout_path.exists():
        try:
            layout_data = json.loads(layout_path.read_text(encoding="utf-8"))
            if isinstance(layout_data, dict) and "content" in layout_data:
                for entry in layout_data["content"]:
                    layout_entries.append(LayoutEntry.from_dict(entry))
            elif isinstance(layout_data, list):
                for entry in layout_data:
                    layout_entries.append(LayoutEntry.from_dict(entry))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            errors.append(f"Failed to parse layout.json: {e}")
            logger.warning(f"  {package_dir.name}: Invalid layout.json - {e}")

    # Find and parse panel.cfg files
    panel_configs = _find_panel_configs(package_dir, layout_entries)

    # Detect version from manifest.json or layout.json
    version_major, version_minor = _detect_version(package_dir, layout_entries)

    # Determine integration status
    hgs_integrated = any(pc.has_hud_gauge for pc in panel_configs)
    integration_status = _determine_integration_status(hgs_integrated, panel_configs)

    # Check if modified
    is_modified = _check_modified(package_dir, layout_entries)

    return AircraftPackage(
        package_path=package_dir,
        aircraft_type=aircraft_type,
        title_prefix=title_prefix,
        layout_path=layout_path if layout_path.exists() else None,
        layout_entries=layout_entries,
        panel_configs=panel_configs,
        detected_version_major=version_major,
        detected_version_minor=version_minor,
        hgs_integrated=hgs_integrated,
        integration_status=integration_status,
        is_modified=is_modified,
        errors=errors,
    )


def _identify_aircraft_type(dir_name: str) -> Optional[AircraftType]:
    """Identify the aircraft type from a directory name using pattern matching."""
    for pattern, atype in AIRCRAFT_PACKAGE_PATTERNS:
        if pattern.search(dir_name):
            return atype
    return None


def _find_panel_configs(package_dir: Path, layout_entries: List[LayoutEntry]) -> List[PanelConfig]:
    """Find and parse panel.cfg files in the package."""
    panel_configs: List[PanelConfig] = []

    # Search via layout.json entries
    panel_cfg_paths = set()
    for entry in layout_entries:
        if entry.path.endswith("panel.cfg"):
            full_path = package_dir / entry.path
            panel_cfg_paths.add(full_path)

    # Also search common locations directly
    for pattern in [
        "SimObjects/Airplanes/*/panel/panel.cfg",
        "SimObjects/Airplanes/*/panel/*/panel.cfg",
    ]:
        # Use glob for the common structure
        for found in package_dir.glob(pattern.replace("*", "**")):
            if found.exists() and found.is_file():
                panel_cfg_paths.add(found.resolve())

    # Also check for panel.cfg in the root or common paths
    for root_dir in [package_dir / "panel", package_dir]:
        candidate = root_dir / "panel.cfg"
        if candidate.exists():
            panel_cfg_paths.add(candidate.resolve())

    # Parse each unique panel.cfg
    for cfg_path in panel_cfg_paths:
        try:
            pc = _parse_panel_config(cfg_path)
            if pc:
                panel_configs.append(pc)
        except Exception as e:
            logger.warning(f"  Failed to parse {cfg_path}: {e}")

    return panel_configs


def _parse_panel_config(cfg_path: Path) -> Optional[PanelConfig]:
    """Parse a panel.cfg file and extract gauge/HTML entries."""
    if not cfg_path.exists():
        return None

    try:
        content = cfg_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        logger.warning(f"  Cannot read {cfg_path}: {e}")
        return None

    entries = []
    has_hud_gauge = False
    has_html_hud = False
    wasm_gauge_name = None

    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith(";") or line.startswith("//") or line.startswith("#"):
            continue

        # Check for HTML gauge entries (starts with 'htmlgauge')
        if line.lower().startswith("htmlgauge") and "=" in line:
            entries.append({"raw": line, "type": "htmlgauge"})
            if HGS_HTML_MARKER in line:
                has_html_hud = True

        # Check for WASM gauge entries (starts with 'gauge' but not 'htmlgauge')
        elif line.lower().startswith("gauge") and "=" in line:
            entries.append({"raw": line, "type": "gauge"})
            if HGS_PANEL_GAUGE_MARKER in line:
                has_hud_gauge = True
                # Extract gauge name
                match = re.search(r'=\s*([^!]+)', line)
                if match:
                    wasm_gauge_name = match.group(1).strip()

    return PanelConfig(
        path=cfg_path,
        entries=entries,
        has_hud_gauge=has_hud_gauge,
        has_html_hud=has_html_hud,
        wasm_gauge_name=wasm_gauge_name,
    )


def _detect_version(package_dir: Path, layout_entries: List[LayoutEntry]) -> Tuple[int, int]:
    """Detect the installed version from manifest.json or layout.json metadata."""
    # Try manifest.json
    manifest_path = package_dir / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            version_str = manifest.get("version", "0.0.0")
            parts = version_str.split(".")
            if len(parts) >= 2:
                return int(parts[0]), int(parts[1])
        except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
            pass

    # Try to extract from layout.json date patterns (approximate version)
    if layout_entries:
        # Use the most recent date as an approximate version indicator
        max_date = max(e.date for e in layout_entries)
        # Map dates to version numbers (heuristic)
        if max_date > 2000000000:
            return 2, 0
        elif max_date > 1000000000:
            return 1, 0

    return 0, 0


def _determine_integration_status(
    hgs_integrated: bool,
    panel_configs: List[PanelConfig],
) -> IntegrationStatus:
    """Determine the integration status of the HGS system for this aircraft."""
    if not hgs_integrated:
        return IntegrationStatus.NOT_INSTALLED

    # Check if the integration is complete (both WASM gauge and HTML overlay)
    all_have_gauge = all(pc.has_hud_gauge for pc in panel_configs if pc.entries)
    all_have_html = all(pc.has_html_hud for pc in panel_configs if pc.entries)

    if all_have_gauge and all_have_html:
        return IntegrationStatus.INSTALLED
    elif all_have_gauge or all_have_html:
        return IntegrationStatus.NEEDS_REPAIR
    else:
        return IntegrationStatus.UNKNOWN


def _check_modified(package_dir: Path, layout_entries: List[LayoutEntry]) -> bool:
    """Check if the package appears to be modified from its original state."""
    # A modified package might have entries that don't match the original layout
    # This is a heuristic - we check for known HGS files that we injected
    hgs_files = [
        "C_HUD_Runway.wasm",
        "HUD/hud_overlay.html",
        "HUD/hud_overlay.js",
    ]

    has_hgs_files = any(
        any(hgs in entry.path for hgs in hgs_files)
        for entry in layout_entries
    )

    return has_hgs_files


# =========================================================================
#  4.  Aircraft matching by title string
# =========================================================================

def match_aircraft_type_from_title(title: str) -> Optional[AircraftType]:
    """Match the best aircraft type from an MSFS aircraft title string."""
    atype = AircraftType.from_prefix(title)
    if atype:
        return atype

    # Fall back to pattern matching
    for pattern, matched_type in AIRCRAFT_PACKAGE_PATTERNS:
        if pattern.search(title):
            return matched_type

    return None


def is_title_supported(title: str) -> bool:
    """Check if an aircraft title is supported by the HGS system."""
    return match_aircraft_type_from_title(title) is not None


# =========================================================================
#  5.  Package structure analysis
# =========================================================================

def analyze_package_structure(pkg: AircraftPackage) -> Dict:
    """Analyze the structure of an aircraft package and return a report."""
    report = {
        "package_name": pkg.package_path.name,
        "aircraft_type": pkg.aircraft_type.value,
        "layout_format": "unknown",
        "total_entries": len(pkg.layout_entries),
        "panel_config_count": len(pkg.panel_configs),
        "hgs_integrated": pkg.hgs_integrated,
        "integration_status": pkg.integration_status.value,
        "version": f"{pkg.detected_version_major}.{pkg.detected_version_minor}",
        "errors": pkg.errors,
    }

    # Determine layout format
    if pkg.layout_path:
        try:
            data = json.loads(pkg.layout_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "content" in data:
                report["layout_format"] = "dict_with_content"
            elif isinstance(data, list):
                report["layout_format"] = "array"
        except (json.JSONDecodeError, UnicodeDecodeError):
            report["layout_format"] = "invalid"

    return report


# =========================================================================
#  6.  Compatibility mapping
# =========================================================================

def get_aircraft_compatibility_map() -> Dict[str, Dict]:
    """
    Return the full compatibility map between aircraft types and HGS profiles.

    This mirrors the C++ compatibility signatures defined in the aircraft detector.
    """
    return {
        "PMDG 737-800": {
            "profile_index": 0,
            "version_major": 3,
            "version_minor": 0,
            "requires_panel_fix": False,
            "requires_eye_offset": True,
            "eye_offset_correction_m": 0.05,
        },
        "PMDG 737-700": {
            "profile_index": 0,
            "version_major": 3,
            "version_minor": 0,
            "requires_panel_fix": False,
            "requires_eye_offset": True,
            "eye_offset_correction_m": 0.05,
        },
        "PMDG 777-300ER": {
            "profile_index": 1,
            "version_major": 1,
            "version_minor": 0,
            "requires_panel_fix": False,
            "requires_eye_offset": True,
            "eye_offset_correction_m": 0.03,
        },
        "ASOBO 787-10": {
            "profile_index": 2,
            "version_major": 1,
            "version_minor": 34,
            "requires_panel_fix": True,
            "requires_eye_offset": False,
            "eye_offset_correction_m": 0.0,
        },
        "WT 787-10": {
            "profile_index": 3,
            "version_major": 1,
            "version_minor": 0,
            "requires_panel_fix": True,
            "requires_eye_offset": False,
            "eye_offset_correction_m": 0.0,
        },
        "iniBuilds A350": {
            "profile_index": 4,
            "version_major": 1,
            "version_minor": 2,
            "requires_panel_fix": True,
            "requires_eye_offset": True,
            "eye_offset_correction_m": -0.02,
        },
        "FBW A32NX": {
            "profile_index": 5,
            "version_major": 1,
            "version_minor": 0,
            "requires_panel_fix": False,
            "requires_eye_offset": False,
            "eye_offset_correction_m": 0.0,
        },
        "HEADWIND A330-900": {
            "profile_index": 5,
            "version_major": 1,
            "version_minor": 0,
            "requires_panel_fix": False,
            "requires_eye_offset": False,
            "eye_offset_correction_m": 0.0,
        },
    }


def check_version_compatibility(pkg: AircraftPackage) -> bool:
    """Check if the aircraft version is compatible with the HGS system.
    
    Uses proper semver comparison: an aircraft is compatible if its version
    is >= the expected version (major.minor).
    """
    compat_map = get_aircraft_compatibility_map()
    key = pkg.aircraft_type.value
    if key not in compat_map:
        return False

    expected = compat_map[key]
    # Proper semver comparison
    if pkg.detected_version_major > expected["version_major"]:
        return True
    if pkg.detected_version_major == expected["version_major"]:
        return pkg.detected_version_minor >= expected["version_minor"]
    return False


# =========================================================================
#  CLI entry point
# =========================================================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    import sys
    if len(sys.argv) > 1:
        community_path = Path(sys.argv[1])
    else:
        from installer.msfs_detector import find_community_folder
        community_path = find_community_folder()
        if community_path is None:
            print("Could not auto-detect Community folder. Provide path as argument.")
            sys.exit(1)

    print(f"\nScanning: {community_path}\n")
    packages = scan_community(community_path)

    if packages:
        print(f"Found {len(packages)} supported aircraft package(s):\n")
        for pkg in packages:
            status = pkg.integration_status.value
            print(f"  [{status.upper()}] {pkg.aircraft_type.value}")
            print(f"          Path: {pkg.package_path.name}")
            print(f"          Version: {pkg.detected_version_major}.{pkg.detected_version_minor}")
            print(f"          HGS Integrated: {pkg.hgs_integrated}")
            print(f"          Panel configs: {len(pkg.panel_configs)}")
            if pkg.errors:
                for err in pkg.errors:
                    print(f"          Error: {err}")
            print()
    else:
        print("No supported aircraft packages found.")
