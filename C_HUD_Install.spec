# -*- mode: python ; coding: utf-8 -*-
"""
C_HUD_Runway — One-Click Installer PyInstaller Spec
====================================================
Builds a single-file, windowed EXE for the one-click installer.
"""

import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
#  Block 1: Gather project metadata
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
INSTALLER_DIR = PROJECT_ROOT / "installer"

# Optional icon
icon_path = INSTALLER_DIR / "icon.ico"
if not icon_path.exists():
    icon_path = None

# ---------------------------------------------------------------------------
#  Block 2: Analysis
# ---------------------------------------------------------------------------
a = Analysis(
    [str(PROJECT_ROOT / "C_HUD_Install.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=[
        # Installer package
        "installer",
        "installer.oneclick",
        "installer.installer",
        "installer.msfs_detector",
        "installer.aircraft_scanner",
        "installer.patch_engine",
        "installer.healer",
        "installer.certification",
        "installer.diagnostics",
        "installer.safety",
        "installer.signature_verifier",
        "installer.repair_wizard",
        "installer.updater",
        # GUI (loaded dynamically by some paths)
        "installer.gui",
        # stdlib tkinter
        "tkinter",
        "tkinter.ttk",
        "tkinter.filedialog",
        "tkinter.messagebox",
        "tkinter.scrolledtext",
        # Other stdlib used by the installer
        "json",
        "logging",
        "threading",
        "pathlib",
        "shutil",
        "hashlib",
        "zipfile",
        "re",
        "time",
        "datetime",
        "enum",
        "dataclasses",
        "argparse",
        "platform",
        "subprocess",
        "webbrowser",
        "xml",
        "xml.etree",
        "xml.etree.ElementTree",
        "html",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Large packages we definitely don't need
        "matplotlib",
        "numpy",
        "scipy",
        "pandas",
        "PIL",
        "Pillow",
        "cv2",
        "tensorflow",
        "torch",
        "transformers",
        "notebook",
        "jupyter",
        "ipython",
        "setuptools",
        "pip",
        "pkg_resources",
        "unittest",
        "pytest",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

# ---------------------------------------------------------------------------
#  Block 3: PYZ archive
# ---------------------------------------------------------------------------
pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=None,
)

# ---------------------------------------------------------------------------
#  Block 4: EXE
# ---------------------------------------------------------------------------
exe_kwargs = dict(
    name="C_HUD_Install",
    console=False,              # No console window — GUI only
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    strip=False,
)

if icon_path:
    exe_kwargs["icon"] = str(icon_path)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    **exe_kwargs,
)

# ---------------------------------------------------------------------------
#  Block 5: COLLECT (not used for onefile builds, but PyInstaller expects it)
# ---------------------------------------------------------------------------
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="C_HUD_Install",
)
