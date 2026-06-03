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
    make_file(
        app
        / "Contents"
        / "Frameworks"
        / "Electron Framework.framework"
        / "Resources"
        / "icudtl.dat"
    )
    make_file(
        app
        / "Contents"
        / "Frameworks"
        / "Slackish Helper.app"
        / "Contents"
        / "MacOS"
        / "Slackish Helper",
        executable=True,
    )
    make_file(
        app / "Contents" / "Frameworks" / "chrome_crashpad_handler", executable=True
    )

    results = ChromiumScanner().scan([tmp_path])

    assert len(results) == 1
    result = results[0]
    assert result.root == app
    assert result.family == "electron"
    assert result.confidence == "high"
    assert app / "Contents" / "MacOS" / "Slackish" in result.entrypoints
    assert result.metadata["CFBundleName"] == "Slackish"
    assert {e.category for e in result.evidence} >= {
        "engine",
        "resource",
        "helper",
        "executable",
    }
    assert result.size_bytes > 0


def test_detects_cef_app_as_high_confidence_runtime(tmp_path):
    app = make_app_bundle(tmp_path, "CEFHost")
    make_file(
        app
        / "Contents"
        / "Frameworks"
        / "Chromium Embedded Framework.framework"
        / "Resources"
        / "icudtl.dat"
    )
    make_file(
        app
        / "Contents"
        / "Frameworks"
        / "Chromium Embedded Framework.framework"
        / "Resources"
        / "locales"
        / "en-US.pak"
    )

    [result] = ChromiumScanner().scan([tmp_path])

    assert result.root == app
    assert result.family == "cef"
    assert result.confidence == "high"


def test_detects_qtwebengine_app_as_high_confidence_runtime(tmp_path):
    app = make_app_bundle(tmp_path, "QtHost")
    make_file(
        app
        / "Contents"
        / "Frameworks"
        / "QtWebEngineCore.framework"
        / "QtWebEngineCore",
        executable=True,
    )
    make_file(
        app
        / "Contents"
        / "Helpers"
        / "QtWebEngineProcess.app"
        / "Contents"
        / "MacOS"
        / "QtWebEngineProcess",
        executable=True,
    )
    make_file(app / "Contents" / "Resources" / "qtwebengine_resources.pak")

    [result] = ChromiumScanner().scan([tmp_path])

    assert result.root == app
    assert result.family == "qtwebengine"
    assert result.confidence == "high"


def test_browser_framework_family_outranks_helper_app_hint(tmp_path):
    app = make_app_bundle(tmp_path, "Google Chrome")
    make_file(
        app
        / "Contents"
        / "Frameworks"
        / "Google Chrome Framework.framework"
        / "Google Chrome Framework",
        executable=True,
    )
    make_file(
        app
        / "Contents"
        / "Frameworks"
        / "Google Chrome Framework.framework"
        / "Resources"
        / "icudtl.dat"
    )
    make_file(
        app
        / "Contents"
        / "Frameworks"
        / "Google Chrome Helper.app"
        / "Contents"
        / "MacOS"
        / "Google Chrome Helper",
        executable=True,
    )
    make_file(
        app
        / "Contents"
        / "Frameworks"
        / "Google Chrome Helper (Renderer).app"
        / "Contents"
        / "MacOS"
        / "Google Chrome Helper (Renderer)",
        executable=True,
    )

    [result] = ChromiumScanner().scan([tmp_path])

    assert result.family == "chrome"


def test_groups_nested_helper_app_under_outer_app(tmp_path):
    app = make_app_bundle(tmp_path, "Outer")
    helper_app = app / "Contents" / "Frameworks" / "Outer Helper.app"
    make_file(
        app
        / "Contents"
        / "Frameworks"
        / "Electron Framework.framework"
        / "Resources"
        / "resources.pak"
    )
    make_file(helper_app / "Contents" / "MacOS" / "Outer Helper", executable=True)

    [result] = ChromiumScanner().scan([tmp_path])

    assert result.root == app
    assert result.root != helper_app


