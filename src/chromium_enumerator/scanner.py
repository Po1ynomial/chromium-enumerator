import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Iterable, Iterator
from contextlib import suppress as _suppress
from dataclasses import dataclass, field
from pathlib import Path

from .model import Confidence, Evidence, RuntimeResult
from .platforms import PlatformProfile, current_profile, infer_family
from .registry import casefold_path
from .walk import FileInfo, depth_from, is_link, walk_paths, within_depth

_EXCEPTIONALLY_SMALL_RUNTIME_BYTES = 5 * 1024 * 1024


@dataclass
class _RuntimeBucket:
    """Everything accumulated for one runtime root during a single walk."""

    evidence: list[Evidence] = field(default_factory=list)
    entrypoints: set[Path] = field(default_factory=set)
    size_bytes: int = 0


class ChromiumScanner:
    def __init__(
        self,
        *,
        include_low_confidence: bool = False,
        max_depth: int | None = None,
        follow_symlinks: bool = False,
        exhaustive: bool = False,
        registry_only: bool = False,
        profile: PlatformProfile | None = None,
    ) -> None:
        self.include_low_confidence = include_low_confidence
        self.max_depth = max_depth
        self.follow_symlinks = follow_symlinks
        self.exhaustive = exhaustive
        self.registry_only = registry_only
        self.profile = profile if profile is not None else current_profile()
        self.warnings: list[str] = []

    def scan(self, roots: Iterable[Path | str]) -> list[RuntimeResult]:
        self.warnings.clear()
        registry_index = self._registry_seed_index()
        buckets: dict[Path, _RuntimeBucket] = {}
        claimed_starts: list[Path] = []

        for root_value in roots:
            root = Path(root_value).expanduser()
            if is_link(root) and not root.exists():
                continue
            if not root.exists():
                self.warnings.append(f"missing root: {root}")
                continue
            if is_link(root) and not self.follow_symlinks:
                self.warnings.append(f"skipped symlink root: {root}")
                continue

            for start, base_depth in self._walk_starts(root, registry_index):
                # Overlapping starts would otherwise be walked twice and have
                # their bytes counted twice.
                if _is_covered(
                    start, claimed_starts, self.profile.case_insensitive_names
                ):
                    continue
                claimed_starts.append(start)
                self._collect(buckets, start, base_depth=base_depth)

        results = [
            self._build_result(root, bucket)
            for root, bucket in self._fold_weak_buckets(buckets).items()
            if bucket.evidence
        ]
        self._apply_registry_metadata(results, registry_index)
        filtered = [
            result
            for result in results
            if self.include_low_confidence or result.confidence != "low"
        ]
        return sorted(filtered, key=lambda result: str(result.root))

    def _walk_starts(
        self, root: Path, registry_index: dict[str, tuple[Path, dict[str, str]]]
    ) -> Iterator[tuple[Path, int]]:
        """Where to start walking, with each start's depth below `root`.

        In exhaustive mode that is the root itself. Otherwise it is the set of
        runtime roots implied by the seed search, narrowed by
        ``--registry-only``.
        """

        if self.exhaustive:
            yield root, 0
            return

        for candidate in self._candidate_roots(root):
            if self.registry_only and not self._has_registry_ancestor(
                candidate, registry_index
            ):
                continue
            yield candidate, depth_from(root, candidate)

    def _candidate_roots(self, root: Path) -> list[Path]:
        candidates: set[Path] = set()
        if self.profile.classify_path(root) is not None:
            candidates.add(self.profile.runtime_root_for(root))
        for path in _iter_seed_paths(
            root,
            profile=self.profile,
            max_depth=self.max_depth,
            follow_symlinks=self.follow_symlinks,
            on_error=self.warnings.append,
        ):
            if self.profile.classify_path(path) is None:
                continue
            candidates.add(self.profile.runtime_root_for(path))
        return _dedupe_nested_roots(
            candidates, case_insensitive=self.profile.case_insensitive_names
        )

    def _collect(
        self,
        buckets: dict[Path, _RuntimeBucket],
        start: Path,
        *,
        base_depth: int,
    ) -> None:
        """Walk one start once, sorting evidence, entrypoints, and size by root.

        A result root owns exactly the files whose nearest runtime root is that
        root, which is why a nested runtime is reported separately instead of
        being double-counted in its parent.
        """

        max_depth = (
            None if self.max_depth is None else max(self.max_depth - base_depth, 0)
        )
        for info in walk_paths(
            start,
            max_depth=max_depth,
            follow_symlinks=self.follow_symlinks,
            on_error=self.warnings.append,
        ):
            if info.is_dir:
                evidence = self.profile.classify_path(info.path, info=info)
                if evidence is not None:
                    bucket = self._bucket_for(buckets, info.path, info)
                    bucket.evidence.append(evidence)
                continue
            if not info.is_file:
                continue

            bucket = self._bucket_for(buckets, info.path, info)
            bucket.size_bytes += info.size
            evidence = self.profile.classify_path(info.path, info=info)
            if evidence is not None:
                bucket.evidence.append(evidence)
            if info.path.suffix.lower() in self.profile.library_suffixes:
                continue
            if self.profile.is_executable(info.path, info=info):
                bucket.entrypoints.add(info.path)

    def _bucket_for(
        self,
        buckets: dict[Path, _RuntimeBucket],
        path: Path,
        info: FileInfo,
    ) -> _RuntimeBucket:
        root = self.profile.runtime_root_for(path, info=info)
        return buckets.setdefault(root, _RuntimeBucket())

    def _fold_weak_buckets(
        self, buckets: dict[Path, _RuntimeBucket]
    ) -> dict[Path, _RuntimeBucket]:
        """Give a runtime the parts of its subtree that are not runtimes themselves.

        A walk attributes every path to its nearest runtime root, which splits
        a real install whenever its payload is spread out: the launcher in
        ``bin/``, ``libcef.dll`` in ``lib/``, resources in ``Resources/``.
        None of those alone scores as a runtime. A bucket that scores ``low``
        therefore merges into the nearest ancestor that is also a bucket, and
        the merge repeats until nothing more can move, so the pieces rejoin at
        the directory that holds them.

        A strong bucket is never merged upward, which is what keeps a nested
        runtime out of its parent's size. A weak bucket with no ancestor bucket
        stays put, so isolated evidence still shows up under
        ``--include-low-confidence``.
        """

        case_insensitive = self.profile.case_insensitive_names
        active = dict(buckets)
        indexes = {_bucket_key(root, case_insensitive): root for root in active}
        ordered = sorted(active, key=lambda path: len(path.parts), reverse=True)

        progress = True
        while progress:
            progress = False
            for root in ordered:
                if root not in active:
                    continue
                bucket = active[root]
                if not _is_weak(bucket):
                    continue
                parent = _nearest_bucket_ancestor(root, indexes, case_insensitive)
                if parent is None:
                    continue
                target = active[parent]
                target.evidence.extend(bucket.evidence)
                target.entrypoints |= bucket.entrypoints
                target.size_bytes += bucket.size_bytes
                del active[root]
                del indexes[_bucket_key(root, case_insensitive)]
                progress = True
        return active

    def _build_result(self, root: Path, bucket: _RuntimeBucket) -> RuntimeResult:
        evidence = _dedupe_evidence(bucket.evidence)
        entrypoints = sorted(bucket.entrypoints, key=str)
        confidence = _cap_confidence_for_size(
            _score_confidence(evidence, entrypoints),
            bucket.size_bytes,
            max_depth=self.max_depth,
            follow_symlinks=self.follow_symlinks,
        )
        return RuntimeResult(
            root=root,
            family=infer_family(evidence),
            confidence=confidence,
            evidence=sorted(evidence, key=lambda item: (item.category, str(item.path))),
            entrypoints=entrypoints,
            metadata=self.profile.read_metadata(root),
            size_bytes=bucket.size_bytes,
        )

    def _registry_seed_index(self) -> dict[str, tuple[Path, dict[str, str]]]:
        """Casefolded registry install paths -> (path, metadata), Windows only."""
        registry_roots = getattr(self.profile, "registry_roots", None)
        if registry_roots is None:
            return {}
        try:
            records = registry_roots()
        except OSError:
            return {}
        return {
            casefold_path(path): (path, metadata) for path, metadata in records.items()
        }

    def _registry_records_for(
        self,
        root: Path,
        index: dict[str, tuple[Path, dict[str, str]]],
    ) -> list[dict[str, str]]:
        """Registry records at or above `root` (shortest match first)."""
        if not index:
            return []
        root_key = casefold_path(root)
        matches = []
        for record_key, (_path, metadata) in index.items():
            if root_key == record_key or root_key.startswith(record_key + os.sep):
                matches.append((len(record_key), metadata))
        matches.sort(key=lambda item: item[0])
        return [metadata for _length, metadata in matches]

    def _has_registry_ancestor(
        self,
        root: Path,
        index: dict[str, tuple[Path, dict[str, str]]],
    ) -> bool:
        return bool(self._registry_records_for(root, index))

    def _apply_registry_metadata(
        self,
        results: list[RuntimeResult],
        index: dict[str, tuple[Path, dict[str, str]]],
    ) -> None:
        if not index:
            return
        for result in results:
            for metadata in self._registry_records_for(result.root, index):
                entry = {
                    key: value
                    for key, value in metadata.items()
                    if key in {"DisplayName", "DisplayVersion", "Publisher", "source"}
                }
                if entry:
                    result.registered_as.append(entry)


