"""Windows registry reads for installed-software records.

Kept apart from the platform profiles: the registry is never detection
evidence, it only enriches results and backs ``--registry-only``. Everything
here is a no-op off Windows.
"""

import os
from collections.abc import Callable
from contextlib import suppress as _suppress
from pathlib import Path

_Record = Callable[[Path, dict[str, str]], None]

UNINSTALL_KEYS = (
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
    r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
)

APP_PATHS_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"

STARTMENU_INTERNET_KEY = r"SOFTWARE\Clients\StartMenuInternet"

_REGISTRY_PATH_PROPS = ("InstallLocation", "DisplayIcon")
_REGISTRY_METADATA_PROPS = ("DisplayName", "DisplayVersion", "Publisher")

_UNINSTALLER_STEMS = {
    "uninstall",
    "uninstaller",
    "uninst",
    "unins000",
    "unins001",
    "unsetup",
    "setup",
    "update",
}


def installed_software() -> dict[Path, dict[str, str]]:
    """Collect install directories and registration metadata from the registry.

    Reads uninstall, App Paths, and StartMenuInternet records (HKLM + HKCU,
    including the 32-bit WOW6432Node uninstall view) and returns existing
    install directories keyed by resolved path. Empty on non-Windows hosts or
    when keys are unreadable.
    """
    if os.name != "nt":
        return {}
    try:
        import winreg
    except ImportError:
        return {}

    discovered: dict[str, dict[str, str]] = {}

    def record(root: Path, props: dict[str, str]) -> None:
        key = casefold_path(root)
        merged = discovered.setdefault(key, {"root": str(root)})
        for name, value in props.items():
            if value and name not in merged:
                merged[name] = value

    for hive, hive_label in (
        (winreg.HKEY_LOCAL_MACHINE, "HKLM"),
        (winreg.HKEY_CURRENT_USER, "HKCU"),
    ):
        for subkey in UNINSTALL_KEYS:
            _collect_uninstall_entries(
                winreg, hive, subkey, f"{hive_label}\\{subkey}", record
            )
        for path in _collect_app_paths(winreg, hive):
            record(path, {})
        for path in _collect_startmenu_internet(winreg, hive):
            record(path, {})

    return {Path(props.pop("root")): props for props in discovered.values()}


def install_root_from_uninstall(props: dict[str | None, str]) -> Path | None:
    """Install directory named by an uninstall record, if one exists."""

    install_location = parse_dir_path(props.get("InstallLocation"))
    if install_location is not None and install_location.is_dir():
        return install_location
    icon = parse_exe_path(props.get("DisplayIcon"))
    if icon is None or not icon.exists():
        return None
    if icon.stem.lower() in _UNINSTALLER_STEMS:
        return None
    return icon.parent


def parse_dir_path(value: str | None) -> Path | None:
    if not value:
        return None
    cleaned = value.strip().strip('"')
    if not cleaned:
        return None
    try:
        return Path(os.path.expandvars(cleaned))
    except OSError, ValueError:
        return None


def parse_exe_path(value: str | None) -> Path | None:
    """Parse an exe path from a registry string that may include quotes/args."""

    if not value:
        return None
    cleaned = value.strip()
    if cleaned.startswith('"'):
        end = cleaned.find('"', 1)
        cleaned = cleaned[1:end] if end > 1 else cleaned.strip('"')
    else:
        exe_index = cleaned.lower().find(".exe")
        if exe_index >= 0:
            cleaned = cleaned[: exe_index + 4]
        else:
            cleaned = cleaned.split(",")[0].strip().strip('"')
    if not cleaned:
        return None
    try:
        path = Path(os.path.expandvars(cleaned))
    except OSError, ValueError:
        return None
    if path.suffix.lower() != ".exe":
        return None
    return path


def casefold_path(path: Path) -> str:
    """Case- and separator-normalized key for comparing install directories."""

    try:
        return os.path.normcase(str(path.resolve()))
    except OSError:
        return os.path.normcase(str(path))


def _collect_uninstall_entries(
    winreg, hive, subkey: str, source: str, record: _Record
) -> None:
    with _suppress(OSError), winreg.OpenKey(hive, subkey) as parent:
        index = 0
        while True:
            try:
                subkey_name = winreg.EnumKey(parent, index)
                index += 1
            except OSError:
                break
            with _suppress(OSError), winreg.OpenKey(parent, subkey_name) as entry:
                props = _read_registry_values(
                    winreg,
                    entry,
                    frozenset((*_REGISTRY_PATH_PROPS, *_REGISTRY_METADATA_PROPS)),
                )
                root = install_root_from_uninstall(props)
                if root is None:
                    continue
                metadata = {
                    name: props[name]
                    for name in _REGISTRY_METADATA_PROPS
                    if props.get(name)
                }
                metadata["source"] = source
                record(root, metadata)


def _collect_app_paths(winreg, hive) -> list[Path]:
    roots: list[Path] = []
    with _suppress(OSError), winreg.OpenKey(hive, APP_PATHS_KEY) as parent:
        index = 0
        while True:
            try:
                subkey_name = winreg.EnumKey(parent, index)
                index += 1
            except OSError:
                break
            if not subkey_name.lower().endswith(".exe"):
                continue
            with _suppress(OSError), winreg.OpenKey(parent, subkey_name) as entry:
                props = _read_registry_values(winreg, entry, None)
                exe = parse_exe_path(props.get(None))
                if exe is not None and exe.exists():
                    roots.append(exe.parent)
    return roots


def _collect_startmenu_internet(winreg, hive) -> list[Path]:
    roots: list[Path] = []
    with (
        _suppress(OSError),
        winreg.OpenKey(hive, STARTMENU_INTERNET_KEY) as parent,
    ):
        index = 0
        while True:
            try:
                client = winreg.EnumKey(parent, index)
                index += 1
            except OSError:
                break
            command_key = f"{client}\\shell\\open\\command"
            with _suppress(OSError), winreg.OpenKey(parent, command_key) as entry:
                props = _read_registry_values(winreg, entry, None)
                exe = parse_exe_path(props.get(None))
                if exe is not None and exe.exists():
                    roots.append(exe.parent)
    return roots


def _read_registry_values(
    winreg, key, wanted: frozenset[str | None] | None
) -> dict[str | None, str]:
    values: dict[str | None, str] = {}
    index = 0
    while True:
        try:
            name, data, _kind = winreg.EnumValue(key, index)
            index += 1
        except OSError:
            break
        label = name if name else None
        if isinstance(data, str) and (wanted is None or label in wanted):
            values[label] = data
    return values
