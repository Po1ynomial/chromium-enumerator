from __future__ import annotations

from pathlib import Path

from .model import Evidence
from .platforms import (
    MACOS_ENGINE_NAMES,
    MACOS_HELPER_NAMES,
    RESOURCE_NAMES,
    MacOSProfile,
    infer_family,
    profile_for_name,
)

ENGINE_NAMES = MACOS_ENGINE_NAMES
HELPER_NAMES = MACOS_HELPER_NAMES


def classify_path(path: Path, *, is_executable: bool) -> Evidence | None:
    """Classify a filesystem path into Chromium evidence, if it is a known signal.

    Legacy wrapper around the macOS platform profile kept for existing callers
    and tests; the `is_executable` hint is forwarded so callers can classify
    paths whose executable bit has not been (or cannot be) statted.
    """
    profile = profile_for_name("macos")
    assert isinstance(profile, MacOSProfile)
    return profile._classify_path(path, is_executable=is_executable)


__all__ = [
    "ENGINE_NAMES",
    "HELPER_NAMES",
    "RESOURCE_NAMES",
    "classify_path",
    "infer_family",
]
