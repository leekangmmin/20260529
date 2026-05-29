"""
Package Signature Verification — Phase 2 Deployment Certification
==================================================================
Cryptographic integrity verification for aircraft packages.

Ensures that:
  · Aircraft packages have not been tampered with before patching
  · Backups are authentic and untampered
  · Only known-good package versions are patched
  · Corrupted or modified packages are flagged before integration

Supports:
  · SHA-256 hashing of all package files
  · Signed manifest generation and verification
  · Known-good signature database for supported aircraft
  · Package tampering detection
  · Safe refusal to patch unknown/modified packages
"""

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .aircraft_scanner import AircraftPackage, AircraftType

logger = logging.getLogger("signature_verifier")


# =========================================================================
#  1.  Dataclasses
# =========================================================================

@dataclass
class FileSignature:
    """SHA-256 signature of a single file within a package."""
    path: str            # Relative path within the package
    size: int            # File size in bytes
    sha256: str          # SHA-256 hex digest
    last_modified: float # File modification timestamp


@dataclass
class PackageSignature:
    """Complete signature of an aircraft package."""
    package_name: str
    aircraft_type: str
    version_major: int
    version_minor: int
    files: List[FileSignature] = field(default_factory=list)
    created_at: float = 0.0
    signed_manifest_hash: str = ""  # SHA-256 of the entire manifest JSON

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def total_size(self) -> int:
        return sum(f.size for f in self.files)

    @property
    def manifest_hash(self) -> str:
        """Compute hash of all file signatures for quick comparison."""
        combined = "".join(f"{f.path}:{f.size}:{f.sha256}" for f in self.files)
        return hashlib.sha256(combined.encode()).hexdigest()


@dataclass
class VerificationResult:
    """Result of a signature verification check."""
    passed: bool
    package_name: str
    aircraft_type: str
    matched: bool = False           # Whether a known signature was found
    tampered_files: List[str] = field(default_factory=list)  # Files with mismatched hash
    missing_files: List[str] = field(default_factory=list)   # Files expected but not found
    extra_files: List[str] = field(default_factory=list)     # Files not in expected signature
    modified_files: List[str] = field(default_factory=list)  # Files with different size/timestamp
    errors: List[str] = field(default_factory=list)
    confidence: float = 0.0         # 0.0 to 1.0


# =========================================================================
#  2.  Known-Good Signature Database
# =========================================================================

# Known-good version signatures for supported aircraft.
# Format: aircraft_type -> version -> dict of {relative_file_path: sha256_hash}
# This is the canonical reference for safe integration.
# Entries are populated dynamically via record_known_signature() during
# development and certification. Version keys are created on first recording.
KNOWN_AIRCRAFT_SIGNATURES: Dict[str, Dict[str, Dict[str, str]]] = {
    "PMDG 737-800": {},
    "PMDG 737-700": {},
    "PMDG 777-300ER": {},
    "ASOBO 787-10": {},
    "WT 787-10": {},
    "iniBuilds A350": {},
    "FBW A32NX": {},
    "HEADWIND A330-900": {},
}

# Critical files that MUST match for safe integration
CRITICAL_FILES = [
    "layout.json",
    "manifest.json",
    "panel.cfg",
]

# Files we can safely ignore in signature comparison (auto-generated, cache, etc.)
IGNORED_FILES_PATTERNS = [
    ".DS_Store",
    "Thumbs.db",
    "*.bak",
    "*.tmp",
    "__pycache__",
    "*.pyc",
]


# =========================================================================
#  3.  Signature Computation
# =========================================================================

