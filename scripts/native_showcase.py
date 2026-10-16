"""Render all provided fixtures with both native tracking models. Python is orchestration only."""

import argparse
import json
import subprocess
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=root / "demos/native")
    parser.add_argument("--engine", type=Path, default=root / "target/release/video-qc")
    args = parser.parse_args()
    summary = []
    for source in sorted((root / "tests/fixtures/video").glob("*.mp4")):
        for mode in ("transform", "perspective"):
            bundle = args.output / source.stem / mode
            subprocess.run(
                [
                    str(args.engine),
                    "blur",
                    str(source),
                    "--output",
                    str(bundle),
                    "--tracking-type",
                    mode,
                    "--feather",
                    "6",
                ],
                check=True,
            )
            tracking = json.loads((bundle / "tracking.json").read_text())
            portrait = tracking["source"]["height"] > tracking["source"]["width"]
            width = 360 if portrait else 640
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
                    "-threads",
                    "2",
                    "-preset",
                    "veryfast",
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
            report = json.loads((bundle / "report.json").read_text())
            summary.append(
                {
                    "clip": source.name,
                    "mode": mode,
                    "frames": report["frames"],
                    "tracks": report["tracks"],
                    "analysis_fps": report["timings"]["analysis_fps"],
                    "elapsed_seconds": report["elapsed_seconds"],
                    "render_seconds": report["timings"]["render_seconds"],
                }
            )
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    main()
