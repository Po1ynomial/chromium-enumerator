"""The layouts: framing, art, decoration, and colour."""

import random

import pytest

from chromium_enumerator.quip import BASELINE, Facts, choose, layout_ids, layouts
from chromium_enumerator.term import (
    BLANK_GLYPH,
    BOLD,
    DIGIT_FONT,
    DIM,
    FOREGROUND,
    GLYPH_ROWS,
    GLYPH_WIDTH,
    digit_art,
    display_len,
    strip_ansi,
)

SIZE_BYTES = 200 * 1024 * 1024


def render(
    style: str, count: int, lang: str = "en", seed: int = 0, size_bytes=SIZE_BYTES
):
    layout, values, facts = choose(
        count, lang=lang, rng=random.Random(seed), size_bytes=size_bytes, style=style
    )
    return layout.render(values, facts), values, facts


def framed_lines(output: str) -> list[str]:
    return [
        line
        for line in strip_ansi(output).splitlines()
        if line[:1] in ("╔", "╠", "╚", "║")
    ]


def test_certificate_rows_all_have_the_same_display_width():
    for lang in ("en", "zh"):
        for count in (0, 1, 3, 30, 42, 70, 999, 10_000, 1_000_000):
            output, _values, _facts = render("certificate", count, lang=lang)
            widths = {display_len(line) for line in framed_lines(output)}
            assert widths == {70}, f"{lang}/{count} ragged frame: {sorted(widths)}"


def test_certificate_shows_the_expected_fields():
    output, values, _facts = render("certificate", 70, lang="en")
    assert "CHROMIUM DIAGNOSTIC CERTIFICATE" in output
    assert values[BASELINE] in output
    assert "70 Chromium instances" in output
    assert values["diagnosis"] in output
    assert "Stage V" in output
    assert "Doom (1993)" in output
    assert "Dr. Electron" in output


def test_certificate_is_chinese_when_asked():
    output, _values, _facts = render("certificate", 70, lang="zh")
    assert "慢性浏览器增生诊断书" in output
    assert "个 Chromium 内核" in output
    assert "《超级马里奥》" in output


def test_certificate_omits_the_disk_row_when_there_is_no_payload():
    output, _values, _facts = render("certificate", 0, lang="en", size_bytes=0)
    assert "Disk:" not in output


def test_certificate_opens_with_the_frame_without_a_parade():
    output, _values, _facts = render("certificate", 70, lang="en")
    assert strip_ansi(output).startswith("╔")
    assert "◉" not in output


@pytest.mark.parametrize("lang", ("en", "zh"))
def test_certificate_promotes_the_count_above_the_copy(lang):
    output, values, _facts = render("certificate", 42, lang=lang)
    plain = strip_ansi(output)
    headline = "42 个 Chromium 内核" if lang == "zh" else "42 Chromium instances"
    assert (
        plain.index(headline)
        < plain.index(values["diagnosis"])
        < plain.index(values[BASELINE])
    )
    count_line = next(line for line in output.splitlines() if headline in line)
    assert BOLD in count_line
    plain_count_line = strip_ansi(count_line)
    left, right = plain_count_line.split(headline)
    assert abs(display_len(left) - display_len(right)) <= 1
    essence_line = next(
        line for line in output.splitlines() if values[BASELINE] in line
    )
    assert DIM + values[BASELINE] in essence_line
    assert FOREGROUND["cyan"] + values[BASELINE] not in essence_line


@pytest.mark.parametrize("lang", ("en", "zh"))
def test_certificate_separates_disk_usage_from_the_conversion(lang):
    output, _values, _facts = render("certificate", 42, lang=lang)
    lines = strip_ansi(output).splitlines()
    disk_row = next(index for index, line in enumerate(lines) if "200.0 MB" in line)
    assert "≈" not in lines[disk_row]
    assert "≈" in lines[disk_row + 1]
    assert {display_len(line) for line in framed_lines(output)} == {70}


def test_bignum_renders_digits_units_and_essence():
    output, values, _facts = render("bignum", 42, lang="en")
    assert DIGIT_FONT["4"][0].rstrip() in strip_ansi(output)
    assert "Chromium instances" in output
    assert values[BASELINE] in output


