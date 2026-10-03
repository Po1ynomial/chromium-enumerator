from __future__ import annotations

import os
import stat
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

# Windows reports directory junctions and other reparse points as ordinary
# directories with this attribute set, not as symlinks.
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


class _ScandirIterator(Protocol):
    """Just enough of ``os.scandir``'s return value for the walk to close it."""

    def __next__(self) -> os.DirEntry[str]: ...

    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class FileInfo:
    """One filesystem entry with the stat data the walk already paid for.

    Profiles consume this instead of calling ``Path.stat()`` again, which is
    what keeps a scan from issuing several syscalls per file.
    """

    path: Path
    is_dir: bool
    is_file: bool
    is_link: bool
    size: int
    mode: int


def is_link(path: Path) -> bool:
    """Whether ``path`` is a symlink, or on Windows a directory junction.

    Junctions are reparse points, and Python reports them as plain
    directories, so ``Path.is_symlink()`` misses them.
    """

    try:
        result = path.lstat()
    except OSError:
        return False
    return stat.S_ISLNK(result.st_mode) or _is_reparse_point(result)


def walk_paths(
    root: Path,
    *,
    max_depth: int | None = None,
    follow_symlinks: bool = False,
    on_error: Callable[[str], None] | None = None,
) -> Iterator[FileInfo]:
    """Yield every entry under ``root``, depth first, at most once each.

    ``max_depth`` counts directory levels below ``root`` (``root`` itself is
    level 0): directories up to that level are entered, so the deepest entry
    yielded lives in a directory at level ``max_depth``. ``root`` is yielded
    first, whether it is a directory or a file.

    Links (symlinks, and on Windows junctions) are skipped unless
    ``follow_symlinks`` is set. Broken links are always skipped silently.
    Directory cycles are never entered twice, which is what makes
    ``follow_symlinks`` safe.
    """

    def report(message: str) -> None:
        if on_error is not None:
            on_error(message)

    root_info = _info_for_path(root, follow_symlinks=follow_symlinks)
    if root_info is None:
        return
    yield root_info
    if not root_info.is_dir:
        return
    if root_info.is_link and not follow_symlinks:
        return

    visited: set[str] = set()
    if follow_symlinks:
        visited.add(_identity(root))
    stack: list[tuple[int, _ScandirIterator]] = []
    try:
        stack.append((0, os.scandir(root)))
    except OSError as error:
        report(f"{root}: {error.strerror}")
        return

    try:
        while stack:
            depth, iterator = stack[-1]
            try:
                entry = next(iterator)
            except StopIteration:
                iterator.close()
                stack.pop()
                continue
            except OSError as error:
                report(f"{error.filename}: {error.strerror}")
                iterator.close()
                stack.pop()
                continue

            info = _info_for_entry(entry, follow_symlinks=follow_symlinks)
            if info is None:
                continue
            if info.is_link and not follow_symlinks:
                continue
            if info.is_dir:
                if max_depth is not None and depth + 1 > max_depth:
                    continue
                if follow_symlinks:
                    # A plain tree cannot cycle, and links are already skipped
                    # when not following, so the guard only matters here.
                    key = _identity(info.path)
                    if key in visited:
                        continue
                    visited.add(key)
                yield info
                try:
                    stack.append((depth + 1, os.scandir(info.path)))
                except OSError as error:
                    report(f"{info.path}: {error.strerror}")
            else:
                yield info
    finally:
        for _depth, iterator in stack:
            iterator.close()


def depth_from(root: Path, path: Path) -> int:
    """Directory depth of ``path`` relative to ``root`` (``root`` is 0)."""

    try:
        return len(path.relative_to(root).parts)
    except ValueError:
        return 0


def within_depth(root: Path, path: Path, max_depth: int | None) -> bool:
    """Whether ``path`` sits inside a directory at most ``max_depth`` below ``root``.

    This is the single depth predicate the whole scanner uses: traversal,
    seed filtering, and the per-start budgets all agree on it.
    """

    if max_depth is None:
        return True
    directory = path if path.is_dir() else path.parent
    return depth_from(root, directory) <= max_depth


def _info_for_path(path: Path, *, follow_symlinks: bool) -> FileInfo | None:
    try:
        is_symlink = path.is_symlink()
        if is_symlink and not follow_symlinks:
            return FileInfo(path, False, False, True, 0, 0)
        result = path.stat() if follow_symlinks else path.lstat()
    except OSError:
        return None
    return _info(path, result, is_symlink=is_symlink)


def _info_for_entry(
    entry: os.DirEntry[str], *, follow_symlinks: bool
) -> FileInfo | None:
    path = Path(entry.path)
    try:
        is_symlink = entry.is_symlink()
    except OSError:
        return None
    if is_symlink and not follow_symlinks:
        return FileInfo(path, False, False, True, 0, 0)
    try:
        result = entry.stat(follow_symlinks=follow_symlinks)
    except OSError:
        return None
    return _info(path, result, is_symlink=is_symlink)


def _info(path: Path, result: os.stat_result, *, is_symlink: bool) -> FileInfo:
    is_file = stat.S_ISREG(result.st_mode)
    return FileInfo(
        path=path,
        is_dir=stat.S_ISDIR(result.st_mode),
        is_file=is_file,
        is_link=is_symlink or _is_reparse_point(result),
        size=result.st_size if is_file else 0,
        mode=result.st_mode,
    )


def _is_reparse_point(result: os.stat_result) -> bool:
    return bool(getattr(result, "st_file_attributes", 0) & _REPARSE_POINT)


def _identity(path: Path) -> str:
    """Stable identity for link cycle detection.

    Inodes are useless here on Windows: ``DirEntry.stat()`` fills its result
    from the directory scan, where ``st_ino`` and ``st_dev`` are zero, so an
    inode-keyed guard would collapse every directory into one. The resolved
    path identifies the same directory through every link that reaches it.
    """

    try:
        return os.path.realpath(path)
    except OSError:
        return str(path)
