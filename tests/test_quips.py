import random

from chromium_enumerator.quips import (
    DOOM_BYTES,
    MARIO_BYTES,
    SPECIAL_QUIPS,
    TIERS,
    build_facts,
    exit_code_for,
    pick_quip,
    tier_for_count,
    validate_copy,
)
from tests.helpers import make_result, make_results


def test_copy_pools_are_structurally_valid():
    assert validate_copy() == []


def test_tiers_are_ascending_and_start_at_zero():
    thresholds = [tier.threshold for tier in TIERS]
    assert thresholds[0] == 0
    assert thresholds == sorted(thresholds)


def test_tier_boundaries():
    assert tier_for_count(0).id == "zero"
    assert tier_for_count(1).id == "one"
    assert tier_for_count(2).id == "two"
    assert tier_for_count(3).id == "few"
    assert tier_for_count(4).id == "few"
    assert tier_for_count(5).id == "starter"
    assert tier_for_count(9).id == "starter"
    assert tier_for_count(10).id == "double_digits"
    assert tier_for_count(24).id == "double_digits"
    assert tier_for_count(25).id == "collector"
    assert tier_for_count(49).id == "collector"
    assert tier_for_count(50).id == "intervention"
    assert tier_for_count(69).id == "intervention"
    assert tier_for_count(70).id == "datacenter"
    assert tier_for_count(10_000).id == "datacenter"


def test_multi_count_tiers_never_hardcode_numbers():
    import re

    for index, tier in enumerate(TIERS):
        if index + 1 >= len(TIERS):
            continue
        span = TIERS[index + 1].threshold - tier.threshold
        if span <= 1:
            continue
        for lang in ("en", "zh"):
            for entry in tier.pool[lang]:
                for key, text in entry.items():
                    assert not re.search(r"\d", text), (
                        f"tier {tier.id!r} [{lang}] {key} hardcodes a number: {text!r}"
                    )


def test_copy_guard_detects_hardcoded_digits():
    from chromium_enumerator import quips

    original = quips._POOLS["few"]["en"]
    quips._POOLS["few"]["en"] = (
        {"headline": "3 instances.", "tagline": "oops", "diagnosis": "d", "prognosis": "p", "closing": "c"},
    )
    try:
        assert any("literal digit" in problem for problem in quips.validate_copy())
    finally:
        quips._POOLS["few"]["en"] = original


def test_special_numbers_override_tier_pool_but_keep_tier_severity():
    facts = build_facts(make_results(42))
    quip = pick_quip(facts, "en", random.Random(0))
    assert "universe" in quip.texts["tagline"]
    assert quip.tier_id == "intervention"

    facts = build_facts(make_results(404))
    quip = pick_quip(facts, "zh", random.Random(0))
    assert "404" in quip.texts["headline"]
    assert quip.tier_id == "datacenter"

    for count in SPECIAL_QUIPS:
        for lang in ("en", "zh"):
            quip = pick_quip(build_facts(make_results(count)), lang, random.Random(1))
            assert "{" not in quip.texts["tagline"]


def test_placeholders_are_interpolated():
    facts = build_facts(make_results(10))
    for lang in ("en", "zh"):
        quip = pick_quip(facts, lang, random.Random(0))
        for text in quip.texts.values():
            assert "{" not in text
            assert "}" not in text


def test_same_seed_reproduces_same_quip():
    facts = build_facts(make_results(70))
    first = pick_quip(facts, "en", random.Random(7))
    second = pick_quip(facts, "en", random.Random(7))
    assert first == second


def test_facts_extraction():
    results = [
        make_result("Big", 3 * DOOM_BYTES),
        make_result("Small", 1, family="cef"),
    ]
    facts = build_facts(results)
    assert facts.count == 2
    assert facts.electron_count == 1
    assert facts.largest_name == "Big"
    assert facts.doom_count == 3
    assert facts.dot_more == 0
    assert facts.dot_faces.count("◉") == 2


def test_dot_parade_is_capped():
    facts = build_facts(make_results(70))
    assert facts.dot_faces.count("◉") == 20
    assert facts.dot_more == 50


def test_chinese_reference_units():
    facts = build_facts(make_results(1, size=100 * MARIO_BYTES))
    assert facts.mario_count == 100


def test_zero_results_facts():
    facts = build_facts([])
    assert facts.count == 0
    assert facts.dot_faces == ""
    assert facts.dot_more == 0
    assert facts.largest_name == ""


def test_exit_code_capped():
    assert exit_code_for(0) == 0
    assert exit_code_for(70) == 70
    assert exit_code_for(300) == 255
