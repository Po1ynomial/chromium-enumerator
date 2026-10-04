"""Two terminal presentations for registered quip copy.

Layouts own the frame, typography, severity bar and unit conversions. Copy
requirements are declared separately from the runtime facts they display.
"""

import math

from .quip import Facts, layout, tier_for_count
from .term import (
    colorize,
    digit_art,
    display_len,
    format_size,
    pad_center,
    pad_left,
    pad_right,
)

CERT_INNER = 62
_GUTTER = "   "
_FRAME_INNER = CERT_INNER + 2 * len(_GUTTER)
_INDENT = "  "

_BAR_WIDTH = 20
_DOOM_BYTES = 2_500_636
_MARIO_BYTES = 40_960

_TITLE = {
    "en": "CHROMIUM DIAGNOSTIC CERTIFICATE",
    "zh": "慢性浏览器增生诊断书",
}
_LABELS = {
    "en": {
        "severity": "Severity:   ",
        "disk": "Disk:       ",
        "prognosis": "Prognosis:  ",
    },
    "zh": {
        "severity": "严重度：",
        "disk": "磁  盘：",
        "prognosis": "预  后：",
    },
}
_SIGNATURE = {
    "en": "Dr. Electron, PhD in RAM Consumption",
    "zh": "电子博士，内存消耗学哲学博士",
}


@layout(
    "certificate",
    requires=frozenset({"diagnosis", "prognosis", "stage", "closing"}),
)
def certificate(values, facts):
    """A restrained medical form, with the count above the diagnosis."""

    tier = tier_for_count(facts.count)
    # Only the severity bar goes rainbow; the headline stays legible.
    headline_color = "red" if tier.color == "rainbow" else tier.color
    rows = [
        _row(""),
        _row(
            pad_center(
                colorize(_count_line(facts), headline_color, bold=True), CERT_INNER
            )
        ),
        _row(pad_center(values["diagnosis"], CERT_INNER)),
        _row(""),
        _row(colorize(values["essence"], dim=True)),
        _row(""),
        _field(
            "severity",
            _severity_bar(tier.severity, values["stage"], tier.color),
            facts.lang,
        ),
    ]
    if facts.size_bytes > 0:
        rows.append(_field("disk", format_size(facts.size_bytes), facts.lang))
        conversion = _disk_conversion(facts)
        if conversion:
            inset = " " * display_len(_LABELS[facts.lang]["disk"])
            rows.append(_row(inset + colorize(conversion, dim=True)))
    rows.extend(
        (
            _field("prognosis", values["prognosis"], facts.lang),
            _row(""),
            _row(colorize(pad_left(_SIGNATURE[facts.lang], CERT_INNER), dim=True)),
        )
    )
    return "\n".join(
        (
            _border("╔" + "═" * _FRAME_INNER + "╗"),
            _center(colorize(_TITLE[facts.lang], bold=True)),
            _border("╠" + "═" * _FRAME_INNER + "╣"),
            *rows,
            _border("╚" + "═" * _FRAME_INNER + "╝"),
            "",
            _INDENT + values["closing"],
        )
    )


@layout("bignum")
def bignum(values, facts):
    """A numeric poster with units and disk usage beside the block digits."""

    color = tier_for_count(facts.count).color
    art = digit_art(str(facts.count)).splitlines()
    width = max(display_len(row) for row in art)
    label_row = len(art) // 2
    unit = (
        "个 Chromium 内核"
        if facts.lang == "zh"
        else ("Chromium instance" if facts.count == 1 else "Chromium instances")
    )
    disk = ""
    if facts.size_bytes > 0:
        human = format_size(facts.size_bytes)
        disk = f"共占用 {human}" if facts.lang == "zh" else f"{human} on disk"
    lines = []
    for index, row in enumerate(art):
        line = _INDENT + colorize(row, color)
        caption = ""
        if index == label_row:
            caption = colorize(unit, bold=True)
        elif index == label_row + 1 and disk:
            caption = colorize(disk, dim=True)
        if caption:
            line += " " * (width - display_len(row) + 3) + caption
        lines.append(line)
    lines.extend(("", _INDENT + values["essence"]))
    closing = values.get("closing")
    if closing:
        lines.extend(("", _INDENT + colorize(closing, dim=True)))
    return "\n".join(lines)


def _border(text: str) -> str:
    return colorize(text, "cyan", dim=True)


def _row(text: str) -> str:
    inner = _GUTTER + pad_right(text, CERT_INNER) + _GUTTER
    return _border("║") + inner + _border("║")


def _center(text: str) -> str:
    return _border("║") + pad_center(text, _FRAME_INNER) + _border("║")


def _field(field: str, value: str, lang: str) -> str:
    return _row(colorize(_LABELS[lang][field], dim=True) + value)


def _count_line(facts: Facts) -> str:
    if facts.lang == "zh":
        return f"{facts.count} 个 Chromium 内核"
    noun = "instance" if facts.count == 1 else "instances"
    return f"{facts.count} Chromium {noun}"


def _severity_bar(severity: float, stage: str, color_name: str) -> str:
    filled = math.ceil(min(max(severity, 0.0), 1.0) * _BAR_WIDTH)
    bar = colorize("█" * filled, color_name) + colorize(
        "░" * (_BAR_WIDTH - filled), dim=True
    )
    return f"{bar}  {stage}"


def _disk_conversion(facts: Facts) -> str:
    """A secondary annotation, separate from the real byte total."""

    unit_bytes = _MARIO_BYTES if facts.lang == "zh" else _DOOM_BYTES
    copies = facts.size_bytes // unit_bytes
    if copies <= 0:
        return ""
    if facts.lang == "zh":
        return f"≈ {copies:,} 份《超级马里奥》"
    return f"≈ {copies:,} copies of Doom (1993)"


assert display_len(_TITLE["zh"]) <= _FRAME_INNER
