"""The quip engine: registries, tiering, pairing, and the copy's invariants."""

import random

import pytest

from chromium_enumerator import quip
from chromium_enumerator.quip import (
    BASELINE,
    TIERS,
    Layout,
    TextModel,
    choose,
    exit_code_for,
    layout_ids,
    layouts,
    text_models,
    tier_for_count,
)
from chromium_enumerator.term import display_len

LANGUAGES = ("en", "zh")
CERT_INNER = 62
CERT_GUTTER = 3
FRAMED_WIDTH = CERT_INNER - 2 * CERT_GUTTER
LABEL_WIDTH = {"en": 14, "zh": 8}
UNFRAMED = frozenset({"closing"})


def widest_count(tier_id: str) -> int:
    """The widest count a tier can be rendered at (unbounded tiers get a big one)."""

    index = [tier.id for tier in TIERS].index(tier_id)
    if index + 1 < len(TIERS):
        return TIERS[index + 1].threshold - 1
    return 1_000_000


def models_for(lang: str, tier_id: str) -> list[TextModel]:
    return [m for m in text_models() if m.lang == lang and m.tier == tier_id]


def test_tiers_ascend_from_zero():
    thresholds = [tier.threshold for tier in TIERS]
    assert thresholds[0] == 0
    assert thresholds == sorted(thresholds)
    assert len(set(thresholds)) == len(thresholds)


def test_tier_boundaries():
    expected = {
        0: "zero",
        1: "one",
        2: "two",
        3: "few",
        4: "few",
        5: "starter",
        9: "starter",
        10: "double_digits",
        24: "double_digits",
        25: "collector",
        49: "collector",
        50: "intervention",
        69: "intervention",
        70: "datacenter",
        10_000: "datacenter",
    }
    for count, tier_id in expected.items():
        assert tier_for_count(count).id == tier_id


def test_every_tier_has_a_model_in_both_languages():
    for tier in TIERS:
        for lang in LANGUAGES:
            assert models_for(lang, tier.id), f"missing {tier.id}/{lang}"


def test_every_special_count_has_a_model_in_both_languages():
    for count in (42, 404, 418):
        for lang in LANGUAGES:
            assert any(m.lang == lang and m.count == count for m in text_models())


def test_every_model_can_serve_every_layout():
    """A forced --quip-style must never hit an incompatible model."""

    for model in text_models():
        for item in layouts():
            assert item.requires <= model.provides(), (
                f"{item.id} cannot serve {model!r}"
            )


@pytest.mark.parametrize("lang", LANGUAGES)
def test_framed_copy_fits_the_certificate_frame(lang):
    """Layouts never wrap, so every framed string must fit on one row."""

    for model in text_models():
        if model.lang != lang:
            continue
        count = widest_count(model.tier)
        framed = {"essence": model.essence, **model.capabilities}
        for name, template in framed.items():
            if not isinstance(template, str) or name in UNFRAMED:
                continue
            value = template.format(count=count)
            assert "\n" not in value, f"{model.tier}/{lang} {name} spans lines"
            assert display_len(value) <= FRAMED_WIDTH, (
                f"{model.tier}/{lang} {name} is too wide: {value!r}"
            )
            if name == "essence":
                continue
            assert display_len(value) <= CERT_INNER - LABEL_WIDTH[lang], (
                f"{model.tier}/{lang} {name} overflows its labelled row"
            )


@pytest.mark.parametrize("lang", LANGUAGES)
def test_every_layout_prints_the_essence_verbatim(lang):
    for count in (0, 1, 3, 30, 42, 70):
        for item in layouts():
            layout, values, facts = choose(
                count, lang=lang, size_bytes=0, rng=random.Random(0), style=item.id
            )
            assert layout.id == item.id
            assert values[BASELINE] in layout.render(values, facts)


def test_explicit_style_is_honoured_for_every_tier():
    for count in (0, 1, 3, 30, 71, 999):
        for style in layout_ids():
            layout, _values, _facts = choose(
                count, lang="en", size_bytes=0, rng=random.Random(0), style=style
            )
            assert layout.id == style


def test_unknown_style_is_rejected():
    with pytest.raises(ValueError, match="unknown quip style"):
        choose(10, lang="en", size_bytes=0, rng=random.Random(0), style="hologram")


def test_unknown_language_is_rejected():
    with pytest.raises(LookupError):
        choose(10, lang="eo", size_bytes=0, rng=random.Random(0))


def test_special_counts_override_their_tier():
    _layout, values, _facts = choose(
        42, lang="en", size_bytes=0, rng=random.Random(0), style="certificate"
    )
    assert "42 instances" in values[BASELINE]
    assert values["prognosis"] == "Mostly harmless"

    _layout, zh_values, _facts = choose(
        42, lang="zh", size_bytes=0, rng=random.Random(0), style="certificate"
    )
    assert "宇宙" in zh_values[BASELINE]


def test_same_seed_reproduces_the_same_choice():
    first = choose(30, lang="zh", size_bytes=0, rng=random.Random(7))
    second = choose(30, lang="zh", size_bytes=0, rng=random.Random(7))
    assert first[0].id == second[0].id
    assert first[1] == second[1]
    assert first[2] == second[2]


def test_the_size_is_carried_through_untouched():
    """Sizing is the backend's job; the quip layer never guesses."""

    _layout, _values, facts = choose(
        10, lang="en", size_bytes=1234, rng=random.Random(0)
    )
    assert facts.size_bytes == 1234
    assert facts.template_values()["size_human"] == "1.2 KB"


def test_registration_rejects_unknown_tier_and_missing_baseline():
    with pytest.raises(TypeError):
        quip.text_model("en", essence="x")
    with pytest.raises(ValueError, match="unknown tier"):
        quip.text_model("en", tier="nowhere", essence="x")


def test_registration_rejects_duplicate_layout():
    with pytest.raises(ValueError, match="duplicate layout"):
        quip.layout("certificate")(lambda values, facts: "")


def test_a_capability_is_local_to_the_model_that_registers_it():
    """Adding a capability is a one-line change; no other model grows."""

    quip.text_model(
        "en", count=999_999, essence="One-off.", haiku="Silent fans spinning."
    )
    model = next(m for m in quip.text_models() if m.count == 999_999)
    probe = quip.Layout(
        "haiku-probe", frozenset({"haiku"}), lambda values, _f: values["haiku"]
    )
    try:
        assert quip.can_serve(probe, model)
        assert all(
            "haiku" not in other.capabilities
            for other in quip.text_models()
            if other.count != 999_999
        )
    finally:
        quip._MODELS.remove(model)


def test_exit_code_is_capped():
    assert exit_code_for(0) == 0
    assert exit_code_for(70) == 70
    assert exit_code_for(300) == 255


def test_registry_entries_are_plain_records():
    assert all(isinstance(item, Layout) for item in layouts())
    assert all(isinstance(model, TextModel) for model in text_models())
