"""
Tests for C_HUD_Runway Installer — Signature Verifier
=====================================================
Phase 2 tests for package signature verification.
"""

import sys
import json
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from installer.signature_verifier import (
    SignatureVerifier,
    VerificationResult,
    PackageSignature,
    FileSignature,
    generate_package_signature,
    compute_file_hash,
    verify_integration_safety,
    record_known_signature,
    KNOWN_AIRCRAFT_SIGNATURES,
    CRITICAL_FILES,
)
from installer.aircraft_scanner import (
    AircraftPackage,
    AircraftType,
    IntegrationStatus,
)


# =========================================================================
#  Helpers
# =========================================================================

def create_test_package(
    tmp_dir: Path,
    name: str = "pmdg-737-800",
    aircraft_type: AircraftType = AircraftType.PMDG_737_800,
    version_major: int = 3,
    version_minor: int = 0,
    with_critical: bool = True,
    extra_files: list = None,
) -> Path:
    """Create a test aircraft package structure."""
    pkg_dir = tmp_dir / name
    pkg_dir.mkdir(parents=True, exist_ok=True)

    sim_dir = pkg_dir / "SimObjects" / "Airplanes" / name
    sim_dir.mkdir(parents=True, exist_ok=True)
    panel_dir = sim_dir / "panel"
    panel_dir.mkdir(parents=True, exist_ok=True)

    if with_critical:
        (panel_dir / "panel.cfg").write_text(
            "[VCockpit01]\nsize_mm = 1024, 1024\n"
            "gauge00 = Test!Gauge, 0, 0, 300, 300\n",
            encoding="utf-8",
        )
        layout = pkg_dir / "layout.json"
        layout.write_text(json.dumps({
            "content": [
                {"path": f"SimObjects/Airplanes/{name}/panel/panel.cfg",
                 "size": 100, "date": 0},
            ]
        }), encoding="utf-8")
        manifest = pkg_dir / "manifest.json"
        manifest.write_text(
            json.dumps({"version": f"{version_major}.{version_minor}.0"}),
            encoding="utf-8",
        )

    if extra_files:
        for fname in extra_files:
            fpath = pkg_dir / fname
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(f"content of {fname}", encoding="utf-8")

    return pkg_dir


def make_aircraft_package(pkg_dir: Path, atype: AircraftType, vmaj: int, vmin: int) -> AircraftPackage:
    """Create an AircraftPackage from a directory path."""
    return AircraftPackage(
        package_path=pkg_dir,
        aircraft_type=atype,
        title_prefix=atype.value,
        detected_version_major=vmaj,
        detected_version_minor=vmin,
    )


# =========================================================================
#  Tests
# =========================================================================

class TestFileHash:
    """Test file hash computation."""

    def test_compute_hash_valid(self):
        import os
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("test content")
            f.flush()
            hash_val = compute_file_hash(Path(f.name))
        os.unlink(f.name)
        assert len(hash_val) == 64
        assert hash_val != ""

    def test_compute_hash_nonexistent(self):
        hash_val = compute_file_hash(Path("/nonexistent/file.txt"))
        assert hash_val == ""


class TestGenerateSignature:
    """Test package signature generation."""

    def test_generate_valid_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg_dir = create_test_package(Path(tmp))
            pkg = make_aircraft_package(pkg_dir, AircraftType.PMDG_737_800, 3, 0)
            sig = generate_package_signature(pkg)
            assert sig is not None
            assert sig.package_name == pkg_dir.name
            assert sig.aircraft_type == "PMDG 737-800"
            assert sig.file_count >= 3

    def test_generate_empty_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty_dir = Path(tmp) / "empty-pkg"
            empty_dir.mkdir()
            pkg = make_aircraft_package(empty_dir, AircraftType.PMDG_737_800, 0, 0)
            sig = generate_package_signature(pkg)
            assert sig is not None
            assert sig.file_count == 0

    def test_signature_manifest_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg_dir = create_test_package(Path(tmp))
            pkg = make_aircraft_package(pkg_dir, AircraftType.PMDG_737_800, 3, 0)
            sig = generate_package_signature(pkg)
            assert sig.manifest_hash != ""
            assert sig.signed_manifest_hash == sig.manifest_hash


