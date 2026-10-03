# Architecture

`chromium-enumerator` is a small pure-Python package with one runtime dependency chain (`pefile`, optional, Windows-only) and no network or background behavior. Everything is synchronous and filesystem-local.

## Module map

| Module | Responsibility |
|---|---|
| `__init__.py` | Re-exports `main` from `cli.py`. The `chromium-count` console script declared in `pyproject.toml` points at `chromium_enumerator:main`. There is no `__main__.py`, so `python -m chromium_enumerator` is not supported. |
| `model.py` | `Evidence`, `RuntimeResult`, and the `EvidenceCategory` / `Confidence` literal types. No behavior. |
| `walk.py` | `FileInfo`, the `scandir`-based `walk_paths()`, and the single depth predicate (`depth_from`, `within_depth`). Every traversal in the project goes through this module. |
| `platforms.py` | Per-OS `PlatformProfile` implementations: evidence tables, path→root grouping, executability, metadata lookup, default roots, and seed-search vocabulary. |
| `registry.py` | Windows installed-software records (uninstall keys, App Paths, StartMenuInternet). No-ops off Windows. |
| `pe_metadata.py` | Windows PE `VS_VERSION_INFO` extraction via the optional `pefile` extra, plus the `CHROMIUM_COUNT_STUB_*` overrides. |
| `scanner.py` | `ChromiumScanner`: seed discovery, single-pass walking, grouping, scoring, size accounting, registry enrichment and filtering. |
| `cli.py` | `argparse` wiring, `main()`, text and JSON formatting, locale resolution, and glue into the quip layer. |
| `quips.py` | Quip facts, tone tiers, localized copy pools, RNG selection, copy validation. Data plus pure functions. |
| `quip_render.py` | Pluggable quip renderers (`QuipRenderer` protocol, `CertificateRenderer`, `BigNumberRenderer`). |

## Data model

```python
@dataclass(frozen=True)
class Evidence:
    category: Literal["engine", "electron-marker", "resource", "helper", "executable"]
    path: Path
    reason: str
    family_hint: str | None = None
```

`Evidence` is the atomic unit of detection: one classified path. `reason` is a short human-readable label; `family_hint` feeds family inference.

```python
@dataclass
class RuntimeResult:
    root: Path
    family: str
    confidence: Literal["high", "medium", "low"]
    evidence: list[Evidence]
    entrypoints: list[Path]
    metadata: dict[str, str]
    size_bytes: int
    registered_as: list[dict[str, str]]
```

`RuntimeResult` is the unit of reporting: one probable runtime. Both dataclasses have `to_dict()` used by `--json`. `Evidence` is frozen (hashable, comparable by value); `RuntimeResult` is mutable because registry enrichment appends to `registered_as` after construction.

`walk.FileInfo` carries the stat data the walker already paid for. Profile
methods accept it as an optional `info=` keyword (`classify_path`,
`runtime_root_for`, `is_executable`), which is what keeps a scan from issuing
several syscalls per file. Callers that have not walked the path omit it and
get one `stat`.

```python
@dataclass(frozen=True, slots=True)
class FileInfo:
    path: Path
    is_dir: bool
    is_file: bool
    is_link: bool
    size: int
    mode: int
```

## Data flow

```text
roots ──> ChromiumScanner.scan()
              │
              ├─ registry index (Windows; built once per scan)
              │
              ├─ per root: choose walk starts
              │    ├─ default: seed search (fd ─> find) ──> runtime_root_for()
              │    │           ──> candidate roots, nested ones dropped
              │    │           ──> [--registry-only] drop roots without a record
              │    └─ --exhaustive: the root itself
              │
              ├─ per start: ONE walk_paths() pass over the subtree
              │    ├─ evidence    ──> bucket of runtime_root_for(path)
              │    ├─ size        ──> same bucket
              │    └─ entrypoints ──> same bucket
              │
              ├─ drop buckets without evidence
              ├─ attach registry metadata (registered_as)
              ├─ filter low confidence unless requested
              └─ sort by root path string
                          │
                          ├─ cli.format_text()────> stdout
                          ├─ json.dumps(...)──────> stdout
                          └─ cli.format_quip()────> stdout
```

Invariants worth knowing:

- **Each walk start is traversed exactly once**, and every entry is attributed by `runtime_root_for()` to the result root that owns it. Evidence, entrypoints, and size all come out of that pass.
- **Overlapping starts are dropped.** Nested candidate roots, and nested scan roots passed on the command line, are skipped so bytes are never counted twice.
- **One depth predicate.** `walk.within_depth()` is the only definition of `--max-depth`, so discovery and verification cannot disagree about it.
- **Evidence is deduplicated** by `(category, path, reason)` before scoring and output.
- **Registry data never creates a result.** Results come only from evidence; the registry only enriches or filters.
- **Warnings are collected, not raised.** Traversal and tool errors land in `scanner.warnings`; the scan continues.
- **`main()` returns an int** rather than calling `sys.exit`, which is what makes CLI tests assert on exit codes.

## Extension points

### Adding a platform (Linux, …)

Implement the `PlatformProfile` protocol in `platforms.py` and register it in `profile_for_name()` / `current_profile()`. The protocol is structural (`typing.Protocol`), so no base class is required. A new profile must provide:

- `name`, `case_insensitive_names`, `library_suffixes`, `find_seed_command_supported`
- `seed_exact_names`, `seed_fd_names_regex`, `seed_extra_globs`
- `classify_path()`, `runtime_root_for()`, `is_executable()`, `read_metadata()`, `default_roots()`, `display_name_for()`
- optionally `registry_roots()` if the platform has a registry-like install database

`classify_path`, `runtime_root_for`, and `is_executable` take an optional
`info: FileInfo` keyword. Pass the walker's record so the profile does not stat
the path again; a profile that ignores it still works, just slower.

Then add the name to the `--platform` choices in `cli.py`. The scanner itself needs no changes; it is profile-agnostic. A Linux profile would additionally want the CLI platform choice and default roots, and probably a `.so`-oriented engine table.

### Adding evidence

Add the filename to the relevant table in `platforms.py` (`MACOS_ENGINE_NAMES`, `WINDOWS_ENGINE_NAMES`, `RESOURCE_NAMES`, `*_HELPER_NAMES`, …). If it introduces a new family, also add a `family_hint`. `seed_exact_names` and `seed_fd_names_regex` are derived from those tables for macOS/Windows, so a new engine name automatically becomes a seed.

If a new *category* is needed (not just a new name), extend `EvidenceCategory` in `model.py` and teach `_score_confidence()` in `scanner.py` how it counts.

### Adding an output format

Text and JSON are produced by `format_text()` and `json.dumps` in `cli.py`. A new format is a branch in `main()`; the data it needs is entirely in the `RuntimeResult` list.

### Adding quip styles or copy

See [quips.md](quips.md). Renderers implement `QuipRenderer` and register in `RENDERERS`; copy lives in `quips.py` data structures guarded by `validate_copy()`.

## Testing

Tests are organized by concern rather than by module:

| File | Scope | Runs on |
|---|---|---|
| `test_scanner.py` | macOS detection, grouping, depth, symlinks, size cap, discovery strategy, single-pass walking | POSIX hosts only (needs executable bits) |
| `test_platforms.py` | Profile primitives from pure paths: classification, flat-layout roots, family inference, stat reuse | Any host |
| `test_platform_windows.py` | Windows evidence tables, root grouping, family mapping | Any host (profile injected) |
| `test_registry.py` | Registry parsing, install-root resolution, `--registry-only` filtering and flag validation, enrichment | Any host (stub registry); one assertion is skipped on Windows itself |
| `test_cli.py` | Text/JSON output shapes | POSIX (fixtures use execute bits) |
| `test_quips.py`, `test_quip_render.py`, `test_quip_cli.py` | Quip layers | Any host |

Synthetic layouts are built in `tmp_path`; nothing touches the real machine. Windows suites work everywhere because `WindowsProfile` is passed explicitly instead of relying on `os.name`.

## Tooling and CI

Development dependencies live in the `dev` group in `pyproject.toml`: `pytest`, `ruff`, and `basedpyright`. The type checker is configured for `standard` mode with `pythonVersion = "3.14"`; the `recommended` mode's `reportAny`/`reportUnknown*`/`reportUnusedCallResult` families are disabled because the optional `pefile` import, the Windows-only `winreg` module, and the deliberately untyped test helpers are `Unknown` by nature here.

```sh
uv run ruff check .
uv run ruff format --check src tests
uv run basedpyright
uv run pytest
```

`.github/workflows/ci.yml` runs those four: a single Ubuntu job for lint, format, types, the lockfile check, and a CLI smoke test that asserts the quip exit-code contract, plus a `pytest` matrix over Ubuntu, macOS, and Windows. CI installs with `uv sync --locked` (and `--all-extras` for the test job) so the lockfile stays authoritative.
