"""
One-Click Installer — Phase 7
==============================
Minimal console-style tkinter window for auto-detecting MSFS,
scanning aircraft, and installing with a single click.
"""

import threading
import tkinter as tk
from tkinter import ttk
from pathlib import Path
from typing import Optional

from . import __version__
from .msfs_detector import (
    detect_msfs_installations,
    find_best_installation,
)
from .aircraft_scanner import scan_community
from .installer import Installer


class OneClickInstaller:
    """
    Minimal auto-install window.

    On open: auto-detects MSFS, scans aircraft, shows status.
    On "Install" click: runs full installation with progress.
    """

    # Colour palette
    BG = "#1a1a2e"
    FG = "#ffffff"
    ACCENT = "#00ff88"
    ERROR = "#ff6666"
    GRAY = "#aaaaaa"
    SUB_FG = "#888888"
    SEPARATOR = "#333355"
    BTN_GREEN = "#2d7d2a"
    BTN_GRAY = "#555555"
    LOG_BG = "#000000"

    # Named tags for log colours (registered once in _build_ui)
    TAG_ACCENT = "log_accent"
    TAG_ERROR  = "log_error"
    TAG_INFO   = "log_info"

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"C_HUD_Runway Installer v{__version__}")
        self.root.configure(bg=self.BG)
        self.root.resizable(False, False)

        # Centre on screen
        win_w, win_h = 500, 380
        screen_w = root.winfo_screenwidth()
        screen_h = root.winfo_screenheight()
        x = (screen_w - win_w) // 2
        y = (screen_h - win_h) // 2
        self.root.geometry(f"{win_w}x{win_h}+{x}+{y}")

        # State
        self.community_path: Optional[Path] = None
        self.install_result: Optional[bool] = None
        self._operation_running = False

        self._build_ui()

        # Start auto-detection shortly after window appears
        self.root.after(100, self._start_auto_detect)

    # ------------------------------------------------------------------
    #  UI Construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        """Build the window layout from top to bottom."""

        # --- Header ---
        header = tk.Label(
            self.root,
            text="C_HUD_Runway",
            font=("Segoe UI", 18, "bold"),
            fg=self.FG,
            bg=self.BG,
        )
        header.pack(pady=(20, 0))

        subtitle = tk.Label(
            self.root,
            text="Conformal HUD \u00b7 One-Click Installer",
            font=("Segoe UI", 10),
            fg=self.SUB_FG,
            bg=self.BG,
        )
        subtitle.pack(pady=(0, 10))

        # --- Separator ---
        sep = tk.Frame(self.root, height=1, bg=self.SEPARATOR)
        sep.pack(fill=tk.X, padx=20, pady=(0, 10))

        # --- Scrollable log area ---
        log_frame = tk.Frame(self.root, bg=self.BG)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 5))

        self.log_text = tk.Text(
            log_frame,
            height=12,
            bg=self.LOG_BG,
            fg=self.ACCENT,
            font=("Courier New", 9),
            bd=0,
            highlightthickness=0,
            relief=tk.FLAT,
            state=tk.DISABLED,
            wrap=tk.WORD,
        )

        # Register colour tags once so they never interfere with each other
        self.log_text.tag_configure(self.TAG_ACCENT, foreground=self.ACCENT)
        self.log_text.tag_configure(self.TAG_ERROR, foreground=self.ERROR)
        self.log_text.tag_configure(self.TAG_INFO, foreground=self.GRAY)

        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        log_scroll = tk.Scrollbar(log_frame, command=self.log_text.yview)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=log_scroll.set)

        # --- Progress bar (indeterminate) ---
        self.progress = ttk.Progressbar(
            self.root,
            mode="indeterminate",
            length=460,
        )
        self.progress.pack(padx=20, pady=(5, 5))

        # --- Status label ---
        self.status_label = tk.Label(
            self.root,
            text="",
            font=("Segoe UI", 10),
            fg=self.ACCENT,
            bg=self.BG,
        )
        self.status_label.pack(pady=(5, 10))

        # --- Bottom buttons row ---
        btn_frame = tk.Frame(self.root, bg=self.BG)
        btn_frame.pack(pady=(0, 15))

        self.install_btn = tk.Button(
            btn_frame,
            text="Install",
            font=("Segoe UI", 10, "bold"),
            fg=self.FG,
            bg=self.BTN_GREEN,
            activebackground="#3a9a3a",
            activeforeground=self.FG,
            bd=0,
            padx=20,
            pady=6,
            cursor="hand2",
            state=tk.DISABLED,
            command=self._on_install,
        )
        self.install_btn.pack(side=tk.LEFT, padx=(0, 15))

        self.close_btn = tk.Button(
            btn_frame,
            text="Close",
            font=("Segoe UI", 10),
            fg=self.FG,
            bg=self.BTN_GRAY,
            activebackground="#777777",
            activeforeground=self.FG,
            bd=0,
            padx=20,
            pady=6,
            cursor="hand2",
            command=self.root.destroy,
        )
        self.close_btn.pack(side=tk.LEFT)

    # ------------------------------------------------------------------
    #  Colour helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _colour_to_tag(color: str) -> str:
        """Map a colour hex string to a pre-registered tag name."""
        # Normalise to lowercase for comparison
        c = color.lower()
        if c == OneClickInstaller.ACCENT.lower():
            return OneClickInstaller.TAG_ACCENT
        if c == OneClickInstaller.ERROR.lower():
            return OneClickInstaller.TAG_ERROR
        if c == OneClickInstaller.GRAY.lower():
            return OneClickInstaller.TAG_INFO
        # Fallback: create a unique tag (rare — shouldn't happen at runtime)
        # We don't register, so we just return the accent tag
        return OneClickInstaller.TAG_ACCENT

    # ------------------------------------------------------------------
    #  Logging Helpers (thread-safe via root.after)
    # ------------------------------------------------------------------

    def _log(self, msg: str, color: Optional[str] = None):
        """Append a message to the log text widget.

        Default colour is green (#00ff88).
        Pass ``self.ERROR`` (#ff6666) for errors, ``self.GRAY`` (#aaaaaa) for info.
        """
        if color is None:
            color = self.ACCENT
        tag = self._colour_to_tag(color)

        def _append():
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, msg + "\n", tag)
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)

        self.root.after(0, _append)

    def _set_status(self, text: str, color: Optional[str] = None):
        """Update the centred status label."""
        if color is None:
            color = self.ACCENT

        def _update():
            self.status_label.config(text=text, fg=color)

        self.root.after(0, _update)

    def _set_install_btn(self, enabled: bool):
        """Enable or disable the Install button."""
        state = tk.NORMAL if enabled else tk.DISABLED

        def _update():
            self.install_btn.config(state=state)

        self.root.after(0, _update)

    # ------------------------------------------------------------------
    #  Auto-Detection
    # ------------------------------------------------------------------

    def _start_auto_detect(self):
        """Kick off auto-detection in a background thread."""
        self._log("\u2192 Detecting MSFS installation...", self.GRAY)
        self._set_status("Detecting MSFS...", self.GRAY)
        threading.Thread(target=self._auto_detect, daemon=True).start()

    def _auto_detect(self):
        """Detect MSFS, locate Community folder, and scan for aircraft."""
        try:
            installations = detect_msfs_installations()
        except Exception as exc:
            self._log(f"\u2717 Detection error: {exc}", self.ERROR)
            self._set_status("Detection failed", self.ERROR)
            return

        if not installations:
            self._log("\u2717 MSFS not detected", self.ERROR)
            self._log("  Please install MSFS first", self.GRAY)
            self._set_status("MSFS not found", self.ERROR)
            self._set_install_btn(False)
            return

        try:
            best = find_best_installation()
        except Exception as exc:
            self._log(f"\u2717 Error finding installation: {exc}", self.ERROR)
            self._set_status("Detection error", self.ERROR)
            return

        if best is None:
            self._log("\u2717 MSFS not detected", self.ERROR)
            self._log("  Please install MSFS first", self.GRAY)
            self._set_status("MSFS not found", self.ERROR)
            self._set_install_btn(False)
            return

        version_str = (
            best.version.value
            if hasattr(best, "version") and best.version is not None
            else "MSFS"
        )
        self._log(f"\u2713 MSFS detected: {version_str} at {best.path}", self.ACCENT)

        community = best.community_path
        if community is None:
            self._log("\u2717 Community folder not found", self.ERROR)
            self._set_status("Community folder not found", self.ERROR)
            self._set_install_btn(False)
            return

        self.community_path = community
        self._log(f"\u2713 Community: {community}", self.ACCENT)

        # Scan for compatible aircraft
        try:
            packages = scan_community(community)
        except Exception as exc:
            self._log(f"\u2717 Scan error: {exc}", self.ERROR)
            self._set_status("Scan failed", self.ERROR)
            self._set_install_btn(False)
            return

        if packages:
            self._log(f"  Found {len(packages)} compatible aircraft", self.GRAY)
            for pkg in packages:
                self._log(f"    \u2022 {pkg.aircraft_type.value}", self.GRAY)
        else:
            self._log("  No compatible aircraft found", self.GRAY)

        self._set_status("Ready to install", self.ACCENT)
        self._set_install_btn(True)

    # ------------------------------------------------------------------
    #  Installation
    # ------------------------------------------------------------------

    def _on_install(self):
        """Handle the Install button click."""
        if self._operation_running:
            return
        if self.community_path is None:
            self._log("\u2717 No Community folder selected", self.ERROR)
            return

        self._operation_running = True
        self._set_install_btn(False)
        self.close_btn.config(state=tk.DISABLED)
        self.progress.start(10)

        self._log("")
        self._log("=" * 40, self.GRAY)
        self._log("Starting installation...", self.GRAY)
        self._set_status("Installing...", self.GRAY)

        threading.Thread(target=self._run_install, daemon=True).start()

    def _run_install(self):
        """Execute the installation in a background thread."""
        try:
            inst = Installer(community_path=self.community_path)
            results = inst.install()
        except Exception as exc:
            self._log(f"\u2717 Installation error: {exc}", self.ERROR)
            self._finish_install(success=False)
            return

        if not results:
            self._log("\u2717 No aircraft were integrated", self.ERROR)
            self._finish_install(success=False)
            return

        success_count = sum(1 for v in results.values() if v)
        total = len(results)

        if success_count == total and total > 0:
            self._log(
                f"\u2713 All {total} aircraft integrated successfully",
                self.ACCENT,
            )
            self._finish_install(success=True)
        elif success_count > 0:
            self._log(
                f"\u26a0 {success_count}/{total} aircraft integrated",
                self.ERROR,
            )
            self._log("  Some integrations failed \u2014 check details above", self.GRAY)
            self._finish_install(success=False)
        else:
            self._log("\u2717 Installation failed for all aircraft", self.ERROR)
            self._finish_install(success=False)

    def _finish_install(self, success: bool):
        """Update UI after installation attempt."""
        def _update():
            self.progress.stop()
            self._operation_running = False
            self.close_btn.config(state=tk.NORMAL)

            if success:
                self._set_status("\u2713 Installation complete!", self.ACCENT)
                # Keep Install disabled — one-shot workflow
                self.install_btn.config(state=tk.DISABLED)
            else:
                self._set_status("\u2717 Installation failed", self.ERROR)

        self.root.after(0, _update)


# ------------------------------------------------------------------
#  Entry Point
# ------------------------------------------------------------------

def run_oneclick():
    """Launch the one-click installer window."""
    root = tk.Tk()
    app = OneClickInstaller(root)  # noqa: F841
    root.mainloop()


if __name__ == "__main__":
    run_oneclick()