def _score_confidence(evidence: list[Evidence], entrypoints: list[Path]) -> Confidence:
    categories = {item.category for item in evidence}
    marker_names = {
        item.path.name for item in evidence if item.category == "electron-marker"
    }

    has_executable = "executable" in categories or bool(entrypoints)
    has_named_engine = "engine" in categories
    # Electron on Windows ships no single identifiable engine file, so two
    # distinct marker DLLs stand in for one.
    has_marker_engine = len(marker_names) >= 2
    has_engine = has_named_engine or has_marker_engine
    has_resource = "resource" in categories
    has_helper = "helper" in categories

    if has_executable and has_engine and (has_resource or has_helper):
        return "high"

    # A lone marker still counts as one secondary signal.
    secondary_signals = sum(
        (has_named_engine or bool(marker_names), has_resource, has_helper)
    )
    if has_executable and secondary_signals >= 2:
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


def _iter_seed_paths(
    root: Path,
    *,
    profile: PlatformProfile,
    max_depth: int | None,
    follow_symlinks: bool,
    on_error: Callable[[str], None],
) -> Iterator[Path]:
    command = _fd_seed_command(
        root, profile=profile, max_depth=max_depth, follow_symlinks=follow_symlinks
    ) or _find_seed_command(
        root, profile=profile, max_depth=max_depth, follow_symlinks=follow_symlinks
    )

    if command is not None:
        for path in _iter_command_paths(command, on_error):
            path = _normalize_external_path(root, path)
            if path == root:
                continue
            if _should_skip_symlink(path, follow_symlinks=follow_symlinks):
                continue
            if not within_depth(root, path, max_depth):
                continue
            yield path
        return

    # No native tool: the same walker used everywhere else, so depth and
    # symlink rules cannot drift between discovery and verification.
    for info in walk_paths(
        root,
        max_depth=max_depth,
        follow_symlinks=follow_symlinks,
        on_error=on_error,
    ):
        if info.path == root:
            continue
        yield info.path


