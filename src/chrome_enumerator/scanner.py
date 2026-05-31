from __future__ import annotations

import os
import plistlib
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from stat import S_IXGRP, S_IXOTH, S_IXUSR
from typing import Literal

from .detectors import classify_path, infer_family
from .model import Confidence, Evidence, RuntimeResult

_ALLOWED_METADATA_KEYS = (
    "CFBundleName",
    "CFBundleDisplayName",
    "CFBundleIdentifier",
    "CFBundleShortVersionString",
    "CFBundleVersion",
    "CFBundleExecutable",
)


class ChromiumScanner:
    def __init__(
        self,
        *,
        include_low_confidence: bool = False,
        max_depth: int | None = None,
        follow_symlinks: bool = False,
    ) -> None:
        self.include_low_confidence = include_low_confidence
        self.max_depth = max_depth
        self.follow_symlinks = follow_symlinks
        self.warnings: list[str] = []

    def scan(self, roots: Iterable[Path | str]) -> list[RuntimeResult]:
        self.warnings.clear()
        grouped: dict[Path, list[Evidence]] = defaultdict(list)

        for root_value in roots:
            root = Path(root_value).expanduser()
            if root.is_symlink() and not root.exists():
                continue
            if not root.exists():
                self.warnings.append(f"missing root: {root}")
                continue
            if root.is_symlink() and not self.follow_symlinks:
                self.warnings.append(f"skipped symlink root: {root}")
                continue
            for evidence in self._walk_evidence(root):
                grouped[self._runtime_root_for(evidence.path)].append(evidence)

        results = [self._build_result(root, evidence) for root, evidence in grouped.items()]
        filtered = [result for result in results if self.include_low_confidence or result.confidence != "low"]
        return sorted(filtered, key=lambda result: str(result.root))

    def _walk_evidence(self, root: Path) -> Iterable[Evidence]:
        root_evidence = classify_path(root, is_executable=_is_executable(root))
        if root_evidence is not None:
            yield root_evidence
        visited_dirs = _initial_visited_dirs(root)

        for current_dir, dir_names, file_names in os.walk(
            root,
            topdown=True,
            followlinks=self.follow_symlinks,
            onerror=self._record_walk_error,
        ):
            current = Path(current_dir)
            if self.max_depth is not None and _depth_from(root, current) >= self.max_depth:
                dir_names[:] = []

            _filter_walk_dirs(current, dir_names, follow_symlinks=self.follow_symlinks, visited_dirs=visited_dirs)

            for dir_name in list(dir_names):
                path = current / dir_name
                evidence = classify_path(path, is_executable=False)
                if evidence is not None:
                    yield evidence

            for file_name in file_names:
                path = current / file_name
                if path.is_symlink() and (not self.follow_symlinks or not path.exists()):
                    continue
                evidence = classify_path(path, is_executable=_is_executable(path))
                if evidence is not None:
                    yield evidence

    def _record_walk_error(self, error: OSError) -> None:
        self.warnings.append(f"{error.filename}: {error.strerror}")

    def _build_result(self, root: Path, evidence: list[Evidence]) -> RuntimeResult:
        unique_evidence = _dedupe_evidence(evidence)
        entrypoints = sorted(
            {
                *[item.path for item in unique_evidence if item.category == "executable" or _is_executable(item.path)],
                *_find_entrypoints(root, max_depth=self.max_depth, follow_symlinks=self.follow_symlinks),
            },
            key=str,
        )
        confidence = _score_confidence(unique_evidence, entrypoints)
        return RuntimeResult(
            root=root,
            family=infer_family(unique_evidence),
            confidence=confidence,
            evidence=sorted(unique_evidence, key=lambda item: (item.category, str(item.path))),
            entrypoints=entrypoints,
            metadata=_read_metadata(root),
            size_bytes=_size_bytes(root, follow_symlinks=self.follow_symlinks),
        )

    def _runtime_root_for(self, path: Path) -> Path:
        app_root = _outermost_bundle(path, ".app")
        if app_root is not None:
            return app_root

        framework_root = _outermost_bundle(path, ".framework")
        if framework_root is not None:
            return framework_root

        return _flat_runtime_root_for(path)


def _score_confidence(evidence: list[Evidence], entrypoints: list[Path]) -> Confidence:
    categories = {item.category for item in evidence}
    has_executable = "executable" in categories or bool(entrypoints) or any(_is_executable(item.path) for item in evidence)
    has_engine = "engine" in categories
    has_resource = "resource" in categories
    has_helper = "helper" in categories

    if has_executable and has_engine and (has_resource or has_helper):
        return "high"

    secondary_count = sum([has_engine, has_resource, has_helper])
    if has_executable and secondary_count >= 2:
        return "medium"

    return "low"


