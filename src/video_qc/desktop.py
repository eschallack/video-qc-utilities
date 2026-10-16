"""Compatibility launcher for the native Swift app. Processing uses the Rust engine."""

import os
import subprocess
import sys
from pathlib import Path


def app_executable() -> Path:
    configured = os.environ.get("URL_GUARD_APP")
    app = Path(configured) if configured else Path(__file__).resolve().parents[2] / "dist/URL Guard.app"
    binary = app / "Contents/MacOS/URLGuard" if app.suffix == ".app" else app
    if not binary.is_file():
        raise RuntimeError("Build the native app first: bash scripts/build_macos.sh")
    return binary


def main(argv=None):
    if sys.platform != "darwin":
        raise SystemExit("The native Swift app requires macOS 13+.")
    args = sys.argv[1:] if argv is None else argv
    try:
        subprocess.Popen([str(app_executable()), *args])
    except (RuntimeError, OSError) as error:
        raise SystemExit(str(error)) from None


if __name__ == "__main__":
    main()
