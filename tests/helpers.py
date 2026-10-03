"""Shared builders for the test suite.

Lives in an importable module rather than a test file so tests can share it
without relying on pytest's implicit ``sys.path`` insertion.
"""

from pathlib import Path

from chromium_enumerator.model import RuntimeResult

DEFAULT_RUNTIME_BYTES = 200 * 1024 * 1024


def make_result(name: str, size: int, family: str = "electron") -> RuntimeResult:
    """One synthetic runtime result rooted at ``/apps/<name>``."""

    return RuntimeResult(
        root=Path(f"/apps/{name}"), family=family, confidence="high", size_bytes=size
    )


def make_results(count: int, size: int = DEFAULT_RUNTIME_BYTES) -> list[RuntimeResult]:
    """``count`` synthetic Electron results of equal size."""

    return [
        make_result(f"App{index}", size)
        for index in range(count)
    ]
