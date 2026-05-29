"""
Operational Safety — Phase 7
=============================
Transaction-safe operations with crash recovery.

Provides:
  · Patch transaction system with atomic commits
  · Crash-safe rollback
  · Partial-install recovery
  · Corrupted install recovery
  · Installer logging with rotation
  · Safe mode startup
"""

import json
import logging
import os
import platform
import shutil
import sys
import time
import traceback
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Callable, Any
from zipfile import ZipFile, ZIP_DEFLATED

logger = logging.getLogger("safety")


# =========================================================================
#  1.  Transaction System
# =========================================================================

class TransactionError(Exception):
    """Raised when a transaction operation fails."""
    pass


@dataclass
class TransactionStep:
    """A single atomic step within a transaction."""
    step_id: str
    description: str
    status: str = "pending"  # pending, completed, failed, rolled_back
    result: Any = None
    error: Optional[str] = None
    timestamp: float = 0.0

    def complete(self, result: Any = None):
        self.status = "completed"
        self.result = result
        self.timestamp = time.time()

    def fail(self, error: str):
        self.status = "failed"
        self.error = error
        self.timestamp = time.time()

    def rollback(self):
        self.status = "rolled_back"
        self.timestamp = time.time()


class Transaction:
    """
    A transaction that groups multiple operations for atomic execution.

    If any step fails, all completed steps are rolled back in reverse order.
    The transaction persists its state to disk for crash recovery.
    """

    def __init__(self, name: str, state_dir: Optional[Path] = None):
        self.name = name
        self.transaction_id = f"txn_{int(time.time())}_{name[:16]}"
        self.steps: List[TransactionStep] = []
        self.status: str = "open"
        self.created_at = time.time()
        self.completed_at: Optional[float] = None

        # State persistence
        if state_dir is None:
            state_dir = Path(__file__).resolve().parent / "backups"
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._state_file = self.state_dir / f"{self.transaction_id}.json"

        # Rollback handlers: step_id -> callable
        self._rollback_handlers: Dict[str, Callable] = {}

    def add_step(self, step_id: str, description: str) -> 'Transaction':
        """Add a step to the transaction."""
        self.steps.append(TransactionStep(step_id=step_id, description=description))
        return self

    def set_rollback(self, step_id: str, handler: Callable):
        """Register a rollback handler for a step."""
        self._rollback_handlers[step_id] = handler

    def execute(self, step_id: str, action: Callable, rollback: Optional[Callable] = None):
        """
        Execute a single step within the transaction.

        Args:
            step_id: ID of the step (must have been added via add_step).
            action: Callable that performs the step.
            rollback: Optional callable to undo the step.

        Raises:
            TransactionError if the step fails.
        """
        step = self._find_step(step_id)
        if step is None:
            raise TransactionError(f"Step '{step_id}' not found")

        logger.info(f"  [{self.transaction_id}] Executing: {step.description}")

        if rollback:
            self.set_rollback(step_id, rollback)

        try:
            result = action()
            step.complete(result)
            self._save_state()
            logger.info(f"  [{self.transaction_id}] ✓ {step.description}")
        except Exception as e:
            step.fail(str(e))
            self._save_state()
            logger.error(f"  [{self.transaction_id}] ✗ {step.description}: {e}")
            raise TransactionError(f"Step '{step_id}' failed: {e}") from e

    def _find_step(self, step_id: str) -> Optional[TransactionStep]:
        """Find a step by ID."""
        for step in self.steps:
            if step.step_id == step_id:
                return step
        return None

    def commit(self):
        """Commit the transaction (all steps completed successfully)."""
        self.status = "committed"
        self.completed_at = time.time()
        self._save_state()
        logger.info(f"[{self.transaction_id}] Transaction committed")
        # Clean up state file after successful commit
        try:
            self._state_file.unlink()
        except OSError:
            pass

    def rollback(self) -> bool:
        """
        Roll back all completed steps in reverse order.

        Returns:
            True if rollback was fully successful.
        """
        logger.info(f"[{self.transaction_id}] Rolling back transaction...")
        all_success = True

        # Roll back in reverse order
        for step in reversed(self.steps):
            if step.status == "completed":
                handler = self._rollback_handlers.get(step.step_id)
                if handler:
                    try:
                        handler()
                        step.rollback()
                        logger.info(f"  Rolled back: {step.description}")
                    except Exception as e:
                        logger.error(f"  Rollback failed for '{step.description}': {e}")
                        all_success = False
                else:
                    logger.warning(f"  No rollback handler for '{step.description}'")
                    step.rollback()

        self.status = "rolled_back"
        self._save_state()
        return all_success

    @staticmethod
    def recover_incomplete(state_dir: Path) -> Optional['Transaction']:
        """
        Recover an incomplete transaction from disk (crash recovery).

        Args:
            state_dir: Directory containing transaction state files.

        Returns:
            The recovered Transaction if found, None otherwise.
        """
        if not state_dir.exists():
            return None

        # Find the most recent incomplete transaction
        txn_files = sorted(state_dir.glob("txn_*.json"), reverse=True)
        if not txn_files:
            return None

        latest = txn_files[0]
        try:
            data = json.loads(latest.read_text(encoding="utf-8"))
            txn = Transaction(data["name"], state_dir)
            txn.transaction_id = data["transaction_id"]
            txn.status = data["status"]
            txn.created_at = data["created_at"]
            txn.completed_at = data.get("completed_at")

            for step_data in data["steps"]:
                step = TransactionStep(**step_data)
                txn.steps.append(step)

            logger.info(f"Recovered incomplete transaction: {txn.transaction_id} (status: {txn.status})")
            return txn

        except Exception as e:
            logger.error(f"Failed to recover transaction: {e}")
            return None

    def _save_state(self):
        """Persist transaction state to disk for crash recovery."""
        try:
            data = {
                "transaction_id": self.transaction_id,
                "name": self.name,
                "status": self.status,
                "created_at": self.created_at,
                "completed_at": self.completed_at,
                "steps": [asdict(s) for s in self.steps],
            }
            self._state_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to save transaction state: {e}")


