"""Windows PE version-resource metadata (optional ``pefile`` dependency)."""

import os
from pathlib import Path

METADATA_KEYS = ("FileDescription", "ProductName", "FileVersion")

_ENV_PREFIX = "CHROMIUM_COUNT_STUB_"


def read_windows_metadata(root: Path) -> dict[str, str]:
    """Best-effort VS_VERSION_INFO extraction from the root's primary exe.

    Requires the optional ``pefile`` extra; metadata is empty when it is not
    installed, the exe is missing, or the binary cannot be parsed. The
    ``CHROMIUM_COUNT_STUB_*`` environment variables override extracted values,
    which is what lets tests and dry runs run without a real Windows binary.
    """

    metadata = _read_pe_version_metadata(root)
    for key in METADATA_KEYS:
        value = os.environ.get(f"{_ENV_PREFIX}{key.upper()}")
        if value:
            metadata[key] = value
    return metadata


def _read_pe_version_metadata(root: Path) -> dict[str, str]:
    try:
        import pefile  # pyright: ignore[reportMissingImports]
    except ImportError:
        return {}

    candidates = sorted(root.glob("*.exe"))
    if not candidates:
        return {}

    try:
        executable = pefile.PE(str(candidates[0]))
    except OSError, pefile.PEFormatError:
        return {}

    wanted = {key.lower(): key for key in METADATA_KEYS}
    metadata: dict[str, str] = {}
    try:
        for file_info in getattr(executable, "FileInfo", []):
            for entry in file_info:
                if _decode(getattr(entry, "Key", b"")) != "StringFileInfo":
                    continue
                for string_table in getattr(entry, "StringTable", []):
                    for raw_key, raw_value in string_table.entries.items():
                        key = wanted.get(_decode(raw_key).lower())
                        if key is None:
                            continue
                        value = _decode(raw_value).strip("\x00 ")
                        if value:
                            metadata[key] = value
    except AttributeError, UnicodeDecodeError, ValueError:
        return metadata
    return metadata


def _decode(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return str(value)
