"""
Tests for the C_HUD_Runway Installer — Aircraft Scanner
========================================================
Phase 2 tests for aircraft package scanning.
"""

import sys
import json
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from installer.aircraft_scanner import (
    AircraftType,
    IntegrationStatus,
    scan_community,
    scan_official,
    _identify_aircraft_type,
    _parse_panel_config,
    _detect_version,
    match_aircraft_type_from_title,
    is_title_supported,
    check_version_compatibility,
    get_aircraft_compatibility_map,
    AircraftPackage,
)


# =========================================================================
#  Helpers
# =========================================================================

def create_mock_aircraft_package(
    temp_dir: Path,
    name: str,
    aircraft_type: AircraftType,
    with_panel: bool = True,
    with_layout: bool = True,
    with_hgs: bool = False,
    version_major: int = 1,
    version_minor: int = 0,
) -> Path:
    """Create a mock aircraft package in temp_dir/Community/{name}."""
    pkg_dir = temp_dir / "Community" / name
    pkg_dir.mkdir(parents=True, exist_ok=True)

    # Create SimObjects structure
    sim_dir = pkg_dir / "SimObjects" / "Airplanes" / name
    sim_dir.mkdir(parents=True, exist_ok=True)
    panel_dir = sim_dir / "panel"
    panel_dir.mkdir(parents=True, exist_ok=True)

    if with_panel:
        panel_cfg = panel_dir / "panel.cfg"
        entries = []
        if with_hgs:
            entries.extend([
                "; --- C_HUD_Runway HGS Integration ---",
                'gauge00 = C_HUD_Runway!Gauge_ConformalHUD,  0, 0, 1024, 1024',
                'htmlgauge00 = HUD/hud_overlay.html,  0, 0, 1024, 1024',
                "; --- End HGS Integration ---",
            ])
        else:
            entries.append('gauge00 = SomeOtherGauge!Gauge, 0, 0, 300, 300')

        panel_cfg.write_text(
            "[VCockpit01]\nsize_mm = 1024, 1024\npixel_size = 1024, 1024\n"
            + "\n".join(entries) + "\n",
            encoding="utf-8",
        )

    if with_layout:
        layout_path = pkg_dir / "layout.json"
        content = [
            {"path": f"SimObjects/Airplanes/{name}/panel/panel.cfg", "size": 100, "date": 2000000000},
        ]
        if with_hgs:
            content.extend([
                {"path": "C_HUD_Runway/panel/C_HUD_Runway.wasm", "size": 50000, "date": 2000000000},
                {"path": "C_HUD_Runway/panel/HUD/hud_overlay.html", "size": 1000, "date": 2000000000},
            ])
        layout_path.write_text(json.dumps({"content": content}), encoding="utf-8")

    # Create manifest
    manifest_path = pkg_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps({"version": f"{version_major}.{version_minor}.0"}),
        encoding="utf-8",
    )

    return pkg_dir


def create_mock_official_package(
    temp_dir: Path,
    publisher: str,
    name: str,
    aircraft_type: AircraftType,
    with_panel: bool = True,
    with_hgs: bool = False,
) -> Path:
    """
    Create a mock aircraft package inside an Official/OneStore/{publisher}/{name} structure.
    Returns the package root path.
    """
    # Official structure: Official/OneStore/{publisher}/{aircraft-folder}/
    official_dir = temp_dir / "Official" / "OneStore" / publisher / name
    official_dir.mkdir(parents=True, exist_ok=True)

    sim_dir = official_dir / "SimObjects" / "Airplanes" / name
    sim_dir.mkdir(parents=True, exist_ok=True)
    panel_dir = sim_dir / "panel"
    panel_dir.mkdir(parents=True, exist_ok=True)

    if with_panel:
        panel_cfg = panel_dir / "panel.cfg"
        entries = []
        if with_hgs:
            entries.extend([
                "; --- C_HUD_Runway HGS Integration ---",
                'gauge00 = C_HUD_Runway!Gauge_ConformalHUD,  0, 0, 1024, 1024',
                'htmlgauge00 = HUD/hud_overlay.html,  0, 0, 1024, 1024',
                "; --- End HGS Integration ---",
            ])
        else:
            entries.append('gauge00 = DefaultGauge!Gauge, 0, 0, 300, 300')

        panel_cfg.write_text(
            "[VCockpit01]\nsize_mm = 1024, 1024\npixel_size = 1024, 1024\n"
            + "\n".join(entries) + "\n",
            encoding="utf-8",
        )

    # Create layout.json
    layout_path = official_dir / "layout.json"
    content = [
        {"path": f"SimObjects/Airplanes/{name}/panel/panel.cfg", "size": 100, "date": 2000000000},
    ]
    layout_path.write_text(json.dumps({"content": content}), encoding="utf-8")

    return official_dir


