import json
import signal
import subprocess
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from . import __version__
from .media import require_tool
from .models import Config

app = typer.Typer(help="URL redaction and editorial video QC.", no_args_is_help=True)
console = Console(stderr=True)


@app.command()
def blur(
    source: Path,
    output: Annotated[Path, typer.Option("--output", "-o", help="New result directory")],
    scan_interval: int = 8,
    ocr_max_side: int = 1600,
    confidence: float = 0.45,
    padding: int = 10,
    sigma: float = 18,
    threads: int = 2,
    crf: int = 18,
    preset: str = "fast",
    sideways: bool = True,
    qc: bool = True,
    json_progress: bool = False,
    cancel_file: Path | None = None,
):
    """Detect, track, blur, and export JSON/SQLite/Fusion masks."""
    from .pipeline import process

    def progress(event):
        if json_progress:
            print(json.dumps(event), flush=True)
        else:
            console.print(
                f"{event['stage']} · frame {event['frame']} · {event['seconds']:.1f}s", highlight=False
            )

    def terminate(_signum, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, terminate)
    try:
        config = Config(
            scan_interval=scan_interval,
            ocr_max_side=ocr_max_side,
            confidence=confidence,
            padding=padding,
            blur_sigma=sigma,
            threads=threads,
            crf=crf,
            preset=preset,
            sideways=sideways,
        )
        result = process(
            source,
            output,
            config,
            progress=progress,
            run_qc=qc,
            cancelled=cancel_file.exists if cancel_file else None,
        )
    except KeyboardInterrupt:
        console.print("Cancelled. No result bundle published.")
        raise typer.Exit(130) from None
    except (ValueError, OSError, RuntimeError, subprocess.CalledProcessError) as error:
        detail = error.stderr if isinstance(error, subprocess.CalledProcessError) else str(error)
        console.print(f"Failed: {detail}", markup=False)
        raise typer.Exit(1) from None
    if json_progress:
        print(json.dumps({"stage": "result", "report": result}), flush=True)
    else:
        console.print(f"Saved {output} · {result['tracks']} URL tracks · {result['elapsed_seconds']:.1f}s")


@app.command()
def check(source: Path, output: Path | None = None):
    """Measure black/frozen frames, silence, integrated loudness, and true peak."""
    from .qc import inspect

    try:
        report = json.dumps(inspect(source), indent=2)
        if output:
            output.write_text(report + "\n", encoding="utf-8")
        else:
            print(report)
    except (ValueError, OSError, RuntimeError, subprocess.CalledProcessError) as error:
        console.print(str(error), markup=False)
        raise typer.Exit(1) from None


@app.command()
def doctor():
    """Check installed media tools and bundled OCR models."""
    console.print(f"video-qc {__version__}")
    for tool in ("ffmpeg", "ffprobe"):
        try:
            console.print(f"{tool}: {require_tool(tool)}")
        except RuntimeError as error:
            console.print(str(error))
            raise typer.Exit(1) from None
    from .ocr import RapidOCRDetector

    RapidOCRDetector(Config())
    console.print("OCR: bundled ONNX models ready")


@app.command()
def desktop(source: Path | None = None):
    """Open the native desktop interface."""
    from .desktop import main

    main([str(source)] if source else [])


if __name__ == "__main__":
    app()
