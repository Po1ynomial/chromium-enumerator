from __future__ import annotations

import os
import plistlib
from collections import Counter
from pathlib import Path
from stat import S_IXGRP, S_IXOTH, S_IXUSR
from typing import Protocol

from .model import Evidence
from .pe_metadata import read_windows_metadata
from .registry import installed_software
from .walk import FileInfo

MACOS_ENGINE_NAMES: dict[str, str] = {
    "Electron Framework.framework": "electron",
    "Chromium Embedded Framework.framework": "cef",
    "Google Chrome Framework.framework": "chrome",
    "Chromium Framework.framework": "chromium",
    "Microsoft Edge Framework.framework": "edge",
    "Brave Browser Framework.framework": "brave",
    "Opera Framework.framework": "opera",
    "Vivaldi Framework.framework": "vivaldi",
    "QtWebEngineCore.framework": "qtwebengine",
    "nwjs Framework.framework": "nwjs",
    "libcef.dylib": "cef",
}

RESOURCE_NAMES = frozenset(
    {
        "icudtl.dat",
        "resources.pak",
        "chrome_100_percent.pak",
        "chrome_200_percent.pak",
        "v8_context_snapshot.bin",
        "snapshot_blob.bin",
        "natives_blob.bin",
        "devtools_resources.pak",
        "qtwebengine_resources.pak",
        "qtwebengine_resources_100p.pak",
        "qtwebengine_resources_200p.pak",
    }
)

RESOURCE_NAMES_LOWER = frozenset(name.lower() for name in RESOURCE_NAMES)

MACOS_HELPER_NAMES = frozenset(
    {
        "chrome_crashpad_handler",
        "crashpad_handler",
        "QtWebEngineProcess.app",
        "QtWebEngineProcess",
    }
)

WINDOWS_ENGINE_NAMES: dict[str, str] = {
    "libcef.dll": "cef",
    "chrome.dll": "chromium",
    "qt5webenginecore.dll": "qtwebengine",
    "qt6webenginecore.dll": "qtwebengine",
    "nw.dll": "nwjs",
}

WINDOWS_ELECTRON_MARKERS: dict[str, str] = {
    "ffmpeg.dll": "electron",
    "libglesv2.dll": "electron",
    "libegl.dll": "electron",
}

WINDOWS_HELPER_NAMES: dict[str, str | None] = {
    "crashpad_handler.exe": None,
    "qtwebengineprocess.exe": "qtwebengine",
}

WINDOWS_FAMILY_BY_EXECUTABLE: dict[str, str] = {
    "chrome.exe": "chrome",
    "msedge.exe": "edge",
    "brave.exe": "brave",
    "vivaldi.exe": "vivaldi",
    "opera.exe": "opera",
    "launcher.exe": "opera",
    "chromium.exe": "chromium",
}

BROWSER_VERSION_DIR_NAMES = frozenset({"application", "chrome-bin"})

WINDOWS_LIBRARY_SUFFIXES = frozenset(
    {
        ".dll",
        ".manifest",
        ".dat",
        ".bin",
        ".pak",
        ".json",
        ".asar",
        ".ico",
        ".png",
        ".sig",
    }
)

MACOS_DEFAULT_ROOTS = ("/Applications", "~/Applications", "/opt/homebrew", "/usr/local")

# Directories that carry a flat runtime's payload rather than being runtimes
# themselves. A file inside one of them belongs to the first ancestor that is
# not one of them.
_MACOS_PAYLOAD_DIR_NAMES = frozenset(
    {
        "bin",
        "lib",
        "Frameworks",
        "Libraries",
        "Resources",
        "Contents",
        "MacOS",
        "Helpers",
        "locales",
    }
)


