# chrome-enumerator

## What This Does

`chrome-enumerator` is a macOS-focused CLI that statically scans unpacked filesystem contents for probable runnable Chromium-family runtime cores.

It is designed for the “how many Chromes are on this machine?” question: Electron apps, CEF apps, Chromium-browser-family bundles, QtWebEngine apps, and similar runtimes that carry their own Chromium engine payload.

## Quick Start

```sh
uv run chrome-enumerator /Applications ~/Applications
```

The default human-readable output summarizes counts by family and lists each probable runtime without dumping every matched file.

Show detailed evidence files and entrypoints:

```sh
uv run chrome-enumerator --verbose /Applications
```

Emit full structured JSON:

```sh
uv run chrome-enumerator --json /Applications /opt/homebrew
```

Include weak evidence clusters that are normally hidden:

```sh
uv run chrome-enumerator --include-low-confidence ~/Downloads
```

Limit recursion depth:

```sh
uv run chrome-enumerator --max-depth 6 /Applications
```

## How Detection Works

Chromium does not have one universal static signature. This scanner uses evidence clusters instead.

A high-confidence result usually has:

1. executable evidence, such as `Contents/MacOS/AppName` or helper executables;
2. engine evidence, such as `Electron Framework.framework`, `Chromium Embedded Framework.framework`, `QtWebEngineCore.framework`, or `libcef.dylib`;
3. resource or helper evidence, such as `icudtl.dat`, `resources.pak`, `locales/*.pak`, `chrome_crashpad_handler`, or `* Helper.app`.

Single isolated files are not counted by default because they are not enough to prove a directly runnable Chromium core.

## Confidence Levels

- `high`: executable + engine + resource/helper evidence.
- `medium`: executable + at least two secondary evidence categories.
- `low`: weak clusters, only shown with `--include-low-confidence`.

## Project Structure

```text
chrome-enumerator/
├── src/chrome_enumerator/
│   ├── cli.py          # argparse CLI and text/JSON formatting
│   ├── detectors.py    # path/name evidence classification
│   ├── model.py        # dataclasses for evidence and results
│   └── scanner.py      # filesystem walking, grouping, scoring, metadata, sizes
├── tests/              # pytest suite with synthetic macOS bundles
└── docs/superpowers/   # design spec and implementation plan
```

## Common Tasks

Run tests:

```sh
uv run pytest -v
```

Show CLI help:

```sh
uv run chrome-enumerator --help
```

Inspect why a runtime was identified:

```sh
uv run chrome-enumerator --verbose /Applications
```

Scan default macOS roots:

```sh
uv run chrome-enumerator
```

## Limitations

- Does not inspect archives such as `.zip`, `.dmg`, `.pkg`, or `.asar`.
- Does not execute application code.
- Does not yet extract Chromium versions from binary strings.
- Targets macOS filesystem layouts.
- Static detection can still produce false positives or miss heavily customized runtimes.