def test_bignum_unit_label_follows_the_language():
    output, _values, _facts = render("bignum", 10, lang="zh")
    assert "个 Chromium 内核" in output


@pytest.mark.parametrize("lang", ("en", "zh"))
def test_bignum_shows_disk_usage_below_the_unit(lang):
    output, _values, _facts = render("bignum", 42, lang=lang)
    lines = strip_ansi(output).splitlines()
    label = "个 Chromium 内核" if lang == "zh" else "Chromium instances"
    unit_row = next(index for index, line in enumerate(lines) if label in line)
    assert "200.0 MB" in lines[unit_row + 1]
    caption = "共占用" if lang == "zh" else "200.0 MB"
    assert display_len(lines[unit_row].split(label)[0]) == display_len(
        lines[unit_row + 1].split(caption)[0]
    )


def test_bignum_omits_the_disk_summary_without_payload():
    output, _values, _facts = render("bignum", 0, size_bytes=0)
    assert "on disk" not in output


def test_bignum_uses_a_singular_unit_for_one_instance():
    output, _values, _facts = render("bignum", 1)
    assert "Chromium instance" in output
    assert "Chromium instances" not in output


def test_bignum_aligns_the_art_and_copy_to_one_left_margin():
    output, values, _facts = render("bignum", 42)
    lines = strip_ansi(output).splitlines()
    assert all(line.startswith("  ") for line in lines if line)
    assert lines[0].startswith("  █")
    assert "  " + values[BASELINE] in lines
    assert "  " + values["closing"] in lines


@pytest.mark.parametrize("count", (1000, 10_000, 1_000_000))
@pytest.mark.parametrize("lang", ("en", "zh"))
def test_bignum_long_counts_keep_the_full_font(count, lang):
    """Counts are never rescaled; a wide number may outrun 80 columns."""

    output, _values, _facts = render("bignum", count, lang=lang)
    lines = strip_ansi(output).splitlines()
    art = digit_art(str(count)).splitlines()
    assert lines[0] == "  " + art[0]
    assert lines[GLYPH_ROWS - 1] == "  " + art[-1]


def test_bignum_only_needs_the_baseline_copy():
    item = next(item for item in layouts() if item.id == "bignum")
    output = item.render({BASELINE: "One-off."}, Facts(12, 0, "en"))
    assert "One-off." in output


def test_bignum_zero_is_still_rendered():
    output, values, _facts = render("bignum", 0, lang="en")
    assert DIGIT_FONT["0"][0].rstrip() in strip_ansi(output)
    assert values[BASELINE] in output


def test_every_layout_and_language_survives_every_extreme():
    for style in layout_ids():
        for lang in ("en", "zh"):
            for count in (0, 1, 42, 70, 1000, 1_000_000):
                output, _values, _facts = render(style, count, lang=lang)
                assert output
                assert "{" not in output


def test_stripping_colour_removes_every_escape():
    for style in layouts():
        output, _values, _facts = render(style.id, 70, lang="en")
        assert "\x1b[" in output
        assert "\x1b" not in strip_ansi(output)


def test_rainbow_tier_still_measures_correctly():
    output, _values, _facts = render("certificate", 70, lang="en")
    assert "\x1b[3" in output
    assert {display_len(line) for line in framed_lines(output)} == {70}


@pytest.mark.parametrize("style", ("certificate", "bignum"))
def test_intervention_tier_does_not_blink(style):
    output, _values, _facts = render(style, 50)
    assert "\x1b[5m" not in output
    assert FOREGROUND["red"] in output


def test_plain_output_keeps_the_same_layout():
    from chromium_enumerator.cli import format_quip

    for style in layout_ids():
        output, _values, _facts = render(style, 42, lang="zh")
        plain = format_quip(
            42, lang="zh", size_bytes=SIZE_BYTES, seed=0, style=style, color=False
        )
        assert plain == strip_ansi(output)


def test_digit_font_glyphs_are_uniformly_sized():
    for digit, rows in DIGIT_FONT.items():
        assert len(rows) == GLYPH_ROWS, digit
        assert {len(row) for row in rows} == {GLYPH_WIDTH}, digit
    assert len(BLANK_GLYPH) == GLYPH_ROWS
    assert all(len(row) == GLYPH_WIDTH for row in BLANK_GLYPH)