class PlatformProfile(Protocol):
    """Per-OS evidence, grouping, metadata, and seed-search behavior.

    ``classify_path``, ``runtime_root_for``, and ``is_executable`` accept a
    ``FileInfo`` when the caller already walked the path: profiles then reuse
    that stat data instead of touching the filesystem again.
    """

    name: str
    case_insensitive_names: bool
    seed_exact_names: tuple[str, ...]
    seed_fd_names_regex: str
    seed_extra_globs: tuple[str, ...]
    find_seed_command_supported: bool
    library_suffixes: frozenset[str]

    def classify_path(
        self, path: Path, *, info: FileInfo | None = None
    ) -> Evidence | None: ...

    def runtime_root_for(self, path: Path, *, info: FileInfo | None = None) -> Path: ...

    def is_executable(self, path: Path, *, info: FileInfo | None = None) -> bool: ...

    def read_metadata(self, root: Path) -> dict[str, str]: ...

    def default_roots(self) -> list[Path]: ...

    def display_name_for(
        self, root: Path, metadata: dict[str, str], family: str
    ) -> str: ...


def infer_family(evidence: list[Evidence]) -> str:
    """Infer a best-effort runtime family from evidence hints.

    Engine/framework evidence is more authoritative than generic helper names:
    Chrome, Edge, Brave, and Electron apps all have helpers, but their engine
    names identify the actual family. Launcher executable hints outrank both:
    on Windows every Chromium browser ships the same chrome.dll, so the exe
    name is the only signal distinguishing them.
    """
    for category in ("executable", "engine"):
        hints = [
            item.family_hint
            for item in evidence
            if item.category == category and item.family_hint
        ]
        if hints:
            return Counter(hints).most_common(1)[0][0]

    hints = [item.family_hint for item in evidence if item.family_hint]
    if not hints:
        return "chromium"
    return Counter(hints).most_common(1)[0][0]


def _classify_resource_path(path: Path, *, case_insensitive: bool) -> Evidence | None:
    name = path.name.lower() if case_insensitive else path.name
    names = RESOURCE_NAMES_LOWER if case_insensitive else RESOURCE_NAMES
    if name in names:
        return Evidence("resource", path, name, _family_hint(name))
    parent = path.parent.name
    if case_insensitive:
        parent = parent.lower()
    if name.endswith(".pak") and parent == "locales":
        return Evidence("resource", path, "locale pak")
    return None


def _family_hint(resource_name: str) -> str | None:
    if resource_name.startswith("qtwebengine_"):
        return "qtwebengine"
    return None


def _path_is_dir(path: Path, info: FileInfo | None) -> bool:
    return info.is_dir if info is not None else path.is_dir()


