import subprocess
from fractions import Fraction
from pathlib import Path

import av
import cv2
import numpy as np
import pytest


@pytest.fixture
def moving_video(tmp_path):
    """VFR clip with moving text and an independently muxed audio track."""
    silent = tmp_path / "silent.mp4"
    times = [0, 100, 200, 340, 450, 550, 700, 800, 900, 1040, 1150, 1250]
    with av.open(str(silent), "w") as out:
        stream = out.add_stream("libx264", rate=10)
        stream.width, stream.height = 640, 320
        stream.pix_fmt = "yuv420p"
        stream.codec_context.time_base = Fraction(1, 1000)
        stream.options = {"crf": "10", "preset": "ultrafast", "threads": "1"}
        for i, timestamp in enumerate(times):
            image = np.full((320, 640, 3), 220, np.uint8)
            cv2.putText(
                image, "www.example.com", (60 + i * 3, 155), cv2.FONT_HERSHEY_SIMPLEX, 1, (10, 10, 10), 2
            )
            cv2.rectangle(image, (480, 230), (610, 290), (20, 100, 180), -1)
            frame = av.VideoFrame.from_ndarray(image, format="bgr24")
            frame.pts, frame.time_base = timestamp, Fraction(1, 1000)
            for packet in stream.encode(frame):
                out.mux(packet)
        for packet in stream.encode():
            out.mux(packet)
    result = tmp_path / "moving.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(silent),
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=1.35",
            "-map",
            "0:v",
            "-map",
            "1:a",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-y",
            str(result),
        ],
        check=True,
    )
    return result


class MovingDetector:
    def __init__(self, interval=4, skip_first=False):
        self.calls = 0
        self.interval = interval
        self.skip_first = skip_first

    def detect(self, image):
        from video_qc.models import Detection

        index = self.calls * self.interval
        self.calls += 1
        if self.skip_first and self.calls == 1:
            return []
        return [Detection("www.example.com", 0.99, (58 + index * 3, 128, 295, 35))]


@pytest.fixture
def detector():
    return MovingDetector()


@pytest.fixture
def fixtures():
    return Path(__file__).parent / "fixtures/video"