def _fd_seed_command(
    root: Path,
    *,
    profile: PlatformProfile,
    max_depth: int | None,
    follow_symlinks: bool,
) -> list[str] | None:
    executable = shutil.which("fd") or shutil.which("fdfind")
    if executable is None or follow_symlinks:
        return None

    command = [executable, "-u", "--absolute-path", "-0"]
    if max_depth is not None:
        command.extend(["--max-depth", str(max_depth + 1)])
    regex = "^(" + profile.seed_fd_names_regex + ")$"
    if profile.case_insensitive_names:
        regex = "(?i)" + regex
    command.extend([regex, str(root)])
    return command


def _find_seed_command(
    root: Path,
    *,
    profile: PlatformProfile,
    max_depth: int | None,
    follow_symlinks: bool,
) -> list[str] | None:
    if not profile.find_seed_command_supported:
        # Windows ships an unrelated legacy find.exe (a grep); never invoke it.
        return None

    executable = shutil.which("find")
    if executable is None:
        return None

    command = [executable, "-L" if follow_symlinks else "-P", str(root)]
    if max_depth is not None:
        command.extend(["-maxdepth", str(max_depth + 1)])
    command.append("(")
    names = list(profile.seed_exact_names) + list(profile.seed_extra_globs)
    for index, name in enumerate(names):
        if index:
            command.append("-o")
        command.extend(["-name", name])
    command.extend([")", "-print0"])
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


def _normalize_external_path(root: Path, path: Path) -> Path:
    if not path.is_absolute() or not root.is_absolute():
        return path
    with _suppress(OSError, ValueError):
        return root / path.relative_to(root.resolve())
    return path


def _should_skip_symlink(path: Path, *, follow_symlinks: bool) -> bool:
    return is_link(path) and (not follow_symlinks or not path.exists())


def _dedupe_nested_roots(roots: set[Path], *, case_insensitive: bool) -> list[Path]:
    ordered = sorted(roots, key=lambda path: (len(path.parts), str(path)))
    kept: list[Path] = []
    for candidate in ordered:
        if _is_covered(candidate, kept, case_insensitive):
            continue
        kept.append(candidate)
    return kept


def _is_covered(path: Path, parents: Iterable[Path], case_insensitive: bool) -> bool:
    for parent in parents:
        if path == parent:
            return True
        target, base = str(path), str(parent)
        if case_insensitive:
            target, base = target.lower(), base.lower()
        if target.startswith(base + os.sep):
            return True
    return False


def _is_weak(bucket: _RuntimeBucket) -> bool:
    evidence = _dedupe_evidence(bucket.evidence)
    entrypoints = sorted(bucket.entrypoints, key=str)
    return _score_confidence(evidence, entrypoints) == "low"


def _bucket_key(path: Path, case_insensitive: bool) -> str:
    text = str(path)
    return text.lower() if case_insensitive else text


def _nearest_bucket_ancestor(
    path: Path, indexes: dict[str, Path], case_insensitive: bool
) -> Path | None:
    for parent in path.parents:
        found = indexes.get(_bucket_key(parent, case_insensitive))
        if found is not None:
            return found
    return None


def _dedupe_evidence(evidence: list[Evidence]) -> list[Evidence]:
    seen: set[tuple[str, Path, str]] = set()
    deduped: list[Evidence] = []
    for item in evidence:
        key = (item.category, item.path, item.reason)
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped
