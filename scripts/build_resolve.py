"""Build a reviewable Resolve extension folder. No system folders are changed."""

import argparse
import json
import shutil
import sys
from pathlib import Path


def build(destination: Path, python: Path):
    root = Path(__file__).resolve().parents[1]
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / "integrations/resolve/URL Guard.py", destination / "URL Guard.py")
    (destination / "url_guard_config.json").write_text(
        json.dumps(
            {
                "python": str(python.resolve()),
                "project_root": str(root),
                "native_app": str(root / "dist/URL Guard.app"),
            },
            indent=2,
        )
        + "\n"
    )
    print(destination.resolve())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=Path("dist/resolve"))
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    args = parser.parse_args()
    build(args.destination, args.python)
