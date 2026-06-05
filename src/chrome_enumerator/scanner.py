from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import tempfile
from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator
from contextlib import suppress as _suppress
from pathlib import Path
from stat import S_IXGRP, S_IXOTH, S_IXUSR
from typing import Literal

from .detectors import classify_path, infer_family
from .model import Confidence, Evidence, RuntimeResult

_EXCEPTIONALLY_SMALL_RUNTIME_BYTES = 5 * 1024 * 1024

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

        results = [
            self._build_result(root, evidence) for root, evidence in grouped.items()
        ]
        filtered = [
            result
            for result in results
            if self.include_low_confidence or result.confidence != "low"
        ]
        return sorted(filtered, key=lambda result: str(result.root))

    def _walk_evidence(self, root: Path) -> Iterable[Evidence]:
        root_evidence = classify_path(root, is_executable=_is_executable(root))
        if root_evidence is not None:
            yield root_evidence

        for path in _iter_traversal_paths(
            root,
            max_depth=self.max_depth,
            follow_symlinks=self.follow_symlinks,
            files_only=False,
            on_error=self.warnings.append,
        ):
            evidence = classify_path(path, is_executable=_is_executable(path))
            if evidence is not None:
                yield evidence

    def _build_result(self, root: Path, evidence: list[Evidence]) -> RuntimeResult:
        unique_evidence = _dedupe_evidence(evidence)
        extra_entrypoints, extra_size = _walk_runtime_extras(
            root, max_depth=self.max_depth, follow_symlinks=self.follow_symlinks
        )
        entrypoints = sorted(
            {
                *[
                    item.path
                    for item in unique_evidence
                    if item.category == "executable" or _is_executable(item.path)
                ],
                *extra_entrypoints,
            },
            key=str,
        )
        confidence = _cap_confidence_for_size(
            _score_confidence(unique_evidence, entrypoints),
            extra_size,
            max_depth=self.max_depth,
            follow_symlinks=self.follow_symlinks,
        )
        return RuntimeResult(
            root=root,
            family=infer_family(unique_evidence),
            confidence=confidence,
            evidence=sorted(
                unique_evidence, key=lambda item: (item.category, str(item.path))
            ),
            entrypoints=entrypoints,
            metadata=_read_metadata(root),
            size_bytes=extra_size,
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
    has_executable = (
        "executable" in categories
        or bool(entrypoints)
        or any(_is_executable(item.path) for item in evidence)
    )
    has_engine = "engine" in categories
    has_resource = "resource" in categories
    has_helper = "helper" in categories

    if has_executable and has_engine and (has_resource or has_helper):
        return "high"

    secondary_count = sum([has_engine, has_resource, has_helper])
    if has_executable and secondary_count >= 2:
        return "medium"

    return "low"


def _cap_confidence_for_size(
    confidence: Confidence,
    size_bytes: int,
    *,
    max_depth: int | None,
    follow_symlinks: bool,
) -> Confidence:
    if max_depth is not None or follow_symlinks:
        return confidence
    if size_bytes < _EXCEPTIONALLY_SMALL_RUNTIME_BYTES:
        return "low"
    return confidence


def _outermost_bundle(path: Path, suffix: Literal[".app", ".framework"]) -> Path | None:
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


def _find_entrypoints(
    root: Path, *, max_depth: int | None = None, follow_symlinks: bool = False
) -> list[Path]:
    """Legacy single-purpose entrypoint walk kept for external callers."""
    return _walk_runtime_extras(
        root, max_depth=max_depth, follow_symlinks=follow_symlinks
    )[0]


def _size_bytes(root: Path, *, follow_symlinks: bool = False) -> int:
    """Legacy single-purpose size walk kept for external callers."""
    return _walk_runtime_extras(root, max_depth=None, follow_symlinks=follow_symlinks)[
        1
    ]


def _walk_runtime_extras(
    root: Path, *, max_depth: int | None = None, follow_symlinks: bool = False
) -> tuple[list[Path], int]:
    if root.is_file():
        size = 0
        with _suppress(OSError):
            size = root.stat().st_size
        return [root] if _is_executable(root) else [], size

    entrypoints: list[Path] = []
    total_size = 0
    for path in _iter_traversal_paths(
        root,
        max_depth=max_depth,
        follow_symlinks=follow_symlinks,
        files_only=True,
        on_error=lambda _message: None,
    ):
        with _suppress(OSError):
            total_size += path.stat().st_size
        if path.suffix in {".dylib", ".so"}:
            continue
        if _is_executable(path):
            entrypoints.append(path)
    return entrypoints, total_size


def _iter_traversal_paths(
    root: Path,
    *,
    max_depth: int | None,
    follow_symlinks: bool,
    files_only: bool,
    on_error: Callable[[str], None],
) -> Iterator[Path]:
    command = _fd_command(
        root,
        max_depth=max_depth,
        follow_symlinks=follow_symlinks,
        files_only=files_only,
    ) or _find_command(
        root,
        max_depth=max_depth,
        follow_symlinks=follow_symlinks,
        files_only=files_only,
    )

    if command is not None:
        paths = _iter_command_paths(command, on_error)
    else:
        paths = _iter_os_walk_paths(
            root,
            max_depth=max_depth,
            follow_symlinks=follow_symlinks,
            files_only=files_only,
            on_error=on_error,
        )

    for path in paths:
        path = _normalize_external_path(root, path)
        if path == root:
            continue
        if _should_skip_symlink(path, follow_symlinks=follow_symlinks):
            continue
        if not _within_scan_depth(
            root, path, max_depth=max_depth, files_only=files_only
        ):
            continue
        yield path


def _fd_command(
    root: Path,
    *,
    max_depth: int | None,
    follow_symlinks: bool,
    files_only: bool,
) -> list[str] | None:
    executable = shutil.which("fd") or shutil.which("fdfind")
    if executable is None or follow_symlinks:
        return None

    command = [executable, "-u", "--absolute-path", "-0"]
    if files_only:
        command.extend(["--type", "file"])
    if max_depth is not None:
        command.extend(["--max-depth", str(max_depth + 1)])
    command.extend([".", str(root)])
    return command


def _find_command(
    root: Path,
    *,
    max_depth: int | None,
    follow_symlinks: bool,
    files_only: bool,
) -> list[str] | None:
    executable = shutil.which("find")
    if executable is None:
        return None

    command = [executable, "-L" if follow_symlinks else "-P", str(root)]
    if max_depth is not None:
        command.extend(["-maxdepth", str(max_depth + 1)])
    if files_only:
        command.extend(["-type", "f"])
    command.append("-print0")
    return command


def _iter_command_paths(
    command: list[str], on_error: Callable[[str], None]
) -> Iterator[Path]:
    with tempfile.TemporaryFile() as stderr_file:
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=stderr_file,
            )
        except OSError as error:
            on_error(str(error))
            return

        if process.stdout is None:
            return

        pending = b""
        while chunk := process.stdout.read(65536):
            parts = (pending + chunk).split(b"\0")
            pending = parts.pop()
            for raw_path in parts:
                if raw_path:
                    yield Path(os.fsdecode(raw_path))
        if pending:
            yield Path(os.fsdecode(pending))

        return_code = process.wait()
        if return_code != 0:
            stderr_file.seek(0)
            message = stderr_file.read(4096).decode(errors="replace").strip()
            if message:
                on_error(message)