# =========================================================================
#  2.  Logging with Rotation
# =========================================================================

class RotatingFileLogger:
    """
    File logger with automatic rotation to prevent unbounded log growth.
    """

    MAX_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
    MAX_BACKUPS = 3

    def __init__(self, log_dir: Path, name: str = "installer"):
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = log_dir / f"{name}.log"
        self._setup_logger(name)

    def _setup_logger(self, name: str):
        """Set up the Python logger with file handler."""
        self.logger = logging.getLogger(f"safety.{name}")
        self.logger.setLevel(logging.DEBUG)

        # File handler
        handler = logging.FileHandler(self.log_path, encoding="utf-8")
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s  %(levelname)s  %(name)s  %(message)s",
        ))
        self.logger.addHandler(handler)

        # Check rotation on setup
        self._check_rotation()

    def _check_rotation(self):
        """Rotate log if it exceeds the maximum size."""
        if self.log_path.exists() and self.log_path.stat().st_size > self.MAX_SIZE_BYTES:
            self._rotate()

    def _rotate(self):
        """Perform log rotation."""
        for i in range(self.MAX_BACKUPS - 1, 0, -1):
            backup = self.log_path.with_suffix(f".log.{i}")
            prev = self.log_path.with_suffix(f".log.{i - 1}")
            if prev.exists():
                shutil.move(str(prev), str(backup))

        # Rename current to .log.0
        if self.log_path.exists():
            shutil.move(str(self.log_path), str(self.log_path.with_suffix(".log.0")))

        # Recreate empty log
        self.log_path.touch()

    def get_content(self, max_lines: int = 200) -> str:
        """Get the last max_lines of the log."""
        if not self.log_path.exists():
            return ""

        try:
            content = self.log_path.read_text(encoding="utf-8", errors="ignore")
            lines = content.splitlines()
            return "\n".join(lines[-max_lines:])
        except Exception:
            return ""


# =========================================================================
#  3.  Safe Mode
# =========================================================================

