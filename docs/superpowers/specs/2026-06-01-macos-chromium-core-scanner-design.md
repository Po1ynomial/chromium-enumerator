# macOS Chromium Core Scanner Design

## Goal

Build a macOS-focused command-line scanner that statically enumerates unpacked, directly usable Chromium-family runtime cores on disk. It should find Electron, CEF, Chromium-browser-family, QtWebEngine, and NW.js-style installations by evidence clusters rather than by package manager inventory or running processes.

## Scope

In scope:

- Scan filesystem contents directly, without opening archives such as `.zip`, `.dmg`, `.pkg`, or `.asar`.
- Accept one or more scan roots from the CLI.
- Walk directories safely, handling permission errors and broken links.
- Detect likely runnable Chromium cores using a multi-signal model.
- Group file-level hits into runtime roots such as outer `.app` bundles, framework bundles, or runtime directories.
- Report runtime family, confidence, evidence, executable entrypoints, metadata, and estimated disk size.
- Emit both human-readable text and JSON.

Out of scope for the first implementation:

- Scanning inside archives or mounted disk images.
- Launching binaries or executing application code.
- Full Chromium version extraction from binary strings.
- Windows or Linux support.
- Browser profile/cache enumeration.

## Detection Model

A candidate runtime root is considered a probable directly usable Chromium core only when it has evidence from multiple categories:

- **Executable evidence:** an executable file under `Contents/MacOS`, an executable framework binary, a helper app executable, `chrome_crashpad_handler`, `crashpad_handler`, or `QtWebEngineProcess`.
- **Engine evidence:** known Chromium-family framework or library names such as `Electron Framework.framework`, `Chromium Embedded Framework.framework`, `Google Chrome Framework.framework`, `Chromium Framework.framework`, `Microsoft Edge Framework.framework`, `Brave Browser Framework.framework`, `Opera Framework.framework`, `Vivaldi Framework.framework`, `QtWebEngineCore.framework`, `nwjs Framework.framework`, or `libcef.dylib`.
- **Runtime resource evidence:** common Chromium/CEF/Electron/QtWebEngine resource payloads such as `icudtl.dat`, `resources.pak`, `chrome_100_percent.pak`, `chrome_200_percent.pak`, `v8_context_snapshot.bin`, `snapshot_blob.bin`, `natives_blob.bin`, `locales/*.pak`, `qtwebengine_resources.pak`, or `devtools_resources.pak`.
- **Helper evidence:** helper apps and subprocess tools such as `* Helper.app`, `* Helper (Renderer).app`, `* Helper (GPU).app`, `chrome_crashpad_handler`, `crashpad_handler`, and `QtWebEngineProcess.app`.

Confidence levels:

- **High:** executable evidence plus engine evidence, with either runtime resource evidence or helper evidence.
- **Medium:** executable evidence plus at least two of engine, resource, or helper evidence.
- **Low:** non-runnable or weak clusters are tracked internally but excluded from normal output unless `--include-low-confidence` is passed.

Single isolated files such as `icudtl.dat`, `.pak` files, source-code mentions, headers, logs, browser profiles, or package metadata are not enough to count as a runnable Chromium core.

## Runtime Grouping

For each evidence hit, the scanner derives a runtime root using these rules:

1. If the path is inside one or more `.app` bundles, group under the outermost `.app` bundle. This prevents nested helper apps from being reported separately from their parent app.
2. Else if the path is inside a `.framework`, group under that framework bundle.
3. Else group under the nearest directory that contains a known engine library/resource cluster.

This produces runtime-level output rather than raw file hits.

## CLI Design

Command examples:

```sh
chrome-enumerator /Applications ~/Applications
chrome-enumerator --json /Applications /opt/homebrew
chrome-enumerator --include-low-confidence --max-depth 8 ~/Downloads
```

Options:

- positional `roots`: directories to scan. Defaults to `/Applications`, `~/Applications`, `/opt/homebrew`, and `/usr/local` when they exist.
- `--json`: emit structured JSON.
- `--include-low-confidence`: include weak candidates that do not meet the default probable-runnable threshold.
- `--max-depth N`: optional recursion depth limit.
- `--follow-symlinks`: follow directory symlinks. Disabled by default.

## Output Model

Each result contains:

- `root`: runtime root path.
- `family`: best-effort family such as `electron`, `cef`, `chrome`, `edge`, `brave`, `opera`, `vivaldi`, `qtwebengine`, `nwjs`, or `chromium`.
- `confidence`: `high`, `medium`, or `low`.
- `evidence`: evidence items with category, matched path, and reason.
- `entrypoints`: executable files that make the runtime plausibly runnable.
- `metadata`: app bundle fields from `Info.plist` when available.
- `size_bytes`: total size under the runtime root.

## Architecture

The implementation is a small Python package using only the standard library at runtime.

Files:

- `src/chrome_enumerator/model.py`: dataclasses and enums for evidence and scan results.
- `src/chrome_enumerator/detectors.py`: filename/path-based Chromium evidence detection.
- `src/chrome_enumerator/scanner.py`: filesystem walking, grouping, scoring, metadata extraction, and size calculation.
- `src/chrome_enumerator/cli.py`: argparse CLI and output formatting.
- `src/chrome_enumerator/__init__.py`: package entrypoint that delegates to the CLI.
- `tests/`: pytest suite using synthetic macOS-style bundles in temporary directories.

## Error Handling

- Permission errors are skipped and recorded as warnings in scanner state, but do not abort the scan.
- Broken symlinks are ignored.
- Invalid or unreadable `Info.plist` files yield empty metadata.
- Size calculation skips unreadable files.

## Testing Strategy

Use pytest with synthetic directory trees to verify:

- Electron app bundles are detected as high confidence.
- CEF app bundles are detected as high confidence.
- QtWebEngine app bundles are detected as high confidence.
- Nested helper apps are grouped under the outer application bundle.
- Isolated resource files are excluded by default.
- JSON output contains stable, serializable result fields.
- Permission and missing-file edge cases do not crash the scanner.

## Spec Self-Review

- No placeholders remain.
- Scope is limited to one CLI scanner and excludes archive/binary deep scanning.
- The detection model aligns with the user requirement: unpacked contents only, directly runnable/functioning in a broad static sense.
- Ambiguity around “Chromium core” is resolved by requiring evidence clusters instead of single signatures.
