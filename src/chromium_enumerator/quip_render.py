"""Renderers for quip output: turn a ResolvedQuip into terminal text.

Renderers are pluggable: anything satisfying QuipRenderer can be registered
in RENDERERS and selected with --quip-style. The built-in renderers:

- CertificateRenderer: a mock-official "diagnostic certificate" box.
- BigNumberRenderer: the instance count in huge block ASCII digits.

Both degrade to plain text when color is disabled (non-TTY or --no-color).
"""

from __future__ import annotations

import math
import os
import sys
from typing import Protocol

from .quips import QuipFacts, ResolvedQuip

_CERT_WIDTH = 62
_BAR_WIDTH = 20
_PLAIN_DOT = "(*)"
_BOX_WIDTH = 3 + 62 + 3  # len("║   ") + content + len("   ║")

_RESET = "\x1b[0m"
_BOLD = "\x1b[1m"
_BLINK = "\x1b[5m"
_FG = {
    "red": "\x1b[31m",
    "green": "\x1b[32m",
    "yellow": "\x1b[33m",
    "blue": "\x1b[34m",
    "magenta": "\x1b[35m",
    "cyan": "\x1b[36m",
}
_RAINBOW = ("red", "yellow", "green", "cyan", "blue", "magenta")

# ANSI Shadow digits. Every row of every glyph is exactly _GLYPH_WIDTH chars,
# so digits line up within and across numerals. Keep it that way (tested).
_GLYPH_WIDTH = 9
_DIGIT_FONT: dict[str, tuple[str, ...]] = {
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
_FALLBACK_DIGIT_ROW = (" " * _GLYPH_WIDTH,) * 6


class QuipRenderer(Protocol):
    id: str
    description: str

    def render(
        self, quip: ResolvedQuip, facts: QuipFacts, *, color: bool, lang: str
    ) -> str:
        """Return the full quip block as text (may contain ANSI if color)."""

        ...


class CertificateRenderer:
    id = "certificate"
    description = "Mock-official diagnostic certificate box"

    def render(
        self, quip: ResolvedQuip, facts: QuipFacts, *, color: bool, lang: str
    ) -> str:
        lines: list[str] = []
        dots = facts.dot_faces if facts.dot_faces else _plain_dots(facts)
        if dots:
            for row in _wrap_dots(dots):
                lines.append(f"  {row}")
            if facts.dot_more > 0:
                lines.append(f"  ... {more_line(facts.dot_more, lang)}")
            lines.append("")
        lines.extend(self._certificate(quip, facts, color=color, lang=lang))
        lines.extend(("", quip.texts["headline"] + " " + quip.texts["tagline"]))
        closing = quip.texts.get("closing", "")
        if closing:
            lines.extend(("", closing))
        return "\n".join(lines)

    def _certificate(
        self, quip: ResolvedQuip, facts: QuipFacts, *, color: bool, lang: str
    ) -> list[str]:
        title = (
            "慢 性 浏 览 器 增 生 诊 断 证 书"
            if lang == "zh"
            else "CHROMIUM DIAGNOSTIC CERTIFICATE"
        )
        severity_text = severity_bar(quip.severity, quip.stage, quip.color, color=color)
        fields = (
            (
                field_label("patient", lang),
                "/dev/disk1" if lang == "en" else "本机硬盘",
            ),
            (field_label("count", lang), count_line(quip.count, lang)),
            (field_label("diagnosis", lang), quip.texts["diagnosis"]),
            (field_label("severity", lang), severity_text),
            (field_label("disk", lang), reference_line(facts, lang)),
            (field_label("prognosis", lang), quip.texts["prognosis"]),
            (field_label("certified", lang), certified_line(lang)),
        )
        rows: list[str] = []
        for label, value in fields:
            text = f"{label}{value}"
            rows.append(_box_row(text, _CERT_WIDTH))
        body = [_box_row("", _CERT_WIDTH)] + rows + [_box_row("", _CERT_WIDTH)]
        return [
            _colorize("╔" + "═" * _BOX_WIDTH + "╗", color, "cyan"),
            _colorize(_center_box(title), color, "cyan", bold=True),
            *(_colorize(row, color, "cyan") for row in body),
            _colorize("╚" + "═" * _BOX_WIDTH + "╝", color, "cyan"),
        ]


class BigNumberRenderer:
    id = "bignum"
    description = "Instance count in giant block digits with a subtitle"

    def render(
        self, quip: ResolvedQuip, facts: QuipFacts, *, color: bool, lang: str
    ) -> str:
        digits = _digit_art(str(quip.count))
        label = _units_label(lang)
        pad = "    "
        art_rows = digits.splitlines()
        label_row = len(art_rows) // 2
        lines: list[str] = []
        for index, row in enumerate(art_rows):
            suffix = f"{pad}{label}" if index == label_row else ""
            lines.append(_colorize(row, color, quip.color) + suffix)
        subtitle_parts = [facts.size_human]
        electron_label = (
            f"Electron {facts.electron_count}"
            if lang == "en"
            else f"Electron {facts.electron_count} 个"
        )
        if facts.electron_count:
            subtitle_parts.append(electron_label)
        reference = reference_line(facts, lang)
        if reference != facts.size_human:
            subtitle_parts.append(reference)
        lines.extend(
            (
                "",
                " · ".join(subtitle_parts),
                "",
                quip.texts["headline"] + " " + quip.texts["tagline"],
            )
        )
        closing = quip.texts.get("closing", "")
        if closing:
            lines.extend(("", closing))
        return "\n".join(lines)


RENDERERS: dict[str, QuipRenderer] = {
    renderer.id: renderer for renderer in (CertificateRenderer(), BigNumberRenderer())
}
DEFAULT_RENDERER = CertificateRenderer.id


def terminal_supports_color(stream=None) -> bool:
    """Passive color detection: quietly degrade for pipes and NO_COLOR."""

    stream = stream if stream is not None else sys.stdout
    if os.environ.get("NO_COLOR") is not None:
        return False
    return hasattr(stream, "isatty") and stream.isatty()


def count_line(count: int, lang: str) -> str:
    if lang == "zh":
        return f"{count} 个 Chromium 内核"
    noun = "instance" if count == 1 else "instances"
    return f"{count} {noun}"


def field_label(field: str, lang: str) -> str:
    if lang == "zh":
        return {
            "patient": "患  者：",
            "count": "数  量：",
            "diagnosis": "诊  断：",
            "severity": "严重度：",
            "disk": "磁  盘：",
            "prognosis": "预  后：",
            "certified": "认证人：",
        }[field]
    return {
        "patient": "Patient:      ",
        "count": "Count:        ",
        "diagnosis": "Diagnosis:    ",
        "severity": "Severity:     ",
        "disk": "Disk:         ",
        "prognosis": "Prognosis:    ",
        "certified": "Certified by: ",
    }[field]


def certified_line(lang: str) -> str:
    if lang == "zh":
        return "电子博士，内存消耗学哲学博士"
    return "Dr. Electron, PhD in RAM Consumption"


def reference_line(facts: QuipFacts, lang: str) -> str:
    if lang == "zh":
        if facts.mario_count > 0:
            return f"{facts.size_human} ≈ {facts.mario_count:,} 份《超级马里奥》"
        return facts.size_human
    if facts.doom_count > 0:
        return f"{facts.size_human} ≈ {facts.doom_count:,} copies of Doom (1993)"
    return facts.size_human


def floppy_line(facts: QuipFacts) -> str:
    if facts.floppy_count <= 0:
        return ""
    if facts.floppy_hours > 0:
        return (
            f"≈ {facts.floppy_count:,} 张 1.44MB 软盘"
            f"（用软盘安装约需 {facts.floppy_hours} 小时）"
        )
    return f"≈ {facts.floppy_count:,} 张 1.44MB 软盘"


def more_line(dot_more: int, lang: str) -> str:
    if lang == "zh":
        return f"还有 {dot_more} 个。它们趁你不注意时繁殖。"
    return f"and {dot_more} more. They multiply when you're not looking."


def severity_bar(severity: float, stage: str, color_name: str, *, color: bool) -> str:
    filled = math.ceil(severity * _BAR_WIDTH)
    bar = "█" * filled + "░" * (_BAR_WIDTH - filled)
    text = f"{bar}  {stage}"
    return _colorize(text, color, color_name)


def _digit_art(text: str) -> str:
    glyphs = [_DIGIT_FONT.get(char, _FALLBACK_DIGIT_ROW) for char in text]
    return "\n".join(
        "  ".join(glyph[row] for glyph in glyphs).rstrip() for row in range(6)
    )


def _units_label(lang: str) -> str:
    return "个 Chromium 内核" if lang == "zh" else "Chromium instances"


def _plain_dots(facts: QuipFacts) -> str:
    shown = facts.dot_faces.count("◉") + facts.dot_faces.count("●")
    return " ".join([_PLAIN_DOT] * shown) if shown else ""


def _wrap_dots(dots: str, per_row: int = 10) -> list[str]:
    tokens = dots.split(" ")
    return [
        " ".join(tokens[index : index + per_row])
        for index in range(0, len(tokens), per_row)
    ]


def _center_box(title: str) -> str:
    return "║" + _center_ansi(title, _BOX_WIDTH) + "║"


def _center_ansi(text: str, width: int) -> str:
    pad = width - _display_len(text)
    left = max(pad // 2, 0)
    return " " * left + text + " " * max(pad - left, 0)


def _box_row(text: str, width: int) -> str:
    return f"║   {text}{' ' * max(width - _display_len(text), 0)}   ║"


def _display_len(text: str) -> int:
    length = 0
    index = 0
    while index < len(text):
        if text[index] == "\x1b":
            end = text.find("m", index)
            index = len(text) if end == -1 else end + 1
            continue
        length += 2 if _is_wide(text[index]) else 1
        index += 1
    return length


def _is_wide(char: str) -> bool:
    import unicodedata

    return unicodedata.east_asian_width(char) in ("F", "W")


def _colorize(text: str, color: bool, color_name: str, *, bold: bool = False) -> str:
    if not color:
        return text
    if color_name == "rainbow":
        parts: list[str] = []
        index = 0
        for char in text:
            if char == "█":
                parts.append(_FG[_RAINBOW[index % len(_RAINBOW)]] + char)
                index += 1
            else:
                parts.append(char)
        return _BOLD + "".join(parts) + _RESET
    codes = _FG.get(color_name, "")
    if color_name == "blink":
        codes = _BLINK + _FG["red"]
    if bold:
        codes = _BOLD + codes
    return f"{codes}{text}{_RESET}" if codes else text
