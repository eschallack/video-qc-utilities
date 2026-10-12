# Distribution notes

The project is MIT licensed. Dependencies retain their own licenses. Pinning in `uv.lock` makes the installed environment reproducible; it does not replace license notices for a distributed desktop installer.

RapidOCR/its bundled OCR models, ONNX Runtime, OpenCV, NumPy, tldextract's bundled suffix data, PyAV, Typer, Rich, and Qt/PySide should be reviewed for the versions being shipped. PySide uses Qt's applicable LGPL/commercial licensing terms. FFmpeg licensing depends on build configuration; libx264 introduces GPL-related distribution considerations. PyAV wheels can carry their own FFmpeg build.

The Resolve adapter relies on Blackmagic's installed scripting APIs. No `WorkflowIntegration.node`, Resolve executable, or Blackmagic SDK bundle is copied into this project. Use the end user's installed host.

The demo videos are user-provided fixtures. Confirm rights before redistributing them. The system leaves network/model downloads out of processing jobs; source files and OCR results remain local.
