"""Render supplied fixtures and reproducible side-by-side comparisons."""

import argparse
import json
import subprocess
from pathlib import Path

from video_qc.media import probe
from video_qc.pipeline import process


def comparison(source, bundle):
    metadata = probe(source)
    width = 360 if metadata["height"] > metadata["width"] else 640
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-i",
            str(source),
            "-i",
            str(bundle / "blurred.mp4"),
            "-filter_complex",
            f"[0:v]scale={width}:-2,setsar=1[a];[1:v]scale={width}:-2,setsar=1[b];[a][b]hstack=shortest=1[out]",
            "-map",
            "[out]",
            "-map",
            "1:a?",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "20",
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            str(bundle / "comparison.mp4"),
        ],
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-ss",
            "2",
            "-i",
            str(bundle / "comparison.mp4"),
            "-frames:v",
            "1",
            str(bundle / "comparison.png"),
        ],
        check=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("demos"))
    parser.add_argument("--comparisons-only", action="store_true")
    args = parser.parse_args()
    reports = []
    root = Path(__file__).resolve().parents[1]
    for source in sorted((root / "tests/fixtures/video").glob("*.mp4")):
        bundle = args.output / source.stem
        if not args.comparisons_only:
            process(source, bundle, progress=lambda e: print(json.dumps(e), flush=True))
        comparison(source, bundle)
        report = json.loads((bundle / "report.json").read_text())
        reports.append(
            {
                "clip": source.name,
                "frames": report["frames"],
                "tracks": report["tracks"],
                "ocr_scans": report["ocr_scans"],
                "analysis_fps": round(report["frames"] / report["timings"]["analysis_seconds"], 2),
                "elapsed_seconds": round(report["elapsed_seconds"], 2),
            }
        )
    (args.output / "summary.json").write_text(json.dumps(reports, indent=2) + "\n")


if __name__ == "__main__":
    main()
