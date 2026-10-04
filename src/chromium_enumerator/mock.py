"""A result backend that fabricates a scan, for debugging the output paths.

Nothing here is detection logic. The backend hands back :class:`RuntimeResult`
objects that are indistinguishable downstream from a real scan: platform-shaped
roots, evidence classified by the real profile, entrypoints, metadata, and a
payload size drawn from a fixed baseline. It never touches the filesystem, so
the macOS fixtures work on any host and vice versa.

The point is to exercise the report, the JSON writer and the quip without
owning the Chromium.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from .model import RuntimeResult
from .platforms import PlatformProfile
from .walk import FileInfo

ENV_VAR = "CHROMIUM_COUNT_MOCK_INSTANCES"
"""Set it to a non-negative integer to run the pipeline on a fabricated scan."""

_FAMILIES = ("electron",) * 7 + ("cef", "electron", "qtwebengine")
_SIZES_MB = (312, 187, 445, 96, 231, 158, 524, 203, 141, 377)
_NAMES = (
    "Slack",
    "Discord",
    "VSCode",
    "Spotify",
    "Teams",
    "Notion",
    "Signal",
    "Figma",
    "Obsidian",
    "Postman",
    "Zoom",
    "Tidal",
)


@dataclass(frozen=True, slots=True)
class _Entry:
    """One fabricated path, relative to the runtime root."""

    relative: str
    is_dir: bool = False
    executable: bool = False


# (root suffix, entries). The first entry is the one whose runtime root the
# profile resolves, so it must be a path the profile maps back to the root.
_TREES: dict[str, dict[str, tuple[str, tuple[_Entry, ...]]]] = {
    "macos": {
        "electron": (
            ".app",
            (
                _Entry("Contents/MacOS/{name}", executable=True),
                _Entry("Contents/Frameworks/Electron Framework.framework", is_dir=True),
                _Entry(
                    "Contents/Frameworks/Electron Framework.framework"
                    "/Resources/icudtl.dat"
                ),
                _Entry("Contents/Frameworks/{name} Helper.app", is_dir=True),
            ),
        ),
        "cef": (
            "",
            (
                _Entry("{name}", executable=True),
                _Entry("libcef.dylib"),
                _Entry("Resources/icudtl.dat"),
            ),
        ),
        "qtwebengine": (
            ".app",
            (
                _Entry("Contents/MacOS/{name}", executable=True),
                _Entry("Contents/Frameworks/QtWebEngineCore.framework", is_dir=True),
                _Entry("Contents/Frameworks/QtWebEngineProcess.app", is_dir=True),
                _Entry("Contents/Resources/qtwebengine_resources.pak"),
            ),
        ),
    },
    "windows": {
        "electron": (
            "",
            (
                _Entry("{name}.exe", executable=True),
                _Entry("ffmpeg.dll"),
                _Entry("libEGL.dll"),
                _Entry("libGLESv2.dll"),
                _Entry("icudtl.dat"),
                _Entry("resources.pak"),
            ),
        ),
        "cef": (
            "",
            (
                _Entry("{name}.exe", executable=True),
                _Entry("libcef.dll"),
                _Entry("icudtl.dat"),
            ),
        ),
        "qtwebengine": (
            "",
            (
                _Entry("{name}.exe", executable=True),
                _Entry("Qt6WebEngineCore.dll"),
                _Entry("QtWebEngineProcess.exe"),
                _Entry("qtwebengine_resources.pak"),
            ),
        ),
    },
}

_BASES = {"macos": Path("/mock"), "windows": Path("C:/mock")}


class MockScanner:
    """Drop-in stand-in for :class:`ChromiumScanner` that invents its results."""

    def __init__(self, count: int, *, profile: PlatformProfile) -> None:
        self.count = count
        self.profile = profile
        self.warnings: list[str] = []

    def scan(self, roots=()) -> list[RuntimeResult]:
        """Return ``count`` fabricated results. ``roots`` is accepted and unused."""

        results = [self._result(index) for index in range(self.count)]
        return sorted(results, key=lambda result: str(result.root))

    def _result(self, index: int) -> RuntimeResult:
        name = _name(index)
        family = _FAMILIES[index % len(_FAMILIES)]
        suffix, entries = _tree(self.profile, family)
        root = _BASES[self.profile.name] / f"{name}{suffix}"

        infos = [_info(root, entry, name) for entry in entries]
        evidence = [
            item
            for item in (
                self.profile.classify_path(info.path, info=info) for info in infos
            )
            if item is not None
        ]
        return RuntimeResult(
            root=self.profile.runtime_root_for(infos[0].path, info=infos[0]),
            family=family,
            confidence="high",
            evidence=evidence,
            entrypoints=[
                info.path for info in infos if _is_entrypoint(self.profile, info)
            ],
            metadata=_metadata(self.profile, name),
            size_bytes=_SIZES_MB[index % len(_SIZES_MB)] * 1024 * 1024,
        )


def _name(index: int) -> str:
    base = _NAMES[index % len(_NAMES)]
    cycle = index // len(_NAMES)
    return base if cycle == 0 else f"{base} {cycle + 1}"


def _tree(profile: PlatformProfile, family: str) -> tuple[str, tuple[_Entry, ...]]:
    trees = _TREES.get(profile.name)
    if trees is None:
        raise ValueError(f"no mock fixture for profile {profile.name!r}")
    try:
        return trees[family]
    except KeyError:
        raise ValueError(f"no mock fixture for family {family!r}") from None


def _info(root: Path, entry: _Entry, name: str) -> FileInfo:
    path = root / entry.relative.format(name=name)
    if entry.is_dir:
        return FileInfo(path, True, False, False, 0, 0o755)
    return FileInfo(path, False, True, False, 0, 0o755 if entry.executable else 0o644)


def _is_entrypoint(profile: PlatformProfile, info: FileInfo) -> bool:
    if info.is_dir or info.path.suffix.lower() in profile.library_suffixes:
        return False
    return profile.is_executable(info.path, info=info)


def _metadata(profile: PlatformProfile, name: str) -> dict[str, str]:
    if profile.name == "windows":
        return {"ProductName": name, "FileDescription": name, "FileVersion": "1.0.0"}
    slug = name.lower().replace(" ", "-")
    return {
        "CFBundleName": name,
        "CFBundleDisplayName": name,
        "CFBundleIdentifier": f"com.mock.{slug}",
        "CFBundleShortVersionString": "1.0",
    }


def mock_count_from_environ(environ: dict[str, str] | None = None) -> str | None:
    """The raw ``CHROMIUM_COUNT_MOCK_INSTANCES`` value, or None when unset."""

    source = os.environ if environ is None else environ
    return source.get(ENV_VAR)
