# Detection and Classification

A **Chromium instance** here is a directory on disk that carries its own runnable Chromium-family engine — an Electron app, a CEF app, a QtWebEngine app, or a bundled Chromium-family browser. The scanner never executes application code and never runs the runtime; it reasons about filenames, directory shape, file sizes, and (on Windows) the registry.

There is no single universal static signature for "Chromium core", so detection is built from **evidence clusters**: several independent signals that together imply a runnable runtime payload.

## Evidence categories

`classify_path()` in each platform profile turns a filesystem path into an `Evidence` record, or returns `None` if the path means nothing. Every record has a category from `model.EvidenceCategory`:

| Category | Meaning | Examples |
|---|---|---|
| `engine` | A named Chromium engine artifact. The strongest signal. | `Electron Framework.framework`, `Chromium Embedded Framework.framework`, `Google Chrome Framework.framework`, `QtWebEngineCore.framework`, `libcef.dylib` (macOS); `libcef.dll`, `chrome.dll`, `Qt6WebEngineCore.dll`, `nw.dll` (Windows) |
| `electron-marker` | Windows-only Electron collateral DLLs. No single identifiable Electron engine file exists on Windows, so these stand in. | `ffmpeg.dll`, `libGLESv2.dll`, `libEGL.dll` |
| `resource` | Shared engine data files that ship inside Chromium payloads. | `icudtl.dat`, `resources.pak`, `chrome_100_percent.pak`, `v8_context_snapshot.bin`, `snapshot_blob.bin`, `devtools_resources.pak`, `qtwebengine_resources*.pak`, and any `*.pak` inside a `locales/` directory |
| `helper` | Sub-process / crashpad artifacts characteristic of Chromium and its embedders. | `chrome_crashpad_handler`, `crashpad_handler`, `QtWebEngineProcess.app` (macOS); `crashpad_handler.exe`, `QtWebEngineProcess.exe` (Windows); macOS also treats `* Helper.app` and `* Helper (*).app` as helpers |
| `executable` | A runnable entrypoint. | macOS: `Contents/MacOS/<name>` executables and framework executables (`Foo.framework/Foo`); Windows: any `*.exe` |

An evidence record also carries an optional `family_hint`, used later for family inference, and a human-readable `reason` string shown in `--verbose` output.

