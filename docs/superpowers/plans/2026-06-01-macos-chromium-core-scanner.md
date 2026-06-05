# macOS Chromium Core Scanner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a macOS CLI that statically enumerates probable directly runnable Chromium-family runtime cores on disk.

**Architecture:** Implement a small Python package with separate model, detector, scanner, and CLI modules. The scanner walks filesystem roots, turns filename/path hits into categorized evidence, groups evidence into runtime roots, scores runnable confidence, extracts app metadata, and formats results as text or JSON.

**Tech Stack:** Python 3.14, standard library runtime, pytest for tests, uv for environment and command execution.

---

## File Structure

- Create `src/chromium_enumerator/model.py`: `Evidence`, `RuntimeResult`, and JSON conversion helpers.
- Create `src/chromium_enumerator/detectors.py`: pure functions that classify paths into evidence categories and infer runtime families.
- Create `src/chromium_enumerator/scanner.py`: `ChromiumScanner` with walking, grouping, scoring, metadata extraction, executable detection, and size calculation.
- Create `src/chromium_enumerator/cli.py`: argparse command, default roots, text output, and JSON output.
- Modify `src/chromium_enumerator/__init__.py`: delegate `main()` to `cli.main()`.
- Create `tests/test_detectors.py`: detector unit tests.
- Create `tests/test_scanner.py`: scanner behavior tests using fake macOS bundles.
- Create `tests/test_cli.py`: CLI JSON/text smoke tests.

### Task 1: Detector and model foundations

**Files:**
- Create: `tests/test_detectors.py`
- Create: `src/chromium_enumerator/model.py`
- Create: `src/chromium_enumerator/detectors.py`

- [ ] **Step 1: Write failing detector tests**

Create `tests/test_detectors.py` with tests that expect known Chromium-family files to classify into engine, resource, helper, and executable evidence.

- [ ] **Step 2: Run detector tests to verify RED**

Run: `uv run pytest tests/test_detectors.py -v`
Expected: FAIL because `chromium_enumerator.detectors` does not exist.

- [ ] **Step 3: Implement detector/model code**

Add dataclasses in `model.py` and path-classification functions in `detectors.py` sufficient to pass detector tests.

- [ ] **Step 4: Run detector tests to verify GREEN**

Run: `uv run pytest tests/test_detectors.py -v`
Expected: PASS.

### Task 2: Scanner grouping and confidence scoring

**Files:**
- Create: `tests/test_scanner.py`
- Create/modify: `src/chromium_enumerator/scanner.py`
- Modify: `src/chromium_enumerator/model.py`

- [ ] **Step 1: Write failing scanner tests**

Create synthetic app bundles under pytest `tmp_path` for Electron, CEF, QtWebEngine, nested helper grouping, and isolated resource exclusion.

- [ ] **Step 2: Run scanner tests to verify RED**

Run: `uv run pytest tests/test_scanner.py -v`
Expected: FAIL because `chromium_enumerator.scanner` does not exist.

- [ ] **Step 3: Implement scanner code**

Implement filesystem walking, runtime-root derivation, evidence grouping, confidence scoring, metadata extraction, executable collection, and size calculation.

- [ ] **Step 4: Run scanner tests to verify GREEN**

Run: `uv run pytest tests/test_scanner.py -v`
Expected: PASS.

### Task 3: CLI and output formats

**Files:**
- Create: `tests/test_cli.py`
- Create: `src/chromium_enumerator/cli.py`
- Modify: `src/chromium_enumerator/__init__.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Write failing CLI tests**

Test JSON output for a fake Electron app and text output containing root, family, confidence, and evidence summary.

- [ ] **Step 2: Run CLI tests to verify RED**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL because CLI behavior is not implemented.

- [ ] **Step 3: Implement CLI code**

Implement argparse options `roots`, `--json`, `--include-low-confidence`, `--max-depth`, and `--follow-symlinks`; add text and JSON formatting.

- [ ] **Step 4: Run CLI tests to verify GREEN**

Run: `uv run pytest tests/test_cli.py -v`
Expected: PASS.

### Task 4: Full verification and documentation polish

**Files:**
- Modify: `pyproject.toml`
- Create or modify: `README.md`

- [ ] **Step 1: Add project metadata and README test first if needed**

Run existing tests to reveal missing packaging or entrypoint issues before changing implementation.

- [ ] **Step 2: Polish package metadata and README**

Set a useful project description and document usage, detection model, confidence levels, and limitations.

- [ ] **Step 3: Run full verification**

Run: `uv run pytest -v`
Expected: PASS.

Run: `uv run chromium-count --help`
Expected: exit 0 and display CLI options.

## Plan Self-Review

- Spec coverage: scanning, grouping, scoring, metadata, JSON/text output, and safe walking are covered.
- Placeholder scan: no TBD/TODO placeholders remain.
- Type consistency: detector/model/scanner/CLI names are consistent across tasks.
