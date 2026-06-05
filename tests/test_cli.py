import json
from pathlib import Path

from chrome_enumerator.cli import main


LARGE_RUNTIME_BYTES = 6 * 1024 * 1024


def make_file(path: Path, content: bytes = b"x", *, executable: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    if executable:
        path.chmod(path.stat().st_mode | 0o111)
    return path


def make_large_payload(root: Path) -> Path:
    payload = root / "Contents" / "Resources" / "large-runtime-payload.bin"
    payload.parent.mkdir(parents=True, exist_ok=True)
    with payload.open("wb") as payload_file:
        payload_file.truncate(LARGE_RUNTIME_BYTES)
    return payload


def make_electron_app(root: Path) -> Path:
    app = root / "Desk.app"
    make_file(app / "Contents" / "MacOS" / "Desk", executable=True)
    make_large_payload(app)
    make_file(
        app
        / "Contents"
        / "Frameworks"
        / "Electron Framework.framework"
        / "Resources"
        / "icudtl.dat"
    )
    make_file(
        app
        / "Contents"
        / "Frameworks"
        / "Desk Helper.app"
        / "Contents"
        / "MacOS"
        / "Desk Helper",
        executable=True,
    )
    return app


def test_cli_outputs_json_results(tmp_path, capsys):
    app = make_electron_app(tmp_path)

    exit_code = main(["--json", str(tmp_path)])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output[0]["root"] == str(app)
    assert output[0]["family"] == "electron"
    assert output[0]["confidence"] == "high"
    assert output[0]["evidence"]


def test_cli_outputs_human_readable_summary(tmp_path, capsys):
    app = make_electron_app(tmp_path)

    exit_code = main([str(tmp_path)])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Found 1 probable Chromium runtime" in output
    assert "electron: 1" in output
    assert "Desk.app — Electron, high confidence" in output
    assert str(app) in output
    assert "evidence:" not in output
    assert "entrypoints:" not in output


def test_cli_verbose_output_includes_identified_files(tmp_path, capsys):
    app = make_electron_app(tmp_path)

    exit_code = main(["--verbose", str(tmp_path)])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert str(app) in output
    assert "evidence:" in output
    assert "entrypoints:" in output
    assert "Electron Framework.framework" in output


def test_cli_can_include_low_confidence_candidates(tmp_path, capsys):
    make_file(tmp_path / "lonely" / "icudtl.dat")

    exit_code = main(["--json", "--include-low-confidence", str(tmp_path)])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert len(output) == 1
    assert output[0]["confidence"] == "low"
