"""Terminal presentation primitives for quip layouts.

Width-aware and ANSI-aware: every measuring or padding function ignores escape
sequences, so padding is computed against what a terminal actually paints.
Colour is always emitted; a caller that wants a plain stream strips it at the
boundary with :func:`strip_ansi`.

East Asian Ambiguous characters (``█``, ``║``, ``◉``) are measured as one cell.
That is the same convention the certificate frame is drawn with.
"""

import os
import re
import sys
import unicodedata

RESET = "\x1b[0m"
BOLD = "\x1b[1m"
BLINK = "\x1b[5m"

FOREGROUND: dict[str, str] = {
    "red": "\x1b[31m",
    "green": "\x1b[32m",
    "yellow": "\x1b[33m",
    "blue": "\x1b[34m",
    "magenta": "\x1b[35m",
    "cyan": "\x1b[36m",
}
RAINBOW = ("red", "yellow", "green", "cyan", "blue", "magenta")

_ANSI = re.compile(r"\x1b\[[0-9;]*m")

DOT_FACE = "(◉)"
PARADE_PER_ROW = 10
PARADE_CAP = 20

GLYPH_WIDTH = 9
GLYPH_ROWS = 6
BLANK_GLYPH: tuple[str, ...] = (" " * GLYPH_WIDTH,) * GLYPH_ROWS

# ANSI Shadow digits. Every row of every glyph is exactly GLYPH_WIDTH chars, so
# digits line up within and across numerals. Keep it that way (tested).
DIGIT_FONT: dict[str, tuple[str, ...]] = {
    "0": (" ██████╗ ", "██╔═████╗", "██║██╔██║", "████╔╝██║", "╚██████╔╝", " ╚═════╝ "),
    "1": (" ██╗     ", "███║     ", "╚██║     ", " ██║     ", " ██║     ", " ╚═╝     "),
    "2": ("██████╗  ", "╚════██╗ ", " █████╔╝ ", "██╔═══╝  ", "███████╗ ", "╚══════╝ "),
    "3": ("██████╗  ", "╚════██╗ ", " █████╔╝ ", " ╚═══██╗ ", "██████╔╝ ", "╚═════╝  "),
    "4": ("██╗  ██╗ ", "██║  ██║ ", "███████║ ", "╚════██║ ", "     ██║ ", "     ╚═╝ "),
    "5": ("███████╗ ", "██╔════╝ ", "███████╗ ", "╚════██║ ", "███████║ ", "╚══════╝ "),
    "6": (" ██████╗ ", "██╔════╝ ", "███████╗ ", "██╔═══██╗", "╚██████╔╝", " ╚═════╝ "),
    "7": ("███████╗ ", "╚════██║ ", "    ██╔╝ ", "   ██╔╝  ", "   ██║   ", "   ╚═╝   "),
    "8": (" █████╗  ", "██╔══██╗ ", "╚█████╔╝ ", "██╔══██╗ ", "╚█████╔╝ ", " ╚════╝  "),
    "9": (" █████╗  ", "██╔══██╗ ", "╚██████╔╝", " ╚═══██║ ", " █████╔╝ ", " ╚════╝  "),
}


def display_len(text: str) -> int:
    """Painted width of ``text`` in terminal cells, ignoring ANSI sequences."""

    length = 0
    for char in _ANSI.sub("", text):
        length += 2 if unicodedata.east_asian_width(char) in ("F", "W") else 1
    return length


def strip_ansi(text: str) -> str:
    return _ANSI.sub("", text)


def pad_right(text: str, width: int) -> str:
    return text + " " * max(width - display_len(text), 0)


def pad_left(text: str, width: int) -> str:
    return " " * max(width - display_len(text), 0) + text


def pad_center(text: str, width: int) -> str:
    padding = max(width - display_len(text), 0)
    left = padding // 2
    return " " * left + text + " " * (padding - left)


def colorize(text: str, color_name: str, *, bold: bool = False) -> str:
    if color_name == "rainbow":
        parts: list[str] = []
        index = 0
        for char in text:
            if char == "█":
                parts.append(FOREGROUND[RAINBOW[index % len(RAINBOW)]] + char)
                index += 1
            else:
                parts.append(char)
        return BOLD + "".join(parts) + RESET
    codes = FOREGROUND.get(color_name, "")
    if color_name == "blink":
        codes = BLINK + FOREGROUND["red"]
    if bold:
        codes = BOLD + codes
    return f"{codes}{text}{RESET}" if codes else text


def digit_art(text: str) -> str:
    """The digits of ``text`` as GLYPH_ROWS rows of block glyphs."""

    glyphs = [DIGIT_FONT.get(char, BLANK_GLYPH) for char in text]
    return "\n".join(
        "  ".join(glyph[row] for glyph in glyphs).rstrip() for row in range(GLYPH_ROWS)
    )


def terminal_supports_color(stream=None) -> bool:
    """Passive colour detection: quietly degrade for pipes and NO_COLOR."""

    stream = stream if stream is not None else sys.stdout
    if os.environ.get("NO_COLOR") is not None:
        return False
    return hasattr(stream, "isatty") and stream.isatty()


def format_size(size_bytes: int) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    size = float(size_bytes)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size_bytes} B"