class SafeMode:
    """
    Safe mode startup for the installer.

    Detects:
      - Previous crash/abnormal termination
      - Corrupted state files
      - Missing critical files
      - Partial installations

    On detection, prompts for recovery action.
    """

    SAFETY_MARKER_FILE = ".installer_safe_start"

    def __init__(self, state_dir: Path):
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.marker_path = state_dir / self.SAFETY_MARKER_FILE
        self.crashed = False
        self.issues: List[str] = []

    def check_startup(self) -> bool:
        """
        Perform safe mode checks on startup.

        Returns:
            True if safe to proceed, False if critical issues found.
        """
        logger.info("Running safe mode startup check...")

        # Check 1: Previous crash marker
        if self.marker_path.exists():
            self.crashed = True
            self.issues.append("Previous session may have crashed or was interrupted.")
            logger.warning("Detected possible previous crash (safety marker present)")

        # Check 2: Incomplete transactions
        incomplete = self._find_incomplete_transactions()
        if incomplete:
            self.issues.append(f"Found {len(incomplete)} incomplete transaction(s).")
            logger.warning(f"Found {len(incomplete)} incomplete transaction(s)")

        # Check 3: Corrupted state files
        corrupted = self._check_corrupted_state()
        if corrupted:
            self.issues.append(f"Found {len(corrupted)} corrupted state file(s).")

        # Create safety marker
        self._create_marker()

        if self.issues:
            logger.warning(f"Safe mode found {len(self.issues)} issue(s):")
            for issue in self.issues:
                logger.warning(f"  - {issue}")

        return len(self.issues) == 0

    def _find_incomplete_transactions(self) -> List[Path]:
        """Find transaction state files with non-terminal status."""
        incomplete = []
        for f in self.state_dir.glob("txn_*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if data.get("status") not in ("committed", "rolled_back"):
                    incomplete.append(f)
            except (json.JSONDecodeError, Exception):
                corrupted = self.state_dir / f.name
                incomplete.append(corrupted)
        return incomplete

    def _check_corrupted_state(self) -> List[Path]:
        """Find corrupted state files."""
        corrupted = []
        for f in self.state_dir.glob("*.json"):
            try:
                json.loads(f.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, Exception):
                corrupted.append(f)
        return corrupted

    def _create_marker(self):
        """Create the safe mode marker file."""
        try:
            self.marker_path.write_text(
                json.dumps({
                    "started_at": time.time(),
                    "pid": os.getpid(),
                    "host": platform.node() if hasattr(platform, 'node') else "unknown",
                }, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"Failed to create safety marker: {e}")

    def clear_marker(self):
        """Remove the safe mode marker (call on clean shutdown)."""
        try:
            if self.marker_path.exists():
                self.marker_path.unlink()
        except OSError as e:
            logger.warning(f"Failed to clear safety marker: {e}")

    def recover(self) -> bool:
        """
        Attempt recovery from detected issues.

        Returns:
            True if recovery was successful or not needed.
        """
        if not self.crashed and not self.issues:
            return True

        logger.info("Attempting recovery...")
        success = True

        # Recover incomplete transactions
        incomplete = self._find_incomplete_transactions()
        for txn_file in incomplete:
            try:
                txn = Transaction.recover_incomplete(self.state_dir)
                if txn:
                    if txn.status == "open":
                        logger.info(f"Rolling back incomplete transaction: {txn.transaction_id}")
                        txn.rollback()
                    # Clean up state file
                    txn_file.unlink(missing_ok=True)
            except Exception as e:
                logger.error(f"Failed to recover transaction from {txn_file}: {e}")
                success = False
                # Remove corrupted file to allow progress
                try:
                    txn_file.rename(txn_file.with_suffix(".recovered.bak"))
                except OSError:
                    pass

        # Clean corrupted state files
        corrupted = self._check_corrupted_state()
        for f in corrupted:
            try:
                f.rename(f.with_suffix(".corrupted.bak"))
                logger.info(f"Renamed corrupted state file: {f.name}")
            except OSError:
                pass

        # Clear marker
        self.clear_marker()

        return success


# =========================================================================
#  4.  Partial Install Recovery
# =========================================================================

class PartialInstallRecovery:
    """
    Handles recovery from partial installations.

    Useful when:
      - WASM file was not found during installation
      - Some aircraft were patched but not others
      - Copy operation was interrupted
    """

    @staticmethod
    def detect_partial_install(community_path: Path) -> List[str]:
        """Detect partial installations in the Community folder."""
        issues = []

        hgs_package = community_path / "C_HUD_Runway"
        if not hgs_package.exists():
            return issues  # No HGS package means no install attempt

        # Check for incomplete HGS package
        expected_files = [
            "layout.json",
            "SimObjects/Airplanes/C_HUD_Runway/panel/panel.cfg",
            "SimObjects/Airplanes/C_HUD_Runway/panel/C_HUD_Runway.wasm",
            "SimObjects/Airplanes/C_HUD_Runway/panel/HUD/hud_overlay.html",
            "SimObjects/Airplanes/C_HUD_Runway/aircraft.cfg",
        ]

        for rel_path in expected_files:
            if not (hgs_package / rel_path).exists():
                issues.append(f"Missing file in HGS package: {rel_path}")

        # Check for aircraft with patched panel.cfg but not layout.json
        from installer.aircraft_scanner import scan_community
        packages = scan_community(community_path)
        for pkg in packages:
            has_panel = any(
                "C_HUD_Runway" in str(pc.path) or "Gauge_ConformalHUD" in str(pc.entries)
                for pc in pkg.panel_configs
            )
            has_layout = False
            if pkg.layout_path:
                from installer.patch_engine import LayoutPatcher
                has_layout = LayoutPatcher.has_hgs_entries(pkg.layout_path)

            if has_panel and not has_layout:
                issues.append(f"Aircraft {pkg.aircraft_type.value}: panel.cfg patched but layout.json not patched")
            elif has_layout and not has_panel:
                issues.append(f"Aircraft {pkg.aircraft_type.value}: layout.json patched but panel.cfg not patched")

        return issues

    @staticmethod
    def fix_partial_install(community_path: Path) -> bool:
        """Fix partial installations."""
        issues = PartialInstallRecovery.detect_partial_install(community_path)
        if not issues:
            return True

        logger.info(f"Fixing {len(issues)} partial install issue(s)...")
        from installer.patch_engine import FileCopier, LayoutPatcher, PanelCfgPatcher
        from installer.aircraft_scanner import scan_community

        # Ensure HGS package is complete
        FileCopier.copy_hgs_to_community(community_path)

        # Re-patch all aircraft
        packages = scan_community(community_path)
        for pkg in packages:
            if pkg.layout_path:
                LayoutPatcher.patch_layout(pkg.layout_path)
            for pc in pkg.panel_configs:
                PanelCfgPatcher.patch_panel(pc.path)

        return True


# =========================================================================
#  CLI entry point
# =========================================================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Operational Safety Module")
    print("=" * 60)
    print("Transaction system, safe mode, and recovery utilities.")
