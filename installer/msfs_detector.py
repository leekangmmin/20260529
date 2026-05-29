"""
MSFS Installation Detection — Phase 1
======================================
Detects MSFS 2020/2024 installations via:

  · Windows Registry (MS Store)
  · Windows Registry (Steam)
  · Custom install paths
  · UserCfg.opt parsing
  · Symbolic link resolution
  · Common default locations

Exports:
  - detect_msfs_installations() -> List[MsfsInstallation]
  - find_community_folder() -> Optional[str]
  - find_official_folder() -> Optional[str]
"""

import json
import logging
import os
import platform
import re
import sys
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
#  Logger
# ---------------------------------------------------------------------------
logger = logging.getLogger("msfs_detector")


# ---------------------------------------------------------------------------
#  Enums & Dataclasses
# ---------------------------------------------------------------------------

class MsfsSource(Enum):
    """Origin of the MSFS installation."""
    MS_STORE = auto()
    STEAM = auto()
    CUSTOM = auto()
    BOXED = auto()


class MsfsVersion(Enum):
    """Detected MSFS version."""
    MSFS2020 = "MSFS 2020"
    MSFS2024 = "MSFS 2024"


@dataclass
class MsfsInstallation:
    """Describes a single MSFS installation."""
    path: Path                     # Root install path
    source: MsfsSource             # How it was installed
    version: MsfsVersion           # 2020 or 2024
    community_path: Optional[Path] = None
    official_path: Optional[Path] = None
    localcache_path: Optional[Path] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
#  Known registry keys (Windows only)
# ---------------------------------------------------------------------------

# MS Store version (Packaged) — MSFS 2020
MS_STORE_KEYS_2020 = [
    # Microsoft Store package installation path
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\MSFS.exe",
    # Official MS Store InstallLocation
    r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Microsoft.FlightSimulator_8wekyb3d8bbwe",
    # Package root via Packages registry
    r"SOFTWARE\Classes\Local Settings\Software\Microsoft\Windows\CurrentVersion\AppModel\Repository\Packages\Microsoft.FlightSimulator_8wekyb3d8bbwe",
]

# MS Store version (Packaged) — MSFS 2024
MS_STORE_KEYS_2024 = [
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\MSFS2024.exe",
    r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Microsoft.FlightSimulator2024_8wekyb3d8bbwe",
    r"SOFTWARE\Classes\Local Settings\Software\Microsoft\Windows\CurrentVersion\AppModel\Repository\Packages\Microsoft.FlightSimulator2024_8wekyb3d8bbwe",
]

# Steam version — MSFS 2020
STEAM_KEYS_2020 = [
    r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Steam App 1250410",
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Steam App 1250410",
]

# Steam version — MSFS 2024
STEAM_KEYS_2024 = [
    r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Steam App 2470030",
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Steam App 2470030",
]

# Common default install paths
DEFAULT_PATHS_2020 = [
    Path("C:/Program Files/WindowsApps/Microsoft.FlightSimulator_8wekyb3d8bbwe"),
    Path("C:/Program Files (x86)/Steam/steamapps/common/MicrosoftFlightSimulator"),
    Path("C:/Program Files (x86)/Microsoft Games/Microsoft Flight Simulator"),
    Path("D:/Program Files (x86)/Steam/steamapps/common/MicrosoftFlightSimulator"),
    Path("E:/Program Files (x86)/Steam/steamapps/common/MicrosoftFlightSimulator"),
]

DEFAULT_PATHS_2024 = [
    Path("C:/Program Files/WindowsApps/Microsoft.FlightSimulator2024_8wekyb3d8bbwe"),
    Path("C:/Program Files (x86)/Steam/steamapps/common/MicrosoftFlightSimulator2024"),
    Path("D:/Program Files (x86)/Steam/steamapps/common/MicrosoftFlightSimulator2024"),
]

