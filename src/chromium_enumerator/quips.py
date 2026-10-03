"""Playful report ("quip") logic: facts extraction, tier matching, and text pools.

This module is pure data + pure functions. It does no I/O and knows nothing
about ANSI colors or box drawing; presentation lives in quip_render.py.

Copy is data, not code: TIERS and SPECIAL_QUIPS are meant to be edited
freely without touching any logic. validate_copy() (exercised by the test
suite) keeps the two languages in sync and checks that every template
placeholder exists on QuipFacts.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass

from .model import RuntimeResult

DOOM_BYTES = 2_500_636
"""Size of Doom (1993), our English unit of disk waste: 2.39 MB.

Do not "fix" this number. The joke does not require precision.
"""

MARIO_BYTES = 40_960
"""Size of the original Super Mario Bros (40 KB), the zh unit of disk waste."""

FLOPPY_BYTES = 1_474_560
"""One 1.44 MB floppy disk, alternate zh unit."""

MAX_DOTS = 20
"""Cap for the runtime dot parade; the remainder becomes "... and N more"."""

_MAX_EXIT_CODE = 255

_DOT_FACE = "(◉)"
_DOT_BLOCK = "[●]"


@dataclass(frozen=True)
class QuipFacts:
    """Everything the copy pools are allowed to reference."""

    count: int
    total_bytes: int
    size_human: str
    family_counts: dict[str, int]
    electron_count: int
    largest_name: str
    largest_bytes: int
    largest_size_human: str
    dot_faces: str
    dot_more: int
    doom_count: int
    mario_count: int
    floppy_count: int
    floppy_hours: int


@dataclass(frozen=True)
class Tier:
    id: str
    threshold: int
    severity: float
    color: str
    stage: dict[str, str]
    pool: dict[str, tuple[dict[str, str], ...]]


@dataclass(frozen=True)
class ResolvedQuip:
    """A fully localized, placeholder-free text bundle ready for a renderer."""

    tier_id: str
    count: int
    severity: float
    color: str
    stage: str
    texts: dict[str, str]


def _family_counts(results: Sequence[RuntimeResult]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in results:
        counts[result.family] = counts.get(result.family, 0) + 1
    return counts


def build_facts(results: Sequence[RuntimeResult], *, dot_style: str = "face") -> QuipFacts:
    """Extract everything a quip might want to joke about from scan results."""

    dot = _DOT_FACE if dot_style == "face" else _DOT_BLOCK
    shown = min(len(results), MAX_DOTS)
    total_bytes = sum(result.size_bytes for result in results)
    largest = max(results, key=lambda result: result.size_bytes, default=None)
    largest_name = largest.root.name if largest is not None else ""
    largest_bytes = largest.size_bytes if largest is not None else 0
    floppy_count = total_bytes // FLOPPY_BYTES
    return QuipFacts(
        count=len(results),
        total_bytes=total_bytes,
        size_human=_format_size(total_bytes),
        family_counts=_family_counts(results),
        electron_count=_family_counts(results).get("electron", 0),
        largest_name=largest_name,
        largest_bytes=largest_bytes,
        largest_size_human=_format_size(largest_bytes),
        dot_faces=" ".join([dot] * shown),
        dot_more=len(results) - shown,
        doom_count=total_bytes // DOOM_BYTES,
        mario_count=total_bytes // MARIO_BYTES,
        floppy_count=floppy_count,
        floppy_hours=round(floppy_count / 20),
    )


def _format_size(size_bytes: int) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    size = float(size_bytes)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size_bytes} B"


_TIER_THRESHOLDS: tuple[tuple[str, int, float, str], ...] = (
    ("zero", 0, 0.0, "green"),
    ("one", 1, 0.1, "green"),
    ("two", 2, 0.2, "green"),
    ("few", 3, 0.28, "green"),
    ("starter", 5, 0.35, "yellow"),
    ("double_digits", 10, 0.5, "yellow"),
    ("collector", 25, 0.65, "red"),
    ("intervention", 50, 0.8, "blink"),
    ("datacenter", 70, 1.0, "rainbow"),
)

_STAGE: dict[str, dict[str, str]] = {
    "zero": {"en": "Stage 0", "zh": "第〇期"},
    "one": {"en": "Stage I", "zh": "第一期"},
    "two": {"en": "Stage I", "zh": "第一期"},
    "few": {"en": "Stage I", "zh": "第一期"},
    "starter": {"en": "Stage II", "zh": "第二期"},
    "double_digits": {"en": "Stage III", "zh": "第三期"},
    "collector": {"en": "Stage III", "zh": "第三期"},
    "intervention": {"en": "Stage IV", "zh": "第四期"},
    "datacenter": {"en": "Stage V", "zh": "终末期"},
}

_POOLS: dict[str, dict[str, tuple[dict[str, str], ...]]] = {
    "zero": {
        "en": (
            {
                "headline": "Impossible.",
                "tagline": "Your machine is in a state of grace.",
                "diagnosis": "Total Chromium Absence",
                "prognosis": "Eternal vigilance",
                "closing": "Print this output and frame it.",
            },
            {
                "headline": "Zero. Not one.",
                "tagline": "Somewhere, a web developer is about to fix that.",
                "diagnosis": "Total Chromium Absence",
                "prognosis": "Temporary",
                "closing": "Enjoy it while it lasts.",
            },
        ),
        "zh": (
            {
                "headline": "难以置信！",
                "tagline": "你的电脑纯净得像刚出厂。",
                "diagnosis": "Chromium 完全缺失",
                "prognosis": "需要终身保持警惕",
                "closing": "建议把这份报告打印装裱。",
            },
            {
                "headline": "一个都没有。",
                "tagline": "此刻，某位前端工程师正准备改变这一切。",
                "diagnosis": "Chromium 完全缺失",
                "prognosis": "暂时的",
                "closing": "且用且珍惜。",
            },
        ),
    },
    "one": {
        "en": (
            {
                "headline": "Just one Chromium.",
                "tagline": "A digital minimalist. We've contacted the museum.",
                "diagnosis": "Solitary Chromium Confinement",
                "prognosis": "It will make friends",
                "closing": "Hold the line.",
            },
        ),
        "zh": (
            {
                "headline": "仅 1 个 Chromium。",
                "tagline": "数字极简主义的活化石，我们已通知博物馆。",
                "diagnosis": "单核孤立综合征",
                "prognosis": "它会交到朋友的",
                "closing": "请守住防线。",
            },
        ),
    },
    "two": {
        "en": (
            {
                "headline": "Two instances.",
                "tagline": "Perfectly normal... for now. We're watching.",
                "diagnosis": "Early Chromium Exposure",
                "prognosis": "Stable, under observation",
                "closing": "The abyss is checking its schedule.",
            },
        ),
        "zh": (
            {
                "headline": "2 个内核，岁月静好。",
                "tagline": "但深渊正在凝视你。",
                "diagnosis": "Chromium 早期暴露",
                "prognosis": "稳定，留院观察",
                "closing": "深渊正在查看日程表。",
            },
        ),
    },
    "few": {
        "en": (
            {
                "headline": "{count} instances.",
                "tagline": "They have started reproducing. Slowly, at first.",
                "diagnosis": "Nascent Chromium Colony",
                "prognosis": "Social animals",
                "closing": "Two was a coincidence. This is a pattern.",
            },
        ),
        "zh": (
            {
                "headline": "{count} 个内核。",
                "tagline": "它们开始自发繁殖了。一开始总是很慢。",
                "diagnosis": "初生 Chromium 群落",
                "prognosis": "群居动物",
                "closing": "两个是巧合。这是规律。",
            },
        ),
    },
    "starter": {
        "en": (
            {
                "headline": "{count} Chromies collected.",
                "tagline": "Starter pack acquired. Gotta catch 'em all!",
                "diagnosis": "Habitual Runtime Acquisition",
                "prognosis": "Collectible",
                "closing": "Each one believes it is special.",
            },
        ),
        "zh": (
            {
                "headline": "{count} 个 Chromium 已就位。",
                "tagline": "新手礼包领取成功。",
                "diagnosis": "习惯性运行时收集",
                "prognosis": "可收藏",
                "closing": "每一个都坚信自己是特别的。",
            },
        ),
    },
    "double_digits": {
        "en": (
            {
                "headline": "Double digits!",
                "tagline": 'Doctors describe your condition as "stable, but contagious."',
                "diagnosis": "Chronic Runtime Multiplication",
                "prognosis": "Contagious",
                "closing": "Your disk has started having its own ideas.",
            },
        ),
        "zh": (
            {
                "headline": "两位数达成！",
                "tagline": "你的硬盘开始有了自己的想法。",
                "diagnosis": "慢性运行时增殖",
                "prognosis": "具有传染性",
                "closing": "建议与家人保持距离。",
            },
        ),
    },
    "collector": {
        "en": (
            {
                "headline": "Good news, everyone!",
                "tagline": "You're not installing apps — you're curating a collection.",
                "diagnosis": "Advanced Chromium Hoarding",
                "prognosis": "Philatelic",
                "closing": "They multiply when you're not looking.",
            },
        ),
        "zh": (
            {
                "headline": "喜报！",
                "tagline": "{count} 个内核。你不是在装软件，是在集邮。",
                "diagnosis": "晚期 Chromium 囤积症",
                "prognosis": "具有收藏价值",
                "closing": "它们趁你不注意时繁殖。",
            },
        ),
    },
    "intervention": {
        "en": (
            {
                "headline": "Good news, everyone!",
                "tagline": "{count} instances. We've scheduled an intervention. Please sit down.",
                "diagnosis": "Chronic Chromium Proliferation",
                "prognosis": "Intervention scheduled",
                "closing": "Step one is admitting you have a problem.",
            },
        ),
        "zh": (
            {
                "headline": "喜报！",
                "tagline": "{count} 个 Chromium。我们已替你预约了戒断互助小组。",
                "diagnosis": "慢性 Chromium 增生",
                "prognosis": "已安排强制干预",
                "closing": "戒断第一步：承认问题的存在。",
            },
        ),
    },
    "datacenter": {
        "en": (
            {
                "headline": "Good news, everyone!",
                "tagline": "You no longer own a computer — you run a Chromium hosting facility with a side hustle in productivity.",
                "diagnosis": "Chronic Chromium Proliferation",
                "prognosis": "Terminal (pun intended)",
                "closing": "Recommendation: rm -rf /*  (This is a joke. We are not liable. You brought this on yourself.)",
            },
            {
                "headline": "Good news, everyone!",
                "tagline": "{count} Chromium instances. Technically, this is a render farm.",
                "diagnosis": "Chronic Chromium Proliferation",
                "prognosis": "Terminal (pun intended)",
                "closing": "Recommendation: rm -rf /*  (This is a joke. We are not liable. You brought this on yourself.)",
            },
        ),
        "zh": (
            {
                "headline": "喜报！",
                "tagline": "{count} 个内核。严格来说你拥有的是一台 Chromium 服务器，顺便能办公。",
                "diagnosis": "慢性 Chromium 增生",
                "prognosis": "终末期（双关语）",
                "closing": "建议：rm -rf /*（这是玩笑。概不负责。这是你自找的。）",
            },
            {
                "headline": "喜报！",
                "tagline": "你的电脑不是电脑，是 Chromium 批发市场。",
                "diagnosis": "慢性 Chromium 增生",
                "prognosis": "终末期（双关语）",
                "closing": "建议：rm -rf /*（这是玩笑。概不负责。这是你自找的。）",
            },
        ),
    },
}

_SPECIAL_POOLS: dict[int, dict[str, tuple[dict[str, str], ...]]] = {
    42: {
        "en": (
            {
                "headline": "Good news, everyone!",
                "tagline": "42 Chromium instances. The answer to life, the universe, and everything is apparently Electron.",
                "diagnosis": "Chronic Chromium Proliferation",
                "prognosis": "Mostly harmless",
                "closing": "Don't panic.",
            },
        ),
        "zh": (
            {
                "headline": "喜报！",
                "tagline": "42 个内核。生命、宇宙以及一切的答案，原来是 Electron。",
                "diagnosis": "慢性 Chromium 增生",
                "prognosis": "基本无害",
                "closing": "不要恐慌。",
            },
        ),
    },
    404: {
        "en": (
            {
                "headline": "404 instances.",
                "tagline": "Chromium Not Found. (Just kidding. They're all here. All {count} of them.)",
                "diagnosis": "Chronic Chromium Proliferation",
                "prognosis": "Terminal (pun intended)",
                "closing": "Recommendation: rm -rf /*  (This is a joke. We are not liable. You brought this on yourself.)",
            },
        ),
        "zh": (
            {
                "headline": "404 个内核。",
                "tagline": "Chromium Not Found。（开玩笑的，全都在，{count} 个，一个没少。）",
                "diagnosis": "慢性 Chromium 增生",
                "prognosis": "终末期（双关语）",
                "closing": "建议：rm -rf /*（这是玩笑。概不负责。这是你自找的。）",
            },
        ),
    },
    418: {
        "en": (
            {
                "headline": "Error 418: I'm a teapot.",
                "tagline": "Just kidding — you're a Chromium data center now.",
                "diagnosis": "Chronic Chromium Proliferation",
                "prognosis": "Terminal (pun intended)",
                "closing": "This facility brews no tea. Only JavaScript.",
            },
        ),
        "zh": (
            {
                "headline": "错误 418：我是一个茶壶。",
                "tagline": "开玩笑的——你现在是一个 Chromium 数据中心了。",
                "diagnosis": "慢性 Chromium 增生",
                "prognosis": "终末期（双关语）",
                "closing": "本设施不泡茶，只跑 JavaScript。",
            },
        ),
    },
}

# Threshold-matched tiers are built lazily below so the copy above stays readable.
TIERS: tuple[Tier, ...] = tuple(
    Tier(
        id=tier_id,
        threshold=threshold,
        severity=severity,
        color=color,
        stage=_STAGE[tier_id],
        pool=_POOLS[tier_id],
    )
    for tier_id, threshold, severity, color in _TIER_THRESHOLDS
)

# (count, tier_id) — tier_id drives severity/color/stage, pool comes from specials.
SPECIAL_QUIPS: dict[int, tuple[str, dict[str, tuple[dict[str, str], ...]]]] = {
    42: ("intervention", _SPECIAL_POOLS[42]),
    404: ("datacenter", _SPECIAL_POOLS[404]),
    418: ("datacenter", _SPECIAL_POOLS[418]),
}

_TIER_BY_ID = {tier.id: tier for tier in TIERS}


def tier_for_count(count: int) -> Tier:
    tier = TIERS[0]
    for candidate in TIERS:
        if count >= candidate.threshold:
            tier = candidate
    return tier


def pick_quip(facts: QuipFacts, lang: str, rng: random.Random) -> ResolvedQuip:
    """Choose one copy entry for these facts and render every field."""

    special = SPECIAL_QUIPS.get(facts.count)
    if special is not None and lang in special[1]:
        tier_id, pools = special
        tier = _TIER_BY_ID[tier_id]
        entry = rng.choice(pools[lang])
    else:
        tier = tier_for_count(facts.count)
        entry = rng.choice(tier.pool[lang])
    template_values = _facts_as_dict(facts)
    texts = {key: value.format_map(template_values) for key, value in entry.items()}
    return ResolvedQuip(
        tier_id=tier.id,
        count=facts.count,
        severity=tier.severity,
        color=tier.color,
        stage=tier.stage[lang],
        texts=texts,
    )


def exit_code_for(count: int) -> int:
    return min(count, _MAX_EXIT_CODE)


def _facts_as_dict(facts: QuipFacts) -> dict[str, int | str]:
    return {
        "count": facts.count,
        "total_bytes": facts.total_bytes,
        "size_human": facts.size_human,
        "electron_count": facts.electron_count,
        "largest_name": facts.largest_name,
        "largest_bytes": facts.largest_bytes,
        "largest_size_human": facts.largest_size_human,
        "dot_faces": facts.dot_faces,
        "dot_more": facts.dot_more,
        "doom_count": facts.doom_count,
        "mario_count": facts.mario_count,
        "floppy_count": facts.floppy_count,
        "floppy_hours": facts.floppy_hours,
    }


def validate_copy() -> list[str]:
    """Structural checks for the copy pools. Returns a list of problems."""

    problems: list[str] = []
    languages = ("en", "zh")
    valid_placeholders = set(_facts_as_dict(build_facts([])))

    for tier in TIERS:
        for lang in languages:
            if lang not in tier.stage:
                problems.append(f"tier {tier.id!r}: missing stage for {lang!r}")
            if lang not in tier.pool:
                problems.append(f"tier {tier.id!r}: missing pool for {lang!r}")
                continue
            if not tier.pool[lang]:
                problems.append(f"tier {tier.id!r}: empty pool for {lang!r}")
            problems.extend(
                _validate_entries(tier.pool[lang], f"tier {tier.id!r} [{lang}]", valid_placeholders)
            )
        reference_keys = set(tier.pool[languages[0]][0]) if tier.pool.get(languages[0]) else set()
        for lang in languages[1:]:
            for index, entry in enumerate(tier.pool.get(lang, ())):
                if set(entry) != reference_keys:
                    problems.append(
                        f"tier {tier.id!r} [{lang}] entry {index}: keys {sorted(entry)} != {sorted(reference_keys)}"
                    )

    for index, tier in enumerate(TIERS):
        next_threshold = TIERS[index + 1].threshold if index + 1 < len(TIERS) else None
        if next_threshold is not None and next_threshold - tier.threshold > 1:
            for lang in languages:
                for entry_index, entry in enumerate(tier.pool.get(lang, ())):
                    for key, text in entry.items():
                        if any(char.isdigit() for char in text):
                            coverage = f"{tier.threshold}-{next_threshold - 1}"
                            detail = f"literal digit in a multi-count tier (covers {coverage}); use {{count}}"
                            problems.append(f"tier {tier.id!r} [{lang}] entry {entry_index} field {key!r}: {detail}")

    for count, (tier_id, pools) in SPECIAL_QUIPS.items():
        if tier_id not in _TIER_BY_ID:
            problems.append(f"special {count}: unknown tier {tier_id!r}")
        for lang in languages:
            if lang not in pools:
                problems.append(f"special {count}: missing pool for {lang!r}")
                continue
            problems.extend(
                _validate_entries(pools[lang], f"special {count} [{lang}]", valid_placeholders)
            )

    return problems


def _validate_entries(
    entries: tuple[dict[str, str], ...], label: str, valid_placeholders: set[str]
) -> list[str]:
    problems = []
    for index, entry in enumerate(entries):
        for key, text in entry.items():
            for field_name in _placeholders(text):
                if field_name not in valid_placeholders:
                    problems.append(
                        f"{label} entry {index} field {key!r}: unknown placeholder {field_name!r}"
                    )
    return problems


def _placeholders(text: str) -> list[str]:
    import string

    return [
        field_name
        for _, field_name, _, _ in string.Formatter().parse(text)
        if field_name is not None
    ]
