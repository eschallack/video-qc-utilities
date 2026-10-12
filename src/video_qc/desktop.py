"""Optional Qt desktop shell. Engine runs in a cancellable child process."""

import json
import sys
import tempfile
import uuid
from pathlib import Path

STYLE = """
QWidget { background: #111214; color: #ededeb; font-family: 'Inter', 'Segoe UI', sans-serif; font-size: 13px; }
QFrame#Sidebar { background: #090a0b; border-right: 1px solid #292a2d; }
QLabel#Brand { color: #f5d547; font-size: 23px; font-weight: 800; }
QLabel#Eyebrow { color: #f5d547; font-size: 11px; font-weight: 700; }
QLabel#Title { font-size: 32px; font-weight: 700; }
QLabel#Muted { color: #92949b; }
QFrame#Card { background: #191a1d; border: 1px solid #303136; border-radius: 12px; }
QFrame#Card QLabel { background: transparent; }
QPushButton { background: #242529; border: 1px solid #38393e; border-radius: 7px; padding: 11px 16px; font-weight: 600; }
QPushButton:hover { border-color: #f5d547; }
QPushButton#Primary { background: #f5d547; color: #111214; border: 0; }
QPushButton:disabled { color: #696b72; background: #242529; border-color: #303136; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { background: #0e0f11; border: 1px solid #38393e; border-radius: 6px; padding: 9px; selection-background-color: #b79921; }
QLineEdit:focus { border-color: #f5d547; }
QCheckBox { spacing: 9px; }
QProgressBar { background: #27282c; border: 0; border-radius: 4px; height: 8px; color: transparent; }
QProgressBar::chunk { background: #f5d547; border-radius: 4px; }
QPlainTextEdit { background: #0d0e10; border: 1px solid #303136; border-radius: 7px; color: #aaaeb7; font-family: monospace; font-size: 11px; }
QSlider::groove:horizontal { height: 4px; background: #33353b; }
QSlider::handle:horizontal { width: 12px; margin: -4px 0; border-radius: 6px; background: #f5d547; }
"""


