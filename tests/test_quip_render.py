import random

from chromium_enumerator.quip_render import (
    _DIGIT_FONT,
    _FALLBACK_DIGIT_ROW,
    _GLYPH_WIDTH,
    RENDERERS,
    _display_len,
    reference_line,
)
from chromium_enumerator.quips import build_facts, pick_quip
from tests.helpers import make_results


def render(style: str, count: int, lang: str = "en", seed: int = 0, color: bool = False):
    facts = build_facts(make_results(count))
    quip = pick_quip(facts, lang, random.Random(seed))
    return RENDERERS[style].render(quip, facts, color=color, lang=lang), quip


def test_certificate_box_borders_align_for_ascii_content():
    output, _ = render("certificate", 70, lang="en")
    lines = output.splitlines()
    top = next(line for line in lines if line.startswith("╔"))
    bottom = next(line for line in lines if line.startswith("╚"))
    assert _display_len(top) == _display_len(bottom)
    for line in lines:
        if line.startswith("║"):
            assert _display_len(line) == _display_len(top)
            assert line.rstrip().endswith("║")


def test_certificate_box_borders_align_for_chinese_content():
    output, _ = render("certificate", 70, lang="zh")
    lines = output.splitlines()
    top = next(line for line in lines if line.startswith("╔"))
    assert _display_len(top) == 70
    for line in lines:
        if line.startswith("║"):
            assert _display_len(line) == _display_len(top)


def test_certificate_contains_core_fields():
    output, _ = render("certificate", 70, lang="en")
    assert "CHROMIUM DIAGNOSTIC CERTIFICATE" in output
    assert "70 instances" in output
    assert "Chronic Chromium Proliferation" in output
    assert "Stage V" in output
    assert "Doom (1993)" in output
    assert "Dr. Electron" in output


def test_dot_parade_shows_cap_and_remainder():
    output, _ = render("certificate", 70, lang="en")
    assert output.count("◉") == 20
    assert "and 50 more" in output


def test_zero_count_has_no_parade():
    output, _ = render("certificate", 0, lang="en")
    assert "◉" not in output
    assert "0 instances" in output


def test_bignum_renders_digits_and_subtitle():
    output, _ = render("bignum", 42, lang="en")
    assert "██╗  ██╗" in output  # digit 4
    assert "Chromium instances" in output
    assert "universe" in output  # the 42 special tagline


def test_bignum_zh_uses_chinese_unit_label():
    output, _ = render("bignum", 10, lang="zh")
    assert "个 Chromium 内核" in output


def test_no_color_output_has_no_ansi():
    output, _ = render("certificate", 70, lang="en", color=False)
    assert "\x1b" not in output


def test_color_output_has_ansi():
    output, _ = render("certificate", 70, lang="en", color=True)
    assert "\x1b[" in output

    output, _ = render("certificate", 50, lang="en", color=True)
    assert "\x1b[5m" in output  # intervention tier blinks


def test_reference_line_falls_back_to_size_when_too_small():
    facts = build_facts(make_results(1, size=1024))
    assert reference_line(facts, "en") == "1.0 KB"
    assert reference_line(facts, "zh") == "1.0 KB"


def test_every_renderer_satisfies_both_languages_and_extremes():
    for style in RENDERERS:
        for lang in ("en", "zh"):
            for count in (0, 1, 42, 70):
                output, _ = render(style, count, lang=lang)
                assert output
                assert "{" not in output


def test_digit_font_glyphs_are_uniformly_sized():
    widths = {}
    for digit, rows in _DIGIT_FONT.items():
        assert len(rows) == 6, digit
        lengths = {len(row) for row in rows}
        assert lengths == {_GLYPH_WIDTH}, f"digit {digit} rows are ragged: {sorted(lengths)}"
        widths[digit] = lengths
    assert widths  # sanity
    assert all(len(row) == _GLYPH_WIDTH for row in _FALLBACK_DIGIT_ROW)


def test_bignum_digits_align_in_every_locale_font(monkeypatch):
    # The fancier outlined font is used everywhere now; CJK locales do not widen
    # these glyphs in practice (verified by cursor-position measurement).
    monkeypatch.setenv("LC_ALL", "zh_CN.UTF-8")
    output, _ = render("bignum", 8, lang="zh", color=True)
    assert "╗" in output
    rows = [row for row in output.splitlines() if "█" in row or "╗" in row]
    assert rows

    monkeypatch.setenv("LC_ALL", "en_US.UTF-8")
    output, _ = render("bignum", 8, lang="en", color=True)
    assert "╗" in output

    output, _ = render("bignum", 8, lang="zh", color=False)
    assert "╗" in output