def test_excludes_isolated_resource_files_by_default(tmp_path):
    make_file(tmp_path / "random" / "icudtl.dat")

    assert ChromiumScanner().scan([tmp_path]) == []


def test_ignores_broken_symlink_file_evidence(tmp_path):
    app = make_app_bundle(tmp_path, "BrokenLinkHost")
    make_file(
        app
        / "Contents"
        / "Frameworks"
        / "Electron Framework.framework"
        / "Electron Framework",
        executable=True,
    )
    (app / "Contents" / "Frameworks" / "chrome_crashpad_handler").symlink_to(
        tmp_path / "missing-handler"
    )

    assert ChromiumScanner().scan([tmp_path]) == []


def test_detects_standalone_framework_runtime(tmp_path):
    framework = tmp_path / "Chromium Embedded Framework.framework"
    make_file(framework / "Chromium Embedded Framework", executable=True)
    make_file(framework / "Resources" / "icudtl.dat")

    [result] = ChromiumScanner().scan([tmp_path])

    assert result.root == framework
    assert result.family == "cef"
    assert result.confidence == "high"
    assert framework / "Chromium Embedded Framework" in result.entrypoints


def test_detects_standalone_framework_when_root_is_framework(tmp_path):
    framework = tmp_path / "Chromium Embedded Framework.framework"
    make_file(framework / "Chromium Embedded Framework", executable=True)
    make_file(framework / "Resources" / "icudtl.dat")

    [result] = ChromiumScanner().scan([framework])

    assert result.root == framework
    assert result.family == "cef"
    assert result.confidence == "high"


def test_follow_symlinks_applies_to_evidence_entrypoints_and_size(tmp_path):
    real = tmp_path / "real-cef"
    make_file(real / "bin" / "cefhost", executable=True)
    make_file(real / "lib" / "libcef.dylib")
    make_file(real / "Resources" / "icudtl.dat")

    runtime = tmp_path / "linked-cef"
    runtime.mkdir()
    (runtime / "bin").symlink_to(real / "bin", target_is_directory=True)
    (runtime / "lib").symlink_to(real / "lib", target_is_directory=True)
    (runtime / "Resources").symlink_to(real / "Resources", target_is_directory=True)

    assert ChromiumScanner().scan([runtime]) == []

    [result] = ChromiumScanner(follow_symlinks=True).scan([runtime])

    assert result.root == runtime
    assert result.confidence == "high"
    assert runtime / "bin" / "cefhost" in result.entrypoints
    assert result.size_bytes > 0


def test_follow_symlinks_skips_directory_cycles(tmp_path):
    runtime = tmp_path / "cef-runtime"
    make_file(runtime / "bin" / "cefhost", executable=True)
    make_file(runtime / "lib" / "libcef.dylib")
    make_file(runtime / "Resources" / "icudtl.dat")
    (runtime / "loop").symlink_to(runtime, target_is_directory=True)

    [result] = ChromiumScanner(follow_symlinks=True).scan([runtime])

    assert result.root == runtime
    assert result.confidence == "high"
    assert result.entrypoints == [runtime / "bin" / "cefhost"]
    assert result.size_bytes == 3
    assert all("loop" not in path.parts for path in result.entrypoints)
    assert all("loop" not in evidence.path.parts for evidence in result.evidence)


def test_symlink_root_requires_follow_symlinks_and_preserves_root_path(tmp_path):
    real = tmp_path / "real-cef"
    make_file(real / "bin" / "cefhost", executable=True)
    make_file(real / "lib" / "libcef.dylib")
    make_file(real / "Resources" / "icudtl.dat")
    link = tmp_path / "linked-cef"
    link.symlink_to(real, target_is_directory=True)

    assert ChromiumScanner().scan([link]) == []

    [result] = ChromiumScanner(follow_symlinks=True).scan([link])

    assert result.root == link
    assert result.confidence == "high"
    assert link / "bin" / "cefhost" in result.entrypoints