class MacOSProfile:
    name = "macos"
    case_insensitive_names = False
    find_seed_command_supported = True
    library_suffixes = frozenset({".dylib", ".so"})

    seed_exact_names = tuple(
        sorted(RESOURCE_NAMES | MACOS_HELPER_NAMES | frozenset(MACOS_ENGINE_NAMES))
    )
    seed_extra_globs: tuple[str, ...] = ("*.pak", "* Helper.app", "* Helper (*).app")
    seed_fd_names_regex = "|".join(
        sorted(
            {
                *seed_exact_names,
                r".*\.pak",
                r".* Helper( \(.+\))?\.app",
            },
            key=len,
            reverse=True,
        )
    )

    def classify_path(
        self, path: Path, *, info: FileInfo | None = None
    ) -> Evidence | None:
        name = path.name
        if name in MACOS_ENGINE_NAMES:
            return Evidence("engine", path, name, MACOS_ENGINE_NAMES[name])

        resource = _classify_resource_path(path, case_insensitive=False)
        if resource is not None:
            return resource

        if name in MACOS_HELPER_NAMES:
            return Evidence(
                "helper",
                path,
                name,
                "qtwebengine" if name.startswith("QtWebEngine") else None,
            )

        if name.endswith(" Helper.app") or (
            " Helper (" in name and name.endswith(").app")
        ):
            return Evidence("helper", path, "Helper.app")

        # Only now does executability matter, so the name tables above never
        # pay for a stat the caller did not need.
        if not self.is_executable(path, info=info):
            return None

        if _is_framework_executable(path):
            return Evidence("executable", path, "framework executable")

        if _is_contents_macos_path(path):
            return Evidence("executable", path, "Contents/MacOS executable")

        return None

    def runtime_root_for(self, path: Path, *, info: FileInfo | None = None) -> Path:
        app_root = _outermost_bundle(path, ".app")
        if app_root is not None:
            return app_root

        framework_root = _outermost_bundle(path, ".framework")
        if framework_root is not None:
            return framework_root

        return _flat_runtime_root_for(path, info=info)

    def is_executable(self, path: Path, *, info: FileInfo | None = None) -> bool:
        if info is not None:
            return info.is_file and bool(info.mode & (S_IXUSR | S_IXGRP | S_IXOTH))
        try:
            mode = path.stat().st_mode
        except OSError:
            return False
        return path.is_file() and bool(mode & (S_IXUSR | S_IXGRP | S_IXOTH))

    def read_metadata(self, root: Path) -> dict[str, str]:
        info_plist = root / "Contents" / "Info.plist"
        if not info_plist.exists():
            return {}
        try:
            with info_plist.open("rb") as plist_file:
                data = plistlib.load(plist_file)
        except OSError, plistlib.InvalidFileException, ValueError:
            return {}

        metadata: dict[str, str] = {}
        for key in (
            "CFBundleName",
            "CFBundleDisplayName",
            "CFBundleIdentifier",
            "CFBundleShortVersionString",
            "CFBundleVersion",
            "CFBundleExecutable",
        ):
            value = data.get(key)
            if isinstance(value, str):
                metadata[key] = value
        return metadata

    def default_roots(self) -> list[Path]:
        return [
            root
            for root in (Path(item).expanduser() for item in MACOS_DEFAULT_ROOTS)
            if root.exists()
        ]

    def display_name_for(
        self, root: Path, metadata: dict[str, str], family: str
    ) -> str:
        for key in ("CFBundleDisplayName", "CFBundleName"):
            value = metadata.get(key)
            if value:
                return value
        return root.name


