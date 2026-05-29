"""
C_HUD_Runway GUI Application — Phase 5/6
=========================================
Standalone graphical installer with:

  · Aircraft compatibility list
  · Install/Repair/Uninstall buttons
  · Update checker
  · Diagnostics viewer
  · Telemetry export
  · Profile manager
  · Portable mode

Uses tkinter for cross-platform compatibility.
"""

import json
import logging
import os
import platform
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime

# Try to import tkinter (available by default on most platforms)
try:
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog, scrolledtext
    TK_AVAILABLE = True
except ImportError:
    TK_AVAILABLE = False

from .. import __version__, __title__
from ..msfs_detector import (
    find_community_folder,
    find_best_installation,
    detect_msfs_installations,
    get_diagnostics,
)
from ..aircraft_scanner import (
    AircraftPackage,
    IntegrationStatus,
    AircraftType,
    scan_community,
    analyze_package_structure,
)
from ..patch_engine import (
    PatchEngine,
    BackupEngine,
    FileCopier,
)
from ..healer import SelfHealer, HealthChecker

logger = logging.getLogger("gui")


# =========================================================================
#  GUI Application
# =========================================================================

class InstallerGUI:
    """
    Main GUI application window.
    """

    def __init__(self, community_path: Optional[Path] = None):
        if not TK_AVAILABLE:
            raise RuntimeError("tkinter is not available on this system")

        self.root = tk.Tk()
        self.root.title(f"{__title__} v{__version__}")
        self.root.geometry("900x700")
        self.root.minsize(800, 600)

        # Set icon if available
        try:
            self.root.iconbitmap(default=__file__.replace(".py", ".ico"))
        except Exception:
            pass

        # State
        self.community_path = community_path
        self.packages: List[AircraftPackage] = []
        self.installer = None
        self.health_data: List[Dict] = []
        self.operation_running = False

        # Build UI
        self._build_menu()
        self._build_toolbar()
        self._build_main_area()
        self._build_status_bar()

        # Auto-detect
        self.root.after(500, self._initial_scan)

    def _build_menu(self):
        """Build the menu bar."""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Select Community Folder...", command=self._select_community)
        file_menu.add_separator()
        file_menu.add_command(label="Export Diagnostics...", command=self._export_diagnostics)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        menubar.add_cascade(label="File", menu=file_menu)

        # Tools menu
        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(label="Rescan Aircraft", command=self._scan_aircraft)
        tools_menu.add_command(label="Repair All", command=self._repair_all)
        tools_menu.add_separator()
        tools_menu.add_command(label="Open Backups Folder", command=self._open_backups)
        tools_menu.add_command(label="View Installer Log", command=self._view_log)
        menubar.add_cascade(label="Tools", menu=tools_menu)

        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="About", command=self._show_about)
        help_menu.add_command(label="Documentation", command=self._open_docs)
        menubar.add_cascade(label="Help", menu=help_menu)

    def _build_toolbar(self):
        """Build the toolbar with action buttons."""
        toolbar = ttk.Frame(self.root, padding=5)
        toolbar.pack(fill=tk.X)

        ttk.Button(
            toolbar, text="Install / Reinstall",
            command=self._install_all,
            width=18,
        ).pack(side=tk.LEFT, padx=2)

        ttk.Button(
            toolbar, text="Repair",
            command=self._repair_all,
            width=12,
        ).pack(side=tk.LEFT, padx=2)

        ttk.Button(
            toolbar, text="Uninstall",
            command=self._uninstall_all,
            width=12,
        ).pack(side=tk.LEFT, padx=2)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)

        ttk.Button(
            toolbar, text="Refresh Scan",
            command=self._scan_aircraft,
            width=14,
        ).pack(side=tk.LEFT, padx=2)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)

        self._status_label = ttk.Label(toolbar, text="Ready")
        self._status_label.pack(side=tk.RIGHT, padx=5)

    def _build_main_area(self):
        """Build the main content area with aircraft list and details."""
        main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Left panel: aircraft list
        left_frame = ttk.LabelFrame(main_paned, text="Aircraft Packages", padding=5)
        main_paned.add(left_frame, weight=1)

        # Treeview for aircraft list
        columns = ("status", "aircraft", "version", "integration")
        self.tree = ttk.Treeview(left_frame, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("status", text="", width=30)
        self.tree.heading("aircraft", text="Aircraft")
        self.tree.heading("version", text="Version", width=80)
        self.tree.heading("integration", text="Integration", width=100)

        self.tree.column("status", width=30, anchor=tk.CENTER)
        self.tree.column("aircraft", width=200)
        self.tree.column("version", width=80, anchor=tk.CENTER)
        self.tree.column("integration", width=100, anchor=tk.CENTER)

        # Scrollbar
        scrollbar = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        # Right panel: details
        right_frame = ttk.LabelFrame(main_paned, text="Details", padding=5)
        main_paned.add(right_frame, weight=1)

        # Details text area
        self.details_text = scrolledtext.ScrolledText(
            right_frame, wrap=tk.WORD, width=40, height=20,
            font=("Consolas", 9) if platform.system() == "Windows" else ("Courier", 9),
        )
        self.details_text.pack(fill=tk.BOTH, expand=True)

        # Bottom: output log
        bottom_frame = ttk.LabelFrame(self.root, text="Output Log", padding=5)
        bottom_frame.pack(fill=tk.BOTH, expand=False, padx=5, pady=(0, 5))

        self.log_text = scrolledtext.ScrolledText(
            bottom_frame, wrap=tk.WORD, width=100, height=8,
            font=("Consolas", 8) if platform.system() == "Windows" else ("Courier", 8),
            state=tk.DISABLED,
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def _build_status_bar(self):
        """Build the status bar at the bottom."""
        status_bar = ttk.Frame(self.root, relief=tk.SUNKEN, padding=2)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)

        self._community_label = ttk.Label(
            status_bar, text="Community: Not detected",
            font=("Segoe UI", 8),
        )
        self._community_label.pack(side=tk.LEFT, padx=5)

        self._count_label = ttk.Label(
            status_bar, text="Aircraft: 0",
            font=("Segoe UI", 8),
        )
        self._count_label.pack(side=tk.RIGHT, padx=5)

    def _log(self, message: str, level: str = "INFO"):
        """Add a message to the log output."""
        def append():
            self.log_text.config(state=tk.NORMAL)
            timestamp = datetime.now().strftime("%H:%M:%S")
            tag = "info"
            if level == "ERROR":
                tag = "error"
            elif level == "WARNING":
                tag = "warning"
            elif level == "SUCCESS":
                tag = "success"

            self.log_text.insert(tk.END, f"[{timestamp}] {message}\n", tag)
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)

        self.root.after(0, append)

    def _initial_scan(self):
        """Perform initial scan on startup."""
        self._log("Starting C_HUD_Runway Installer...")
        self._log(f"Version: {__version__}")

        # Detect MSFS
        installations = detect_msfs_installations()
        if installations:
            best = find_best_installation()
            if best and best.community_path:
                self.community_path = best.community_path
                self._community_label.config(text=f"Community: {best.community_path}")
                self._log(f"Detected MSFS ({best.version.value}) at {best.path}")
                self._log(f"Community folder: {best.community_path}")
                self._scan_aircraft()
            else:
                self._log("MSFS detected but Community folder not found", "WARNING")
        else:
            self._log("No MSFS installation detected", "WARNING")
            self._log("Use File > Select Community Folder to specify manually")

    def _select_community(self):
        """Open a dialog to select the Community folder."""
        path = filedialog.askdirectory(title="Select MSFS Community Folder")
        if path:
            self.community_path = Path(path)
            self._community_label.config(text=f"Community: {self.community_path}")
            self._log(f"Community folder set to: {self.community_path}")
            self._scan_aircraft()

    def _scan_aircraft(self):
        """Scan the Community folder for supported aircraft."""
        if self.community_path is None or not self.community_path.exists():
            self._log("Community folder not available", "ERROR")
            return

        self._log("Scanning for supported aircraft...")
        self._set_status("Scanning...")

        def scan():
            try:
                packages = scan_community(self.community_path)
                self.root.after(0, lambda: self._update_aircraft_list(packages))
            except Exception as e:
                self.root.after(0, lambda: self._log(f"Scan error: {e}", "ERROR"))
                self.root.after(0, lambda: self._set_status("Scan failed"))

        threading.Thread(target=scan, daemon=True).start()

    def _update_aircraft_list(self, packages: List[AircraftPackage]):
        """Update the aircraft list in the GUI."""
        self.packages = packages

        # Clear existing items
        for item in self.tree.get_children():
            self.tree.delete(item)

        if not packages:
            self._log("No supported aircraft found in Community folder.", "WARNING")
            self._count_label.config(text="Aircraft: 0")
            return

        for pkg in packages:
            status_icon = "✓" if pkg.hgs_integrated else "✗"
            if pkg.integration_status == IntegrationStatus.NEEDS_REPAIR:
                status_icon = "⚠"
            elif pkg.integration_status == IntegrationStatus.INSTALLED:
                status_icon = "✓"

            version = f"{pkg.detected_version_major}.{pkg.detected_version_minor}"
            integration = pkg.integration_status.value.replace("_", " ").title()

            self.tree.insert("", tk.END, values=(
                status_icon,
                pkg.aircraft_type.value,
                version,
                integration,
            ))

        self._count_label.config(text=f"Aircraft: {len(packages)}")
        self._log(f"Found {len(packages)} supported aircraft", "SUCCESS")
        self._set_status("Ready")

    def _on_select(self, event):
        """Handle aircraft selection in the tree."""
        selection = self.tree.selection()
        if not selection:
            return

        item = selection[0]
        values = self.tree.item(item, "values")
        if not values:
            return

        aircraft_name = values[1]
        pkg = next((p for p in self.packages if p.aircraft_type.value == aircraft_name), None)
        if pkg is None:
            return

        # Show details
        self.details_text.delete(1.0, tk.END)
        self.details_text.insert(tk.END, f"Aircraft: {pkg.aircraft_type.value}\n")
        self.details_text.insert(tk.END, f"Package: {pkg.package_path.name}\n")
        self.details_text.insert(tk.END, f"Path: {pkg.package_path}\n")
        self.details_text.insert(tk.END, f"Version: {pkg.detected_version_major}.{pkg.detected_version_minor}\n")
        self.details_text.insert(tk.END, f"HGS Integrated: {pkg.hgs_integrated}\n")
        self.details_text.insert(tk.END, f"Integration Status: {pkg.integration_status.value}\n")
        self.details_text.insert(tk.END, f"Layout Entries: {len(pkg.layout_entries)}\n")
        self.details_text.insert(tk.END, f"Panel Configs: {len(pkg.panel_configs)}\n")

        if pkg.panel_configs:
            self.details_text.insert(tk.END, "\nPanel Configs:\n")
            for pc in pkg.panel_configs:
                self.details_text.insert(tk.END, f"  {pc.path.name}: ")
                if pc.has_hud_gauge:
                    self.details_text.insert(tk.END, "✓ WASM, ")
                else:
                    self.details_text.insert(tk.END, "✗ WASM, ")
                if pc.has_html_hud:
                    self.details_text.insert(tk.END, "✓ HTML\n")
                else:
                    self.details_text.insert(tk.END, "✗ HTML\n")

        if pkg.errors:
            self.details_text.insert(tk.END, "\nErrors:\n")
            for err in pkg.errors:
                self.details_text.insert(tk.END, f"  ⚠ {err}\n")

    def _install_all(self):
        """Install HGS integration for all aircraft."""
        if self.operation_running:
            messagebox.showinfo("Busy", "An operation is already in progress.")
            return

        if not self.packages:
            messagebox.showwarning("No Aircraft", "No supported aircraft found. Run a scan first.")
            return

        if not messagebox.askyesno("Confirm Install",
            "This will install HGS integration for all compatible aircraft.\n\n"
            "Backups will be created automatically.\n"
            "Continue?"):
            return

        self.operation_running = True
        self._log("Starting installation...")
        self._set_status("Installing...")

        def run():
            try:
                engine = PatchEngine(self.community_path)
                results = {}
                for pkg in self.packages:
                    self.root.after(0, lambda a=pkg: self._log(
                        f"Installing for {a.aircraft_type.value}..."
                    ))
                    success = engine.install_hgs_to_aircraft(pkg)
                    results[pkg.aircraft_type.value] = success
                    if success:
                        self.root.after(0, lambda a=pkg: self._log(
                            f"✓ {a.aircraft_type.value} integrated successfully", "SUCCESS"
                        ))
                    else:
                        self.root.after(0, lambda a=pkg: self._log(
                            f"✗ {a.aircraft_type.value} integration failed", "ERROR"
                        ))

                self.root.after(0, self._scan_aircraft)  # Refresh
                self.root.after(0, lambda: self._log("Installation complete", "SUCCESS"))
                self.root.after(0, lambda: self._set_status("Ready"))
            finally:
                self.operation_running = False

        threading.Thread(target=run, daemon=True).start()

    def _uninstall_all(self):
        """Uninstall HGS integration from all aircraft."""
        if self.operation_running:
            messagebox.showinfo("Busy", "An operation is already in progress.")
            return

        if not messagebox.askyesno("Confirm Uninstall",
            "This will remove HGS integration from all aircraft.\n\n"
            "Backups will be created first.\n"
            "Continue?"):
            return

        self.operation_running = True
        self._log("Starting uninstall...")
        self._set_status("Uninstalling...")

        def run():
            try:
                engine = PatchEngine(self.community_path)
                for pkg in self.packages:
                    self.root.after(0, lambda a=pkg: self._log(
                        f"Removing HGS from {a.aircraft_type.value}..."
                    ))
                    success = engine.uninstall_hgs_from_aircraft(pkg)
                    if success:
                        self.root.after(0, lambda a=pkg: self._log(
                            f"✓ {a.aircraft_type.value} cleaned successfully", "SUCCESS"
                        ))
                    else:
                        self.root.after(0, lambda a=pkg: self._log(
                            f"✗ {a.aircraft_type.value} uninstall had issues", "WARNING"
                        ))

                # Remove HGS package
                self.root.after(0, lambda: self._log("Removing HGS package..."))
                if self.community_path:
                    FileCopier.remove_hgs_from_community(self.community_path)

                self.root.after(0, self._scan_aircraft)  # Refresh
                self.root.after(0, lambda: self._log("Uninstall complete", "SUCCESS"))
                self.root.after(0, lambda: self._set_status("Ready"))
            finally:
                self.operation_running = False

        threading.Thread(target=run, daemon=True).start()

    def _repair_all(self):
        """Repair all broken integrations."""
        if self.operation_running:
            messagebox.showinfo("Busy", "An operation is already in progress.")
            return

        self.operation_running = True
        self._log("Checking aircraft health...")
        self._set_status("Repairing...")

        def run():
            try:
                healer = SelfHealer(self.community_path)
                results = healer.repair_all()

                if not results:
                    self.root.after(0, lambda: self._log(
                        "All aircraft are healthy. No repair needed.", "SUCCESS"
                    ))
                else:
                    fixed = sum(1 for v in results.values() if v)
                    self.root.after(0, lambda: self._log(
                        f"Repair complete: {fixed}/{len(results)} repaired", "SUCCESS"
                    ))

                self.root.after(0, self._scan_aircraft)  # Refresh
                self.root.after(0, lambda: self._set_status("Ready"))
            finally:
                self.operation_running = False

        threading.Thread(target=run, daemon=True).start()

    def _export_diagnostics(self):
        """Export diagnostic information to a file."""
        filename = filedialog.asksaveasfilename(
            title="Save Diagnostics",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile=f"hgs_diagnostics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
        )
        if not filename:
            return

        diag = get_diagnostics()
        diag["installer_version"] = __version__
        diag["timestamp"] = datetime.now().isoformat()

        try:
            Path(filename).write_text(json.dumps(diag, indent=2, default=str), encoding="utf-8")
            self._log(f"Diagnostics saved to: {filename}", "SUCCESS")
            messagebox.showinfo("Exported", f"Diagnostics saved to:\n{filename}")
        except Exception as e:
            self._log(f"Failed to export diagnostics: {e}", "ERROR")

    def _open_backups(self):
        """Open the backups folder in the file manager."""
        backup_dir = Path(__file__).resolve().parent.parent / "backups"
        if backup_dir.exists():
            if platform.system() == "Windows":
                os.startfile(str(backup_dir))
            elif platform.system() == "Darwin":
                subprocess.run(["open", str(backup_dir)])
            else:
                subprocess.run(["xdg-open", str(backup_dir)])
        else:
            messagebox.showinfo("No Backups", "Backups folder is empty or does not exist.")

    def _view_log(self):
        """Open the installer log file."""
        log_path = Path(__file__).resolve().parent.parent / "installer.log"
        if log_path.exists():
            if platform.system() == "Windows":
                os.startfile(str(log_path))
            else:
                subprocess.run(["cat", str(log_path)])
        else:
            messagebox.showinfo("No Log", "Installer log not found. Run an operation first.")

    def _show_about(self):
        """Show the About dialog."""
        about_text = (
            f"{__title__} v{__version__}\n\n"
            "Conformal HUD Runway Guidance System\n"
            "HGS/HUD Integration Management Platform\n\n"
            "A professional avionics integration platform\n"
            "for Microsoft Flight Simulator.\n\n"
            "Features:\n"
            "  · One-click installation\n"
            "  · Automatic aircraft integration\n"
            "  · Safe rollback with backups\n"
            "  · Self-healing across aircraft updates\n"
            "  · Multi-aircraft compatibility\n\n"
            f"Python {sys.version.split()[0]}\n"
            f"Platform: {platform.platform()}"
        )
        messagebox.showinfo("About", about_text)

    def _open_docs(self):
        """Open documentation."""
        readme_path = Path(__file__).resolve().parent.parent.parent / "README.md"
        if readme_path.exists():
            if platform.system() == "Windows":
                os.startfile(str(readme_path))
            else:
                subprocess.run(["less", str(readme_path)])

    def _set_status(self, status: str):
        """Set the status bar text."""
        self._status_label.config(text=status)

    def run(self):
        """Start the GUI main loop."""
        self.root.mainloop()


# =========================================================================
#  Entry point
# =========================================================================

def run_gui(community_path: Optional[Path] = None):
    """Launch the GUI application."""
    if not TK_AVAILABLE:
        print("ERROR: tkinter is not available. Cannot launch GUI.")
        print("Install python3-tk (Linux) or use a Python build with tkinter.")
        sys.exit(1)

    try:
        app = InstallerGUI(community_path=community_path)
        app.run()
    except Exception as e:
        logger.error(f"GUI failed to start: {e}")
        messagebox.showerror("GUI Error", f"Failed to start GUI:\n{e}")
        sys.exit(1)


if __name__ == "__main__":
    run_gui()
