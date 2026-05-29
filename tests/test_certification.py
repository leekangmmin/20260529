"""
Tests for C_HUD_Runway Installer — Release Certification
==========================================================
Phase 7 tests for certification pipeline.
"""

import sys
import json
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from installer.certification import (
    CertificationEngine,
    CertificationMatrix,
    CertificationStatus,
    AircraftCertification,
    ReleaseReadinessScore,
    ReportGenerator,
    generate_certification_package,
)
from installer import __version__


# =========================================================================
#  Tests
# =========================================================================

class TestAircraftCertification:
    """Test AircraftCertification dataclass."""

    def test_create_certification(self):
        cert = AircraftCertification(
            aircraft_type="PMDG 737-800",
            aircraft_version="3.0+",
            msfs_version="both",
            status=CertificationStatus.CERTIFIED,
            certification_date="2024-01-01",
        )
        assert cert.aircraft_type == "PMDG 737-800"
        assert cert.status == CertificationStatus.CERTIFIED


class TestCertificationMatrix:
    """Test CertificationMatrix dataclass."""

    def test_empty_matrix(self):
        matrix = CertificationMatrix()
        assert matrix.installer_version == __version__
        assert len(matrix.aircraft_certifications) == 0

    def test_matrix_to_dict(self):
        matrix = CertificationMatrix()
        matrix.aircraft_certifications.append(AircraftCertification(
            aircraft_type="Test",
            aircraft_version="1.0",
            msfs_version="both",
            status=CertificationStatus.BETA,
            certification_date="2024-01-01",
        ))
        data = matrix.to_dict()
        assert "installer_version" in data
        assert len(data["aircraft_certifications"]) == 1


class TestCertificationEngine:
    """Test the certification engine."""

    def test_generate_matrix(self):
        engine = CertificationEngine()
        matrix = engine.generate_certification_matrix()
        assert len(matrix.aircraft_certifications) > 0
        assert matrix.installer_version == __version__
        assert "MSFS 2020" in matrix.supported_simulators

    def test_matrix_has_all_types(self):
        engine = CertificationEngine()
        matrix = engine.generate_certification_matrix()
        types = [ac.aircraft_type for ac in matrix.aircraft_certifications]
        assert "PMDG 737-800" in types
        assert "PMDG 777-300ER" in types
        assert "iniBuilds A350" in types
        assert "FBW A32NX" in types

    def test_compute_readiness_score(self):
        engine = CertificationEngine()
        score = engine.compute_readiness_score()
        assert 0 <= score.total_score <= 100
        assert score.category in ("production_ready", "release_candidate", "beta", "development")
        assert len(score.details) > 0

    def test_readiness_breakdown(self):
        engine = CertificationEngine()
        score = engine.compute_readiness_score()
        assert score.test_score >= 0
        assert score.coverage_score >= 0
        assert score.compatibility_score >= 0
        assert score.stability_score >= 0


class TestReportGenerator:
    """Test report generation."""

    def test_generate_deployment_json(self):
        engine = CertificationEngine()
        reporter = ReportGenerator(engine)
        report = reporter.generate_deployment_report(fmt="json")
        data = json.loads(report)
        assert "certification_matrix" in data
        assert "readiness_score" in data
        assert "installer_version" in data

    def test_generate_deployment_markdown(self):
        engine = CertificationEngine()
        reporter = ReportGenerator(engine)
        report = reporter.generate_deployment_report(fmt="markdown")
        assert "# HGS Deployment Report" in report
        assert "## Certified Aircraft" in report
        assert "## Readiness Breakdown" in report

    def test_generate_aircraft_support_json(self):
        engine = CertificationEngine()
        reporter = ReportGenerator(engine)
        report = reporter.generate_aircraft_support_report(fmt="json")
        data = json.loads(report)
        assert "supported_aircraft" in data
        assert "summary" in data

    def test_generate_aircraft_support_markdown(self):
        engine = CertificationEngine()
        reporter = ReportGenerator(engine)
        report = reporter.generate_aircraft_support_report(fmt="markdown")
        assert "# HGS Aircraft Support Report" in report
        assert "## " in report  # Should have aircraft sections

    def test_save_report(self):
        engine = CertificationEngine()
        reporter = ReportGenerator(engine)
        with tempfile.TemporaryDirectory() as tmp:
            path = reporter.save_report(
                "test content", "test_report.json", Path(tmp)
            )
            assert path.exists()
            assert path.read_text(encoding="utf-8") == "test content"


class TestCertificationPackage:
    """Test complete certification package generation."""

    def test_generate_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            results = generate_certification_package(Path(tmp))
            assert len(results) >= 4  # 4 reports
            for name, path in results.items():
                assert path.exists(), f"Missing: {name} at {path}"
                content = path.read_text(encoding="utf-8")
                assert len(content) > 0

    def test_reports_have_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            results = generate_certification_package(Path(tmp))
            for name, path in results.items():
                content = path.read_text(encoding="utf-8")
                if name.endswith("json"):
                    data = json.loads(content)
                    assert "installer_version" in data or "certification_matrix" in data
                elif name.endswith("md"):
                    assert "#" in content or "**" in content


class TestCertificationEdgeCases:
    """Test edge cases in certification."""

    def test_release_readiness_score_range(self):
        engine = CertificationEngine()
        for _ in range(10):
            score = engine.compute_readiness_score()
            assert 0 <= score.total_score <= 100
            assert 0 <= score.test_score <= 40
            assert 0 <= score.coverage_score <= 30
            assert 0 <= score.compatibility_score <= 20
            assert 0 <= score.stability_score <= 10

    def test_certification_status_enum(self):
        assert CertificationStatus.CERTIFIED.value == "certified"
        assert CertificationStatus.BETA.value == "beta"
        assert CertificationStatus.DEPRECATED.value == "deprecated"
        assert CertificationStatus.UNSUPPORTED.value == "unsupported"
