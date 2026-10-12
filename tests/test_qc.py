import subprocess

import pytest

from video_qc.qc import inspect


@pytest.mark.integration
def test_black_freeze_and_silence(tmp_path):
    source = tmp_path / "black.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=320x180:r=10:d=2",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=48000:cl=stereo",
            "-t",
            "2",
            "-c:v",
            "libx264",
            "-threads",
            "1",
            "-c:a",
            "aac",
            "-y",
            str(source),
        ],
        check=True,
    )
    result = inspect(source)
    assert {event["kind"] for event in result["events"]} == {"black", "freeze", "silence"}
    assert result["loudness"]["integrated_lufs"] is None
