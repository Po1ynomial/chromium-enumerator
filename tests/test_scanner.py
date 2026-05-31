import plistlib
from pathlib import Path

from chrome_enumerator.scanner import ChromiumScanner


def make_file(path: Path, content: bytes = b"x", *, executable: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    if executable:
        path.chmod(path.stat().st_mode | 0o111)
    return path


def make_app_bundle(root: Path, name: str) -> Path:
    app = root / f"{name}.app"
    make_file(app / "Contents" / "MacOS" / name, executable=True)
    plist = {
        "CFBundleName": name,
        "CFBundleIdentifier": f"com.example.{name.lower()}",
        "CFBundleShortVersionString": "1.2.3",
    }
    info = app / "Contents" / "Info.plist"
    info.parent.mkdir(parents=True, exist_ok=True)
    info.write_bytes(plistlib.dumps(plist))
    return app


def test_detects_electron_app_as_high_confidence_runtime(tmp_path):
    app = make_app_bundle(tmp_path, "Slackish")
    make_file(app / "Contents" / "Frameworks" / "Electron Framework.framework" / "Resources" / "icudtl.dat")
    make_file(app / "Contents" / "Frameworks" / "Slackish Helper.app" / "Contents" / "MacOS" / "Slackish Helper", executable=True)
    make_file(app / "Contents" / "Frameworks" / "chrome_crashpad_handler", executable=True)

    results = ChromiumScanner().scan([tmp_path])

    assert len(results) == 1
    result = results[0]
    assert result.root == app
    assert result.family == "electron"
    assert result.confidence == "high"
    assert app / "Contents" / "MacOS" / "Slackish" in result.entrypoints
    assert result.metadata["CFBundleName"] == "Slackish"
    assert {e.category for e in result.evidence} >= {"engine", "resource", "helper", "executable"}
    assert result.size_bytes > 0


def test_detects_cef_app_as_high_confidence_runtime(tmp_path):
    app = make_app_bundle(tmp_path, "CEFHost")
    make_file(app / "Contents" / "Frameworks" / "Chromium Embedded Framework.framework" / "Resources" / "icudtl.dat")
    make_file(app / "Contents" / "Frameworks" / "Chromium Embedded Framework.framework" / "Resources" / "locales" / "en-US.pak")

    [result] = ChromiumScanner().scan([tmp_path])

    assert result.root == app
    assert result.family == "cef"
    assert result.confidence == "high"


def test_detects_qtwebengine_app_as_high_confidence_runtime(tmp_path):
    app = make_app_bundle(tmp_path, "QtHost")
    make_file(app / "Contents" / "Frameworks" / "QtWebEngineCore.framework" / "QtWebEngineCore", executable=True)
    make_file(app / "Contents" / "Helpers" / "QtWebEngineProcess.app" / "Contents" / "MacOS" / "QtWebEngineProcess", executable=True)
    make_file(app / "Contents" / "Resources" / "qtwebengine_resources.pak")

    [result] = ChromiumScanner().scan([tmp_path])

    assert result.root == app
    assert result.family == "qtwebengine"
    assert result.confidence == "high"


def test_groups_nested_helper_app_under_outer_app(tmp_path):
    app = make_app_bundle(tmp_path, "Outer")
    helper_app = app / "Contents" / "Frameworks" / "Outer Helper.app"
    make_file(app / "Contents" / "Frameworks" / "Electron Framework.framework" / "Resources" / "resources.pak")
    make_file(helper_app / "Contents" / "MacOS" / "Outer Helper", executable=True)

    [result] = ChromiumScanner().scan([tmp_path])

    assert result.root == app
    assert result.root != helper_app


def test_excludes_isolated_resource_files_by_default(tmp_path):
    make_file(tmp_path / "random" / "icudtl.dat")

    assert ChromiumScanner().scan([tmp_path]) == []


def test_can_limit_scan_depth(tmp_path):
    app = make_app_bundle(tmp_path / "too" / "deep", "Deep")
    make_file(app / "Contents" / "Frameworks" / "Electron Framework.framework" / "Resources" / "icudtl.dat")

    assert ChromiumScanner(max_depth=1).scan([tmp_path]) == []