def _iter_os_walk_paths(
    root: Path,
    *,
    max_depth: int | None,
    follow_symlinks: bool,
    files_only: bool,
    on_error: Callable[[str], None],
) -> Iterator[Path]:
    visited_dirs = _initial_visited_dirs(root)

    def record_error(error: OSError) -> None:
        on_error(f"{error.filename}: {error.strerror}")

    for current_dir, dir_names, file_names in os.walk(
        root,
        topdown=True,
        followlinks=follow_symlinks,
        onerror=record_error,
    ):
        current = Path(current_dir)
        if max_depth is not None and _depth_from(root, current) >= max_depth:
            dir_names[:] = []

        _filter_walk_dirs(
            current,
            dir_names,
            follow_symlinks=follow_symlinks,
            visited_dirs=visited_dirs,
        )

        if not files_only:
            for dir_name in list(dir_names):
                yield current / dir_name

        for file_name in file_names:
            yield current / file_name


def _normalize_external_path(root: Path, path: Path) -> Path:
    if not path.is_absolute() or not root.is_absolute():
        return path
    with _suppress(OSError, ValueError):
        return root / path.relative_to(root.resolve())
    return path


def _should_skip_symlink(path: Path, *, follow_symlinks: bool) -> bool:
    return path.is_symlink() and (not follow_symlinks or not path.exists())


def _within_scan_depth(
    root: Path, path: Path, *, max_depth: int | None, files_only: bool
) -> bool:
    if max_depth is None:
        return True
    if files_only:
        return _depth_from(root, path.parent) < max_depth
    depth_path = path if path.is_dir() else path.parent
    return _depth_from(root, depth_path) <= max_depth


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
