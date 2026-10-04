import os
import subprocess
import sys

import pytest

from chromium_enumerator.cli import format_quip, main, resolve_lang
from tests.helpers import make_results


def test_quip_and_json_are_mutually_exclusive(capsys):
    with pytest.raises(SystemExit) as error:
        main(["--quip", "--json", "/nonexistent"])
    assert error.value.code == 2
    assert "mutually exclusive" in capsys.readouterr().err


def test_quip_renders_for_empty_scan_and_exits_zero(tmp_path, capsys):
    exit_code = main(
        [
            "--quip",
            "--no-color",
            "--lang",
            "en",
            "--quip-style",
            "certificate",
            str(tmp_path),
        ]
    )
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "DIAGNOSTIC CERTIFICATE" in out
    assert "0 instances" in out
    assert "\x1b" not in out


def test_quip_exit_code_matches_a_real_scan_count(tmp_path, capsys, monkeypatch):
    from chromium_enumerator import cli

    class FakeScanner:
        def __init__(self, **kwargs):
            pass

        def scan(self, roots):
            return make_results(42)

    monkeypatch.setattr(cli, "ChromiumScanner", FakeScanner)
    exit_code = main(
        ["--quip", "--no-color", "--lang", "en", "--quip-seed", "0", str(tmp_path)]
    )
    assert exit_code == 42
    assert "Electron" in capsys.readouterr().out


def test_explicit_no_color_adds_jab(tmp_path, capsys):
    main(["--quip", "--no-color", "--lang", "en", str(tmp_path)])
    assert "Coward" in capsys.readouterr().out


def test_lang_auto_resolution():
    assert resolve_lang("auto", {"LC_ALL": "zh_CN.UTF-8"}) == "zh"
    assert resolve_lang("auto", {"LC_ALL": "en_US.UTF-8"}) == "en"
    assert resolve_lang("auto", {"LC_ALL": "", "LC_MESSAGES": "zh_TW"}) == "zh"
    assert resolve_lang("auto", {}) == "en"
    assert resolve_lang("zh") == "zh"
    assert resolve_lang("en") == "en"


def test_zh_quip_output(tmp_path, capsys):
    main(
        [
            "--quip",
            "--no-color",
            "--lang",
            "zh",
            "--quip-style",
            "certificate",
            str(tmp_path),
        ]
    )
    assert "诊 断 证 书" in capsys.readouterr().out


def test_quip_count_skips_scan_and_renders_tier(capsys):
    exit_code = main(
        [
            "--quip",
            "--no-color",
            "--lang",
            "en",
            "--quip-count",
            "70",
            "--quip-style",
            "certificate",
        ]
    )
    assert exit_code == 70
    out = capsys.readouterr().out
    assert "70 instances" in out
    assert "Doom (1993)" in out


def test_auto_style_is_deterministic_for_a_seed():
    first = format_quip(10, lang="en", seed=3, style="auto", color=False)
    second = format_quip(10, lang="en", seed=3, style="auto", color=False)
    assert first == second


def test_auto_style_reaches_both_layouts():
    seen = set()
    for seed in range(30):
        out = format_quip(10, lang="en", seed=seed, style="auto", color=False)
        seen.add("certificate" if "CERTIFICATE" in out else "bignum")
    assert seen == {"bignum", "certificate"}


def test_explicit_style_wins_over_auto():
    out = format_quip(10, lang="en", seed=0, style="bignum", color=False)
    assert "CERTIFICATE" not in out
    assert "Chromium instances" in out

    out = format_quip(10, lang="en", seed=0, style="certificate", color=False)
    assert "CERTIFICATE" in out


def test_fabricated_size_varies_between_runs_but_tracks_the_seed():
    pinned = {
        format_quip(10, lang="en", seed=5, size_bytes=None, color=False)
        for _ in range(5)
    }
    assert len(pinned) == 1
    unpinned = {format_quip(10, lang="en", color=False) for _ in range(40)}
    assert len(unpinned) > 1


def test_quip_count_requires_quip_flag(capsys):
    with pytest.raises(SystemExit) as error:
        main(["--quip-count", "70"])
    assert error.value.code == 2
    assert "fake Chromium is still Chromium" in capsys.readouterr().err


def test_quip_count_rejects_verbose_and_negative(capsys):
    with pytest.raises(SystemExit):
        main(["--quip", "--verbose", "--quip-count", "5"])
    assert "no listing" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        main(["--quip", "--quip-count", "-1"])
    assert "zero or more" in capsys.readouterr().err


def test_quip_survives_a_non_utf8_console():
    # The certificate frame draws ◉, which a GBK code page cannot encode.
    # Strict encoding would turn the whole report into a traceback.
    env = {key: value for key, value in os.environ.items() if key != "PYTHONUTF8"}
    env["PYTHONIOENCODING"] = "gbk"
    script = (
        "import sys; from chromium_enumerator.cli import main; "
        "sys.exit(main(['--quip', '--no-color', '--lang', 'en', "
        "'--quip-style', 'certificate', '--quip-count', '5']))"
    )

    completed = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, env=env, check=False
    )

    assert completed.returncode == 5
    assert b"Traceback" not in completed.stderr
    assert b"CERTIFICATE" in completed.stdout


def test_stdout_without_reconfigure_is_tolerated(monkeypatch):
    class Plain:
        pass

    monkeypatch.setattr(sys, "stdout", Plain())

    from chromium_enumerator.cli import _configure_stdout

    _configure_stdout()  # must not raise


def test_quip_count_zero_renders_zero_tier(capsys):
    exit_code = main(
        [
            "--quip",
            "--no-color",
            "--lang",
            "zh",
            "--quip-count",
            "0",
            "--quip-style",
            "certificate",
        ]
    )
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "0 个 Chromium 内核" in out
    assert "难以置信" in out or "一个都没有" in out
