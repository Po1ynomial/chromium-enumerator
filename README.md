# chromium-enumerator

## What This Does

`chromium-count` is a CLI that statically scans unpacked filesystem contents for probable runnable Chromium-family runtime cores. It supports macOS and Windows layouts.

It is designed for the “how many Chromes are on this machine?” question: Electron apps, CEF apps, Chromium-browser-family bundles, QtWebEngine apps, and similar runtimes that carry their own Chromium engine payload.

## Install

Requires Python ≥ 3.14 and either [uv](https://docs.astral.sh/uv/) or [pipx](https://pipx.pypa.io/).

```sh
# with uv (recommended)
uv tool install git+https://github.com/Po1ynomial/chromium-enumerator

# with pipx
pipx install git+https://github.com/Po1ynomial/chromium-enumerator

# from a local checkout
uv tool install /path/to/chromium-enumerator
pipx install /path/to/chromium-enumerator
```

After install, `chromium-count` is available on your `$PATH`.

## Quick Start

```sh
chromium-count /Applications ~/Applications
```

Show detailed evidence files and entrypoints:

```sh
chromium-count --verbose /Applications
```

Emit full structured JSON:

```sh
chromium-count --json /Applications /opt/homebrew
```

Replace the report with a playful summary of your Chromium situation:

```sh
chromium-count --quip /Applications
```

`--quip` supports localized copy (`--lang zh`), alternate presentation styles
(`--quip-style bignum`), reproducible jokes (`--quip-seed`), and returns the
instance count as the exit code. The style is chosen randomly per run unless
you pin it. To preview any tier without enough Chromium on your machine, fake
it: `chromium-count --quip --quip-count 70`.
See [docs/quips.md](docs/quips.md).

Include weak evidence clusters that are normally hidden:

```sh
chromium-count --include-low-confidence ~/Downloads
```

Limit recursion depth:

```sh
chromium-count --max-depth 6 /Applications
```

Force an exhaustive Python `os.walk` scan instead of the default direct search:

```sh
chromium-count --exhaustive /Applications
```

Scan Windows-style layouts from any host (useful for mounted drives or testing):

```sh
chromium-count --platform windows /mnt/windows/Program\ Files
```

On Windows, restrict results to software registered in the registry (uninstall records, App Paths, StartMenuInternet):

```sh
chromium-count --registry-only
```

Windows results also carry registry metadata when the runtime matches an installed-program record; see `registered_as` in `--json` output or the `registered:` lines in `--verbose`.

## Documentation

- [docs/detection.md](docs/detection.md) — how instances are found, grouped, classified, and scored (evidence tables, runtime-root grouping, family inference, confidence, seed discovery, registry integration).
- [docs/cli.md](docs/cli.md) — full flag reference, output formats, exit codes, environment variables.
- [docs/architecture.md](docs/architecture.md) — module map, data model, data flow, extension points.
- [docs/quips.md](docs/quips.md) — the `--quip` presentation layer.

## How Detection Works (summary)

Chromium has no single universal static signature, so the scanner uses **evidence clusters**: an executable plus engine evidence (an `Electron Framework.framework` / `libcef.dll` / `QtWebEngineCore.framework` / two or more Electron marker DLLs) plus resource or helper evidence such as `icudtl.dat`, `resources.pak`, `locales/*.pak`, `chrome_crashpad_handler`, or `* Helper.app`. Isolated single files are not counted, because they do not prove a runnable Chromium core.

Evidence paths are grouped into a single **runtime root** per runtime: the outermost `.app` or `.framework` on macOS, and the version/browser install directory on Windows. A **family** label (`electron`, `cef`, `qtwebengine`, `chrome`, `edge`, `brave`, `opera`, `vivaldi`, `nwjs`, `chromium`) is inferred with executable hints outranking engine hints. See [docs/detection.md](docs/detection.md) for the full tables and algorithms.

Rules live in per-platform profiles (`platforms.py`), selected from the host OS unless `--platform` overrides it. By default the scanner uses native tools (`fd`, then macOS-only `find`) only to locate seed filenames, then verifies each candidate root with Python traversal; `--exhaustive` skips seeds and walks everything. On Windows, registry install records (uninstall keys under HKLM/HKCU including the 32-bit view, App Paths, StartMenuInternet) enrich results with `registered_as` metadata and enable `--registry-only` filtering, but are never detection evidence on their own.

## Confidence Levels

| Level | Condition |
|---|---|
| `high` | executable + engine + resource/helper evidence, with a plausible payload size |
| `medium` | executable + at least two secondary evidence signals |
| `low` | weak clusters, or an exceptionally tiny (< 5 MiB) layout; shown only with `--include-low-confidence` |

Tiny fixture-like layouts are demoted to `low` rather than hard-excluded, so `--include-low-confidence` and `--json` can still surface them. The size cap is skipped under `--max-depth`/`--follow-symlinks`, where measured size is unreliable. Details in [docs/detection.md](docs/detection.md#confidence-scoring).

## Project Structure

```text
chromium-enumerator/
├── src/chromium_enumerator/
│   ├── cli.py          # argparse CLI and text/JSON formatting
│   ├── detectors.py    # legacy macOS classify_path wrapper
│   ├── platforms.py    # per-OS evidence, root grouping, metadata, seed rules
│   ├── model.py        # dataclasses for evidence and results
│   ├── quips.py        # quip facts, tone tiers, and localized copy pools
│   ├── quip_render.py  # pluggable quip renderers (certificate, bignum)
│   └── scanner.py      # filesystem walking, grouping, scoring, metadata, sizes
├── tests/              # pytest suite with synthetic macOS and Windows layouts
└── docs/               # detection.md, cli.md, architecture.md, quips.md
```

## Common Tasks

Run tests:

```sh
uv run pytest -v
```

Lint and type check:

```sh
uv run ruff check .
uv run basedpyright
```

Show CLI help:

```sh
chromium-count --help
```

Inspect why a runtime was identified:

```sh
chromium-count --verbose /Applications
```

Run a full exhaustive traversal when validating direct-search results:

```sh
chromium-count --exhaustive /Applications
```

Scan default roots for the host platform (`/Applications` etc. on macOS, `Program Files` / `%LOCALAPPDATA%\Programs` on Windows):

```sh
chromium-count
```

## Limitations

Full list in [docs/detection.md](docs/detection.md#caveats-and-known-limits). The short version:

- Does not inspect archives such as `.zip`, `.dmg`, `.pkg`, or `.asar`.
- Does not execute application code.
- Does not extract Chromium versions from binary strings; only the macOS plist and the Windows PE version resource are read.
- Windows metadata (`ProductName`, `FileDescription`, `FileVersion`) requires the optional `pefile` extra (`chromium-enumerator[windows-metadata]`); without it, metadata is empty unless stubbed via `CHROMIUM_COUNT_STUB_*` environment variables. Registry `registered_as` metadata needs no extra but exists only on Windows.
- Linux layouts are not yet supported; the platform profile mechanism (`platforms.py`) is the extension point.
- Static detection can still produce false positives or miss heavily customized runtimes.
- `--registry-only` is ignored in `--exhaustive` mode.
