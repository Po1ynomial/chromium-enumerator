import argparse
import json
import os
import random
import sys
from collections.abc import Mapping, Sequence
from contextlib import suppress as _suppress
from pathlib import Path

from .model import RuntimeResult
from .platforms import PlatformProfile, current_profile, profile_for_name
from .quip import choose, exit_code_for, layout_ids
from .scanner import ChromiumScanner
from .term import format_size, strip_ansi, terminal_supports_color


def main(argv: Sequence[str] | None = None) -> int:
    _configure_stdout()
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.quip and args.json:
        parser.error("--quip and --json are mutually exclusive: jokes are for humans.")
    if args.quip_count is not None and not args.quip:
        parser.error(
            "--quip-count only makes sense with --quip: fake Chromium is still Chromium."
        )
    if args.quip_count is not None and args.verbose:
        parser.error(
            "--quip-count skips scanning, so there is no listing for --verbose to show."
        )
    if args.quip_count is not None and args.quip_count < 0:
        parser.error(
            "--quip-count must be zero or more. Negative Chromium is a different diagnosis."
        )

    profile = (
        current_profile()
        if args.platform == "auto"
        else profile_for_name(args.platform)
    )
    if args.registry_only and args.exhaustive:
        parser.error(
            "--registry-only cannot be combined with --exhaustive: an exhaustive scan "
            "builds no seed list to filter."
        )
    if args.registry_only and profile.name != "windows":
        parser.error(
            "--registry-only needs a Windows registry: pass --platform windows."
        )

    if args.quip_count is not None:
        results: list[RuntimeResult] = []
        instance_count = args.quip_count
        instance_bytes: int | None = None
    else:
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
        instance_count = len(results)
        instance_bytes = sum(result.size_bytes for result in results)

    if args.json:
        print(
            json.dumps(
                [result.to_dict() for result in results], indent=2, sort_keys=True
            )
        )
        return 0

    if args.quip:
        sections = []
        if args.verbose:
            sections.append(format_text(results, verbose=True, profile=profile))
        sections.append(
            format_quip(
                instance_count,
                lang=resolve_lang(args.lang),
                size_bytes=instance_bytes,
                seed=args.quip_seed,
                style=args.quip_style,
                color=terminal_supports_color() and not args.no_color,
                explicit_no_color=args.no_color,
            )
        )
        print("\n\n".join(sections))
        return exit_code_for(instance_count)

    print(format_text(results, verbose=args.verbose, profile=profile))
    return 0


def _configure_stdout() -> None:
    """Stop an unencodable glyph from killing a report.

    A non-UTF-8 console (a GBK code page, say) cannot encode the certificate
    renderer's dot glyph, and CPython's default strict error handler turns
    that into a traceback. Replacing the character is better than losing the
    whole report.
    """

    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is None:
        return
    with _suppress(OSError, ValueError):
        reconfigure(errors="replace")


def default_roots(profile: PlatformProfile | None = None) -> list[Path]:
    active = profile if profile is not None else current_profile()
    return active.default_roots()


def format_text(
    results: Sequence[RuntimeResult],
    *,
    verbose: bool = False,
    profile: PlatformProfile | None = None,
) -> str:
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
            summary = f"{summary}, {format_size(result.size_bytes)}"
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


def format_quip(
    count: int,
    *,
    lang: str,
    size_bytes: int | None = None,
    seed: int | None = None,
    style: str = "auto",
    color: bool = True,
    explicit_no_color: bool = False,
) -> str:
    """Render the playful report for a count of Chromium runtimes.

    The layout pick and the fabricated-size jitter both draw from the same
    seeded RNG, so a fixed --quip-seed reproduces the whole output.
    """

    rng = random.Random(seed)
    chosen, values, facts = choose(
        count,
        lang=lang,
        rng=rng,
        size_bytes=size_bytes,
        style=None if style == "auto" else style,
    )
    body = chosen.render(values, facts)
    if not color:
        body = strip_ansi(body)
    if explicit_no_color:
        jab = (
            "检测到 --no-color。懦夫。"
            if lang == "zh"
            else "--no-color detected. Coward."
        )
        return f"{jab}\n\n{body}"
    return body


def resolve_lang(requested: str, environ: Mapping[str, str] | None = None) -> str:
    """Resolve --lang auto from the environment; zh* locales get Chinese copy."""

    if requested in ("zh", "en"):
        return requested
    source: Mapping[str, str] = os.environ if environ is None else environ
    for variable in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = source.get(variable, "")
        if value:
            return "zh" if value.lower().startswith("zh") else "en"
    return "en"


def _display_name(result: RuntimeResult, profile: PlatformProfile) -> str:
    if result.registered_as:
        name = result.registered_as[0].get("DisplayName")
        if name:
            return name
    return profile.display_name_for(result.root, result.metadata, result.family)


def _title_family(family: str) -> str:
    if family == "qtwebengine":
        return "QtWebEngine"
    return family.capitalize()


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
        help="Walk every path with the project's scandir walker instead of the default targeted seed search.",
    )
    parser.add_argument(
        "--registry-only",
        action="store_true",
        help="Windows only: only report runtimes whose root matches an installed-program registry record (uninstall, App Paths, or StartMenuInternet). Requires --platform windows and is rejected with --exhaustive.",
    )
    parser.add_argument(
        "--quip",
        action="store_true",
        help="Replace the report with a playful summary of your Chromium situation. Combine with --verbose to keep the listing (quip prints last). Mutually exclusive with --json. Exit code becomes the instance count (capped at 255).",
    )
    parser.add_argument(
        "--lang",
        choices=("auto", "zh", "en"),
        default="auto",
        help="Quip language. Defaults to the locale, falling back to English.",
    )
    parser.add_argument(
        "--quip-seed",
        type=int,
        default=None,
        help="Fix the quip RNG seed for reproducible jokes.",
    )
    parser.add_argument(
        "--quip-style",
        choices=("auto", *layout_ids()),
        default="auto",
        help="Quip presentation style. Defaults to a seeded random pick per run.",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI colors in quip output. NO_COLOR is also respected, silently.",
    )
    parser.add_argument(
        "--quip-count",
        type=int,
        default=None,
        metavar="N",
        help="Preview quip mode for a machine with N Chromium instances. Skips scanning entirely; the payload size is estimated.",
    )
    parser.epilog = (
        "Environment overrides for Windows metadata extraction: "
        "CHROMIUM_COUNT_STUB_FILEDESCRIPTION, CHROMIUM_COUNT_STUB_PRODUCTNAME, "
        "CHROMIUM_COUNT_STUB_FILEVERSION."
    )
    return parser
