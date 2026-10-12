"""FFmpeg's established filters do the media measurements."""

import json
import math
import re
from pathlib import Path

from .media import probe, require_tool, run_command


def _number(value):
    result = float(value)
    return result if math.isfinite(result) else None


def inspect(source: Path, metadata=None, cancelled=None) -> dict:
    metadata = metadata or probe(source)
    cmd = [
        require_tool("ffmpeg"),
        "-hide_banner",
        "-nostats",
        "-i",
        str(source),
        "-map",
        f"0:{metadata['video']['index']}",
        "-vf",
        "scale=320:-2,blackdetect=d=0.5:pix_th=0.10:pic_th=0.98,freezedetect=n=-50dB:d=1",
    ]
    if metadata["audio"]:
        cmd += [
            "-map",
            "0:a:0",
            "-af",
            "silencedetect=n=-50dB:d=1,loudnorm=I=-24:TP=-2:LRA=7:print_format=json",
        ]
    cmd += ["-f", "null", "-"]
    result = run_command(cmd, cancelled)
    log = result.stderr
    events = []
    for match in re.finditer(r"black_start:([\d.]+) black_end:([\d.]+) black_duration:([\d.]+)", log):
        events.append({"kind": "black", "start": float(match[1]), "end": float(match[2])})
    for kind, prefix in [("freeze", "lavfi.freezedetect.freeze"), ("silence", "silence")]:
        start = None
        for match in re.finditer(re.escape(prefix) + r"_(start|end)[:=]\s*([\d.]+)", log):
            if match[1] == "start":
                start = float(match[2])
            elif start is not None:
                events.append({"kind": kind, "start": start, "end": float(match[2])})
                start = None
        if start is not None:
            events.append({"kind": kind, "start": start, "end": metadata["duration"]})
    loudness = None
    matches = re.findall(r'\{\s*"input_i".*?\}', log, re.DOTALL)
    if matches:
        value = json.loads(matches[-1])
        loudness = {
            "integrated_lufs": _number(value["input_i"]),
            "true_peak_dbtp": _number(value["input_tp"]),
            "range_lu": _number(value["input_lra"]),
        }
    return {
        "schema_version": 1,
        "source": metadata,
        "events": sorted(events, key=lambda e: e["start"]),
        "loudness": loudness,
        "audio_measured": "first audio stream only",
        "notice": "Measurements for editorial review. No Amazon/Tubi compliance certification.",
    }
