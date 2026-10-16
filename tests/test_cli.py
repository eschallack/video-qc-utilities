import json

from typer.testing import CliRunner

from video_qc.legacy_cli import app

runner = CliRunner()


def test_cli_help_and_missing_input(tmp_path):
    assert runner.invoke(app, ["--help"]).exit_code == 0
    result = runner.invoke(app, ["blur", str(tmp_path / "missing.mp4"), "--output", str(tmp_path / "out")])
    assert result.exit_code == 1
    assert "Failed" in result.output


def test_cli_json_contract(moving_video, tmp_path):
    output = tmp_path / "cli-result"
    result = runner.invoke(
        app, ["blur", str(moving_video), "--output", str(output), "--no-qc", "--json-progress"]
    )
    assert result.exit_code == 0, result.output
    events = [json.loads(line) for line in result.stdout.splitlines()]
    assert events[-1]["stage"] == "result"
    assert events[-1]["report"]["tracks"] >= 1
    assert events[-2]["stage"] == "complete"
    result = runner.invoke(app, ["check", str(moving_video)])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["loudness"]["integrated_lufs"] is not None


def test_cli_cancel_file(moving_video, tmp_path):
    marker = tmp_path / "cancel"
    marker.touch()
    result = runner.invoke(
        app, ["blur", str(moving_video), "--output", str(tmp_path / "out"), "--cancel-file", str(marker)]
    )
    assert result.exit_code == 130
    assert not (tmp_path / "out").exists()
    assert not list(tmp_path.glob(".video-qc-*"))
