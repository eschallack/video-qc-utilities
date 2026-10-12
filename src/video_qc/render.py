from fractions import Fraction
from pathlib import Path

import av
import cv2

from .media import frames, require_tool, run_command
from .models import Config


def padded_box(box, width, height, padding):
    x, y, w, h = box
    return (
        max(0, int(x - padding)),
        max(0, int(y - padding)),
        min(width, int(x + w + padding + 1)),
        min(height, int(y + h + padding + 1)),
    )


def blur_frame(image, boxes, config: Config):
    # Blur from the original so overlapping masks never weaken earlier blur.
    result = image.copy()
    for box in boxes:
        x0, y0, x1, y1 = padded_box(box, image.shape[1], image.shape[0], config.padding)
        if x1 <= x0 or y1 <= y0:
            continue
        roi = image[y0:y1, x0:x1]
        result[y0:y1, x0:x1] = cv2.GaussianBlur(roi, (0, 0), config.blur_sigma)
    return result


def render(source: Path, destination: Path, metadata: dict, store, config: Config, progress, cancelled=None):
    silent = destination.with_name(".video-only.mp4")
    try:
        with av.open(str(silent), "w") as output:
            rate = Fraction(metadata["fps"])
            # Nominal codec rate; actual presentation times stay in source time base.
            stream = output.add_stream("libx264", rate=rate.limit_denominator(1001))
            stream.width, stream.height = metadata["width"], metadata["height"]
            stream.pix_fmt = "yuv420p"
            stream.codec_context.time_base = Fraction(metadata["time_base"])
            stream.codec_context.color_range = 1
            if metadata["video"].get("color_space") == "bt709":
                stream.codec_context.colorspace = 1
                stream.codec_context.color_primaries = 1
                stream.codec_context.color_trc = 1
            stream.options = {"crf": str(config.crf), "preset": config.preset, "threads": str(config.threads)}
            for index, seconds, image in frames(source, metadata):
                if cancelled and cancelled():
                    raise KeyboardInterrupt
                frame = av.VideoFrame.from_ndarray(blur_frame(image, store.at(index), config), format="bgr24")
                frame.time_base = Fraction(metadata["time_base"])
                frame.pts = round(seconds / frame.time_base)
                for packet in stream.encode(frame):
                    output.mux(packet)
                if index % 30 == 0:
                    progress("render", index, float(seconds))
            for packet in stream.encode():
                output.mux(packet)
        # Explicit stream mapping preserves all audio tracks. No shell interpolation.
        run_command(
            [
                require_tool("ffmpeg"),
                "-v",
                "error",
                "-y",
                "-copyts",
                "-i",
                str(silent),
                "-itsoffset",
                str(-float(metadata["video"].get("start_time", 0))),
                "-i",
                str(source),
                "-map",
                "0:v:0",
                "-map",
                "1:a?",
                "-c",
                "copy",
                "-map_metadata",
                "1",
                "-metadata:s:v:0",
                "rotate=0",
                "-avoid_negative_ts",
                "disabled",
                "-movie_timescale",
                "720000",
                "-movflags",
                "+faststart",
                str(destination),
            ],
            cancelled,
        )
    finally:
        silent.unlink(missing_ok=True)
