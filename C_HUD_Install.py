"""
C_HUD_Runway — One-Click Installer Launcher
============================================
Minimal entry point for the built EXE.
"""

import os
import sys

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from installer.oneclick import run_oneclick

run_oneclick()
