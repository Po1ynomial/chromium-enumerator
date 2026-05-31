from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from .scanner import ChromiumScanner

_DEFAULT_ROOTS = ("/Applications", "~/Applications", "/opt/homebrew", "/usr/local")


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    roots = [Path(root).expanduser() for root in args.roots] if args.roots else default_roots()
    scanner = ChromiumScanner(
        include_low_confidence=args.include_low_confidence,
        max_depth=args.max_depth,
        follow_symlinks=args.follow_symlinks,
    )
    results = scanner.scan(roots)

    if args.json:
        print(json.dumps([result.to_dict() for result in results], indent=2, sort_keys=True))
    else:
        print(format_text(results))

    return 0


def default_roots() -> list[Path]:
    return [Path(root).expanduser() for root in _DEFAULT_ROOTS if Path(root).expanduser().exists()]


def format_text(results) -> str:  # noqa: ANN001 - accepts RuntimeResult-like values for simple tests and reuse.
    if not results:
        return "No probable Chromium runtimes found."

    blocks: list[str] = []
    for result in results:
        lines = [
            str(result.root),
            f"  family: {result.family}",
            f"  confidence: {result.confidence}",
            f"  size_bytes: {result.size_bytes}",
        ]
        if result.metadata:
            metadata = ", ".join(f"{key}={value}" for key, value in sorted(result.metadata.items()))
            lines.append(f"  metadata: {metadata}")
        if result.entrypoints:
            lines.append("  entrypoints:")
            lines.extend(f"    - {path}" for path in result.entrypoints)
        lines.append("  evidence:")
        lines.extend(f"    - {item.category}: {item.reason} ({item.path})" for item in result.evidence)
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chrome-enumerator",
        description="Statically enumerate probable runnable Chromium-family runtime cores on macOS.",
    )
    parser.add_argument("roots", nargs="*", help="Directories to scan. Defaults to common macOS application/install roots.")
    parser.add_argument("--json", action="store_true", help="Emit structured JSON instead of human-readable text.")
    parser.add_argument(
        "--include-low-confidence",
        action="store_true",
        help="Include weak evidence clusters that are normally excluded.",
    )
    parser.add_argument("--max-depth", type=int, default=None, help="Maximum directory depth to recurse from each root.")
    parser.add_argument("--follow-symlinks", action="store_true", help="Follow directory symlinks while scanning.")
    return parser
