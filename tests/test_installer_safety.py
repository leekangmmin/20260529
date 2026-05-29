"""
Tests for the C_HUD_Runway Installer — Safety Module
=====================================================
Phase 7 tests for operational safety.
"""

import sys
import json
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from installer.safety import (
    Transaction,
    TransactionStep,
    TransactionError,
    SafeMode,
    PartialInstallRecovery,
)


# =========================================================================
#  Tests
# =========================================================================

class TestTransactionSystem:
    """Test the transaction system."""

    def test_create_transaction(self):
        with tempfile.TemporaryDirectory() as tmp:
            txn = Transaction("test", Path(tmp))
            assert txn.status == "open"
            assert txn.transaction_id.startswith("txn_")

    def test_add_steps(self):
        txn = Transaction("test")
        txn.add_step("step1", "First step")
        txn.add_step("step2", "Second step")
        assert len(txn.steps) == 2
        assert txn.steps[0].step_id == "step1"
        assert txn.steps[1].step_id == "step2"

    def test_execute_success(self):
        txn = Transaction("test")
        txn.add_step("step1", "Test step")

        def action():
            return 42

        txn.execute("step1", action)
        assert txn.steps[0].status == "completed"
        assert txn.steps[0].result == 42

    def test_execute_failure(self):
        txn = Transaction("test")
        txn.add_step("step1", "Failing step")

        def action():
            raise ValueError("Something went wrong")

        try:
            txn.execute("step1", action)
            assert False, "Should have raised TransactionError"
        except TransactionError:
            assert txn.steps[0].status == "failed"
            assert txn.steps[0].error is not None

    def test_commit(self):
        txn = Transaction("test")
        txn.add_step("step1", "Step")
        txn.execute("step1", lambda: None)
        txn.commit()
        assert txn.status == "committed"
        assert txn.completed_at is not None

    def test_rollback_with_handler(self):
        txn = Transaction("test")
        txn.add_step("step1", "Rollback step")

        rolled_back = False

        def action():
            return "done"

        def rollback_handler():
            nonlocal rolled_back
            rolled_back = True

        txn.execute("step1", action, rollback_handler)
        txn.rollback()
        assert rolled_back is True
        assert txn.status == "rolled_back"

    def test_complex_workflow(self):
        """Test a multi-step transaction workflow."""
        txn = Transaction("complex")
        state = []

        # Step 1
        txn.add_step("step1", "Initialize")
        txn.execute("step1", lambda: state.append(1))

        # Step 2
        txn.add_step("step2", "Process")
        txn.execute("step2", lambda: state.append(2))

        # Step 3
        txn.add_step("step3", "Finalize")
        txn.execute("step3", lambda: state.append(3))

        txn.commit()
        assert state == [1, 2, 3]
        assert txn.status == "committed"


class TestSafeMode:
    """Test safe mode startup."""

    def test_clean_startup(self):
        with tempfile.TemporaryDirectory() as tmp:
            safety = SafeMode(Path(tmp))
            result = safety.check_startup()
            assert result is True
            # Should clear marker after check
            safety.clear_marker()

    def test_detect_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            safety = SafeMode(Path(tmp))
            # Create a crash marker
            marker = Path(tmp) / ".installer_safe_start"
            marker.write_text("crashed", encoding="utf-8")
            result = safety.check_startup()
            assert result is False  # Issues found

    def test_recover(self):
        with tempfile.TemporaryDirectory() as tmp:
            safety = SafeMode(Path(tmp))
            safety.check_startup()
            safety.clear_marker()
            result = safety.recover()
            assert result is True  # Recovery succeeded or not needed


class TestPartialInstallRecovery:
    """Test partial install recovery."""

    def test_detect_no_issues(self):
        with tempfile.TemporaryDirectory() as tmp:
            community = Path(tmp) / "Community"
            community.mkdir()
            issues = PartialInstallRecovery.detect_partial_install(community)
            assert issues == []  # No HGS package, no issues

    def test_fix_no_issues(self):
        with tempfile.TemporaryDirectory() as tmp:
            community = Path(tmp) / "Community"
            community.mkdir()
            result = PartialInstallRecovery.fix_partial_install(community)
            assert result is True