Isolated resource or helper files in unrelated directories produce `low` confidence and are hidden by default (see [Confidence](#confidence-scoring)), so a stray `icudtl.dat` in `~/Downloads` is not reported as a Chromium instance.

## Platform profiles

Detection rules live in `platforms.py` as classes implementing the `PlatformProfile` protocol. Two profiles ship today: `MacOSProfile` and `WindowsProfile`. The active profile is chosen from the host OS (`current_profile()`), or forced with `--platform macos|windows` (`profile_for_name()`), which lets you scan a mounted Windows drive from macOS or test Windows rules from any host.

A profile owns:

- the evidence tables (`classify_path`),
- how a piece of evidence maps back to a runtime root (`runtime_root_for`),
- what counts as an executable (`is_executable`),
- version/bundle metadata extraction (`read_metadata`),
- default scan roots (`default_roots`),
- the seed-search vocabulary (`seed_exact_names`, `seed_fd_names_regex`, `seed_extra_globs`, `case_insensitive_names`, `find_seed_command_supported`),
- optional registry integration (`registry_roots`, Windows only).

`classify_path`, `runtime_root_for`, and `is_executable` accept the walker's
`FileInfo` as an optional `info=` keyword. The scanner always passes it, so a
profiled method never re-stats a path the walk already statted.

### macOS

`MacOSProfile` matches names **case-sensitively**. Engines are the `.framework` directories and `libcef.dylib` listed above. Name matching is exact for engine, resource, and helper names; helper apps are matched by suffix (`* Helper.app`, `* Helper (*).app`).

Executability is the POSIX execute bit on a regular file.

### Windows

`WindowsProfile` matches names **case-insensitively** (all tables are lowercased at comparison time). Because Chromium browsers on Windows all ship the same `chrome.dll`, engine DLLs identify the *engine* but not the *browser*; the launcher executable name is what distinguishes Chrome, Edge, Brave, Vivaldi, and Opera. That mapping lives in `WINDOWS_FAMILY_BY_EXECUTABLE`:

| Launcher | Family |
|---|---|
| `chrome.exe` | `chrome` |
| `msedge.exe` | `edge` |
| `brave.exe` | `brave` |
| `vivaldi.exe` | `vivaldi` |
| `opera.exe`, `launcher.exe` | `opera` |
| `chromium.exe` | `chromium` |
| any other `*.exe` | `executable` evidence with no family hint |

`classify_path` treats *any* `*.exe` as `executable` evidence, so a Windows runtime root is usually recognized by "some exe" plus engine/resource evidence rather than by a specific launcher name.

Executability on Windows is "is a regular file with a `.exe` suffix" — there is no execute bit to consult.

## Grouping evidence into runtime roots

Raw evidence paths are scattered deep inside a bundle (`.../Frameworks/Electron Framework.framework/Resources/icudtl.dat`). Each evidence path is mapped to a single **runtime root** by `runtime_root_for()`, and all evidence mapping to the same root is grouped into one `RuntimeResult`.

**macOS** resolves, in order:

1. the **outermost enclosing `.app` bundle**, if any;
2. else the **outermost enclosing `.framework`**, if any;
3. else a flat-layout rule: payload directories (`bin`, `lib`, `Frameworks`, `Libraries`, `Resources`, `Contents`, `MacOS`, `Helpers`, `locales`) are transparent, and the root is the parent of the highest one on the path. So `cef/bin/deep/cefhost` and `cef/Contents/Resources/icudtl.dat` both belong to `cef`, while a file directly in a normal directory stays in that directory.

"Outermost" matters: a nested `Outer Helper.app` inside `Outer.app` groups under `Outer.app`, and nested helper bundles never become their own results.

**Windows** resolves, in order:

1. a **version-directory layout**: the leftmost path component named `Application` or `chrome-bin` becomes the root, so `.../Application/1.2.3/chrome.exe` groups under `.../Application` (the launcher sits one level above the version directory);
2. else a path component named `locales` → the directory above it;
3. else a file whose parent is named `resources` → two levels up;
4. else the containing directory (or the path itself if it is a directory).

Example, macOS Electron bundle:

```text
/Applications/Slack.app/Contents/Frameworks/Electron Framework.framework/Resources/icudtl.dat
    → engine:   Electron Framework.framework        family_hint=electron
    → resource: icudtl.dat
    → helper:   Slack Helper.app
    → executable: Contents/MacOS/Slack
    all group under root /Applications/Slack.app
```

Example, Windows CEF app:

```text
C:\Apps\MyApp\libcef.dll          → engine: libcef.dll          family_hint=cef
C:\Apps\MyApp\MyApp.exe           → executable                  (no hint)
C:\Apps\MyApp\icudtl.dat          → resource
    all group under root C:\Apps\MyApp
```

## Family inference

`infer_family()` picks one family label per runtime. Precedence, highest first:

1. **executable hints** — a `.exe` name like `msedge.exe`. On Windows this is the only signal that separates browsers that share `chrome.dll`.
2. **engine hints** — the framework/DLL that names the engine (`Electron Framework.framework` → `electron`, `Chromium Embedded Framework.framework` → `cef`, `QtWebEngineCore.framework` → `qtwebengine`, …). This outranks generic helper names, so a branded Electron app whose helper is just "Foo Helper.app" is still `electron`.
3. **any remaining hints**, by majority.
4. fallback **`chromium`** when no hint exists.

This is why `Google Chrome.app` reports `chrome` even though it also contains a `Google Chrome Helper.app`: the engine hint wins over the hint-less helper.

The reported family is a best-effort label; a customized runtime can be misclassified without being a false positive.

## Confidence scoring

`_score_confidence()` in `scanner.py` derives a level from the categories present and the discovered entrypoints:

| Level | Condition |
|---|---|
| `high` | executable evidence **and** strong engine evidence **and** (resource **or** helper evidence) |
| `medium` | executable evidence **and** at least two secondary signals |
| `low` | anything weaker |

Definitions used above:

- **executable evidence** = an `executable` category record, or any entrypoint discovered in the root.
- **strong engine evidence** = an `engine` record, **or** two or more *distinct* Electron marker DLLs (the Windows Electron substitute).
- **secondary signals** = any Electron marker present (even one), a resource, a helper.

So a single Electron marker DLL is not enough for `high`, but counts toward `medium`; two distinct markers count as a strong engine.

**Size sanity cap.** `_cap_confidence_for_size()` demotes `high`/`medium` to `low` when the runtime's total size is under 5 MiB (`_EXCEPTIONALLY_SMALL_RUNTIME_BYTES`), because realistic Chromium payloads are far larger and tiny layouts are usually test fixtures or incomplete leftovers. The cap is applied **only when neither `--max-depth` nor `--follow-symlinks` is in effect** — a bounded walk can under-measure size, so in those modes the size signal is considered unreliable and skipped.

`low` results are excluded from output unless `--include-low-confidence` is passed; `--json` obeys the same rule. Size-based demotion means small fixtures are surfaced (with that flag) rather than hard-excluded.

## Entrypoints and size

A result's entrypoints and bytes are accumulated during the same walk that
gathers its evidence, in `ChromiumScanner._collect()`. There is no second
pass over a runtime root.

- **entrypoints** — every regular file that is executable under the profile and whose suffix is not a library suffix. macOS skips `.dylib`/`.so`; Windows skips `.dll`, `.manifest`, `.dat`, `.bin`, `.pak`, `.json`, `.asar`, `.ico`, `.png`, `.sig`. Deduplicated and sorted.
- **size_bytes** — the sum of every regular file attributed to the root, including the library and resource files excluded from entrypoints.

**Ownership.** Every walked path is attributed to `runtime_root_for(path)`, and
a result owns exactly the files that resolve to it. A nested runtime is
reported separately and its bytes are not counted again in its parent. This
holds in both seed and exhaustive mode: the two modes differ only in which
subtrees they walk, not in how a path is attributed.

## Discovery strategy

Scanning has two modes. Both end up calling the same per-root evidence walk; they differ in how candidate roots are found.

### Default: targeted seed search

1. For each root, run a **native seed search** for known Chromium filenames (engine binaries, `.pak` resources, crashpad handlers, helper apps).
2. Translate each hit into a runtime root (`runtime_root_for`) and keep the distinct roots as **candidate roots**.
3. Walk each candidate root once in Python: evidence, entrypoints, and size all come out of that pass. Nested candidate roots are dropped first, so no subtree is walked twice.

Native tools used, in preference order:

- **`fd`** (or `fdfind`) when on `PATH` and symlink-following is off. Invoked with `-u` (unrestricted: no ignore files, hidden files included), `--absolute-path`, `-0` (NUL-separated), an optional `--max-depth <max_depth + 1>`, and an anchored alternation regex of the profile's seed names. Windows runs it case-insensitively via `(?i)`.
- **`find`**, macOS only. Invoked with `-P`/`-L`, an optional `-maxdepth <max_depth + 1>`, and a parenthesized `-name` alternation printed NUL-separated. Windows disables this fallback entirely because Windows ships an unrelated legacy `find.exe` (a grep), which would produce nonsense.
- **`walk.walk_paths`**, the project's own `scandir` walker, used when neither tool applies. That is always the case on Windows without `fd`.

The native search is given `max_depth + 1` as a margin; `walk.within_depth` then re-filters results in Python so the effective depth is what you asked for. The same predicate governs the verification walk, so discovery and verification cannot disagree about `--max-depth`. Symlinked paths are skipped unless `--follow-symlinks`, and broken symlinks are ignored rather than reported. Because `fd -u` consults no ignore files and the `scandir` walker does not either, **hidden and gitignored paths are always considered**; Spotlight/`mdfind` is deliberately not used because indexed search can omit files.

If the native search returns nothing, the scan simply finds no candidates for that root — it does not silently fall back to a full walk.

### `--exhaustive`

Skips seed discovery and walks every root with `walk.walk_paths`, classifying every path. Slower, but it will find layouts whose seed filenames are unusual. Useful for validating that the targeted search is not missing anything.

Both modes share the same walker, the same depth predicate, and the same
path→root attribution. They differ only in which subtrees they start from.

## Windows registry integration

On Windows the scanner additionally reads **installed-software records** from the registry (HKLM and HKCU, including the 32-bit `WOW6432Node` uninstall view):

| Source | Read from | Used for |
|---|---|---|
| Uninstall entries | `SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall` and the WOW6432Node counterpart | install location and display metadata |
| App Paths | `SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths` (subkeys ending in `.exe`) | the exe's parent directory |
| StartMenuInternet | `SOFTWARE\Clients\StartMenuInternet\<client>\shell\open\command` | the browser exe's parent directory |

An uninstall record's root comes from `InstallLocation` when it names an existing directory; otherwise from the `DisplayIcon` executable's parent, unless that executable looks like an uninstaller/setup stub (`uninstall`, `uninst`, `unins000`, `setup`, `update`, …). Registry strings may contain quotes, arguments, or icon indices, which `registry.parse_exe_path` strips. Only paths that exist on disk are kept. The whole index is built once per scan and is **empty on non-Windows hosts**.

Registry data is **never detection evidence**. It is used in exactly two ways:

1. **Enrichment** — for each result whose root equals, or lives under, a registry install directory, matching records are attached to `RuntimeResult.registered_as` (shortest match first), filtered to `DisplayName`, `DisplayVersion`, `Publisher`, and `source` (e.g. `HKLM\SOFTWARE\...`). In `--verbose` these print as `registered:` lines; `--json` includes them; the first record's `DisplayName` becomes the display name in text output.
2. **Filtering** — `--registry-only` drops candidate roots that have no registry ancestor, so only software the system knows it has installed is reported.

`--registry-only` requires the Windows profile and is rejected together with
`--exhaustive`, since an exhaustive scan builds no seed list to filter. Both
conditions are argparse errors (exit status 2) rather than silent no-ops.

## Metadata and display names

**macOS** reads `Contents/Info.plist` from the runtime root and keeps `CFBundleName`, `CFBundleDisplayName`, `CFBundleIdentifier`, `CFBundleShortVersionString`, `CFBundleVersion`, `CFBundleExecutable`.

**Windows** extracts `FileDescription`, `ProductName`, and `FileVersion` from the `VS_VERSION_INFO` resource of the first `*.exe` in the runtime root. This requires the optional `pefile` extra (`chromium-enumerator[windows-metadata]`); without it metadata is empty. Tests and dry runs can stub values with the `CHROMIUM_COUNT_STUB_FILEDESCRIPTION`, `CHROMIUM_COUNT_STUB_PRODUCTNAME`, and `CHROMIUM_COUNT_STUB_FILEVERSION` environment variables, which override extracted values.

Display names resolve as: the first `registered_as[0]["DisplayName"]` if present, else the profile's `display_name_for()` — macOS prefers `CFBundleDisplayName` then `CFBundleName`; Windows prefers `FileDescription` then `ProductName`, then `<family>.exe`'s stem, then the directory name.

Version *strings* are not extracted from macOS binaries or from arbitrary DLLs; only the Windows PE version resource and the macOS plist are consulted.

## Caveats and known limits

- **No archive or container inspection** — `.zip`, `.dmg`, `.pkg`, and `.asar` contents are not opened. A runtime shipped as an `.asar` payload with no loose engine evidence may be missed.
- **No code execution** — detection is entirely static.
- **Static false positives are possible** — a directory that merely resembles a Chromium layout can be reported. `low` results are hidden by default precisely for this reason.
- **Static false negatives are possible** — heavily repackaged or renamed runtimes whose engine artifacts no longer match the name tables will not be found. `--exhaustive` does not help if the names themselves are unknown; extending the profile tables is the fix.
- **Linux is not supported.** `platforms.py` is the extension point (see [architecture.md](architecture.md)).
- **`low` filtering and the size cap interact** — a genuinely small but real runtime is demoted to `low`; use `--include-low-confidence` to see it.
- **Warnings are collected, not printed.** `ChromiumScanner.warnings` records missing roots, skipped symlink roots, and traversal/tool errors; the CLI does not currently surface them. Library callers can read the attribute after `scan()`.
- **Results are sorted by root path** (string sort), independent of confidence or family.

## Code map

| Concern | Where |
|---|---|
| Evidence and result dataclasses | `src/chromium_enumerator/model.py` |
| Traversal, `FileInfo`, depth predicate | `src/chromium_enumerator/walk.py` |
| Platform profiles, evidence tables, root grouping, metadata | `src/chromium_enumerator/platforms.py` |
| Windows registry reads | `src/chromium_enumerator/registry.py` |
| Windows PE version metadata | `src/chromium_enumerator/pe_metadata.py` |
| Seed discovery, walking, grouping, scoring, size/entrypoint collection | `src/chromium_enumerator/scanner.py` |
| Text/JSON formatting, CLI | `src/chromium_enumerator/cli.py` |

## Tests

Detection behavior is covered by:

- `tests/test_scanner.py` — macOS layouts: Electron/CEF/QtWebEngine bundles, standalone frameworks, nested helpers, isolated resources, symlink and depth handling, the size demotion, hidden/gitignored candidates, single-pass walking, and that seed mode uses the native tool while `--exhaustive` skips it.
- `tests/test_platforms.py` — profile primitives from pure paths: classification, flat-layout root rules, family inference, and that classification reuses walker stat data.
- `tests/test_platform_windows.py` — Windows layouts and family mapping; hosted on any OS by injecting `WindowsProfile`.
- `tests/test_registry.py` — registry path parsing and install-root resolution, `--registry-only` filtering and flag validation, and `registered_as` enrichment with a stub registry.
- `tests/test_cli.py` — text and JSON output shapes.

POSIX-dependent suites are skipped on Windows hosts; Windows suites run anywhere because the profile is injected.