# UserCfg.opt search paths
USERCFG_SEARCH_PATHS = [
    # MS Store / AppData
    Path(os.environ.get("LOCALAPPDATA", "C:/Users/Default/AppData/Local")) / "Packages" / "Microsoft.FlightSimulator_8wekyb3d8bbwe" / "LocalCache",
    Path(os.environ.get("LOCALAPPDATA", "C:/Users/Default/AppData/Local")) / "Packages" / "Microsoft.FlightSimulator2024_8wekyb3d8bbwe" / "LocalCache",
    # Steam
    Path(os.environ.get("APPDATA", "C:/Users/Default/AppData/Roaming")) / "Microsoft Flight Simulator",
    Path(os.environ.get("APPDATA", "C:/Users/Default/AppData/Roaming")) / "Microsoft Flight Simulator 2024",
    # Generic
    Path.home() / "AppData" / "Local" / "Packages" / "Microsoft.FlightSimulator_8wekyb3d8bbwe" / "LocalCache",
    Path.home() / "AppData" / "Local" / "Packages" / "Microsoft.FlightSimulator2024_8wekyb3d8bbwe" / "LocalCache",
    Path.home() / "AppData" / "Roaming" / "Microsoft Flight Simulator",
    Path.home() / "AppData" / "Roaming" / "Microsoft Flight Simulator 2024",
]


# ---------------------------------------------------------------------------
#  Registry helpers (Windows)
# ---------------------------------------------------------------------------

def _try_read_registry(key_path: str, value_name: str = "InstallLocation") -> Optional[str]:
    """Attempt to read a Windows registry value. Returns None on failure or non-Windows."""
    if platform.system() != "Windows":
        return None
    try:
        import winreg
        # Try both 64-bit and 32-bit views
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for sam in (winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
                        winreg.KEY_READ | winreg.KEY_WOW64_32KEY):
                try:
                    with winreg.OpenKey(hive, key_path, 0, sam) as key:
                        value, _ = winreg.QueryValueEx(key, value_name)
                        if value and os.path.isdir(value):
                            return value
                except (OSError, FileNotFoundError):
                    continue
    except ImportError:
        pass
    return None


def _try_read_registry_any(keys: List[str], value_name: str = "InstallLocation") -> Optional[str]:
    """Try multiple registry keys and return the first valid path."""
    for key in keys:
        path = _try_read_registry(key, value_name)
        if path:
            logger.debug(f"Found registry key: {key} -> {path}")
            return path
    return None


# ---------------------------------------------------------------------------
#  UserCfg.opt parser
# ---------------------------------------------------------------------------

def _find_user_cfg() -> Optional[Path]:
    """Search common locations for UserCfg.opt."""
    for search_path in USERCFG_SEARCH_PATHS:
        candidate = search_path / "UserCfg.opt"
        if candidate.exists():
            logger.debug(f"Found UserCfg.opt at: {candidate}")
            return candidate
    return None


def _parse_user_cfg(user_cfg_path: Path) -> Dict[str, str]:
    """Parse UserCfg.opt into a dictionary of key->value pairs."""
    config = {}
    try:
        content = user_cfg_path.read_text(encoding="utf-8", errors="ignore")
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("//") or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                config[key.strip()] = value.strip().strip('"').strip("'")
    except Exception as e:
        logger.warning(f"Failed to parse UserCfg.opt: {e}")
    return config


def _extract_community_from_user_cfg(user_cfg_path: Optional[Path]) -> Optional[Path]:
    """Extract the 'InstalledPackagesPath' from UserCfg.opt and derive Community folder."""
    if user_cfg_path is None or not user_cfg_path.exists():
        return None
    config = _parse_user_cfg(user_cfg_path)
    packages_path = config.get("InstalledPackagesPath")
    if packages_path:
        community = Path(packages_path) / "Community"
        if community.exists():
            return community.resolve()
        # Maybe the path itself is the Community folder parent
        community_alt = Path(packages_path)
        if (community_alt / "Community").exists():
            return (community_alt / "Community").resolve()
    return None


# ---------------------------------------------------------------------------
#  Default location detection
# ---------------------------------------------------------------------------

def _check_default_paths(version: MsfsVersion) -> List[Path]:
    """Check common default installation paths."""
    paths = DEFAULT_PATHS_2024 if version == MsfsVersion.MSFS2024 else DEFAULT_PATHS_2020
    found = []
    for p in paths:
        if p.exists() and (p / "Community").exists() or (p / "fs-base").exists() or (p / "SimObjects").exists():
            found.append(p)
    return found


# ---------------------------------------------------------------------------
#  Symbolic link resolution
# ---------------------------------------------------------------------------

def _resolve_community_symlink(path: Path) -> Path:
    """If the Community folder is a symbolic link, resolve to its target."""
    try:
        if path.is_symlink():
            resolved = path.resolve()
            logger.info(f"Resolved symlink: {path} -> {resolved}")
            return resolved
    except (OSError, RuntimeError) as e:
        logger.warning(f"Failed to resolve symlink at {path}: {e}")
    return path


# ---------------------------------------------------------------------------
#  Main detection functions
# ---------------------------------------------------------------------------