class TestSignatureVerifier:
    """Test signature verification."""

    def test_verify_clean_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg_dir = create_test_package(Path(tmp))
            pkg = make_aircraft_package(pkg_dir, AircraftType.PMDG_737_800, 3, 0)
            verifier = SignatureVerifier()
            result = verifier.verify_package(pkg)
            # No known signature, should pass via confidence
            assert result.confidence >= 0.5

    def test_verify_with_known_signature(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg_dir = create_test_package(Path(tmp))
            pkg = make_aircraft_package(pkg_dir, AircraftType.PMDG_737_800, 3, 0)
            record_known_signature(pkg)
            verifier = SignatureVerifier()
            result = verifier.verify_package(pkg)
            assert result.matched or result.passed

    def test_verify_tampered_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg_dir = create_test_package(Path(tmp))
            pkg = make_aircraft_package(pkg_dir, AircraftType.PMDG_737_800, 3, 0)
            record_known_signature(pkg)

            # Find and tamper with panel.cfg
            panel_cfg = pkg_dir / "SimObjects" / "Airplanes" / pkg_dir.name / "panel" / "panel.cfg"
            if not panel_cfg.exists():
                cfgs = list(pkg_dir.rglob("panel.cfg"))
                panel_cfg = cfgs[0] if cfgs else None
            if panel_cfg and panel_cfg.exists():
                panel_cfg.write_text(
                    "gauge00 = Malicious!Code, 0, 0, 9999, 9999\n",
                    encoding="utf-8",
                )

            verifier = SignatureVerifier()
            result = verifier.verify_package(pkg)
            assert len(result.tampered_files) > 0 or not result.passed

    def test_verify_missing_critical_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg_dir = create_test_package(Path(tmp), with_critical=False)
            pkg = make_aircraft_package(pkg_dir, AircraftType.PMDG_737_800, 3, 0)
            verifier = SignatureVerifier()
            result = verifier.verify_package(pkg)
            has_critical_missing = any(
                "layout.json" in e or "manifest.json" in e
                for e in result.errors
            )
            assert has_critical_missing or len(result.missing_files) > 0

    def test_verify_then_tamper_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg_dir = create_test_package(Path(tmp))
            pkg = make_aircraft_package(pkg_dir, AircraftType.PMDG_737_800, 3, 0)
            sig = record_known_signature(pkg)
            assert sig is not None

            layout = pkg_dir / "layout.json"
            if layout.exists():
                original = layout.read_text(encoding="utf-8")
                layout.write_text(original + "\n", encoding="utf-8")

            verifier = SignatureVerifier()
            result = verifier.verify_package(pkg)
            assert not result.passed or len(result.tampered_files) > 0

    def test_integration_safety_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg_dir = create_test_package(Path(tmp))
            pkg = make_aircraft_package(pkg_dir, AircraftType.PMDG_737_800, 3, 0)
            safe, result = verify_integration_safety(pkg)
            assert isinstance(safe, bool)
            assert isinstance(result, VerificationResult)

    def test_is_package_safe_to_patch(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg_dir = create_test_package(Path(tmp))
            pkg = make_aircraft_package(pkg_dir, AircraftType.PMDG_737_800, 3, 0)
            verifier = SignatureVerifier()
            safe, warnings = verifier.is_package_safe_to_patch(pkg)
            assert isinstance(safe, bool)
            assert isinstance(warnings, list)

    def test_verify_backup_integrity(self):
        with tempfile.TemporaryDirectory() as tmp:
            from zipfile import ZipFile
            backup_dir = Path(tmp) / "backups"
            backup_dir.mkdir()
            backup_path = backup_dir / "test_backup.zip"
            with ZipFile(backup_path, "w") as zf:
                zf.writestr("panel.cfg", "gauge00 = Test\n")
                zf.writestr("layout.json", '{"content": []}')

            verifier = SignatureVerifier()
            result = verifier.verify_backup_integrity(backup_path)
            assert result.passed is True


class TestKnownSignatures:
    """Test known signature database."""

    def test_known_signatures_exist(self):
        assert len(KNOWN_AIRCRAFT_SIGNATURES) > 0
        assert "PMDG 737-800" in KNOWN_AIRCRAFT_SIGNATURES

    def test_record_known_signature(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg_dir = create_test_package(Path(tmp))
            pkg = make_aircraft_package(pkg_dir, AircraftType.PMDG_737_800, 3, 0)
            sig = record_known_signature(pkg)
            assert sig is not None
            assert pkg.aircraft_type.value in KNOWN_AIRCRAFT_SIGNATURES

    def test_all_aircraft_have_entries(self):
        all_types = [
            "PMDG 737-800", "PMDG 737-700", "PMDG 777-300ER",
            "ASOBO 787-10", "WT 787-10", "iniBuilds A350",
            "FBW A32NX", "HEADWIND A330-900",
        ]
        for atype in all_types:
            assert atype in KNOWN_AIRCRAFT_SIGNATURES, f"Missing: {atype}"


class TestVerificationResult:
    """Test VerificationResult data integrity."""

    def test_passed_defaults_to_false(self):
        result = VerificationResult(passed=False, package_name="test", aircraft_type="test")
        assert result.passed is False
        assert result.confidence == 0.0

    def test_tampered_files_tracked(self):
        result = VerificationResult(
            passed=False, package_name="test", aircraft_type="test",
            tampered_files=["panel.cfg"],
        )
        assert "panel.cfg" in result.tampered_files

    def test_missing_files_tracked(self):
        result = VerificationResult(
            passed=False, package_name="test", aircraft_type="test",
            missing_files=["layout.json"],
        )
        assert "layout.json" in result.missing_files


class TestAircraftCompatibilityViaSignature:
    """Test that all supported aircraft types can generate signatures."""

    def _create_and_verify(self, tmp: str, name: str, atype: AircraftType, vmaj: int, vmin: int):
        tmp_path = Path(tmp)
        pkg_dir = create_test_package(tmp_path, name, atype, vmaj, vmin)
        pkg = make_aircraft_package(pkg_dir, atype, vmaj, vmin)
        sig = generate_package_signature(pkg)
        assert sig is not None
        assert sig.file_count >= 3

    def test_pmdg_737_signature(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._create_and_verify(tmp, "pmdg-737-800", AircraftType.PMDG_737_800, 3, 0)

    def test_pmdg_777_signature(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._create_and_verify(tmp, "pmdg-777-300er", AircraftType.PMDG_777_300ER, 1, 0)

    def test_inibuilds_a350_signature(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._create_and_verify(tmp, "inibuilds-a350", AircraftType.INIBUILDS_A350, 1, 0)

    def test_fbw_a32nx_signature(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._create_and_verify(tmp, "fbw-a32nx", AircraftType.FBW_A32NX, 1, 0)

    def test_headwind_a330_signature(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._create_and_verify(tmp, "headwind-a330-900", AircraftType.HEADWIND_A330_900, 1, 0)
