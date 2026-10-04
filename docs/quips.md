# Quip Mode

`--quip` replaces the plain report with a playful summary of the scan. It never changes what is scanned or detected: the engine is handed a count, a byte total, a language, and an RNG, and it returns text.

## Behaviour contract

- `--quip` alone prints only the quip. Add `--verbose` to also get the normal listing; the quip always prints **last**.
- `--quip` and `--json` are mutually exclusive; argparse rejects the combination.
- The exit code becomes the instance count, capped at 255 (`echo $?` for the post-scan aftershock).

To see any tier without owning the Chromium, fabricate the scan: `--mock-instances N` or `CHROMIUM_COUNT_MOCK_INSTANCES=N`. The mock backend is not part of this layer; it is a general debug switch that happens to feed the quip like a real scan. See [cli.md](cli.md#debugging).

## Layers

```text
cli.py           upstream: seed → rng → layout pick, language, exit code
  │
quip_layout.py   layouts: frame and decorate the core text
  │
quip_copy.py     core text: the copy, one registration per level and language
  │
term.py          terminal text: ANSI, display width, frame padding, art
```

| Module | Job |
|---|---|
| `term.py` | Display width, padding, ANSI colour, the digit font and dot glyph. Emits colour unconditionally; stripping is the caller's business. |
| `quip_copy.py` | Pure data: `text_model(...)` calls and nothing else. |
| `quip_layout.py` | The `certificate` and `bignum` layouts, and everything decorative they own. |
| `quip.py` | The two registries, the tier table, and the pairing between models and layouts. |

## Text models

A text model is one `text_model(...)` registration. `essence` is mandatory — it is the baseline every layout may rely on. Every other keyword is a **capability**: its name is the keyword, its value a template string or a callable taking `Facts`.

```python
text_model("zh", tier="collector",
    essence="喜报！ {count} 个内核。你不是在装软件，是在集邮。",
    diagnosis="晚期 Chromium 囤积症",
    prognosis="具有收藏价值",
    stage="第三期",
    closing="它们趁你不注意时繁殖。")
```

A level spans a count range (`tier=`) or one exact count (`count=42`). Registration derives the tier from an exact count, so the 42/404/418 specials only need the number.

## Layouts

A layout is one `@layout` registration that declares the capabilities it needs beyond the baseline:

```python
@layout("certificate", requires={"diagnosis", "prognosis", "stage", "closing"})
def certificate(values, facts): ...
```

It receives the model's already-interpolated values plus the runtime `Facts` (count, size, language) and returns the finished block. Layouts own everything that is not copy: the frame, the severity bar, the unit conversions, the art.

## Selection

1. Count → tier, or an exact-count registration when one exists (42, 404, 418 win over the tier).
2. Pick a text model for that tier and language at random.
3. Narrow the layouts to those the model can serve (`requires <= provides`), then pick one at random — unless `--quip-style` forces one, in which case the model pool is narrowed to models that can serve it.
4. Render, then strip colour if the stream wants none.

The RNG is the one the CLI seeded, so `--quip-seed` reproduces the layout pick and the fabricated-size jitter together.

Two properties keep this honest, and both are tested:

- The baseline `essence` guarantees the pairing is never empty, because a layout requiring only the baseline is compatible with every model. `bignum` is that layout.
- Every level has a model for every layout in both languages, so a forced `--quip-style` never hits an incompatible model.

## Adding copy, a capability, or a layout

- **Another joke for a level**: one more `text_model(...)` call with a different `essence`, same tier and language. The model pick is random, so both get used.
- **A new capability**: one more keyword on the registrations that should provide it. No other model grows, and no schema changes — this is the whole reason capabilities live in the registry rather than in a shared record type.
- **A new layout**: one `@layout` decorator with its `requires`. It pairs only with models that offer them. If you want it forceable with `--quip-style`, make sure at least one model per level and language provides the capability; a test enforces this.
- **A new level**: one `Tier(...)` in `TIERS`, models for both languages, and an entry in the width test's expectations. Thresholds must keep ascending from zero.

## Writing rules

Layouts never wrap. Anything that lands inside the certificate frame must fit **56 display columns**, counting a CJK character as two. A test formats every framed string at the widest count its level can see and fails on overflow. A level that spans more than one count must not spell a number out; use `{count}`. An exact-count special may.

The rules are deliberately cheap to satisfy: `{count}` in a framed string caps the level's usable width, so unbounded levels (70+) are written without it.

## The two layouts

### certificate

A mock-official box with a dim cyan double-line frame and a neutral title. The count is bold, coloured, and centred above the diagnosis. The essence follows as a dim note, then the severity bar and stage, disk usage, prognosis, and a right-aligned signature. The closing line sits outside the box. There is no dot parade.

Disk usage and its game conversion occupy separate rows: the real byte total is foreground text, while the conversion is a dim annotation aligned below it. English compares the payload to Doom (1993), Chinese to Super Mario Bros cartridges. Both rows are omitted when there is no payload; a payload smaller than one game only shows the byte total.

### bignum

The count in six-row ANSI Shadow block digits. The bold unit label sits beside the middle row, with a dim disk-usage summary directly beneath it when a payload exists. Art, essence, and closing share a two-cell left margin. The closing is dim and optional, so the layout requires only the baseline.

The digit fonts and certificate frame use East Asian Ambiguous characters (`█`, `╗`, `═`). Whether a terminal renders those one or two cells wide is a terminal setting, not something a locale reliably predicts; kitty, for instance, keeps them narrow even under `LC_ALL=zh_CN.UTF-8`. The measuring functions therefore assume the same ambiguous-is-narrow convention the frames are drawn with. Per-character rainbow colouring is unaffected by glyph width because ANSI codes are zero-width.

## Colour

Labels, annotations, signatures, and the certificate border are dim; body text keeps the terminal's default foreground. Severity uses green, yellow, or red, without blinking. At 70+ the certificate colours only its filled severity bar as a rainbow, while bignum colours only its digits that way.

Layouts always emit ANSI. The CLI decides whether to keep it: `terminal_supports_color()` (a TTY, and no `NO_COLOR`) combined with `--no-color`. When colour is off, the boundary strips every escape with `term.strip_ansi`.

`--no-color` and `NO_COLOR` differ in tone only: the explicit flag prints a "Coward." jab, the environment variable does not.

## Tests

- `tests/test_quip.py` — tier table, language and layout coverage, frame-width invariants, the essence appearing in every layout, exact-count overrides, seeded reproducibility, registration errors.
- `tests/test_quip_layout.py` — frame alignment and visual hierarchy in both languages, disk annotations, long-count rendering, digit-font integrity, colour and stripping.
- `tests/test_quip_cli.py` — flag wiring, `--quip`/`--json` rejection, exit code, locale resolution, layout randomisation, the `--no-color` jab.