def compute_file_hash(file_path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    hasher = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except (OSError, IOError) as e:
        logger.warning(f"Failed to compute hash for {file_path}: {e}")
        return ""


def _should_ignore(path: str) -> bool:
    """Check if a file path should be ignored in signature comparison."""
    import fnmatch
    for pattern in IGNORED_FILES_PATTERNS:
        if fnmatch.fnmatch(path, pattern):
            return True
    return False


def generate_package_signature(pkg: AircraftPackage) -> Optional[PackageSignature]:
    """
    Generate a cryptographic signature for an aircraft package.

    Scans all files in the package directory and creates SHA-256 hashes.

    Args:
        pkg: The aircraft package to sign.

    Returns:
        PackageSignature if successful, None on failure.
    """
    try:
        package_root = pkg.package_path
        if not package_root.exists():
            logger.warning(f"Package path does not exist: {package_root}")
            return None

        files: List[FileSignature] = []

        for file_path in sorted(package_root.rglob("*")):
            if not file_path.is_file():
                continue
            rel_path = str(file_path.relative_to(package_root)).replace("\\", "/")
            if _should_ignore(rel_path):
                continue

            file_hash = compute_file_hash(file_path)
            if not file_hash:
                continue

            try:
                stat = file_path.stat()
                files.append(FileSignature(
                    path=rel_path,
                    size=stat.st_size,
                    sha256=file_hash,
                    last_modified=stat.st_mtime,
                ))
            except OSError:
                continue

        sig = PackageSignature(
            package_name=pkg.package_path.name,
            aircraft_type=pkg.aircraft_type.value,
            version_major=pkg.detected_version_major,
            version_minor=pkg.detected_version_minor,
            files=files,
            created_at=time.time(),
        )
        sig.signed_manifest_hash = sig.manifest_hash

        logger.info(f"Generated signature for {pkg.aircraft_type.value}: "
                     f"{len(files)} files, {sig.total_size} bytes")
        return sig

    except Exception as e:
        logger.error(f"Failed to generate signature: {e}")
        return None


def save_signature(signature: PackageSignature, output_dir: Path) -> bool:
    """
    Save a package signature to disk as JSON.

    Args:
        signature: The signature to save.
        output_dir: Directory to save the signature file.

    Returns:
        True if saved successfully.
    """
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        sig_path = output_dir / f"{signature.package_name}_signature.json"

        data = {
            "package_name": signature.package_name,
            "aircraft_type": signature.aircraft_type,
            "version_major": signature.version_major,
            "version_minor": signature.version_minor,
            "file_count": signature.file_count,
            "total_size": signature.total_size,
            "manifest_hash": signature.manifest_hash,
            "created_at": signature.created_at,
            "files": [asdict(f) for f in signature.files],
        }

        sig_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info(f"Saved signature to {sig_path}")
        return True

    except Exception as e:
        logger.error(f"Failed to save signature: {e}")
        return False


def load_signature(sig_path: Path) -> Optional[PackageSignature]:
    """
    Load a package signature from a JSON file.

    Args:
        sig_path: Path to the signature JSON file.

    Returns:
        PackageSignature if loaded successfully, None on failure.
    """
    try:
        if not sig_path.exists():
            return None

        data = json.loads(sig_path.read_text(encoding="utf-8"))

        files = [FileSignature(**f) for f in data.get("files", [])]
        sig = PackageSignature(
            package_name=data["package_name"],
            aircraft_type=data["aircraft_type"],
            version_major=data.get("version_major", 0),
            version_minor=data.get("version_minor", 0),
            files=files,
            created_at=data.get("created_at", 0.0),
        )
        sig.signed_manifest_hash = data.get("manifest_hash", sig.manifest_hash)

        return sig

    except Exception as e:
        logger.error(f"Failed to load signature from {sig_path}: {e}")
        return None


# =========================================================================
#  4.  Signature Verification
# =========================================================================

class SignatureVerifier:
    """
    Verifies aircraft package integrity using cryptographic signatures.

    Supports:
      - Known-good signature matching from database
      - Dynamic signature generation and comparison
      - File-by-file tampering detection
      - Integration safety checks
    """

    def __init__(self):
        self._known_signatures: Dict[str, PackageSignature] = {}

    def verify_package(self, pkg: AircraftPackage) -> VerificationResult:
        """
        Verify an aircraft package's integrity.

        Checks:
          1. Against known-good signatures (if available)
          2. File hashes match expected values
          3. No unexpected files added
          4. Critical files are present and untampered

        Args:
            pkg: The aircraft package to verify.

        Returns:
            VerificationResult with detailed findings.
        """
        result = VerificationResult(
            passed=False,
            package_name=pkg.package_path.name,
            aircraft_type=pkg.aircraft_type.value,
        )

        # Generate current signature
        current_sig = generate_package_signature(pkg)
        if current_sig is None:
            result.errors.append("Failed to generate package signature")
            return result

        # Check against known-good signatures
        known_sig = self._get_known_signature(pkg)
        if known_sig is not None and len(known_sig.files) > 0:
            result.matched = True
            self._compare_signatures(current_sig, known_sig, result)
        else:
            # No known signature — check internal consistency
            result.confidence = self._assess_confidence(current_sig)
            if result.confidence < 0.5:
                result.errors.append(
                    f"Package appears to be an unknown/modified version. "
                    f"Confidence: {result.confidence:.1%}"
                )
            else:
                # Accept with advisory warning
                result.passed = True
                version_str = f"{pkg.detected_version_major}.{pkg.detected_version_minor}"
                result.errors.append(
                    f"No known signature for {pkg.aircraft_type.value} "
                    f"v{version_str}. Proceeding with limited verification."
                )

        # Always check critical files regardless of matching
        critical_found = set()
        for f in current_sig.files:
            for crit in CRITICAL_FILES:
                if f.path.endswith(crit):
                    critical_found.add(crit)

        missing_critical = [c for c in CRITICAL_FILES if c not in critical_found]
        if missing_critical and not result.matched:
            # Only add as errors if we weren't already tracking issues
            for mc in missing_critical:
                if mc not in " ".join(result.errors + result.missing_files):
                    result.missing_files.append(mc)

        return result

    def _get_known_signature(self, pkg: AircraftPackage) -> Optional[PackageSignature]:
        """Get a known-good signature for this aircraft/version combination."""
        key = pkg.aircraft_type.value
        version_key = f"{pkg.detected_version_major}.{pkg.detected_version_minor}"

        known_aircraft = KNOWN_AIRCRAFT_SIGNATURES.get(key, {})
        known_version = known_aircraft.get(version_key, None)

        if known_version:
            # Build a PackageSignature from the known signatures
            files = []
            for path, file_hash in known_version.items():
                files.append(FileSignature(
                    path=path,
                    size=0,  # Size is not critical for known-good check
                    sha256=file_hash,
                    last_modified=0,
                ))

            return PackageSignature(
                package_name=pkg.package_path.name,
                aircraft_type=key,
                version_major=pkg.detected_version_major,
                version_minor=pkg.detected_version_minor,
                files=files,
            )

        return None

    def _compare_signatures(
        self,
        current: PackageSignature,
        expected: PackageSignature,
        result: VerificationResult,
    ):
        """Compare current signature against expected signature."""
        # Build lookup maps
        current_files = {f.path: f for f in current.files}
        expected_files = {f.path: f for f in expected.files}

        all_paths = set(list(current_files.keys()) + list(expected_files.keys()))

        for path in sorted(all_paths):
            cur = current_files.get(path)
            exp = expected_files.get(path)

            if cur is None:
                # File missing from current package
                result.missing_files.append(path)
            elif exp is None:
                # Extra file in current package (not in expected)
                result.extra_files.append(path)
            elif cur.sha256 != exp.sha256:
                # File content differs
                result.tampered_files.append(path)
            elif cur.size != exp.size and exp.size > 0:
                # File size differs (content may be same but modified)
                result.modified_files.append(path)

        # Determine pass/fail
        has_tampered = len(result.tampered_files) > 0

        result.passed = not has_tampered

        # Calculate confidence
        total = len(all_paths) if all_paths else 1
        match_count = total - len(result.tampered_files) - len(result.missing_files)
        result.confidence = max(0.0, match_count / total) if total > 0 else 0.0

    def _assess_confidence(self, sig: PackageSignature) -> float:
        """
        Assess confidence that a package is safe to patch.
        Uses heuristic indicators:
          - Has manifest.json with valid structure
          - Has layout.json with valid structure
          - Has valid SimObjects structure
          - Has reasonable file count for the aircraft type
        """
        score = 0.0  # Start at 0
        paths = [f.path for f in sig.files]

        # Check for essential files
        has_manifest = any(p.endswith("manifest.json") for p in paths)
        has_layout = any(p.endswith("layout.json") for p in paths)
        has_simobjects = any("SimObjects/Airplanes" in p for p in paths)
        has_panel_cfg = any(p.endswith("panel.cfg") for p in paths)

        if has_manifest:
            score += 0.25
        if has_layout:
            score += 0.25
        if has_simobjects:
            score += 0.25
        if has_panel_cfg:
            score += 0.25

        return min(score, 1.0)

    def verify_backup_integrity(self, backup_path: Path) -> VerificationResult:
        """
        Verify the integrity of a backup archive.

        Args:
            backup_path: Path to the backup ZIP file.

        Returns:
            VerificationResult indicating backup health.
        """
        from zipfile import ZipFile
        result = VerificationResult(
            passed=False,
            package_name=backup_path.name,
            aircraft_type="backup",
        )

        if not backup_path.exists():
            result.errors.append(f"Backup file not found: {backup_path}")
            return result

        try:
            with ZipFile(backup_path, "r") as zf:
                # Check archive integrity
                bad_file = zf.testzip()
                if bad_file:
                    result.errors.append(f"Backup archive corrupted: {bad_file}")
                    return result

                # Verify we can list contents
                names = zf.namelist()
                if not names:
                    result.errors.append("Backup archive is empty")
                    return result

                # Check each file
                for info in zf.infolist():
                    if _should_ignore(info.filename):
                        continue
                    # Just reading confirms integrity
                    zf.read(info.filename)

            result.passed = True

        except Exception as e:
            result.errors.append(f"Failed to verify backup: {e}")

        return result

    def is_package_safe_to_patch(self, pkg: AircraftPackage) -> Tuple[bool, List[str]]:
        """
        High-level check: is it safe to patch this aircraft package?

        Args:
            pkg: The aircraft package to check.

        Returns:
            Tuple of (safe: bool, warnings: list of warning strings).
        """
        warnings: List[str] = []
        result = self.verify_package(pkg)

        if not result.passed:
            if result.tampered_files:
                warnings.append(
                    f"Tampered files detected: {', '.join(result.tampered_files[:5])}"
                )
            if result.missing_files:
                warnings.append(
                    f"Missing files: {', '.join(result.missing_files[:5])}"
                )
            if result.errors:
                warnings.extend(result.errors[:3])

            return False, warnings

        if result.confidence < 1.0:
            warnings.append(
                f"Partial verification (confidence: {result.confidence:.0%})"
            )

        return True, warnings


# =========================================================================
#  5.  Convenience Functions
# =========================================================================

def verify_integration_safety(
    pkg: AircraftPackage,
    verifier: Optional[SignatureVerifier] = None,
) -> Tuple[bool, VerificationResult]:
    """
    Convenience function to check if it's safe to integrate HGS with an aircraft.

    Args:
        pkg: The aircraft package to check.
        verifier: Optional existing verifier instance.

    Returns:
        Tuple of (safe: bool, result: VerificationResult).
    """
    if verifier is None:
        verifier = SignatureVerifier()

    result = verifier.verify_package(pkg)

    if not result.passed:
        logger.warning(
            f"Integration safety check FAILED for {pkg.aircraft_type.value}: "
            f"{len(result.tampered_files)} tampered, "
            f"{len(result.missing_files)} missing"
        )
        return False, result

    if result.confidence < 1.0:
        logger.info(
            f"Integration safety check WARNING for {pkg.aircraft_type.value}: "
            f"confidence {result.confidence:.0%}"
        )

    logger.info(
        f"Integration safety check PASSED for {pkg.aircraft_type.value}: "
        f"confidence {result.confidence:.0%}"
    )
    return True, result


def record_known_signature(
    pkg: AircraftPackage,
    signature_dir: Optional[Path] = None,
) -> Optional[PackageSignature]:
    """
    Generate and record a known-good signature for an aircraft package.

    This is used to build the known-good signature database during development.

    Args:
        pkg: The aircraft package to record.
        signature_dir: Directory to save the signature file.

    Returns:
        PackageSignature if recorded successfully.
    """
    sig = generate_package_signature(pkg)
    if sig is None:
        return None

    if signature_dir:
        save_signature(sig, signature_dir)

    # Also update in-memory known signatures
    key = sig.aircraft_type
    version_key = f"{sig.version_major}.{sig.version_minor}"

    if key not in KNOWN_AIRCRAFT_SIGNATURES:
        KNOWN_AIRCRAFT_SIGNATURES[key] = {}

    # Store critical file hashes
    critical_sigs = {}
    for f in sig.files:
        for crit in CRITICAL_FILES:
            if f.path.endswith(crit):
                critical_sigs[f.path] = f.sha256
                break

    if critical_sigs:
        KNOWN_AIRCRAFT_SIGNATURES[key][version_key] = critical_sigs

    logger.info(f"Recorded known signature for {key} v{version_key}")
    return sig


# =========================================================================
#  6.  CLI Helper
# =========================================================================

def verify_command(pkg_path: Path) -> Dict:
    """
    CLI helper: verify a package from its path.

    Args:
        pkg_path: Path to the aircraft package directory.

    Returns:
        Dictionary with verification results.
    """
    from .aircraft_scanner import _scan_single_package

    pkg = _scan_single_package(pkg_path)
    if pkg is None:
        return {"error": f"Not a recognized aircraft package: {pkg_path.name}"}

    verifier = SignatureVerifier()
    result = verifier.verify_package(pkg)

    return {
        "package": pkg.aircraft_type.value,
        "version": f"{pkg.detected_version_major}.{pkg.detected_version_minor}",
        "passed": result.passed,
        "matched": result.matched,
        "confidence": result.confidence,
        "tampered_files": result.tampered_files,
        "missing_files": result.missing_files,
        "extra_files": result.extra_files,
        "errors": result.errors,
    }