def _outermost_bundle(path: Path, suffix: Literal[".app", ".framework"]) -> Path | None:
    candidates = [candidate for candidate in (path, *path.parents) if candidate.name.endswith(suffix)]
    if not candidates:
        return None
    return min(candidates, key=lambda candidate: len(candidate.parts))


def _flat_runtime_root_for(path: Path) -> Path:
    if path.name == "libcef.dylib" and path.parent.name in {"lib", "Frameworks", "Libraries"}:
        return path.parent.parent

    if path.parent.name == "Resources":
        return path.parent.parent

    if path.parent.name == "locales" and path.parent.parent.name == "Resources":
        return path.parent.parent.parent

    return path.parent if path.is_file() else path


def _find_entrypoints(root: Path, *, max_depth: int | None = None, follow_symlinks: bool = False) -> list[Path]:
    if root.is_file():
        return [root] if _is_executable(root) else []

    entrypoints: list[Path] = []
    visited_dirs = _initial_visited_dirs(root)
    for current_dir, dir_names, file_names in os.walk(
        root,
        topdown=True,
        followlinks=follow_symlinks,
        onerror=lambda _error: None,
    ):
        current = Path(current_dir)
        current_depth = _depth_from(root, current)
        if max_depth is not None and current_depth >= max_depth:
            dir_names[:] = []
            continue

        _filter_walk_dirs(current, dir_names, follow_symlinks=follow_symlinks, visited_dirs=visited_dirs)
        for file_name in file_names:
            path = current / file_name
            if path.is_symlink() and (not follow_symlinks or not path.exists()):
                continue
            if path.suffix in {".dylib", ".so"}:
                continue
            if _is_executable(path):
                entrypoints.append(path)
    return entrypoints


def _initial_visited_dirs(root: Path) -> set[tuple[int, int]]:
    try:
        stat_result = root.stat()
    except OSError:
        return set()
    return {(stat_result.st_dev, stat_result.st_ino)} if root.is_dir() else set()


def _filter_walk_dirs(
    current: Path,
    dir_names: list[str],
    *,
    follow_symlinks: bool,
    visited_dirs: set[tuple[int, int]],
) -> None:
    kept: list[str] = []
    for dir_name in dir_names:
        path = current / dir_name
        if path.is_symlink() and (not follow_symlinks or not path.exists()):
            continue
        try:
            stat_result = path.stat()
        except OSError:
            continue
        key = (stat_result.st_dev, stat_result.st_ino)
        if key in visited_dirs:
            continue
        visited_dirs.add(key)
        kept.append(dir_name)
    dir_names[:] = kept


def _is_executable(path: Path) -> bool:
    try:
        mode = path.stat().st_mode
    except OSError:
        return False
    return path.is_file() and bool(mode & (S_IXUSR | S_IXGRP | S_IXOTH))


def _depth_from(root: Path, current: Path) -> int:
    try:
        return len(current.relative_to(root).parts)
    except ValueError:
        return 0


def _dedupe_evidence(evidence: list[Evidence]) -> list[Evidence]:
    seen: set[tuple[str, Path, str]] = set()
    deduped: list[Evidence] = []
    for item in evidence:
        key = (item.category, item.path, item.reason)
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped


def _read_metadata(root: Path) -> dict[str, str]:
    info_plist = root / "Contents" / "Info.plist"
    if not info_plist.exists():
        return {}
    try:
        with info_plist.open("rb") as plist_file:
            data = plistlib.load(plist_file)
    except (OSError, plistlib.InvalidFileException, ValueError):
        return {}

    metadata: dict[str, str] = {}
    for key in _ALLOWED_METADATA_KEYS:
        value = data.get(key)
        if isinstance(value, str):
            metadata[key] = value
    return metadata


def _size_bytes(root: Path, *, follow_symlinks: bool = False) -> int:
    if root.is_file():
        try:
            return root.stat().st_size
        except OSError:
            return 0

    total = 0
    visited_dirs = _initial_visited_dirs(root)
    for current_dir, dir_names, file_names in os.walk(
        root,
        topdown=True,
        followlinks=follow_symlinks,
        onerror=lambda _error: None,
    ):
        current = Path(current_dir)
        _filter_walk_dirs(current, dir_names, follow_symlinks=follow_symlinks, visited_dirs=visited_dirs)
        for file_name in file_names:
            path = current / file_name
            if path.is_symlink() and (not follow_symlinks or not path.exists()):
                continue
            try:
                total += path.stat().st_size
            except OSError:
                continue
    return total
