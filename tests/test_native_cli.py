from video_qc import cli


def test_native_cli_passes_settings_and_paths(tmp_path, monkeypatch):
    executable = tmp_path / "video-qc"
    executable.touch()
    monkeypatch.setenv("URL_GUARD_ENGINE", str(executable))
    monkeypatch.setattr(
        cli.sys,
        "argv",
        ["video-qc", "blur", "/tmp/My Video.mp4", "--tracking-type", "perspective", "--feather", "12"],
    )
    calls = []
    monkeypatch.setattr(cli.subprocess, "call", lambda args: calls.append(args) or 0)
    assert cli.app() == 0
    assert calls[0] == [
        str(executable),
        "blur",
        "/tmp/My Video.mp4",
        "--tracking-type",
        "perspective",
        "--feather",
        "12",
    ]


def test_native_cli_failure_is_reported(monkeypatch, capsys):
    def missing():
        raise RuntimeError("missing native engine")

    monkeypatch.setattr(cli, "engine_executable", missing)
    monkeypatch.setattr(cli.sys, "argv", ["video-qc", "doctor"])
    assert cli.app() == 1
    assert "missing native engine" in capsys.readouterr().err
