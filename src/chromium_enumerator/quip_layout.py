"""The layouts: two ways to shape a registered text for a terminal.

A layout receives the interpolated values of one text model plus the runtime
facts, and returns the finished block. Layouts own everything that is not copy:
the frame, the severity bar, the dot parade, the unit conversions, the art.
Anything they need beyond the baseline they must declare in ``requires``.
"""

import math

from .quip import Facts, layout, tier_for_count
from .term import (
    DOT_FACE,
    PARADE_CAP,
    PARADE_PER_ROW,
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

_BAR_WIDTH = 20
_DOOM_BYTES = 2_500_636
_MARIO_BYTES = 40_960

_TITLE = {
    "en": "CHROMIUM DIAGNOSTIC CERTIFICATE",
    "zh": "慢 性 浏 览 器 增 生 诊 断 证 书",
}
_LABELS = {
    "en": {
        "count": "Count:        ",
        "diagnosis": "Diagnosis:    ",
        "severity": "Severity:     ",
        "disk": "Disk:         ",
        "prognosis": "Prognosis:    ",
    },
    "zh": {
        "count": "数  量：",
        "diagnosis": "诊  断：",
        "severity": "严重度：",
        "disk": "磁  盘：",
        "prognosis": "预  后：",
    },
}
_SIGNATURE = {
    "en": "Dr. Electron, PhD in RAM Consumption",
    "zh": "电子博士，内存消耗学哲学博士",
}
_UNIT = {"en": "Chromium instances", "zh": "个 Chromium 内核"}
_MORE = {"en": "and {n} more.", "zh": "还有 {n} 个。"}


@layout(
    "certificate",
    requires=frozenset({"diagnosis", "prognosis", "stage", "closing"}),
)
def certificate(values, facts):
    """A framed medical form whose body is the model's essence."""

    tier = tier_for_count(facts.count)
    lang = facts.lang

    rows = [
        _row(""),
        _row(values["essence"]),
        _row(""),
        _row(f"{_label('count', lang)}{_count_line(facts)}"),
        _row(f"{_label('diagnosis', lang)}{values['diagnosis']}"),
        _row(
            f"{_label('severity', lang)}"
            f"{_severity_bar(tier.severity, values['stage'], tier.color)}"
        ),
    ]
    disk = _disk_line(facts)
    if disk:
        rows.append(_row(f"{_label('disk', lang)}{disk}"))
    rows.extend(
        (
            _row(f"{_label('prognosis', lang)}{values['prognosis']}"),
            _row(""),
            _row(pad_left(_SIGNATURE[lang], CERT_INNER)),
        )
    )

    lines = _parade(facts)
    lines.extend(
        (
            colorize("╔" + "═" * _FRAME_INNER + "╗", "cyan"),
            colorize(_center(_TITLE[lang]), "cyan", bold=True),
            colorize("╠" + "═" * _FRAME_INNER + "╣", "cyan"),
            *(colorize(row, "cyan") for row in rows),
            colorize("╚" + "═" * _FRAME_INNER + "╝", "cyan"),
            "",
            "  " + values["closing"],
        )
    )
    return "\n".join(lines)


@layout("bignum")
def bignum(values, facts):
    """The count in block digits, captioned by the model's essence."""

    color = tier_for_count(facts.count).color
    art = digit_art(str(facts.count)).splitlines()
    label_row = len(art) // 2
    lines = [
        colorize(row, color)
        + ("    " + _UNIT[facts.lang] if index == label_row else "")
        for index, row in enumerate(art)
    ]
    lines.extend(("", "  " + values["essence"], "", "  " + values["closing"]))
    return "\n".join(lines)


def _row(text: str) -> str:
    inner = _GUTTER + pad_right(text, CERT_INNER) + _GUTTER
    return f"║{inner}║"


def _center(text: str) -> str:
    return f"║{pad_center(text, _FRAME_INNER)}║"


def _label(field: str, lang: str) -> str:
    return _LABELS[lang][field]


def _parade(facts: Facts) -> list[str]:
    """The dot parade and its remainder, or nothing when there is no count."""

    shown = min(facts.count, PARADE_CAP)
    if shown <= 0:
        return []
    tokens = [DOT_FACE] * shown
    rows = [
        "  " + " ".join(tokens[index : index + PARADE_PER_ROW])
        for index in range(0, shown, PARADE_PER_ROW)
    ]
    if facts.count > shown:
        rows.append("  ... " + _MORE[facts.lang].format(n=facts.count - shown))
    rows.append("")
    return rows


def _count_line(facts: Facts) -> str:
    if facts.lang == "zh":
        return f"{facts.count} 个 Chromium 内核"
    noun = "instance" if facts.count == 1 else "instances"
    return f"{facts.count} {noun}"


def _severity_bar(severity: float, stage: str, color_name: str) -> str:
    filled = math.ceil(min(max(severity, 0.0), 1.0) * _BAR_WIDTH)
    bar = "█" * filled + "░" * (_BAR_WIDTH - filled)
    return colorize(f"{bar}  {stage}", color_name)


def _disk_line(facts: Facts) -> str:
    """Layout-owned unit conversion: how many old games fit in the payload."""

    if facts.size_bytes <= 0:
        return ""
    human = format_size(facts.size_bytes)
    unit_bytes = _MARIO_BYTES if facts.lang == "zh" else _DOOM_BYTES
    copies = facts.size_bytes // unit_bytes
    if copies <= 0:
        return human
    if facts.lang == "zh":
        return f"{human} ≈ {copies:,} 份《超级马里奥》"
    return f"{human} ≈ {copies:,} copies of Doom (1993)"


assert display_len(_TITLE["zh"]) <= _FRAME_INNER