def make_window(source=None):
    from PySide6.QtCore import QProcess, Qt, QUrl
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PySide6.QtMultimediaWidgets import QVideoWidget
    from PySide6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QFileDialog,
        QFrame,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QPlainTextEdit,
        QProgressBar,
        QPushButton,
        QSlider,
        QSpinBox,
        QVBoxLayout,
        QWidget,
    )

    class Window(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("URL Detect & Blur · Video QC")
            self.resize(1180, 820)
            self.setMinimumSize(980, 730)
            self.setStyleSheet(STYLE)
            self.buffer = b""
            self.stderr = b""
            self.bundle = None
            self.cancelled = False
            self.cancel_path = None
            self.process = QProcess(self)
            self.process.readyReadStandardOutput.connect(self.read_progress)
            self.process.readyReadStandardError.connect(self.read_errors)
            self.process.finished.connect(self.finished)
            self.process.errorOccurred.connect(self.process_error)
            root = QWidget()
            self.setCentralWidget(root)
            layout = QHBoxLayout(root)
            layout.setContentsMargins(0, 0, 0, 0)
            sidebar = QFrame(objectName="Sidebar")
            sidebar.setFixedWidth(210)
            nav = QVBoxLayout(sidebar)
            nav.setContentsMargins(24, 35, 24, 28)
            nav.addWidget(QLabel("▧  URL Detect & Blur", objectName="Brand"))
            nav.addWidget(QLabel("VIDEO QC", objectName="Muted"))
            nav.addSpacing(45)
            nav.addWidget(QLabel("●   URL redaction", objectName="Eyebrow"))
            nav.addStretch()
            nav.addWidget(QLabel("Github @eschallack", objectName="Muted"))
            nav.addSpacing(18)
            nav.addWidget(QLabel("v0.1  /  CORE", objectName="Muted"))
            layout.addWidget(sidebar)
            main = QVBoxLayout()
            main.setContentsMargins(28, 25, 28, 20)
            layout.addLayout(main, 1)
            main.addWidget(QLabel("DELIVERY PREP  /  01", objectName="Eyebrow"))
            main.addWidget(QLabel("Detect & Blur URLs", objectName="Title"))
            # main.addWidget(
            #     QLabel(
            #         "Export editable masks.", objectName="Muted"
            #     )
            # )
            main.addSpacing(14)
            card = QFrame(objectName="Card")
            inputs = QVBoxLayout(card)
            inputs.setContentsMargins(18, 16, 18, 16)
            source_row = QHBoxLayout()
            self.source = QLineEdit(str(source or ""))
            self.source.setPlaceholderText("Choose a video file…")
            self.browse = QPushButton("Browse")
            self.browse.clicked.connect(self.choose_source)
            source_row.addWidget(self.source, 1)
            source_row.addWidget(self.browse)
            inputs.addWidget(QLabel("SOURCE VIDEO", objectName="Eyebrow"))
            inputs.addLayout(source_row)
            self.output = QLineEdit()
            self.output.setPlaceholderText("New result folder — video, tracking, Fusion masks, QC")
            inputs.addWidget(self.output)
            controls = QHBoxLayout()
            controls.addWidget(QLabel("Scan every"))
            self.interval = QSpinBox()
            self.interval.setRange(1, 60)
            self.interval.setValue(8)
            self.interval.setSuffix(" frames")
            controls.addWidget(self.interval)
            controls.addWidget(QLabel("Blur"))
            self.sigma = QSpinBox()
            self.sigma.setRange(5, 100)
            self.sigma.setValue(18)
            controls.addWidget(self.sigma)
            self.qc = QCheckBox("Run QC checks")
            self.qc.setChecked(True)
            controls.addWidget(self.qc)
            controls.addStretch()
            inputs.addLayout(controls)
            main.addWidget(card)
            self.video = QVideoWidget()
            self.video.setMinimumHeight(200)
            self.player = QMediaPlayer(self)
            self.audio = QAudioOutput(self)
            self.audio.setVolume(0.5)
            self.player.setAudioOutput(self.audio)
            self.player.setVideoOutput(self.video)
            main.addWidget(self.video, 1)
            playback = QHBoxLayout()
            self.play = QPushButton("Play / pause")
            self.play.clicked.connect(self.toggle_play)
            playback.addWidget(self.play)
            self.seek = QSlider(Qt.Orientation.Horizontal)
            self.seek.sliderMoved.connect(self.player.setPosition)
            self.player.positionChanged.connect(self.seek.setValue)
            self.player.durationChanged.connect(lambda ms: self.seek.setRange(0, ms))
            playback.addWidget(self.seek, 1)
            self.view = QComboBox()
            self.view.addItems(["Original", "Blurred render"])
            self.view.currentIndexChanged.connect(self.load_preview)
            playback.addWidget(self.view)
            main.addLayout(playback)
            self.status = QLabel("Ready · review every render before delivery.", objectName="Muted")
            main.addWidget(self.status)
            self.progress = QProgressBar()
            self.progress.setValue(0)
            main.addWidget(self.progress)
            self.log = QPlainTextEdit()
            self.log.setReadOnly(True)
            self.log.setMaximumHeight(85)
            self.log.document().setMaximumBlockCount(200)
            main.addWidget(self.log)
            actions = QHBoxLayout()
            self.reveal = QPushButton("Open result folder")
            self.reveal.setEnabled(False)
            self.reveal.clicked.connect(
                lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.bundle)))
            )
            actions.addWidget(self.reveal)
            actions.addStretch()
            self.cancel = QPushButton("Cancel")
            self.cancel.setEnabled(False)
            self.cancel.clicked.connect(self.cancel_job)
            actions.addWidget(self.cancel)
            self.start = QPushButton("Analyze & render  →", objectName="Primary")
            self.start.clicked.connect(self.start_job)
            actions.addWidget(self.start)
            main.addLayout(actions)
            self.source.editingFinished.connect(self.source_changed)
            if source:
                self.source_changed()

        def choose_source(self):
            name, _ = QFileDialog.getOpenFileName(
                self, "Choose video", "", "Video (*.mp4 *.mov *.mkv *.mxf *.avi);;All files (*)"
            )
            if name:
                self.source.setText(name)
                self.source_changed()

        def source_changed(self):
            path = Path(self.source.text())
            if path.is_file():
                destination = path.with_name(path.stem + "_qc")
                n = 2
                while destination.exists():
                    destination = path.with_name(path.stem + f"_qc_{n}")
                    n += 1
                self.output.setText(str(destination))
                self.bundle = None
                self.view.setCurrentIndex(0)
                self.reveal.setEnabled(False)
                self.load_preview()

        def load_preview(self):
            if self.view.currentIndex() == 1:
                if not self.bundle:
                    self.view.setCurrentIndex(0)
                    return
                path = self.bundle / "blurred.mp4"
            else:
                path = Path(self.source.text())
            if path.is_file():
                self.player.setSource(QUrl.fromLocalFile(str(path.resolve())))

        def toggle_play(self):
            if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                self.player.pause()
            else:
                self.player.play()

        def set_busy(self, busy):
            for widget in [
                self.source,
                self.output,
                self.browse,
                self.interval,
                self.sigma,
                self.qc,
                self.start,
            ]:
                widget.setEnabled(not busy)
            self.cancel.setEnabled(busy)

        def start_job(self):
            if not Path(self.source.text()).is_file() or not self.output.text().strip():
                QMessageBox.warning(
                    self, "Choose source and output", "Choose a video and a new result folder."
                )
                return
            if Path(self.output.text()).exists():
                QMessageBox.warning(self, "Folder already exists", "Choose a new result folder.")
                return
            self.bundle = None
            self.reveal.setEnabled(False)
            self.cancelled = False
            self.cancel_path = Path(tempfile.gettempdir()) / ("video-qc-cancel-" + uuid.uuid4().hex)
            self.buffer = self.stderr = b""
            self.log.clear()
            self.progress.setValue(0)
            self.status.setText("Loading OCR models…")
            self.set_busy(True)
            args = [
                "-m",
                "video_qc.cli",
                "blur",
                self.source.text(),
                "--output",
                self.output.text(),
                "--scan-interval",
                str(self.interval.value()),
                "--sigma",
                str(self.sigma.value()),
                "--json-progress",
                "--cancel-file",
                str(self.cancel_path),
            ]
            if not self.qc.isChecked():
                args.append("--no-qc")
            self.process.start(sys.executable, args)

        def read_progress(self):
            self.buffer += bytes(self.process.readAllStandardOutput())
            while b"\n" in self.buffer:
                line, self.buffer = self.buffer.split(b"\n", 1)
                try:
                    event = json.loads(line)
                except (ValueError, UnicodeDecodeError):
                    continue
                stage = event["stage"]
                if stage == "result":
                    report = event["report"]
                    self.log.appendPlainText(
                        f"{report['tracks']} URL tracks · {report['frames']} frames · {report['elapsed_seconds']:.1f}s"
                    )
                    continue
                fraction = min(1, event.get("seconds", 0) / max(0.01, event.get("duration", 1)))
                percent = {
                    "analyze": round(fraction * 50),
                    "render": 50 + round(fraction * 45),
                    "qc": 96,
                    "complete": 100,
                }.get(stage, 0)
                self.progress.setValue(percent)
                self.status.setText(f"{stage.capitalize()} · frame {event.get('frame', 0)}")

        def read_errors(self):
            data = bytes(self.process.readAllStandardError())
            self.stderr = (self.stderr + data)[-16000:]
            self.log.appendPlainText(data.decode(errors="replace").strip())

        def process_error(self, error):
            if error == QProcess.ProcessError.FailedToStart:
                self.set_busy(False)
                self.status.setText("Could not start the engine. Check Python installation.")

        def finished(self, code, _status):
            if self.cancel_path:
                self.cancel_path.unlink(missing_ok=True)
            self.read_progress()
            self.read_errors()
            self.set_busy(False)
            if code == 0 and (Path(self.output.text()) / "report.json").is_file():
                self.bundle = Path(self.output.text())
                self.reveal.setEnabled(True)
                self.view.setCurrentIndex(1)
                self.progress.setValue(100)
                self.status.setText("Render ready · review coverage. Fusion masks and QC reports saved.")
            else:
                self.status.setText(
                    "Cancelled." if self.cancelled else "Processing failed. See details below."
                )

        def cancel_job(self):
            self.cancelled = True
            self.cancel.setEnabled(False)
            self.status.setText("Cancelling…")
            if self.cancel_path:
                self.cancel_path.touch()

        def closeEvent(self, event):
            if self.process.state() != QProcess.ProcessState.NotRunning:
                self.cancel_job()
                self.process.waitForFinished(5000)
                if self.process.state() != QProcess.ProcessState.NotRunning:
                    self.process.kill()
                    self.process.waitForFinished(1000)
            self.player.stop()
            event.accept()

    return Window()


def main(argv=None):
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        raise SystemExit("Desktop UI requires: uv sync --extra gui") from None
    args = sys.argv[1:] if argv is None else argv
    app = QApplication.instance() or QApplication([sys.argv[0]])
    window = make_window(args[0] if args else None)
    window.show()
    return app.exec()


if __name__ == "__main__":
    main()
