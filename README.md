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

## How Detection Works

Chromium does not have one universal static signature. This scanner uses evidence clusters instead.

A high-confidence result usually has:

1. executable evidence, such as `Contents/MacOS/AppName` on macOS or `AppName.exe` on Windows;
2. engine evidence, such as `Electron Framework.framework`, `Chromium Embedded Framework.framework`, or `QtWebEngineCore.framework` on macOS, and `libcef.dll`, `chrome.dll`, `Qt6WebEngineCore.dll`, or two or more Electron marker DLLs (`ffmpeg.dll`, `libGLESv2.dll`, `libEGL.dll`) on Windows;
3. resource or helper evidence, such as `icudtl.dat`, `resources.pak`, `locales/*.pak`, `chrome_crashpad_handler`/`crashpad_handler.exe`, or `* Helper.app`.

Single isolated files are not counted by default because they are not enough to prove a directly runnable Chromium core.

Detection rules live in per-platform profiles (`platforms.py`); the active profile is chosen from the host OS unless `--platform` overrides it. On Windows, install records from the registry (uninstall keys under HKLM/HKCU including the 32-bit view, App Paths, and StartMenuInternet clients) additionally enrich results with `registered_as` metadata and enable `--registry-only` filtering; registry data is never treated as detection evidence on its own.

By default, the scanner uses native tools only for direct seed discovery: it asks `fd` when available, then (on macOS only) `find`, to locate known Chromium target filenames such as engine binaries, `.pak` resources, crashpad handlers, and helper apps. It then merges those seed paths into probable runtime roots and verifies each candidate root with Python traversal. On Windows the POSIX `find` fallback is disabled (Windows ships an unrelated legacy `find.exe`); without `fd`, seed discovery falls back to `os.walk`. Windows filename matching is case-insensitive.

Use `--exhaustive` to skip seed discovery and scan every path with Python `os.walk`. Hidden files and gitignored paths are considered in both modes: `fd` is invoked unrestricted for seed search, `find` includes those paths by default, and `os.walk` does not consult ignore files. Spotlight/`mdfind` is not used as authoritative input because indexed search can omit files.

## Confidence Levels

- `high`: executable + engine + resource/helper evidence, with a plausible runtime payload size.
- `medium`: executable + at least two secondary evidence categories.
- `low`: weak clusters or exceptionally tiny realistic-looking layouts, only shown with `--include-low-confidence`.

Tiny app/test fixture layouts are demoted to `low` instead of hard-excluded, so `--include-low-confidence` and `--json` can still show them when needed.

## Project Structure

```text
chromium-enumerator/
├── src/chromium_enumerator/
│   ├── cli.py          # argparse CLI and text/JSON formatting
│   ├── detectors.py    # legacy macOS classify_path wrapper
│   ├── platforms.py    # per-OS evidence, root grouping, metadata, seed rules
│   ├── model.py        # dataclasses for evidence and results
│   └── scanner.py      # filesystem walking, grouping, scoring, metadata, sizes
├── tests/              # pytest suite with synthetic macOS and Windows layouts
└── docs/superpowers/   # design spec and implementation plan
```

## Common Tasks

Run tests:

```sh
uv run pytest -v
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

- Does not inspect archives such as `.zip`, `.dmg`, `.pkg`, or `.asar`.
- Does not execute application code.
- Does not yet extract Chromium versions from binary strings.
- Windows metadata (ProductName, FileDescription, FileVersion) requires the optional `pefile` extra (`chromium-enumerator[windows-metadata]`); without it, metadata is empty unless stubbed via `CHROMIUM_COUNT_STUB_*` environment variables. Registry `registered_as` metadata requires no extra dependencies but only exists on Windows.
- Linux layouts are not yet supported; the platform profile mechanism (`platforms.py`) is the extension point.
- Static detection can still produce false positives or miss heavily customized runtimes.
- Exceptionally small candidates are treated as likely fixtures/incomplete leftovers and demoted to low confidence.