def test_broken_symlink_root_is_ignored_without_warning(tmp_path):
    broken = tmp_path / "broken-root"
    broken.symlink_to(tmp_path / "missing-target", target_is_directory=True)
    scanner = ChromiumScanner()

    assert scanner.scan([broken]) == []
    assert scanner.warnings == []


def test_build_result_walks_root_at_most_once(tmp_path, monkeypatch):
    import os as os_module

    app = make_app_bundle(tmp_path, "WalkApp")
    make_file(app / "Contents" / "Frameworks" / "Electron Framework.framework" / "Resources" / "icudtl.dat")
    make_file(app / "Contents" / "Frameworks" / "WalkApp Helper.app" / "Contents" / "MacOS" / "WalkApp Helper", executable=True)

    calls = []
    original_walk = os_module.walk

    def counting_walk(*args, **kwargs):
        calls.append(1)
        yield from original_walk(*args, **kwargs)

    monkeypatch.setattr(os_module, "walk", counting_walk)
    [result] = ChromiumScanner().scan([tmp_path])

    assert result.entrypoints
    assert result.size_bytes > 0
    assert len(calls) <= 2


def test_warnings_are_cleared_between_scans(tmp_path):
    scanner = ChromiumScanner()

    scanner.scan([tmp_path / "missing"])
    assert scanner.warnings

    scanner.scan([tmp_path])
    assert scanner.warnings == []


def test_groups_flat_cef_runtime_directory(tmp_path):
    runtime = tmp_path / "cef-runtime"
    make_file(runtime / "cefhost", executable=True)
    make_file(runtime / "lib" / "libcef.dylib")
    make_file(runtime / "Resources" / "icudtl.dat")

    [result] = ChromiumScanner().scan([tmp_path])

    assert result.root == runtime
    assert result.family == "cef"
    assert result.confidence == "high"
    assert runtime / "cefhost" in result.entrypoints


def test_groups_flat_cef_runtime_with_bin_launcher(tmp_path):
    runtime = tmp_path / "cef-runtime"
    make_file(runtime / "bin" / "cefhost", executable=True)
    make_file(runtime / "lib" / "libcef.dylib")
    make_file(runtime / "Resources" / "icudtl.dat")

    [result] = ChromiumScanner().scan([tmp_path])

    assert result.root == runtime
    assert result.confidence == "high"
    assert runtime / "bin" / "cefhost" in result.entrypoints


def test_max_depth_limits_entrypoint_discovery(tmp_path):
    runtime = tmp_path / "cef-runtime"
    make_file(runtime / "bin" / "deep" / "cefhost", executable=True)
    make_file(runtime / "lib" / "libcef.dylib")
    make_file(runtime / "Resources" / "icudtl.dat")

    assert ChromiumScanner(max_depth=2).scan([tmp_path]) == []


def test_helper_app_hint_is_neutral_without_engine_evidence(tmp_path):
    app = make_app_bundle(tmp_path, "HelperOnly")
    make_file(
        app
        / "Contents"
        / "Frameworks"
        / "HelperOnly Helper.app"
        / "Contents"
        / "MacOS"
        / "HelperOnly Helper",
        executable=True,
    )

    [result] = ChromiumScanner(include_low_confidence=True).scan([tmp_path])

    assert result.confidence == "low"
    assert result.family == "chromium"


def test_can_limit_scan_depth(tmp_path):
    app = make_app_bundle(tmp_path / "too" / "deep", "Deep")
    make_file(
        app
        / "Contents"
        / "Frameworks"
        / "Electron Framework.framework"
        / "Resources"
        / "icudtl.dat"
    )

    assert ChromiumScanner(max_depth=1).scan([tmp_path]) == []
