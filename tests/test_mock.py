"""The fabricated-scan backend and the flags and variables that switch it on."""

import json
from typing import cast

import pytest

from chromium_enumerator import cli
from chromium_enumerator.cli import main
from chromium_enumerator.mock import ENV_VAR, MockScanner
from chromium_enumerator.platforms import MacOSProfile, PlatformProfile, WindowsProfile
from chromium_enumerator.scanner import _score_confidence
from chromium_enumerator.walk import FileInfo

PROFILES = (MacOSProfile(), WindowsProfile())

# The families the backend cycles through, and the categories each fixture must
# produce under a given profile.
EXPECTED_CATEGORIES = {
    ("macos", "electron"): {"engine", "resource", "helper", "executable"},
    ("macos", "cef"): {"engine", "resource"},
    ("macos", "qtwebengine"): {"engine", "helper", "resource", "executable"},
    ("windows", "electron"): {"electron-marker", "resource", "executable"},
    ("windows", "cef"): {"engine", "resource", "executable"},
    ("windows", "qtwebengine"): {"engine", "helper", "resource", "executable"},
}


def scan(profile, count):
    return MockScanner(count, profile=profile).scan(())


def as_directory(path):
    return FileInfo(path, True, False, False, 0, 0o755)


def test_the_count_is_exact():
    for profile in PROFILES:
        assert len(scan(profile, 7)) == 7
        assert scan(profile, 0) == []


def test_results_are_deterministic():
    for profile in PROFILES:
        assert scan(profile, 6) == scan(profile, 6)


def test_roots_are_plainly_mock_paths():
    for profile in PROFILES:
        for result in scan(profile, 3):
            assert "mock" in result.root.parts


def test_the_profile_resolves_each_root_to_itself():
    for profile in PROFILES:
        for result in scan(profile, 6):
            info = as_directory(result.root)
            assert profile.runtime_root_for(result.root, info=info) == result.root


def test_every_fixture_produces_a_high_confidence_runtime():
    for profile in PROFILES:
        for result in scan(profile, 10):
            assert result.confidence == "high"
            assert _score_confidence(result.evidence, result.entrypoints) == "high"


def test_evidence_matches_the_family_and_profile():
    for profile in PROFILES:
        for result in scan(profile, 10):
            key = (profile.name, result.family)
            categories = {item.category for item in result.evidence}
            assert categories == EXPECTED_CATEGORIES[key], key


def test_entrypoints_follow_the_platform_conventions():
    for profile in PROFILES:
        for result in scan(profile, 10):
            assert result.entrypoints, result.root
            for path in result.entrypoints:
                if profile.name == "windows":
                    assert path.suffix.lower() == ".exe"
                elif result.root.name.endswith(".app"):
                    assert path.parent.name == "MacOS"
                else:
                    assert path.parent == result.root


def test_sizes_come_from_the_baseline_table():
    baseline = {312, 187, 445, 96, 231, 158, 524, 203, 141, 377}
    for profile in PROFILES:
        for result in scan(profile, 30):
            assert result.size_bytes // (1024 * 1024) in baseline


def test_metadata_names_the_product_for_its_platform():
    for profile in PROFILES:
        for result in scan(profile, 4):
            name = profile.display_name_for(result.root, result.metadata, result.family)
            assert name
            assert name in result.root.name
            if profile.name == "windows":
                assert "FileDescription" in result.metadata
            else:
                assert "CFBundleDisplayName" in result.metadata


def test_generated_names_stay_unique_past_the_cycle():
    roots = [result.root for result in scan(MacOSProfile(), 30)]
    assert len(set(roots)) == 30


# --- the switch -----------------------------------------------------------


def test_the_environment_variable_alone_switches_it_on(capsys, monkeypatch):
    monkeypatch.setenv(ENV_VAR, "3")
    assert main(["--json"]) == 0
    assert len(json.loads(capsys.readouterr().out)) == 3


def test_the_flag_outranks_the_environment_variable(capsys, monkeypatch):
    monkeypatch.setenv(ENV_VAR, "3")
    assert main(["--json", "--mock-instances", "5"]) == 0
    assert len(json.loads(capsys.readouterr().out)) == 5


