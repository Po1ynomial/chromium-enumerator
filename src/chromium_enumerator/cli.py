from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from .platforms import PlatformProfile, current_profile, profile_for_name
from .scanner import ChromiumScanner


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    profile = current_profile() if args.platform == "auto" else profile_for_name(args.platform)
    roots = (
        [Path(root).expanduser() for root in args.roots]
        if args.roots
        else default_roots(profile)
    )
    scanner = ChromiumScanner(
        include_low_confidence=args.include_low_confidence,
        max_depth=args.max_depth,
        follow_symlinks=args.follow_symlinks,
        exhaustive=args.exhaustive,
        registry_only=args.registry_only,
        profile=profile,
    )
    results = scanner.scan(roots)

    if args.json:
        print(
            json.dumps(
                [result.to_dict() for result in results], indent=2, sort_keys=True
            )
        )
    else:
        print(format_text(results, verbose=args.verbose, profile=profile))

    return 0


def default_roots(profile: PlatformProfile | None = None) -> list[Path]:
    active = profile if profile is not None else current_profile()
    return active.default_roots()


def format_text(results, *, verbose: bool = False, profile: PlatformProfile | None = None) -> str:
    active = profile if profile is not None else current_profile()
    if not results:
        return "No probable Chromium runtimes found."

    runtime_word = "runtime" if len(results) == 1 else "runtimes"
    lines = [f"Found {len(results)} probable Chromium {runtime_word}", ""]

    family_counts: dict[str, int] = {}
    for result in results:
        family_counts[result.family] = family_counts.get(result.family, 0) + 1

    lines.append("By family:")
    for family, count in sorted(family_counts.items()):
        lines.append(f"  {family}: {count}")

    lines.extend(["", "Runtimes:"])
    for index, result in enumerate(results, start=1):
        display_name = _display_name(result, active)
        summary = f"{display_name} — {_title_family(result.family)}, {result.confidence} confidence"
        if result.size_bytes:
            summary = f"{summary}, {_format_size(result.size_bytes)}"
        lines.append(f"  {index}. {summary}")
        lines.append(f"     {result.root}")

        if verbose:
            if result.metadata:
                metadata = ", ".join(
                    f"{key}={value}" for key, value in sorted(result.metadata.items())
                )
                lines.append(f"     metadata: {metadata}")
            for registration in result.registered_as:
                registered = ", ".join(
                    f"{key}={value}" for key, value in sorted(registration.items())
                )
                lines.append(f"     registered: {registered}")
            if result.entrypoints:
                lines.append("     entrypoints:")
                lines.extend(f"       - {path}" for path in result.entrypoints)
            lines.append("     evidence:")
            lines.extend(
                f"       - {item.category}: {item.reason} ({item.path})"
                for item in result.evidence
            )
    return "\n".join(lines)


def _display_name(result, profile: PlatformProfile) -> str:
    if result.registered_as:
        name = result.registered_as[0].get("DisplayName")
        if name:
            return name
    return profile.display_name_for(result.root, result.metadata, result.family)


def _title_family(family: str) -> str:
    if family == "qtwebengine":
        return "QtWebEngine"
    return family.capitalize()


def _format_size(size_bytes: int) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    size = float(size_bytes)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size_bytes} B"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chromium-count",
        description="Statically enumerate probable runnable Chromium-family runtime cores.",
    )
    parser.add_argument(
        "roots",
        nargs="*",
        help="Directories to scan. Defaults to common application/install roots for the active platform.",
    )
    parser.add_argument(
        "--platform",
        choices=("auto", "macos", "windows"),
        default="auto",
        help="Detection rules to use. Defaults to the host platform.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit structured JSON instead of human-readable text.",
    )
    parser.add_argument(
        "--include-low-confidence",
        action="store_true",
        help="Include weak evidence clusters that are normally excluded.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show identified files, entrypoints, and metadata in human-readable output.",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=None,
        help="Maximum directory depth to recurse from each root.",
    )
    parser.add_argument(
        "--follow-symlinks",
        action="store_true",
        help="Follow directory symlinks while scanning.",
    )
    parser.add_argument(
        "--exhaustive",
        action="store_true",
        help="Use full Python os.walk traversal instead of default targeted seed search.",
    )
    parser.add_argument(
        "--registry-only",
        action="store_true",
        help="Windows only: only report runtimes whose root matches an installed-program registry record (uninstall, App Paths, or StartMenuInternet).",
    )
    parser.epilog = (
        "Environment overrides for Windows metadata extraction: "
        "CHROMIUM_COUNT_STUB_FILEDESCRIPTION, CHROMIUM_COUNT_STUB_PRODUCTNAME, "
        "CHROMIUM_COUNT_STUB_FILEVERSION."
    )
    return parser
