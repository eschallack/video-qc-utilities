import json
import shutil
import subprocess
from pathlib import Path

import av
import numpy as np


def run_command(command: list[str], cancelled=None):
    """Wait for a media child while supporting cancellation and deterministic cleanup."""
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as child:
        try:
            while True:
                if cancelled and cancelled():
                    raise KeyboardInterrupt
                try:
                    stdout, stderr = child.communicate(timeout=0.25)
                    break
                except subprocess.TimeoutExpired:
                    continue
            if child.returncode:
                raise subprocess.CalledProcessError(child.returncode, command, stdout, stderr)
            return subprocess.CompletedProcess(command, child.returncode, stdout, stderr)
        except BaseException:
            child.terminate()
            try:
                child.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                child.kill()
                child.communicate()
            raise


def require_tool(name: str) -> str:
    result = shutil.which(name)
    if not result:
        raise RuntimeError(f"{name} is required. Install FFmpeg and put its bin directory on PATH.")
    return result


def probe(path: Path) -> dict:
    result = subprocess.run(
        [require_tool("ffprobe"), "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(result.stdout)
    streams = [
        s
        for s in data["streams"]
        if s["codec_type"] == "video" and not s.get("disposition", {}).get("attached_pic")
    ]
    if not streams:
        raise ValueError("Input contains no video stream")
    video = streams[0]
    rotation = next(
        (int(s.get("rotation", 0)) for s in video.get("side_data_list", []) if "rotation" in s), 0
    )
    if rotation % 90:
        raise ValueError("Only right-angle display rotation is supported")
    width, height = video["width"], video["height"]
    if rotation % 180:
        width, height = height, width
    return {
        "source": str(path.resolve()),
        "width": width,
        "height": height,
        "rotation": rotation,
        "fps": video["avg_frame_rate"],
        "time_base": video["time_base"],
        "duration": float(data["format"].get("duration", 0)),
        "video": video,
        "audio": [s for s in data["streams"] if s["codec_type"] == "audio"],
    }


def frames(path: Path, metadata: dict):
    """Display-oriented BGR frames and source presentation timestamps. Never buffer a clip."""
    with av.open(str(path)) as container:
        stream = next(s for s in container.streams.video if s.index == metadata["video"]["index"])
        stream.thread_type = "AUTO"
        origin = None
        for index, frame in enumerate(container.decode(stream)):
            if frame.pts is None:
                raise ValueError("Video has a frame without a presentation timestamp")
            if origin is None:
                origin = frame.pts
            image = frame.to_ndarray(format="bgr24")
            if metadata["rotation"]:
                image = np.ascontiguousarray(np.rot90(image, metadata["rotation"] // 90))
            yield index, (frame.pts - origin) * frame.time_base, image
