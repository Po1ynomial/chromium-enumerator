# CLI Reference

`chromium-count` is the single entrypoint (`chromium_enumerator.cli:main`). It scans directories for probable runnable Chromium-family runtimes and prints either a human-readable report or JSON.

```sh
chromium-count [options] [roots ...]
```

## Positional arguments

| Argument | Meaning |
|---|---|
| `roots` | Directories to scan. Any number, `~` is expanded. |

When no roots are given, platform defaults are used, filtered to those that exist:

- **macOS**: `/Applications`, `~/Applications`, `/opt/homebrew`, `/usr/local`
- **Windows**: `%ProgramFiles%`, `%ProgramFiles(x86)%`, `%LOCALAPPDATA%\Programs`

A missing root produces a warning on `ChromiumScanner.warnings` and is skipped; it is not a fatal error. A symlinked root is also skipped unless `--follow-symlinks` is set.

## Options

### Detection

| Flag | Default | Effect |
|---|---|---|
| `--platform {auto,macos,windows}` | `auto` | Which detection rules to use. `auto` follows the host OS. Forcing a platform lets you scan a mounted foreign filesystem. |
| `--include-low-confidence` | off | Include `low`-confidence evidence clusters, normally hidden. |
| `--max-depth N` | unlimited | Maximum directory depth to recurse below each scan root. The same predicate governs seed discovery and the verification walk. The native seed search is invoked with `max_depth + 1` as a margin and results are re-filtered in Python. |
| `--follow-symlinks` | off | Follow directory symlinks, and on Windows directory junctions and other reparse points, with cycle protection. Also disables the `fd` fast path and the size-based confidence cap. |
| `--exhaustive` | off | Walk every path instead of the targeted seed search. Slower; use to validate the default search. |
| `--registry-only` | off | Windows only: report only runtimes whose root matches an installed-program registry record. Requires `--platform windows`; rejected with `--exhaustive`. |

### Output

| Flag | Default | Effect |
|---|---|---|
| `--json` | off | Emit a JSON array instead of text. |
| `--verbose` | off | In text mode, show per-runtime metadata, registry records, entrypoints, and evidence. In `--quip` mode, keep the normal listing and print the quip after it. |

### Quip mode

See [quips.md](quips.md) for the full design. Summary of the flags:

| Flag | Default | Effect |
|---|---|---|
| `--quip` | off | Replace the report with a playful summary. Mutually exclusive with `--json`. Exit code becomes the instance count, capped at 255. |
| `--lang {auto,zh,en}` | `auto` | Quip language. `auto` reads `LC_ALL`, `LC_MESSAGES`, `LANG`; `zh*` gets Chinese, otherwise English. |
| `--quip-seed N` | random | Fix the RNG seed, reproducing both the copy and the presentation style. |
| `--quip-style {auto,certificate,bignum}` | `auto` | Presentation style. `auto` draws a renderer from the seeded RNG. |
| `--no-color` | off | Disable ANSI colors and print a jab. `NO_COLOR` and non-TTY output degrade silently instead. |
| `--quip-count N` | unset | Skip scanning entirely and render the quip for a fabricated machine with `N` instances. Requires `--quip`; rejected with `--verbose`; must be non-negative. |

Argument-combination errors are reported by argparse with exit status 2, using these exact messages:

- `--quip` with `--json` — `--quip and --json are mutually exclusive: jokes are for humans.`
- `--quip-count` without `--quip` — `--quip-count only makes sense with --quip: fake Chromium is still Chromium.`
- `--quip-count` with `--verbose` — `--quip-count skips scanning, so there is no listing for --verbose to show.`
- negative `--quip-count` — `--quip-count must be zero or more. Negative Chromium is a different diagnosis.`
- `--registry-only` with `--exhaustive` — `--registry-only cannot be combined with --exhaustive: an exhaustive scan builds no seed list to filter.`
- `--registry-only` without the Windows profile — `--registry-only needs a Windows registry: pass --platform windows.`

## Text output

```text
Found 3 probable Chromium runtimes

By family:
  cef: 1
  electron: 2

Runtimes:
  1. Slack — Electron, high confidence, 512.4 MB
     /Applications/Slack.app
  2. ...
```

