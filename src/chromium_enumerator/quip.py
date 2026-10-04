"""Registry-based quip engine: text models, layouts, and the pairing between them.

A *text model* is one registered record: a required ``essence`` line plus any
number of named capabilities (``diagnosis``, ``closing``, ...). A *layout* is a
registered renderer that declares which capabilities it needs beyond the
baseline. Selection picks a text model for the count's tier, narrows the layouts
to those the model can serve, and picks one.

Neither registry knows about terminals: layouts live in ``quip_layout`` and the
copy lives in ``quip_copy``. Both register themselves at import time, loaded by
:func:`_load_builtins` at the bottom of this module, so importing ``quip`` is
enough to have a working engine.
"""

import random
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from .term import format_size

_MAX_EXIT_CODE = 255

BASELINE = "essence"
"""Every text model must provide it; every layout may rely on it."""


@dataclass(frozen=True, slots=True)
class Facts:
    """The runtime numbers a layout is allowed to render."""

    count: int
    size_bytes: int
    lang: str

    def template_values(self) -> dict[str, int | str]:
        return {
            "count": self.count,
            "size_bytes": self.size_bytes,
            "size_human": format_size(self.size_bytes),
            "lang": self.lang,
        }


@dataclass(frozen=True, slots=True)
class Tier:
    id: str
    threshold: int
    severity: float
    color: str


TIERS: tuple[Tier, ...] = (
    Tier("zero", 0, 0.0, "green"),
    Tier("one", 1, 0.1, "green"),
    Tier("two", 2, 0.2, "green"),
    Tier("few", 3, 0.28, "green"),
    Tier("starter", 5, 0.35, "yellow"),
    Tier("double_digits", 10, 0.5, "yellow"),
    Tier("collector", 25, 0.65, "red"),
    Tier("intervention", 50, 0.8, "red"),
    Tier("datacenter", 70, 1.0, "rainbow"),
)

_TIER_IDS = frozenset(tier.id for tier in TIERS)


def tier_for_count(count: int) -> Tier:
    tier = TIERS[0]
    for candidate in TIERS:
        if count >= candidate.threshold:
            tier = candidate
    return tier


@dataclass(frozen=True, slots=True)
class TextModel:
    lang: str
    tier: str
    essence: str
    capabilities: Mapping[str, str | Callable[[Facts], str]]
    count: int | None = None

    def provides(self) -> frozenset[str]:
        return frozenset({BASELINE, *self.capabilities})


@dataclass(frozen=True, slots=True)
class Layout:
    id: str
    requires: frozenset[str]
    render: Callable[[Mapping[str, str], Facts], str]


_MODELS: list[TextModel] = []
_LAYOUTS: dict[str, Layout] = {}


def text_model(
    lang: str,
    *,
    essence: str,
    count: int | None = None,
    tier: str | None = None,
    **capabilities: str | Callable[[Facts], str],
) -> None:
    """Register one text model.

    ``essence`` is the baseline every layout may rely on. Everything else is a
    capability: its name is the keyword, its value a template string or a
    callable taking :class:`Facts`. Registering more capabilities is a local
    change; it never obliges other models to grow.
    """

    if count is None and tier is None:
        raise TypeError("text_model needs tier= or count=")
    if count is not None:
        tier = tier_for_count(count).id
    if tier not in _TIER_IDS:
        raise ValueError(f"unknown tier: {tier!r}")
    _MODELS.append(TextModel(lang, tier, essence, capabilities, count))


def layout(id: str, *, requires: frozenset[str] = frozenset()):
    """Register a layout. ``requires`` lists capabilities beyond the baseline."""

    def register(render: Callable[[Mapping[str, str], Facts], str]):
        if id in _LAYOUTS:
            raise ValueError(f"duplicate layout: {id!r}")
        _LAYOUTS[id] = Layout(id, frozenset(requires), render)
        return render

    return register


def layout_ids() -> tuple[str, ...]:
    return tuple(sorted(_LAYOUTS))


def text_models() -> tuple[TextModel, ...]:
    return tuple(_MODELS)


def layouts() -> tuple[Layout, ...]:
    return tuple(_LAYOUTS.values())


def can_serve(layout: Layout, model: TextModel) -> bool:
    return layout.requires <= model.provides()


def choose(
    count: int,
    *,
    lang: str,
    size_bytes: int,
    rng: random.Random,
    style: str | None = None,
) -> tuple[Layout, dict[str, str], Facts]:
    """Pick a text model for the count, then a layout that model can serve.

    ``style`` forces a layout (``None`` picks one at random from the compatible
    ones). Returned values are the model's templates already interpolated.
    """

    facts = Facts(count, size_bytes, lang)
    forced = None if style is None else _layout(style)

    model = rng.choice(_candidates(lang, count, forced))
    usable = [item for item in _LAYOUTS.values() if can_serve(item, model)]
    return (
        (forced if forced is not None else rng.choice(usable)),
        _resolve(model, facts),
        facts,
    )


def exit_code_for(count: int) -> int:
    return min(count, _MAX_EXIT_CODE)


def _layout(style: str) -> Layout:
    try:
        return _LAYOUTS[style]
    except KeyError:
        raise ValueError(f"unknown quip style: {style!r}") from None


def _candidates(lang: str, count: int, forced: Layout | None) -> list[TextModel]:
    """Models for this count: exact-count specials first, then the tier's."""

    tier_id = tier_for_count(count).id
    specials = [m for m in _MODELS if m.lang == lang and m.count == count]
    tiers = [
        m for m in _MODELS if m.lang == lang and m.count is None and m.tier == tier_id
    ]
    for source in (specials, tiers):
        pool = [m for m in source if forced is None or can_serve(forced, m)]
        if pool:
            return pool
    wanted = "" if forced is None else f" for style {forced.id!r}"
    raise LookupError(f"no text model for lang={lang!r} count={count}{wanted}")


def _resolve(model: TextModel, facts: Facts) -> dict[str, str]:
    values = {BASELINE: _interpolate(model.essence, facts)}
    for name, provider in model.capabilities.items():
        values[name] = (
            provider(facts) if callable(provider) else _interpolate(provider, facts)
        )
    return values


def _interpolate(template: str, facts: Facts) -> str:
    return template.format(**facts.template_values())


def _load_builtins() -> None:
    from . import quip_copy, quip_layout  # noqa: F401  (registration side effects)


_load_builtins()
