from pathlib import Path

from chromium_enumerator.model import Evidence
from chromium_enumerator.platforms import MacOSProfile, WindowsProfile, infer_family
from chromium_enumerator.walk import FileInfo


def make_info(path: Path, *, is_dir: bool = False, mode: int = 0o644) -> FileInfo:
    return FileInfo(
        path=path,
        is_dir=is_dir,
        is_file=not is_dir,
        is_link=False,
        size=1,
        mode=mode,
    )


def counting_stat(monkeypatch) -> list[Path]:
    calls: list[Path] = []
    real_stat = Path.stat

    def wrapper(self: Path, *args, **kwargs):
        calls.append(self)
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", wrapper)
    return calls


def test_classify_reuses_walker_stat_data(monkeypatch):
    calls = counting_stat(monkeypatch)
    path = Path("/tmp/Foo.app/Contents/Resources/readme.txt")

    assert MacOSProfile().classify_path(path, info=make_info(path)) is None
    assert calls == []


def test_engine_names_do_not_touch_the_filesystem(monkeypatch):
    calls = counting_stat(monkeypatch)

    evidence = MacOSProfile().classify_path(Path("/nope/Electron Framework.framework"))

    assert evidence is not None
    assert evidence.category == "engine"
    assert calls == []


def test_classify_uses_walker_stat_data(monkeypatch):
    calls = counting_stat(monkeypatch)
    path = Path("/tmp/Foo.app/Contents/MacOS/Foo")

    evidence = MacOSProfile().classify_path(path, info=make_info(path, mode=0o755))

    assert evidence is not None
    assert evidence.category == "executable"
    assert calls == []


def test_flat_root_climbs_payload_directories():
    profile = MacOSProfile()

    assert profile.runtime_root_for(Path("/opt/cef/bin/cefhost")) == Path("/opt/cef")
    assert profile.runtime_root_for(Path("/opt/cef/bin/deep/cefhost")) == Path(
        "/opt/cef"
    )
    assert profile.runtime_root_for(Path("/opt/cef/lib/libcef.dylib")) == Path(
        "/opt/cef"
    )
    assert profile.runtime_root_for(Path("/opt/cef/Contents/Resources/x.bin")) == Path(
        "/opt/cef"
    )
    assert profile.runtime_root_for(Path("/opt/cef/loose.bin")) == Path("/opt/cef")


def test_bundle_rule_beats_flat_climb():
    profile = MacOSProfile()

    assert profile.runtime_root_for(
        Path("/Applications/Foo.app/Contents/Resources/x.bin")
    ) == Path("/Applications/Foo.app")


def test_windows_runtime_root_uses_walker_stat_data():
    profile = WindowsProfile()
    directory = Path("/apps/cefapp")

    assert (
        profile.runtime_root_for(directory, info=make_info(directory, is_dir=True))
        == directory
    )
    assert (
        profile.runtime_root_for(
            directory / "cefapp.exe", info=make_info(directory / "cefapp.exe")
        )
        == directory
    )


def test_infer_family_ranks_executable_hints_above_engine_hints():
    evidence = [
        Evidence(
            "engine",
            Path("/app/Electron Framework.framework"),
            "Electron Framework.framework",
            "electron",
        ),
        Evidence("executable", Path("/app/msedge.exe"), "msedge.exe", "edge"),
    ]

    assert infer_family(evidence) == "edge"


def test_infer_family_ranks_engine_hints_above_helper_hints():
    evidence = [
        Evidence("helper", Path("/app/Foo Helper.app"), "Helper.app"),
        Evidence(
            "engine",
            Path("/app/Electron Framework.framework"),
            "Electron Framework.framework",
            "electron",
        ),
    ]

    assert infer_family(evidence) == "electron"


def test_infer_family_needs_two_distinct_markers_for_electron():
    single = [
        Evidence("executable", Path("/app/app.exe"), "app.exe"),
        Evidence("electron-marker", Path("/app/ffmpeg.dll"), "ffmpeg.dll", "electron"),
        Evidence("resource", Path("/app/resources.pak"), "resources.pak"),
    ]
    repeated = [
        Evidence("electron-marker", Path("/app/ffmpeg.dll"), "ffmpeg.dll", "electron"),
        Evidence(
            "electron-marker", Path("/app/sub/ffmpeg.dll"), "ffmpeg.dll", "electron"
        ),
    ]
    full_set = [
        Evidence("electron-marker", Path("/app/ffmpeg.dll"), "ffmpeg.dll", "electron"),
        Evidence("electron-marker", Path("/app/libegl.dll"), "libegl.dll", "electron"),
    ]

    # One marker is collateral that every Chromium build can ship, so it names
    # nothing; the set is Electron's only Windows signature.
    assert infer_family(single) == "chromium"
    assert infer_family(repeated) == "chromium"
    assert infer_family(full_set) == "electron"


def test_infer_family_falls_back_to_chromium():
    evidence = [Evidence("executable", Path("/app/launcher"), "launcher")]

    assert infer_family(evidence) == "chromium"