def detect_msfs_installations() -> List[MsfsInstallation]:
    """
    Detect all MSFS installations on the system.

    Returns a list of MsfsInstallation objects, one per detected installation.
    The list may be empty if no installation is found.
    """
    installations: List[MsfsInstallation] = []
    seen_paths: set = set()

    def add_install(path: Path, source: MsfsSource, version: MsfsVersion):
        """Add an installation if not already seen."""
        try:
            path = path.resolve()
        except (OSError, RuntimeError):
            return
        path_str = str(path).lower()
        if path_str in seen_paths:
            return
        if not path.exists():
            return
        seen_paths.add(path_str)

        # Derive community and official folders
        community = _find_community_for_install(path, version)
        official = _find_official_for_install(path, version)
        localcache = _find_localcache_for_version(version)

        installations.append(MsfsInstallation(
            path=path,
            source=source,
            version=version,
            community_path=community,
            official_path=official,
            localcache_path=localcache,
        ))
        logger.info(f"Detected {version.value} ({source.name}): {path}")

    # --- Attempt 1: Windows Registry (MS Store) ---
    if platform.system() == "Windows":
        # MSFS 2020 from MS Store
        store_path = _try_read_registry_any(MS_STORE_KEYS_2020)
        if store_path:
            add_install(Path(store_path), MsfsSource.MS_STORE, MsfsVersion.MSFS2020)

        # MSFS 2024 from MS Store
        store_path_2024 = _try_read_registry_any(MS_STORE_KEYS_2024)
        if store_path_2024:
            add_install(Path(store_path_2024), MsfsSource.MS_STORE, MsfsVersion.MSFS2024)

        # MSFS 2020 from Steam
        steam_path = _try_read_registry_any(STEAM_KEYS_2020, "InstallLocation")
        if steam_path:
            add_install(Path(steam_path), MsfsSource.STEAM, MsfsVersion.MSFS2020)

        # MSFS 2024 from Steam
        steam_path_2024 = _try_read_registry_any(STEAM_KEYS_2024, "InstallLocation")
        if steam_path_2024:
            add_install(Path(steam_path_2024), MsfsSource.STEAM, MsfsVersion.MSFS2024)

    # --- Attempt 2: UserCfg.opt parsing ---
    user_cfg = _find_user_cfg()
    if user_cfg:
        config = _parse_user_cfg(user_cfg)
        packages_path = config.get("InstalledPackagesPath")
        if packages_path:
            pkg = Path(packages_path).resolve()
            # Check if there's a Community folder parent
            community_parent = pkg if (pkg / "Community").exists() else None
            if community_parent:
                # Determine version from the UserCfg location
                version = MsfsVersion.MSFS2024 if "2024" in str(user_cfg) else MsfsVersion.MSFS2020
                # Try to find the root install path
                install_root = community_parent.parent
                if install_root.exists():
                    add_install(install_root, MsfsSource.CUSTOM, version)

    # --- Attempt 3: Default paths ---
    for version in (MsfsVersion.MSFS2020, MsfsVersion.MSFS2024):
        for p in _check_default_paths(version):
            source = MsfsSource.STEAM if "steam" in str(p).lower() else MsfsSource.CUSTOM
            add_install(p, source, version)

    # --- Attempt 4: Resolve from Community folder symlinks ---
    _detect_from_community_symlinks(installations, seen_paths, add_install)

    return installations


def _detect_from_community_symlinks(
    installations: List[MsfsInstallation],
    seen_paths: set,
    add_install_cb,
):
    """Detect installations by resolving symbolic links found in common locations."""
    # Common junction/symlink locations
    symlink_candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Flight Simulator" / "Packages" / "Community",
        Path(os.environ.get("LOCALAPPDATA", "")) / "MSFS" / "Community",
        Path.home() / "AppData" / "Local" / "MSFS" / "Community",
    ]
    for candidate in symlink_candidates:
        try:
            if candidate.is_symlink():
                target = candidate.resolve()
                # Walk up to find the install root
                for parent in target.parents:
                    if (parent / "fs-base").exists() or (parent / "SimObjects").exists():
                        version = MsfsVersion.MSFS2024 if "2024" in str(parent) else MsfsVersion.MSFS2020
                        add_install_cb(parent, MsfsSource.CUSTOM, version)
                        break
        except (OSError, RuntimeError):
            continue


