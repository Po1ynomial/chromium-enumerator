from pathlib import Path

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


def test_exhaustive_scan_uses_os_walk_on_windows(tmp_path, monkeypatch):
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