# =========================================================================
#  Tests
# =========================================================================

class TestAircraftTypeIdentification:
    """Test aircraft type identification from directory names."""

    def test_identify_pmdg_737(self):
        assert _identify_aircraft_type("pmdg-737-800") == AircraftType.PMDG_737_800
        assert _identify_aircraft_type("PMDG 737-700") == AircraftType.PMDG_737_700
        assert _identify_aircraft_type("PMDG737") == AircraftType.PMDG_737_800

    def test_identify_pmdg_777(self):
        assert _identify_aircraft_type("pmdg-777-300er") == AircraftType.PMDG_777_300ER
        assert _identify_aircraft_type("PMDG 777") == AircraftType.PMDG_777_300ER

    def test_identify_asobo_787(self):
        assert _identify_aircraft_type("asobo-787-10") == AircraftType.ASOBO_787_10

    def test_identify_wt_787(self):
        assert _identify_aircraft_type("wt-787-10") == AircraftType.WT_787_10

    def test_identify_inibuilds_a350(self):
        assert _identify_aircraft_type("inibuilds-a350") == AircraftType.INIBUILDS_A350
        assert _identify_aircraft_type("A350-1000") == AircraftType.INIBUILDS_A350

    def test_identify_fbw_a32nx(self):
        assert _identify_aircraft_type("fbw-a32nx") == AircraftType.FBW_A32NX
        assert _identify_aircraft_type("flybywire-a32nx") == AircraftType.FBW_A32NX
        assert _identify_aircraft_type("A32NX") == AircraftType.FBW_A32NX

    def test_identify_headwind_a330(self):
        assert _identify_aircraft_type("headwind-a330-900") == AircraftType.HEADWIND_A330_900

    def test_identify_unknown(self):
        assert _identify_aircraft_type("random-aircraft") is None
        assert _identify_aircraft_type("some-other-plane") is None

    def test_identify_case_insensitive(self):
        assert _identify_aircraft_type("PMDG-737-800") == AircraftType.PMDG_737_800
        assert _identify_aircraft_type("IniBuilds_A350") == AircraftType.INIBUILDS_A350


class TestTitleMatching:
    """Test aircraft type matching from title strings."""

    def test_match_exact(self):
        assert match_aircraft_type_from_title("PMDG 737-800") == AircraftType.PMDG_737_800

    def test_match_with_variant(self):
        assert match_aircraft_type_from_title("PMDG 737-800WL") == AircraftType.PMDG_737_800

    def test_match_case_insensitive(self):
        assert match_aircraft_type_from_title("pmdg 737-800") == AircraftType.PMDG_737_800

    def test_match_unknown(self):
        assert match_aircraft_type_from_title("Some Random Plane") is None

    def test_is_supported(self):
        assert is_title_supported("PMDG 737-800") is True
        assert is_title_supported("Random Plane") is False


class TestPackageScanning:
    """Test scanning of aircraft packages."""

    def test_scan_empty_community(self):
        with tempfile.TemporaryDirectory() as tmp:
            community = Path(tmp) / "Community"
            community.mkdir()
            packages = scan_community(community)
            assert packages == []

    def test_scan_single_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            create_mock_aircraft_package(Path(tmp), "pmdg-737-800", AircraftType.PMDG_737_800)
            community = Path(tmp) / "Community"
            packages = scan_community(community)
            assert len(packages) == 1
            assert packages[0].aircraft_type == AircraftType.PMDG_737_800

    def test_scan_multiple_packages(self):
        with tempfile.TemporaryDirectory() as tmp:
            create_mock_aircraft_package(Path(tmp), "pmdg-737-800", AircraftType.PMDG_737_800)
            create_mock_aircraft_package(Path(tmp), "inibuilds-a350", AircraftType.INIBUILDS_A350)
            create_mock_aircraft_package(Path(tmp), "fbw-a32nx", AircraftType.FBW_A32NX)
            community = Path(tmp) / "Community"
            packages = scan_community(community)
            assert len(packages) == 3

    def test_scan_hgs_integration_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            create_mock_aircraft_package(
                Path(tmp), "pmdg-737-800",
                AircraftType.PMDG_737_800,
                with_hgs=True,
            )
            community = Path(tmp) / "Community"
            packages = scan_community(community)
            assert len(packages) == 1
            assert packages[0].hgs_integrated is True
            assert packages[0].integration_status == IntegrationStatus.INSTALLED

    def test_scan_no_hgs_integration(self):
        with tempfile.TemporaryDirectory() as tmp:
            create_mock_aircraft_package(
                Path(tmp), "pmdg-737-800",
                AircraftType.PMDG_737_800,
                with_hgs=False,
            )
            community = Path(tmp) / "Community"
            packages = scan_community(community)
            assert len(packages) == 1
            assert packages[0].hgs_integrated is False
            assert packages[0].integration_status == IntegrationStatus.NOT_INSTALLED

    def test_scan_detects_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            create_mock_aircraft_package(
                Path(tmp), "pmdg-737-800",
                AircraftType.PMDG_737_800,
                version_major=3,
                version_minor=0,
            )
            community = Path(tmp) / "Community"
            packages = scan_community(community)
            assert packages[0].detected_version_major == 3
            assert packages[0].detected_version_minor == 0

    def test_scan_ignores_non_aircraft_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            community = Path(tmp) / "Community"
            community.mkdir()
            # Non-aircraft dirs
            (community / "random-mod").mkdir()
            (community / "some-liveries").mkdir()
            packages = scan_community(community)
            assert packages == []


