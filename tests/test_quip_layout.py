"""The layouts: framing, art, decoration, and colour."""

import random

from chromium_enumerator.quip import BASELINE, choose, layout_ids, layouts
from chromium_enumerator.term import (
    BLANK_GLYPH,
    DIGIT_FONT,
    GLYPH_ROWS,
    GLYPH_WIDTH,
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
        for count in (0, 1, 3, 30, 42, 70, 999):
            output, _values, _facts = render("certificate", count, lang=lang)
            widths = {display_len(line) for line in framed_lines(output)}
            assert widths == {70}, f"{lang}/{count} ragged frame: {sorted(widths)}"


def test_certificate_shows_the_expected_fields():
    output, values, _facts = render("certificate", 70, lang="en")
    assert "CHROMIUM DIAGNOSTIC CERTIFICATE" in output
    assert values[BASELINE] in output
    assert "Count:        70 instances" in output
    assert "Stage V" in output
    assert "Doom (1993)" in output
    assert "Dr. Electron" in output


def test_certificate_is_chinese_when_asked():
    output, _values, _facts = render("certificate", 70, lang="zh")
    assert "诊 断 证 书" in output
    assert "个 Chromium 内核" in output
    assert "《超级马里奥》" in output


def test_certificate_omits_the_disk_row_when_there_is_no_payload():
    output, _values, _facts = render("certificate", 0, lang="en", size_bytes=0)
    assert "Disk:" not in output


def test_dot_parade_is_capped_with_a_remainder():
    output, _values, _facts = render("certificate", 70, lang="en")
    assert output.count("◉") == 20
    assert "and 50 more" in strip_ansi(output)


def test_zero_count_has_no_parade():
    output, _values, _facts = render("certificate", 0, lang="en")
    assert "◉" not in output


def test_bignum_renders_digits_units_and_essence():
    output, values, _facts = render("bignum", 42, lang="en")
    assert DIGIT_FONT["4"][0].rstrip() in strip_ansi(output)
    assert "Chromium instances" in output
    assert values[BASELINE] in output


def test_bignum_unit_label_follows_the_language():
    output, _values, _facts = render("bignum", 10, lang="zh")
    assert "个 Chromium 内核" in output


def test_bignum_zero_is_still_rendered():
    output, values, _facts = render("bignum", 0, lang="en")
    assert DIGIT_FONT["0"][0].rstrip() in strip_ansi(output)
    assert values[BASELINE] in output


def test_every_layout_and_language_survives_every_extreme():
    for style in layout_ids():
        for lang in ("en", "zh"):
            for count in (0, 1, 42, 70):
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


def test_digit_font_glyphs_are_uniformly_sized():
    for digit, rows in DIGIT_FONT.items():
        assert len(rows) == GLYPH_ROWS, digit
        assert {len(row) for row in rows} == {GLYPH_WIDTH}, digit
    assert len(BLANK_GLYPH) == GLYPH_ROWS
    assert all(len(row) == GLYPH_WIDTH for row in BLANK_GLYPH)
