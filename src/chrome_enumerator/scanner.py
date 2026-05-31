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
        grouped: dict[Path, list[Evidence]] = defaultdict(list)

        for root_value in roots:
            root = Path(root_value).expanduser()
            if not root.exists():
                self.warnings.append(f"missing root: {root}")
                continue
            for evidence in self._walk_evidence(root):
                grouped[self._runtime_root_for(evidence.path)].append(evidence)

        results = [self._build_result(root, evidence) for root, evidence in grouped.items()]
        filtered = [result for result in results if self.include_low_confidence or result.confidence != "low"]
        return sorted(filtered, key=lambda result: str(result.root))

    def _walk_evidence(self, root: Path) -> Iterable[Evidence]:
        root = root.resolve(strict=False)

        for current_dir, dir_names, file_names in os.walk(
            root,
            topdown=True,
            followlinks=self.follow_symlinks,
            onerror=self._record_walk_error,
        ):
            current = Path(current_dir)
            if self.max_depth is not None and _depth_from(root, current) >= self.max_depth:
                dir_names[:] = []

            if not self.follow_symlinks:
                dir_names[:] = [name for name in dir_names if not (current / name).is_symlink()]

            for dir_name in list(dir_names):
                path = current / dir_name
                evidence = classify_path(path, is_executable=False)
                if evidence is not None:
                    yield evidence

            for file_name in file_names:
                path = current / file_name
                evidence = classify_path(path, is_executable=_is_executable(path))
                if evidence is not None:
                    yield evidence

    def _record_walk_error(self, error: OSError) -> None:
        self.warnings.append(f"{error.filename}: {error.strerror}")

    def _build_result(self, root: Path, evidence: list[Evidence]) -> RuntimeResult:
        unique_evidence = _dedupe_evidence(evidence)
        confidence = _score_confidence(unique_evidence)
        entrypoints = sorted(
            {item.path for item in unique_evidence if item.category == "executable" or _is_executable(item.path)},
            key=str,
        )
        return RuntimeResult(
            root=root,
            family=infer_family(unique_evidence),
            confidence=confidence,
            evidence=sorted(unique_evidence, key=lambda item: (item.category, str(item.path))),
            entrypoints=entrypoints,
            metadata=_read_metadata(root),
            size_bytes=_size_bytes(root),
        )

    def _runtime_root_for(self, path: Path) -> Path:
        app_root = _outermost_bundle(path, ".app")
        if app_root is not None:
            return app_root

        framework_root = _outermost_bundle(path, ".framework")
        if framework_root is not None:
            return framework_root

        return path.parent if path.is_file() else path


def _score_confidence(evidence: list[Evidence]) -> Confidence:
    categories = {item.category for item in evidence}
    has_executable = "executable" in categories or any(_is_executable(item.path) for item in evidence)
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


def _size_bytes(root: Path) -> int:
    if root.is_file():
        try:
            return root.stat().st_size
        except OSError:
            return 0

    total = 0
    for current_dir, dir_names, file_names in os.walk(root, topdown=True, onerror=lambda _error: None):
        current = Path(current_dir)
        dir_names[:] = [name for name in dir_names if not (current / name).is_symlink()]
        for file_name in file_names:
            path = current / file_name
            if path.is_symlink():
                continue
            try:
                total += path.stat().st_size
            except OSError:
                continue
    return total