def _find_community_for_install(install_path: Path, version: MsfsVersion) -> Optional[Path]:
    """Find the Community folder for a given installation."""
    # Standard location
    community = install_path / "Community"
    if community.exists():
        return _resolve_community_symlink(community)

    # Check Packages folder (MS Store layout)
    packages_community = install_path / "Packages" / "Community"
    if packages_community.exists():
        return _resolve_community_symlink(packages_community)

    # Try parent directory (some custom layouts)
    parent_community = install_path.parent / "Community"
    if parent_community.exists():
        return _resolve_community_symlink(parent_community)

    # Fall back to UserCfg.opt extraction
    user_cfg = _find_user_cfg()
    extracted = _extract_community_from_user_cfg(user_cfg)
    if extracted:
        return extracted

    return None


def _find_official_for_install(install_path: Path, version: MsfsVersion) -> Optional[Path]:
    """Find the Official folder for a given installation."""
    official = install_path / "Official"
    if official.exists():
        return official.resolve()
    packages_official = install_path / "Packages" / "Official"
    if packages_official.exists():
        return packages_official.resolve()
    return None


def _find_localcache_for_version(version: MsfsVersion) -> Optional[Path]:
    """Find the LocalCache folder for a given version."""
    for search_path in USERCFG_SEARCH_PATHS:
        if search_path.exists() and version.value.replace(" ", "") in str(search_path):
            return search_path
    for search_path in USERCFG_SEARCH_PATHS:
        if search_path.exists():
            return search_path
    return None


# ---------------------------------------------------------------------------
#  Convenience functions
# ---------------------------------------------------------------------------

def find_community_folder() -> Optional[Path]:
    """
    Find the primary MSFS Community folder.

    Returns the first Community folder found, or None.
    """
    installations = detect_msfs_installations()
    for inst in installations:
        if inst.community_path:
            return inst.community_path
    return None


def find_official_folder() -> Optional[Path]:
    """Find the primary MSFS Official folder."""
    installations = detect_msfs_installations()
    for inst in installations:
        if inst.official_path:
            return inst.official_path
    return None


def find_best_installation() -> Optional[MsfsInstallation]:
    """
    Find the 'best' MSFS installation (prioritising MS Store, then Steam, then custom).

    Returns the first valid installation found.
    """
    installations = detect_msfs_installations()
    if not installations:
        return None

    # Priority: MS Store > Steam > Custom
    def sort_key(inst: MsfsInstallation) -> int:
        return {
            MsfsSource.MS_STORE: 0,
            MsfsSource.STEAM: 1,
            MsfsSource.CUSTOM: 2,
            MsfsSource.BOXED: 3,
        }.get(inst.source, 99)

    installations.sort(key=sort_key)
    return installations[0]


# ---------------------------------------------------------------------------
#  Diagnostic information
# ---------------------------------------------------------------------------

def get_diagnostics() -> Dict:
    """Return a diagnostic report of all detected MSFS installations."""
    installations = detect_msfs_installations()
    user_cfg = _find_user_cfg()

    diag = {
        "system": platform.platform(),
        "python_version": sys.version,
        "installations": [],
        "user_cfg_path": str(user_cfg) if user_cfg else None,
        "user_cfg_parsed": _parse_user_cfg(user_cfg) if user_cfg else {},
        "errors": [],
    }

    for inst in installations:
        diag["installations"].append({
            "path": str(inst.path),
            "source": inst.source.name,
            "version": inst.version.value,
            "community_path": str(inst.community_path) if inst.community_path else None,
            "official_path": str(inst.official_path) if inst.official_path else None,
            "has_error": inst.error is not None,
            "error": inst.error,
        })

    if not installations:
        diag["errors"].append("No MSFS installations detected on this system.")

    return diag


# ===========================================================================
#  CLI entry point (for testing)
# ===========================================================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    print("=" * 60)
    print("MSFS Installation Detector")
    print("=" * 60)

    installations = detect_msfs_installations()
    if installations:
        print(f"\nFound {len(installations)} installation(s):\n")
        for i, inst in enumerate(installations):
            print(f"  [{i+1}] {inst.version.value} ({inst.source.name})")
            print(f"       Path: {inst.path}")
            print(f"       Community: {inst.community_path}")
            print(f"       Official: {inst.official_path}")
            print()
    else:
        print("\n  No MSFS installations detected.")
        print("  Try: Is MSFS installed? Is the registry accessible?")

    print("\nDiagnostics:")
    diag = get_diagnostics()
    print(f"  UserCfg.opt: {diag.get('user_cfg_path')}")
    print(f"  System: {diag['system']}")
