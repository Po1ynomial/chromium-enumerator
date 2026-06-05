from __future__ import annotations

from collections import Counter
from pathlib import Path

from .model import Evidence

ENGINE_NAMES: dict[str, str] = {
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

HELPER_NAMES = {
    "chrome_crashpad_handler",
    "crashpad_handler",
    "QtWebEngineProcess.app",
    "QtWebEngineProcess",
}


def classify_path(path: Path, *, is_executable: bool) -> Evidence | None:
    """Classify a filesystem path into Chromium evidence, if it is a known signal."""
    name = path.name

    if name in ENGINE_NAMES:
        return Evidence("engine", path, name, ENGINE_NAMES[name])

    if name in RESOURCE_NAMES:
        return Evidence("resource", path, name, _family_hint_from_resource(name))

    if name.endswith(".pak") and path.parent.name == "locales":
        return Evidence("resource", path, "locale pak")

    if name in HELPER_NAMES:
        return Evidence(
            "helper",
            path,
            name,
            "qtwebengine" if name.startswith("QtWebEngine") else None,
        )

    if name.endswith(" Helper.app") or " Helper (" in name and name.endswith(").app"):
        return Evidence("helper", path, "Helper.app")

    if is_executable and _is_framework_executable(path):
        return Evidence("executable", path, "framework executable")

    if is_executable and _is_contents_macos_path(path):
        return Evidence("executable", path, "Contents/MacOS executable")

    return None


def infer_family(evidence: list[Evidence]) -> str:
    """Infer a best-effort runtime family from evidence hints.

    Engine/framework evidence is more authoritative than generic helper app names:
    Chrome, Edge, Brave, and Electron apps all have helper apps, but their engine
    framework names identify the actual family.
    """
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


def _family_hint_from_resource(name: str) -> str | None:
    if name.startswith("qtwebengine_"):
        return "qtwebengine"
    return None


def _is_contents_macos_path(path: Path) -> bool:
    parts = path.parts
    return len(parts) >= 3 and parts[-3] == "Contents" and parts[-2] == "MacOS"


def _is_framework_executable(path: Path) -> bool:
    for parent in path.parents:
        if parent.name.endswith(".framework"):
            return path.name == parent.stem
    return False