class TestPanelConfigParsing:
    """Test panel.cfg parsing."""

    def test_parse_basic_panel(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "panel.cfg"
            cfg_path.write_text(
                "[VCockpit01]\n"
                "size_mm = 1024, 1024\n"
                'gauge00 = SomeGauge!Gauge, 0, 0, 300, 300\n'
                'htmlgauge00 = some/overlay.html, 0, 0, 1024, 1024\n',
                encoding="utf-8",
            )
            pc = _parse_panel_config(cfg_path)
            assert pc is not None
            assert pc.has_hud_gauge is False
            assert pc.has_html_hud is False
            assert len(pc.entries) == 2

    def test_parse_with_hgs(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "panel.cfg"
            cfg_path.write_text(
                "[VCockpit01]\n"
                'gauge00 = C_HUD_Runway!Gauge_ConformalHUD, 0, 0, 1024, 1024\n'
                'htmlgauge00 = HUD/hud_overlay.html, 0, 0, 1024, 1024\n',
                encoding="utf-8",
            )
            pc = _parse_panel_config(cfg_path)
            assert pc is not None
            assert pc.has_hud_gauge is True
            assert pc.has_html_hud is True
            assert pc.wasm_gauge_name == "C_HUD_Runway"

    def test_parse_with_complex_panel(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "panel.cfg"
            cfg_path.write_text(
                "[VCockpit01]\n"
                'size_mm = 1024, 1024\n'
                'pixel_size = 1024, 1024\n'
                'texture = $SomeTexture\n'
                'gauge00 = PMDG_737!Something, 0,0,300,300\n'
                'gauge01 = C_HUD_Runway!Gauge_ConformalHUD, 0,0,1024,1024\n'
                'htmlgauge00 = HUD/hud_overlay.html, 0,0,1024,1024\n'
                ';\n'
                '// Comment\n',
                encoding="utf-8",
            )
            pc = _parse_panel_config(cfg_path)
            assert pc is not None
            assert pc.has_hud_gauge is True
            assert len(pc.entries) == 3  # 2 gauge entries + 1 htmlgauge entry

    def test_parse_missing_file(self):
        pc = _parse_panel_config(Path("/nonexistent/panel.cfg"))
        assert pc is None


class TestCompatibilityMap:
    """Test compatibility mapping."""

    def test_compatibility_map_has_all_types(self):
        compat = get_aircraft_compatibility_map()
        assert "PMDG 737-800" in compat
        assert "PMDG 777-300ER" in compat
        assert "ASOBO 787-10" in compat
        assert "iniBuilds A350" in compat
        assert "FBW A32NX" in compat

    def test_version_compatibility_check(self):
        """Test version compatibility logic."""
        with tempfile.TemporaryDirectory() as tmp:
            pkg = AircraftPackage(
                package_path=Path(tmp),
                aircraft_type=AircraftType.PMDG_737_800,
                title_prefix="PMDG 737-800",
                detected_version_major=3,
                detected_version_minor=0,
            )
            assert check_version_compatibility(pkg) is True

    def test_version_compatibility_old(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = AircraftPackage(
                package_path=Path(tmp),
                aircraft_type=AircraftType.PMDG_737_800,
                title_prefix="PMDG 737-800",
                detected_version_major=0,
                detected_version_minor=9,
            )
            assert check_version_compatibility(pkg) is False


class TestOfficialScanning:
    """Test scanning of Official (OneStore) aircraft packages."""

    def test_scan_official_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            official = Path(tmp) / "Official" / "OneStore"
            official.mkdir(parents=True)
            packages = scan_official(official)
            assert packages == []

    def test_scan_official_nonexistent(self):
        packages = scan_official(Path("/nonexistent/official"))
        assert packages == []

    def test_scan_official_single_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            create_mock_official_package(
                Path(tmp), "asobo", "asobo-787-10",
                AircraftType.ASOBO_787_10,
            )
            official = Path(tmp) / "Official" / "OneStore"
            packages = scan_official(official)
            assert len(packages) == 1
            assert packages[0].aircraft_type == AircraftType.ASOBO_787_10
            assert packages[0].is_official is True

    def test_scan_official_multiple_publishers(self):
        with tempfile.TemporaryDirectory() as tmp:
            create_mock_official_package(
                Path(tmp), "asobo", "asobo-787-10",
                AircraftType.ASOBO_787_10,
            )
            create_mock_official_package(
                Path(tmp), "asobo", "asobo-747-8i",
                AircraftType.ASOBO_787_10,  # not real but tests the scanner
            )
            official = Path(tmp) / "Official" / "OneStore"
            packages = scan_official(official)
            # Only asobo-787-10 matches the known patterns
            assert len(packages) == 1
            assert packages[0].aircraft_type == AircraftType.ASOBO_787_10
            assert packages[0].is_official is True

    def test_scan_official_ignores_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Unknown aircraft in Official should be ignored
            official = Path(tmp) / "Official" / "OneStore"
            official.mkdir(parents=True)
            (official / "unknown-publisher" / "some-unknown-plane").mkdir(parents=True)
            packages = scan_official(official)
            assert packages == []

    def test_scan_official_sets_is_official_flag(self):
        """Verify that packages discovered via scan_official() have is_official=True."""
        with tempfile.TemporaryDirectory() as tmp:
            create_mock_official_package(
                Path(tmp), "asobo", "asobo-787-10",
                AircraftType.ASOBO_787_10,
            )
            official = Path(tmp) / "Official" / "OneStore"
            packages = scan_official(official)
            assert len(packages) >= 1
            for pkg in packages:
                assert pkg.is_official is True

    def test_scan_community_sets_is_official_false(self):
        """Verify that packages discovered via scan_community() have is_official=False."""
        with tempfile.TemporaryDirectory() as tmp:
            create_mock_aircraft_package(
                Path(tmp), "pmdg-737-800",
                AircraftType.PMDG_737_800,
            )
            community = Path(tmp) / "Community"
            packages = scan_community(community)
            assert len(packages) >= 1
            for pkg in packages:
                assert pkg.is_official is False


class TestAircraftPackageFields:
    """Test the AircraftPackage dataclass fields."""

    def test_default_is_official_false(self):
        pkg = AircraftPackage(
            package_path=Path("/tmp/test"),
            aircraft_type=AircraftType.PMDG_737_800,
            title_prefix="PMDG 737-800",
        )
        assert pkg.is_official is False
        assert pkg.is_official_backed_up is False

    def test_is_official_set_explicitly(self):
        pkg = AircraftPackage(
            package_path=Path("/tmp/test"),
            aircraft_type=AircraftType.ASOBO_787_10,
            title_prefix="ASOBO 787-10",
            is_official=True,
        )
        assert pkg.is_official is True
        assert pkg.is_official_backed_up is False

    def test_steam_official_folder_structure(self):
        """Official folder may also exist under Official/Steam/..."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            # Create mock package directly under Official/Steam
            publisher_dir = tmp_path / "Official" / "Steam" / "asobo"
            pkg_dir = publisher_dir / "asobo-787-10"
            pkg_dir.mkdir(parents=True)
            # Minimal package structure
            sim_dir = pkg_dir / "SimObjects" / "Airplanes" / "asobo-787-10"
            sim_dir.mkdir(parents=True)
            panel_dir = sim_dir / "panel"
            panel_dir.mkdir(parents=True)
            panel_cfg = panel_dir / "panel.cfg"
            panel_cfg.write_text('[VCockpit01]\nsize_mm = 1024, 1024\ngauge00 = DefaultGauge!Gauge, 0,0,300,300\n', encoding='utf-8')
            layout_path = pkg_dir / "layout.json"
            layout_path.write_text(json.dumps({"content": [{"path": "SimObjects/Airplanes/asobo-787-10/panel/panel.cfg", "size": 100, "date": 2000000000}]}), encoding="utf-8")

            steam_dir = tmp_path / "Official" / "Steam"
            packages = scan_official(steam_dir)
            assert len(packages) >= 1
            for pkg in packages:
                assert pkg.is_official is True
