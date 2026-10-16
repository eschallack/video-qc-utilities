"""Compatibility entry point. The native Rust binary owns processing and CLI parsing."""

import os
import subprocess
import sys
from pathlib import Path


def engine_executable() -> Path:
    root = Path(__file__).resolve().parents[2]
    candidates = [
        Path(os.environ["URL_GUARD_ENGINE"]) if os.environ.get("URL_GUARD_ENGINE") else None,
        root / "target/release/video-qc",
        root / "dist/URL Guard.app/Contents/Resources/video-qc",
    ]
    for path in candidates:
        if path and path.is_file():
            return path
    raise RuntimeError("Build the Rust engine first: bash scripts/build_macos.sh")


def app():
    args = sys.argv[1:]
    if args and args[0] == "desktop":
        from .desktop import main

        main(args[1:])
        return 0
    try:
        return subprocess.call([str(engine_executable()), *args])
    except (RuntimeError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(app())