class WindowsProfile:
    name = "windows"
    case_insensitive_names = True
    find_seed_command_supported = False
    library_suffixes = WINDOWS_LIBRARY_SUFFIXES

    seed_exact_names = tuple(
        sorted(
            {
                *WINDOWS_ENGINE_NAMES,
                *WINDOWS_ELECTRON_MARKERS,
                *WINDOWS_HELPER_NAMES,
                *RESOURCE_NAMES_LOWER,
            }
        )
    )
    seed_extra_globs: tuple[str, ...] = ("*.pak",)
    seed_fd_names_regex = "|".join(
        sorted({*seed_exact_names, r".*\.pak"}, key=len, reverse=True)
    )

    def classify_path(
        self, path: Path, *, info: FileInfo | None = None
    ) -> Evidence | None:
        name = path.name.lower()

        if name in WINDOWS_ENGINE_NAMES:
            return Evidence("engine", path, name, WINDOWS_ENGINE_NAMES[name])

        if name in WINDOWS_ELECTRON_MARKERS:
            return Evidence("electron-marker", path, name, "electron")

        resource = _classify_resource_path(path, case_insensitive=True)
        if resource is not None:
            return resource

        if name in WINDOWS_HELPER_NAMES:
            return Evidence("helper", path, name, WINDOWS_HELPER_NAMES[name])

        if name.endswith(".exe"):
            hint = WINDOWS_FAMILY_BY_EXECUTABLE.get(name)
            return Evidence("executable", path, name, hint)

        return None

    def runtime_root_for(self, path: Path, *, info: FileInfo | None = None) -> Path:
        parts = path.parts
        lowered = tuple(part.lower() for part in parts)

        # Version-dir layout: .../Application/<version>/... with the launcher
        # exe one level up from the version directory. Checked before the
        # locales/resources rules because browser resources nest inside the
        # version directory.
        for index in range(len(lowered) - 1):
            if lowered[index] in BROWSER_VERSION_DIR_NAMES:
                return Path(*parts[: index + 1])

        for index in range(len(lowered)):
            if lowered[index] == "locales":
                return Path(*parts[:index])

        if len(lowered) >= 2 and lowered[-2] == "resources":
            return Path(*parts[:-2])

        return path if _path_is_dir(path, info) else path.parent

    def is_executable(self, path: Path, *, info: FileInfo | None = None) -> bool:
        if info is not None:
            return info.is_file and path.suffix.lower() == ".exe"
        return path.is_file() and path.suffix.lower() == ".exe"

    def read_metadata(self, root: Path) -> dict[str, str]:
        return read_windows_metadata(root)

    def registry_roots(self) -> dict[Path, dict[str, str]]:
        """Installed-software records from the Windows registry.

        Maps install directories to registration metadata (DisplayName,
        DisplayVersion, Publisher, source). Empty on non-Windows hosts.
        """
        return installed_software()

    def default_roots(self) -> list[Path]:
        candidates: list[Path] = []
        program_files = os.environ.get("ProgramFiles")
        if program_files:
            candidates.append(Path(program_files))
        program_files_x86 = os.environ.get("ProgramFiles(x86)")
        if program_files_x86:
            candidates.append(Path(program_files_x86))
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            candidates.append(Path(local_app_data) / "Programs")
        return [root for root in candidates if root.exists()]

    def display_name_for(
        self, root: Path, metadata: dict[str, str], family: str
    ) -> str:
        for key in ("FileDescription", "ProductName"):
            value = metadata.get(key)
            if value:
                return value
        if family == "chromium":
            return root.name
        exe = root / f"{family}.exe"
        if exe.exists():
            return exe.stem
        return root.name


def _is_contents_macos_path(path: Path) -> bool:
    parts = path.parts
    return len(parts) >= 3 and parts[-3] == "Contents" and parts[-2] == "MacOS"


def _is_framework_executable(path: Path) -> bool:
    for parent in path.parents:
        if parent.name.endswith(".framework"):
            return path.name == parent.stem
    return False


def _outermost_bundle(path: Path, suffix: str) -> Path | None:
    candidates = [
        candidate
        for candidate in (path, *path.parents)
        if candidate.name.endswith(suffix)
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda candidate: len(candidate.parts))


def _flat_runtime_root_for(path: Path, *, info: FileInfo | None = None) -> Path:
    """Runtime root for a path outside any ``.app`` or ``.framework``.

    Flat Chromium distributions keep payload under ``bin``, ``lib``,
    ``Resources``, and friends. Those directories are transparent: the runtime
    root is the parent of the highest one on the path, so ``app/bin/deep/exe``
    and ``app/Resources/locales/x.pak`` both belong to ``app``. A path with no
    payload directory stays in its own directory.
    """

    current = path if _path_is_dir(path, info) else path.parent
    root = current
    while current.parent != current:
        if current.name in _MACOS_PAYLOAD_DIR_NAMES:
            root = current.parent
        current = current.parent
    return root


_MACOS_PROFILE = MacOSProfile()
_WINDOWS_PROFILE = WindowsProfile()


def profile_for_name(name: str) -> PlatformProfile:
    normalized = name.strip().lower()
    if normalized in {"macos", "darwin", "osx"}:
        return _MACOS_PROFILE
    if normalized in {"windows", "win32", "win"}:
        return _WINDOWS_PROFILE
    raise ValueError(f"unknown platform profile: {name}")


def current_profile() -> PlatformProfile:
    if os.name == "nt":
        return _WINDOWS_PROFILE
    return _MACOS_PROFILE
