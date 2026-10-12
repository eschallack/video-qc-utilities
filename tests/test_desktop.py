import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.mark.gui
def test_native_ui_and_engine_process(moving_video, tmp_path):
    pytest.importorskip("PySide6.QtWidgets")
    from PySide6.QtCore import QProcess
    from PySide6.QtWidgets import QApplication

    from video_qc.desktop import make_window

    app = QApplication.instance() or QApplication([])
    window = make_window(str(moving_video))
    output = tmp_path / "desktop-result"
    window.output.setText(str(output))
    window.qc.setChecked(False)
    window.show()
    app.processEvents()
    assert "#f5d547" in window.styleSheet()
    window.start_job()
    assert not window.start.isEnabled()
    assert window.process.waitForStarted(5000)
    assert window.process.waitForFinished(30000)
    app.processEvents()
    assert window.process.state() == QProcess.ProcessState.NotRunning
    assert window.bundle == Path(output)
    assert window.start.isEnabled() and window.reveal.isEnabled()
    assert window.progress.value() == 100
    assert window.view.currentIndex() == 1
    assert (output / "blurred.mp4").is_file()
    window.close()


@pytest.mark.gui
def test_desktop_cancellation(moving_video, tmp_path):
    pytest.importorskip("PySide6.QtWidgets")
    from PySide6.QtWidgets import QApplication

    from video_qc.desktop import make_window

    app = QApplication.instance() or QApplication([])
    window = make_window(str(moving_video))
    output = tmp_path / "cancelled-result"
    window.output.setText(str(output))
    window.start_job()
    assert window.process.waitForStarted(5000)
    window.cancel_job()
    assert window.process.waitForFinished(30000)
    app.processEvents()
    assert window.status.text() == "Cancelled."
    assert not output.exists()
    assert not list(tmp_path.glob(".video-qc-*"))
    assert not window.cancel_path.exists()
    window.close()
