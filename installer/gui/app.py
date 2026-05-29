"""
GUI Application module for C_HUD_Runway Installer.

Provides the run_gui() entry point used by installer.py.
"""

from . import InstallerGUI


def run_gui(community_path=None):
    """Launch the GUI application."""
    app = InstallerGUI(community_path=community_path)
    app.run()


if __name__ == "__main__":
    run_gui()
