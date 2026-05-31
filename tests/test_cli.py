import json
from pathlib import Path

from chrome_enumerator.cli import main


def make_file(path: Path, content: bytes = b"x", *, executable: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    if executable:
        path.chmod(path.stat().st_mode | 0o111)
    return path


def make_electron_app(root: Path) -> Path:
    app = root / "Desk.app"
    make_file(app / "Contents" / "MacOS" / "Desk", executable=True)
    make_file(app / "Contents" / "Frameworks" / "Electron Framework.framework" / "Resources" / "icudtl.dat")
    make_file(app / "Contents" / "Frameworks" / "Desk Helper.app" / "Contents" / "MacOS" / "Desk Helper", executable=True)
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
    assert str(app) in output
    assert "family: electron" in output
    assert "confidence: high" in output
    assert "evidence:" in output


def test_cli_can_include_low_confidence_candidates(tmp_path, capsys):
    make_file(tmp_path / "lonely" / "icudtl.dat")

    exit_code = main(["--json", "--include-low-confidence", str(tmp_path)])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert len(output) == 1
    assert output[0]["confidence"] == "low"
