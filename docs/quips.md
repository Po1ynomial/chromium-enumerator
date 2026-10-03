# Quip Mode

`--quip` replaces the plain report with a playful, dramatized summary of the scan results. It never changes what is scanned or detected — it is a pure presentation layer on top of the same `RuntimeResult` list.

```sh
chromium-count --quip /Applications
```

Behavior contract:

- `--quip` alone prints only the quip. Add `--verbose` to also get the normal listing; the quip always prints **last** (the punchline lands at the end).
- `--quip` and `--json` are mutually exclusive; argparse rejects the combination. JSON is for scripts, jokes are for humans.
- The exit code becomes the instance count, capped at 255 (`echo $?` for the post-scan aftershock).

## Flags

| Flag | Effect |
|---|---|
| `--quip` | Enable quip mode |
| `--lang auto\|zh\|en` | Quip language. `auto` reads `LC_ALL`/`LC_MESSAGES`/`LANG`; `zh*` locales get Chinese copy, everything else English |
| `--quip-seed N` | Fix the RNG seed for a reproducible joke |
| `--quip-style auto\|certificate\|bignum` | Presentation style. `auto` (default) picks a renderer from the seeded RNG, so a fixed `--quip-seed` reproduces both the joke and its presentation |
| `--no-color` | Disable ANSI colors, with an audible-wink jab. Passive `NO_COLOR`/non-TTY detection degrades silently |
| `--quip-count N` | Skip scanning and preview quip mode for a machine with N instances (fabricated runtimes with plausible sizes and families). Requires `--quip`; incompatible with `--verbose` |

## Architecture

```text
scanner.py ──> RuntimeResult list
                    │
quips.py      build_facts() ──> QuipFacts        (pure data extraction)
              pick_quip()   ──> ResolvedQuip     (tier match + RNG pick +
                                                  placeholder interpolation)
                    │
quip_render.py renderer.render() ──> str         (pluggable presentation)
```

Three separable concerns:

1. **Facts** (`QuipFacts`) — everything copy is allowed to reference: count, total bytes, per-family counts, largest runtime, dot parade pieces, and the localized units of disk waste (Doom copies for English, Super Mario Bros copies for Chinese, floppies as an alternate).
2. **Copy** (`TIERS`, `SPECIAL_QUIPS` in `quips.py`) — pure data. Tiers are threshold-matched on count; each tier carries severity (0–1), a color mood, a stage label, and a pool of interchangeable copy entries per language. Special exact counts (42, 404, 418) override the pool of their severity tier. Editing copy means editing this data only.
3. **Renderers** (`quip_render.py`) — anything satisfying the `QuipRenderer` protocol can be registered in `RENDERERS` and selected via `--quip-style`.

## Tone curve

| Count | Mood | zh voice | en voice |
|---|---|---|---|
| 0 | Reverence | 纯净得像刚出厂 | state of grace |
| 1 | Museum piece | 数字极简主义活化石 | we've contacted the museum |
| 2 | Foreshadowing | 深渊正在凝视你 | we're watching |
| 3–4 | First signs | 它们开始自发繁殖了 | they have started reproducing |
| 5–9 | Starter pack | 新手礼包领取成功 | gotta catch 'em all |
| 10–24 | Clinical concern | 硬盘有了自己的想法 | stable, but contagious |
| 25–49 | Fake celebration | 喜报！你在集邮 | Good news, everyone! |
| 50–69 | Intervention | 已预约戒断互助小组 | we've scheduled an intervention |
| 70+ | Black humor | Chromium 批发市场 | Chromium hosting facility |

A tier that spans more than one count may not contain literal digits in its copy — `validate_copy()` rejects that, so "2 instances" cannot silently lie when the tier also covers 3 and 4. Use `{count}` (or a wording without a number). Single-count tiers are free to spell the number out.

Chinese copy uses the 喜报 (jubilant announcement) register; English uses Futurama's "Good news, everyone!" — both deliver bad news in a celebratory form. The two languages are independently written, not translated.

## Renderers

The renderer is chosen per run: `auto` (the default) draws one from the same seeded RNG as the copy, so repeated scans vary while `--quip-seed` stays reproducible.

### certificate (default)

A mock-official "Chromium Diagnostic Certificate" box: patient, count, diagnosis, animated severity bar with stage, disk waste in localized units, prognosis, and certification by Dr. Electron, PhD in RAM Consumption. Above the box, a parade of `(◉)` dots (capped at 20, remainder summarized).

### bignum

The instance count in giant ANSI Shadow block digits (each glyph 9 columns wide) with a subtitle line of facts.

Note on width: these glyphs use East Asian Ambiguous characters (`█`, `╗`, `═`). Whether a terminal renders those one or two cells wide is a terminal setting, not something a locale reliably predicts; kitty, for instance, keeps them narrow even under `LC_ALL=zh_CN.UTF-8` (verified by cursor-position measurement). The renderer therefore always uses the outlined font and assumes the same ambiguous-is-narrow convention as the certificate box. Per-character rainbow coloring is unaffected by glyph width because ANSI codes are zero-width.

## Color discipline

- Colors only on a TTY, and never when `NO_COLOR` is set (silent) or `--no-color` is passed (with a "Coward." jab).
- Severity color ramps green → yellow → red → blink → rainbow with the tiers.

## Adding copy or a renderer

- New copy: add entries to the tier pool in `quips.py`. Any `{placeholder}` must exist on `QuipFacts`; `validate_copy()` (run by the test suite) checks placeholders, language/tier coverage, and rejects literal digits in multi-count tiers.
- New special count: add to `_SPECIAL_POOLS` + `SPECIAL_QUIPS`.
- New renderer: implement `QuipRenderer`, register in `RENDERERS`. The `--quip-style` choices pick it up automatically.

## Tests

- `tests/test_quips.py` — facts, tier boundaries, specials, RNG reproducibility, copy validation (including the hardcoded-digit guard).
- `tests/test_quip_render.py` — box border alignment in both languages (wide-char aware), digit-font integrity (uniform glyph widths), dot parade cap, both renderers, color/no-color.
- `tests/test_quip_cli.py` — flag wiring, `--quip`/`--json` rejection, exit code, locale resolution, style randomization, the `--no-color` jab.