def test_mock_results_reach_the_plain_report(capsys, monkeypatch):
    monkeypatch.setenv(ENV_VAR, "2")
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "Found 2 probable Chromium runtimes" in out
    assert "mock" in out


def test_mock_results_reach_verbose(capsys, monkeypatch):
    monkeypatch.setenv(ENV_VAR, "1")
    assert main(["--platform", "macos", "--verbose"]) == 0
    out = capsys.readouterr().out
    assert "Electron Framework.framework" in out
    assert "CFBundleName" in out


def test_platform_selects_the_fixture_shape(capsys, monkeypatch):
    monkeypatch.setenv(ENV_VAR, "1")
    assert main(["--platform", "windows", "--verbose"]) == 0
    out = capsys.readouterr().out
    assert "libcef.dll" in out or "resources.pak" in out
    assert ".app" not in out


def test_a_non_integer_environment_value_is_rejected(capsys, monkeypatch):
    monkeypatch.setenv(ENV_VAR, "lots")
    with pytest.raises(SystemExit) as error:
        main([])
    assert error.value.code == 2
    assert "must be a non-negative integer" in capsys.readouterr().err


def test_a_negative_count_is_rejected(capsys, monkeypatch):
    with pytest.raises(SystemExit) as error:
        main(["--mock-instances", "-1"])
    assert error.value.code == 2
    assert "zero or more" in capsys.readouterr().err

    monkeypatch.setenv(ENV_VAR, "-1")
    with pytest.raises(SystemExit) as error:
        main([])
    assert error.value.code == 2


def test_the_flag_and_the_environment_both_work_without_quip(monkeypatch, capsys):
    monkeypatch.setenv(ENV_VAR, "0")
    assert main([]) == 0
    assert "No probable Chromium runtimes found." in capsys.readouterr().out


@pytest.mark.parametrize(
    "argv",
    [
        ["--mock-instances", "3", "/tmp"],
        ["--mock-instances", "3", "--exhaustive"],
        ["--mock-instances", "3", "--max-depth", "2"],
        ["--mock-instances", "3", "--follow-symlinks"],
        ["--mock-instances", "3", "--platform", "windows", "--registry-only"],
    ],
)
def test_scan_shaping_flags_conflict_with_mocking(argv, capsys):
    with pytest.raises(SystemExit) as error:
        main(argv)
    assert error.value.code == 2
    assert "fabricates the scan" in capsys.readouterr().err


def test_conflicts_are_reported_even_when_the_count_came_from_the_environment(
    capsys, monkeypatch
):
    monkeypatch.setenv(ENV_VAR, "3")
    with pytest.raises(SystemExit) as error:
        main(["--exhaustive"])
    assert error.value.code == 2
    assert ENV_VAR in capsys.readouterr().err


def test_include_low_confidence_is_harmless_with_mocking(capsys, monkeypatch):
    monkeypatch.setenv(ENV_VAR, "1")
    assert main(["--include-low-confidence"]) == 0
    assert "Found 1 probable Chromium runtime" in capsys.readouterr().out


def test_the_mock_scanner_ignores_roots():
    scanner = MockScanner(2, profile=MacOSProfile())
    assert scanner.scan(["/does/not/exist"]) == scanner.scan(())
    assert scanner.warnings == []


def test_an_unknown_profile_is_reported_clearly():
    class Alien:
        name = "plan9"

    with pytest.raises(ValueError, match="no mock fixture"):
        MockScanner(1, profile=cast(PlatformProfile, Alien())).scan(())


def test_cli_does_not_scan_when_mocking(monkeypatch, capsys):
    class ExplodingScanner:
        def __init__(self, **kwargs):
            raise AssertionError("a mocked run must not construct the real scanner")

    monkeypatch.setattr(cli, "ChromiumScanner", ExplodingScanner)
    monkeypatch.setenv(ENV_VAR, "2")
    assert main(["--json"]) == 0
    assert len(json.loads(capsys.readouterr().out)) == 2
