import os
import subprocess
from pathlib import Path

import pytest

from chromium_enumerator.walk import is_link, walk_paths

needs_symlinks = pytest.mark.skipif(
    os.name != "posix", reason="symlink fixtures need POSIX symlink support"
)
needs_junctions = pytest.mark.skipif(
    os.name != "nt", reason="directory junctions are Windows-only"
)


def make_file(path: Path, content: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def collected(root: Path, **kwargs) -> set[tuple[str, ...]]:
    return {info.path.relative_to(root).parts for info in walk_paths(root, **kwargs)}


def test_walks_every_level_of_a_deep_tree(tmp_path):
    # Regression guard: a directory-identity scheme that keys on the stat data
    # of Windows DirEntry results collapses every directory into one and stops
    # descending after the first level.
    for depth in range(1, 6):
        make_file(
            tmp_path.joinpath(*(f"d{index}" for index in range(depth))) / "leaf.txt"
        )

    seen = collected(tmp_path)

    assert ("d0", "d1", "d2", "d3", "d4", "leaf.txt") in seen
    assert len([entry for entry in seen if entry and entry[-1] == "leaf.txt"]) == 5
    assert len(seen) == 11  # root + 5 directories + 5 files


def test_max_depth_counts_directory_levels(tmp_path):
    make_file(tmp_path / "top.txt")
    make_file(tmp_path / "a" / "mid.txt")
    make_file(tmp_path / "a" / "b" / "deep.txt")

    assert collected(tmp_path, max_depth=0) == {(), ("top.txt",)}
    assert collected(tmp_path, max_depth=1) == {
        (),
        ("top.txt",),
        ("a",),
        ("a", "mid.txt"),
    }
    assert ("a", "b", "deep.txt") in collected(tmp_path, max_depth=2)
    assert ("a", "b", "deep.txt") in collected(tmp_path)


def test_root_file_is_yielded_once(tmp_path):
    target = make_file(tmp_path / "runtime", b"abcd")

    infos = list(walk_paths(target))

    assert [info.path for info in infos] == [target]
    assert infos[0].is_file
    assert infos[0].size == 4


@needs_symlinks
def test_symlinked_directories_are_skipped_without_following(tmp_path):
    target = tmp_path / "outside" / "payload"
    make_file(target / "payload.bin")
    root = tmp_path / "runtime"
    root.mkdir()
    (root / "linked").symlink_to(target, target_is_directory=True)

    assert collected(root) == {()}
    assert collected(root, follow_symlinks=True) == {
        (),
        ("linked",),
        ("linked", "payload.bin"),
    }


@needs_symlinks
def test_following_symlinks_visits_cycles_once(tmp_path):
    runtime = tmp_path / "runtime"
    make_file(runtime / "bin" / "tool")
    (runtime / "loop").symlink_to(runtime, target_is_directory=True)

    single = collected(runtime)
    followed = collected(runtime, follow_symlinks=True)

    assert followed == single
    assert not any("loop" in parts for parts in followed)


@needs_junctions
def test_directory_junctions_are_treated_as_links(tmp_path):
    runtime = tmp_path / "runtime"
    make_file(runtime / "bin" / "tool.exe")
    make_file(runtime / "lib" / "libcef.dll")
    make_file(runtime / "Resources" / "icudtl.dat")
    junction = runtime / "loop"
    created = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(runtime)],
        capture_output=True,
        check=False,
    )
    if created.returncode != 0:
        pytest.skip("could not create a directory junction")

    # Python reports a junction as a plain directory, so it must be treated
    # as a link explicitly: otherwise the walk descends into it forever.
    assert junction.is_symlink() is False
    assert is_link(junction)
    assert collected(runtime) == collected(runtime, follow_symlinks=True)
    assert not any("loop" in parts for parts in collected(runtime))


@needs_symlinks
def test_is_link_distinguishes_links_from_plain_entries(tmp_path):
    make_file(tmp_path / "file.txt")
    (tmp_path / "dir").mkdir()
    (tmp_path / "link").symlink_to(tmp_path / "dir", target_is_directory=True)
    (tmp_path / "broken").symlink_to(tmp_path / "gone")

    assert is_link(tmp_path / "link")
    assert is_link(tmp_path / "broken")
    assert not is_link(tmp_path / "dir")
    assert not is_link(tmp_path / "file.txt")
    assert not is_link(tmp_path / "missing")


@needs_symlinks
def test_broken_symlinks_are_skipped_silently(tmp_path):
    make_file(tmp_path / "real.txt")
    (tmp_path / "dead.txt").symlink_to(tmp_path / "missing.txt")
    (tmp_path / "dead-dir").symlink_to(
        tmp_path / "missing-dir", target_is_directory=True
    )
    warnings: list[str] = []

    seen = collected(tmp_path, follow_symlinks=True, on_error=warnings.append)

    assert seen == {(), ("real.txt",)}
    assert warnings == []
