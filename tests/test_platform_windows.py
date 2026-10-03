import json
from pathlib import Path

from chromium_enumerator.cli import main
from chromium_enumerator.model import Evidence
from chromium_enumerator.platforms import WindowsProfile
from chromium_enumerator.scanner import (
    ChromiumScanner,
    _find_seed_command,
    _score_confidence,
)

LARGE_RUNTIME_BYTES = 6 * 1024 * 1024


def make_file(path: Path, content: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def make_large_payload(root: Path) -> Path:
    payload = root / "large-runtime-payload.bin"
    payload.parent.mkdir(parents=True, exist_ok=True)
    with payload.open("wb") as payload_file:
        payload_file.truncate(LARGE_RUNTIME_BYTES)
    return payload


def windows_scanner(**kwargs) -> ChromiumScanner:
    return ChromiumScanner(profile=WindowsProfile(), **kwargs)


def test_detects_flat_cef_layout(tmp_path):
    runtime = tmp_path / "cefapp"
    make_file(runtime / "cefapp.exe")
    make_file(runtime / "libcef.dll")
    make_file(runtime / "icudtl.dat")
    make_file(runtime / "locales" / "en-US.pak")
    make_large_payload(runtime)

    [result] = windows_scanner().scan([tmp_path])

    assert result.root == runtime
    assert result.family == "cef"
    assert result.confidence == "high"
    assert runtime / "cefapp.exe" in result.entrypoints


def test_detects_flat_electron_layout_as_electron_family(tmp_path):
    runtime = tmp_path / "CoolApp"
    make_file(runtime / "CoolApp.exe")
    make_file(runtime / "ffmpeg.dll")
    make_file(runtime / "libGLESv2.dll")
    make_file(runtime / "libEGL.dll")
    make_file(runtime / "resources.pak")
    make_file(runtime / "v8_context_snapshot.bin")
    make_file(runtime / "resources" / "app.asar")
    make_large_payload(runtime)

    [result] = windows_scanner().scan([tmp_path])

    assert result.root == runtime
    assert result.family == "electron"
    assert result.confidence == "high"
    assert {item.category for item in result.evidence} >= {
        "electron-marker",
        "resource",
        "executable",
    }


def test_single_electron_marker_needs_a_second_engine_signal(tmp_path):
    runtime = tmp_path / "LooseApp"
    make_file(runtime / "LooseApp.exe")
    make_file(runtime / "ffmpeg.dll")
    make_file(runtime / "icudtl.dat")
    make_large_payload(runtime)

    [result] = windows_scanner().scan([tmp_path])

    assert result.confidence == "medium"
    assert result.family == "electron"


def test_detects_browser_version_dir_layout(tmp_path):
    app = tmp_path / "Google" / "Chrome" / "Application"
    make_file(app / "chrome.exe")
    make_file(app / "138.0.7204.101" / "chrome.dll")
    make_file(app / "138.0.7204.101" / "locales" / "en-US.pak")
    make_large_payload(app)

    [result] = windows_scanner().scan([tmp_path])

    assert result.root == app
    assert result.family == "chrome"
    assert result.confidence == "high"
    assert app / "chrome.exe" in result.entrypoints


def test_detects_qtwebengine_layout(tmp_path):
    runtime = tmp_path / "QtHost"
    make_file(runtime / "QtHost.exe")
    make_file(runtime / "Qt6WebEngineCore.dll")
    make_file(runtime / "QtWebEngineProcess.exe")
    make_file(runtime / "resources" / "qtwebengine_resources.pak")
    make_large_payload(runtime)

    [result] = windows_scanner().scan([tmp_path])

    assert result.root == runtime
    assert result.family == "qtwebengine"
    assert result.confidence == "high"


def test_matching_is_case_insensitive(tmp_path):
    runtime = tmp_path / "MixedCase"
    make_file(runtime / "MIXEDCASE.EXE")
    make_file(runtime / "LIBCEF.DLL")
    make_file(runtime / "ICUDTL.DAT")
    make_file(runtime / "LOCALES" / "EN-US.PAK")
    make_large_payload(runtime)

    [result] = windows_scanner().scan([tmp_path])

    assert result.root == runtime
    assert result.family == "cef"
    assert result.confidence == "high"


def test_excludes_isolated_resource_files_by_default(tmp_path):
    make_file(tmp_path / "random" / "icudtl.dat")

    assert windows_scanner().scan([tmp_path]) == []


def test_find_seed_command_is_never_built_on_windows():
    command = _find_seed_command(
        Path("/irrelevant"),
        profile=WindowsProfile(),
        max_depth=None,
        follow_symlinks=False,
    )

    assert command is None


def test_exhaustive_scan_skips_seed_commands(tmp_path, monkeypatch):
    import shutil

    import chromium_enumerator.scanner as scanner_module

    runtime = tmp_path / "cefapp"
    make_file(runtime / "cefapp.exe")
    make_file(runtime / "libcef.dll")
    make_file(runtime / "icudtl.dat")
    make_large_payload(runtime)

    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/fd")
    monkeypatch.setattr(
        scanner_module,
        "_iter_command_paths",
        lambda command, on_error: (_ for _ in ()).throw(
            AssertionError("exhaustive scan should not use native seed commands")
        ),
    )

    [result] = windows_scanner(exhaustive=True).scan([tmp_path])
    assert result.root == runtime


def test_entrypoints_exclude_payload_dlls(tmp_path):
    runtime = tmp_path / "cefapp"
    make_file(runtime / "cefapp.exe")
    make_file(runtime / "libcef.dll")
    make_file(runtime / "icudtl.dat")
    make_large_payload(runtime)

    [result] = windows_scanner().scan([tmp_path])

    assert result.entrypoints == [runtime / "cefapp.exe"]


def test_nested_version_dir_resources_stay_under_application(tmp_path):
    app = tmp_path / "Microsoft" / "Edge" / "Application"
    make_file(app / "msedge.exe")
    make_file(app / "137.0.0.0" / "chrome.dll")
    make_file(app / "137.0.0.0" / "locales" / "en-US.pak")
    make_file(app / "137.0.0.0" / "resources.pak")
    make_large_payload(app)

    results = windows_scanner(include_low_confidence=True).scan([tmp_path])

    assert [result.root for result in results] == [app]
    [result] = results
    assert result.family == "edge"
    assert result.confidence == "high"


def test_cli_platform_windows_scans_windows_layout(tmp_path, capsys):
    runtime = tmp_path / "cefapp"
    make_file(runtime / "cefapp.exe")
    make_file(runtime / "libcef.dll")
    make_file(runtime / "icudtl.dat")
    make_large_payload(runtime)

    exit_code = main(["--platform", "windows", "--json", str(tmp_path)])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output[0]["root"] == str(runtime)
    assert output[0]["family"] == "cef"
    assert output[0]["confidence"] == "high"


def test_subdirectories_without_engine_evidence_fold_into_the_install(tmp_path):
    runtime = tmp_path / "BigApp"
    make_file(runtime / "BigApp.exe")
    make_file(runtime / "libcef.dll")
    make_file(runtime / "icudtl.dat")
    make_file(runtime / "swiftshader" / "libEGL.dll")
    make_file(runtime / "swiftshader" / "libGLESv2.dll")
    make_file(runtime / "Installer" / "setup.exe")
    make_file(runtime / "legacyPM" / "Extra.exe")
    make_large_payload(runtime)

    results = windows_scanner(include_low_confidence=True).scan([tmp_path])

    [result] = results
    assert result.root == runtime
    assert result.confidence == "high"
    assert {
        runtime / "Installer" / "setup.exe",
        runtime / "legacyPM" / "Extra.exe",
    } <= set(result.entrypoints)
    assert {
        runtime / "swiftshader" / "libEGL.dll",
        runtime / "swiftshader" / "libGLESv2.dll",
        runtime / "Installer" / "setup.exe",
    } <= {item.path for item in result.evidence}
    assert result.size_bytes == sum(
        path.stat().st_size for path in runtime.rglob("*") if path.is_file()
    )


def test_split_payload_and_launcher_rejoin_the_runtime(tmp_path):
    runtime = tmp_path / "Split"
    make_file(runtime / "bin" / "app.exe")
    make_file(runtime / "lib" / "libcef.dll")
    make_file(runtime / "Resources" / "icudtl.dat")
    make_large_payload(runtime)

    [result] = windows_scanner(include_low_confidence=True).scan([tmp_path])

    assert result.root == runtime
    assert result.confidence == "high"
    assert runtime / "bin" / "app.exe" in result.entrypoints
    assert {item.category for item in result.evidence} >= {
        "engine",
        "resource",
        "executable",
    }


def test_nested_runtime_keeps_its_bytes_out_of_the_parent(tmp_path):
    outer = tmp_path / "Outer"
    make_file(outer / "Outer.exe")
    make_file(outer / "libcef.dll")
    make_file(outer / "icudtl.dat")
    make_large_payload(outer)
    inner = outer / "bundled" / "cef.win64"
    make_file(inner / "inner.exe")
    make_file(inner / "libcef.dll")
    make_file(inner / "icudtl.dat")
    make_large_payload(inner)

    results = windows_scanner().scan([tmp_path])

    roots = {result.root: result for result in results}
    assert set(roots) == {outer, inner}
    inner_bytes = sum(
        path.stat().st_size for path in inner.rglob("*") if path.is_file()
    )
    outer_bytes = sum(
        path.stat().st_size for path in outer.rglob("*") if path.is_file()
    )
    assert roots[inner].size_bytes == inner_bytes
    assert roots[outer].size_bytes == outer_bytes - inner_bytes
    assert inner / "libcef.dll" not in {item.path for item in roots[outer].evidence}


def test_metadata_reads_stub_environment(monkeypatch, tmp_path):
    runtime = tmp_path / "cefapp"
    make_file(runtime / "cefapp.exe")
    make_file(runtime / "libcef.dll")
    make_file(runtime / "icudtl.dat")
    make_large_payload(runtime)
    monkeypatch.setenv("CHROMIUM_COUNT_STUB_FILEDESCRIPTION", "CEF Test Host")
    monkeypatch.setenv("CHROMIUM_COUNT_STUB_PRODUCTNAME", "cefapp")

    [result] = windows_scanner().scan([tmp_path])

    assert result.metadata["FileDescription"] == "CEF Test Host"
    assert result.metadata["ProductName"] == "cefapp"


def test_metadata_is_empty_without_pefile_or_stub(tmp_path):
    runtime = tmp_path / "cefapp"
    make_file(runtime / "cefapp.exe")

    assert WindowsProfile().read_metadata(runtime) == {}


def test_scoring_treats_electron_markers_as_engine_signals():
    evidence = [
        Evidence("executable", Path("/app/app.exe"), "app.exe"),
        Evidence("electron-marker", Path("/app/ffmpeg.dll"), "ffmpeg.dll", "electron"),
        Evidence("electron-marker", Path("/app/libegl.dll"), "libegl.dll", "electron"),
        Evidence("resource", Path("/app/resources.pak"), "resources.pak"),
    ]

    assert _score_confidence(evidence, [Path("/app/app.exe")]) == "high"


def test_scoring_needs_two_distinct_electron_markers():
    evidence = [
        Evidence("executable", Path("/app/app.exe"), "app.exe"),
        Evidence("electron-marker", Path("/app/ffmpeg.dll"), "ffmpeg.dll", "electron"),
        Evidence("resource", Path("/app/resources.pak"), "resources.pak"),
    ]

    assert _score_confidence(evidence, [Path("/app/app.exe")]) == "medium"


def test_scoring_dedupes_repeated_marker_names():
    evidence = [
        Evidence("executable", Path("/app/app.exe"), "app.exe"),
        Evidence("electron-marker", Path("/app/ffmpeg.dll"), "ffmpeg.dll", "electron"),
        Evidence(
            "electron-marker", Path("/app/sub/ffmpeg.dll"), "ffmpeg.dll", "electron"
        ),
        Evidence("resource", Path("/app/resources.pak"), "resources.pak"),
    ]

    assert _score_confidence(evidence, [Path("/app/app.exe")]) == "medium"
