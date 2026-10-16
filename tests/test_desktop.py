import pytest

from video_qc import desktop


def test_native_launcher_path_and_arguments(tmp_path, monkeypatch):
    app = tmp_path / "URL Guard.app"
    binary = app / "Contents/MacOS/URLGuard"
    binary.parent.mkdir(parents=True)
    binary.touch()
    monkeypatch.setenv("URL_GUARD_APP", str(app))
    monkeypatch.setattr(desktop.sys, "platform", "darwin")
    calls = []
    monkeypatch.setattr(desktop.subprocess, "Popen", lambda args: calls.append(args))
    desktop.main(["/tmp/Video with spaces.mp4"])
    assert calls == [[str(binary), "/tmp/Video with spaces.mp4"]]


def test_missing_native_app(tmp_path, monkeypatch):
    monkeypatch.setenv("URL_GUARD_APP", str(tmp_path / "missing.app"))
    with pytest.raises(RuntimeError, match="build_macos"):
        desktop.app_executable()