- The header uses the singular "runtime" for exactly one result.
- "By family" lists each family with its count, sorted by name.
- Each runtime line is `Name — Family, confidence confidence, size`. Size is omitted when zero.
- Family display names are naive title-casing with one special case: `electron` → `Electron`, `chrome` → `Chrome`, `chromium` → `Chromium`, `edge` → `Edge`, `brave` → `Brave`, `opera` → `Opera`, `vivaldi` → `Vivaldi`, `cef` → `Cef`, `nwjs` → `Nwjs`, and `qtwebengine` → `QtWebEngine`. The acronym families (`Cef`, `Nwjs`) are not upper-cased; the JSON `family` field always carries the raw lowercase identifier.
- `Name` comes from the first registry `DisplayName` if present, else platform metadata (`CFBundleDisplayName`/`CFBundleName` on macOS, `FileDescription`/`ProductName` on Windows), else the directory name.
- `--verbose` adds, per runtime: a `metadata:` line, one `registered:` line per registry record, an `entrypoints:` list, and an `evidence:` list of `category: reason (path)`.
- With no results the output is exactly `No probable Chromium runtimes found.`

## JSON output

A JSON array with one object per runtime, `indent=2`, keys sorted:

```json
[
  {
    "confidence": "high",
    "entrypoints": ["/Applications/Slack.app/Contents/MacOS/Slack"],
    "evidence": [
      {
        "category": "engine",
        "family_hint": "electron",
        "path": "/Applications/Slack.app/Contents/Frameworks/Electron Framework.framework",
        "reason": "Electron Framework.framework"
      }
    ],
    "family": "electron",
    "metadata": {"CFBundleName": "Slack"},
    "registered_as": [],
    "root": "/Applications/Slack.app",
    "size_bytes": 537232384
  }
]
```

Notes:

- `evidence` entries always carry `category`, `path`, `reason`, and `family_hint` (which may be `null`).
- `metadata` is an object of string values (may be empty).
- `registered_as` is a list of registry record objects (Windows only; empty elsewhere).
- `size_bytes` is a raw integer; the text formatter is what humanizes units.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Normal completion (text, JSON, or `--verbose`). |
| `2` | Argument error, including the rejected flag combinations above. |
| `N` | In `--quip` mode, the instance count, capped at 255. |

## Environment variables

| Variable | Effect |
|---|---|
| `NO_COLOR` | Any value disables ANSI colors in quip mode, silently. |
| `LC_ALL`, `LC_MESSAGES`, `LANG` | Read by `--lang auto` to pick Chinese or English copy; first non-empty wins. |
| `CHROMIUM_COUNT_STUB_FILEDESCRIPTION` | Windows: stub `FileDescription` metadata (overrides extracted value). |
| `CHROMIUM_COUNT_STUB_PRODUCTNAME` | Windows: stub `ProductName` metadata. |
| `CHROMIUM_COUNT_STUB_FILEVERSION` | Windows: stub `FileVersion` metadata. |
| `ProgramFiles`, `ProgramFiles(x86)`, `LOCALAPPDATA` | Windows: used to build default scan roots. |

`--no-color` and `NO_COLOR` differ in tone only: the explicit flag prints a "Coward." jab, the environment variable does not.

Text output is encoded with the interpreter's stdout encoding. Characters the code page cannot represent are written as `?` instead of raising, so `--quip` still works on a GBK console that cannot encode the certificate renderer's `◉`. Set `PYTHONUTF8=1` or switch the console to UTF-8 to see them. `--json` escapes non-ASCII, so it is never affected.

## Examples

```sh
# scan the default roots for this platform
chromium-count

# scan two specific directories
chromium-count /Applications ~/Applications

# full evidence dump for one app
chromium-count --verbose /Applications/Slack.app

# machine-readable output, low-confidence included
chromium-count --json --include-low-confidence ~/Downloads

# validate the targeted search against a full walk
chromium-count --exhaustive /Applications

# Windows layout from a non-Windows host
chromium-count --platform windows /mnt/windows/Program\ Files

# only software the registry knows about (Windows profile required)
chromium-count --platform windows --registry-only

# the playful report, pinned so it is reproducible
chromium-count --quip --lang zh --quip-seed 7 /Applications

# preview a tier without owning that many runtimes
chromium-count --quip --quip-count 70
```

## Library use

`main()` returns the exit code instead of calling `sys.exit`, so it is testable and embeddable. For programmatic scanning, use `ChromiumScanner` directly:

```python
from pathlib import Path
from chromium_enumerator.scanner import ChromiumScanner
from chromium_enumerator.platforms import WindowsProfile

scanner = ChromiumScanner(profile=WindowsProfile(), include_low_confidence=True)
results = scanner.scan([Path("/mnt/windows/Program Files")])
for result in results:
    print(result.root, result.family, result.confidence)

print(scanner.warnings)  # missing roots, traversal errors, tool failures
```

See [architecture.md](architecture.md) for the data model.
