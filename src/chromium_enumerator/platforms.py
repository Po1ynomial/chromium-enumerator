from __future__ import annotations

import os
import plistlib
from collections import Counter
from pathlib import Path
from stat import S_IXGRP, S_IXOTH, S_IXUSR
from typing import Protocol

from .model import Evidence

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

RESOURCE_NAMES = {
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

MACOS_HELPER_NAMES = {
    "chrome_crashpad_handler",
    "crashpad_handler",
    "QtWebEngineProcess.app",
    "QtWebEngineProcess",
}

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

BROWSER_VERSION_DIR_NAMES = {"application", "chrome-bin"}

WINDOWS_LIBRARY_SUFFIXES = {
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

MACOS_DEFAULT_ROOTS = ("/Applications", "~/Applications", "/opt/homebrew", "/usr/local")

_WINDOWS_METADATA_ENV_VARS = ("FileDescription", "ProductName", "FileVersion")


class PlatformProfile(Protocol):
    """Per-OS evidence, grouping, metadata, and seed-search behavior."""

    name: str
    case_insensitive_names: bool
    seed_exact_names: tuple[str, ...]
    seed_fd_names_regex: str
    seed_extra_globs: tuple[str, ...]
    find_seed_command_supported: bool
    library_suffixes: frozenset[str]

    def classify_path(self, path: Path) -> Evidence | None: ...

    def runtime_root_for(self, path: Path) -> Path: ...

    def is_executable(self, path: Path) -> bool: ...

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
    executable_hints = [
        item.family_hint
        for item in evidence
        if item.category == "executable" and item.family_hint
    ]
    if executable_hints:
        return Counter(executable_hints).most_common(1)[0][0]

    engine_hints = [
        item.family_hint
        for item in evidence
        if item.category == "engine" and item.family_hint
    ]
    if engine_hints:
        return Counter(engine_hints).most_common(1)[0][0]

    hints = [item.family_hint for item in evidence if item.family_hint]
    if not hints:
        return "chromium"
    return Counter(hints).most_common(1)[0][0]


def _classify_resource_path(path: Path, *, case_insensitive: bool) -> Evidence | None:
    name = path.name.lower() if case_insensitive else path.name
    names = (
        {resource.lower() for resource in RESOURCE_NAMES}
        if case_insensitive
        else RESOURCE_NAMES
    )
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


class MacOSProfile:
    name = "macos"
    case_insensitive_names = False
    find_seed_command_supported = True
    library_suffixes = frozenset({".dylib", ".so"})

    seed_exact_names = tuple(
        sorted(
            frozenset(MACOS_ENGINE_NAMES)
            | frozenset(RESOURCE_NAMES)
            | frozenset(MACOS_HELPER_NAMES)
        )
    )
    seed_extra_globs = ("*.pak", "* Helper.app", "* Helper (*).app")
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

    def classify_path(self, path: Path) -> Evidence | None:
        return self._classify_path(path, is_executable=self.is_executable(path))

    def _classify_path(self, path: Path, *, is_executable: bool) -> Evidence | None:
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

        if is_executable and _is_framework_executable(path):
            return Evidence("executable", path, "framework executable")

        if is_executable and _is_contents_macos_path(path):
            return Evidence("executable", path, "Contents/MacOS executable")

        return None

    def runtime_root_for(self, path: Path) -> Path:
        app_root = _outermost_bundle(path, ".app")
        if app_root is not None:
            return app_root

        framework_root = _outermost_bundle(path, ".framework")
        if framework_root is not None:
            return framework_root

        return _flat_runtime_root_for(path)

    def is_executable(self, path: Path) -> bool:
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
        except (OSError, plistlib.InvalidFileException, ValueError):
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
    library_suffixes = frozenset(WINDOWS_LIBRARY_SUFFIXES)

    seed_exact_names = tuple(
        sorted(
            {
                *WINDOWS_ENGINE_NAMES,
                *WINDOWS_ELECTRON_MARKERS,
                *WINDOWS_HELPER_NAMES,
                *(resource.lower() for resource in RESOURCE_NAMES),
            }
        )
    )
    seed_extra_globs = ("*.pak",)
    seed_fd_names_regex = "|".join(
        sorted({*seed_exact_names, r".*\.pak"}, key=len, reverse=True)
    )

    def classify_path(self, path: Path) -> Evidence | None:
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

    def runtime_root_for(self, path: Path) -> Path:
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

        return path.parent if path.is_file() else path

    def is_executable(self, path: Path) -> bool:
        return path.is_file() and path.suffix.lower() == ".exe"

    def read_metadata(self, root: Path) -> dict[str, str]:
        metadata = _read_pe_version_metadata(root)
        for env_var in _WINDOWS_METADATA_ENV_VARS:
            value = os.environ.get(f"CHROMIUM_COUNT_STUB_{env_var.upper()}")
            if value:
                metadata[env_var] = value
        return metadata

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


def _flat_runtime_root_for(path: Path) -> Path:
    if path.name == "libcef.dylib" and path.parent.name in {
        "lib",
        "Frameworks",
        "Libraries",
    }:
        return path.parent.parent

    if path.parent.name == "Resources":
        return path.parent.parent

    if path.parent.name == "locales" and path.parent.parent.name == "Resources":
        return path.parent.parent.parent

    return path.parent if path.is_file() else path


def _read_pe_version_metadata(root: Path) -> dict[str, str]:
    """Best-effort VS_VERSION_INFO extraction from the root's primary exe.

    Requires the optional `pefile` extra; returns an empty mapping when it is
    not installed, the exe is missing, or the binary cannot be parsed.
    """
    try:
        import pefile  # type: ignore[import-not-found]
    except ImportError:
        return {}

    candidates = sorted(root.glob("*.exe"))
    if not candidates:
        return {}

    wanted = {key.lower(): key for key in _WINDOWS_METADATA_ENV_VARS}
    metadata: dict[str, str] = {}
    try:
        pe = pefile.PE(str(candidates[0]))
    except (OSError, pefile.PEFormatError):
        return {}
    try:
        for file_info in getattr(pe, "FileInfo", []):
            for entry in file_info:
                key = getattr(entry, "Key", b"")
                if isinstance(key, bytes) and key.decode(
                    errors="replace"
                ) != "StringFileInfo":
                    continue
                for string_table in getattr(entry, "StringTable", []):
                    for raw_key, raw_value in string_table.entries.items():
                        name = raw_key.decode(errors="replace").lower()
                        if name in wanted:
                            value = raw_value.decode(errors="replace").strip("\x00 ")
                            if value:
                                metadata[wanted[name]] = value
    except (AttributeError, UnicodeDecodeError, ValueError):
        return metadata
    return metadata


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
