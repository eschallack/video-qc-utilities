import json
import subprocess
from pathlib import Path

import cv2
import numpy as np
import pytest
from conftest import MovingDetector

from video_qc.media import frames, probe
from video_qc.models import Config
from video_qc.pipeline import process


def audio_hashes(path):
    result = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a",
            "-show_packets",
            "-show_data_hash",
            "sha256",
            "-of",
            "json",
            str(path),
        ]
    )
    return [p["data_hash"] for p in json.loads(result)["packets"]]


@pytest.mark.integration
def test_render_timing_audio_tracking_and_locality(moving_video, detector, tmp_path):
    source_meta = probe(moving_video)
    events = []
    output = tmp_path / "result"
    report = process(moving_video, output, Config(scan_interval=4, threads=1), detector, events.append)
    assert report["frames"] == 12
    assert report["ocr_scans"] == 3
    assert report["tracks"] >= 1
    assert report["review_required"]
    assert events[-1]["stage"] == "complete"
    assert all(
        (output / name).is_file()
        for name in [
            "blurred.mp4",
            "tracking.json",
            "tracking.sqlite",
            "masks.fusion.lua",
            "qc.json",
            "report.json",
        ]
    )
    output_meta = probe(output / "blurred.mp4")
    source_frames = list(frames(moving_video, source_meta))
    output_frames = list(frames(output / "blurred.mp4", output_meta))
    assert len(output_frames) == len(source_frames)
    for before, after in zip(source_frames, output_frames, strict=True):
        assert float(after[1]) == pytest.approx(float(before[1]), abs=0.0001)
    assert audio_hashes(moving_video) == audio_hashes(output / "blurred.mp4")
    before, after = source_frames[6][2], output_frames[6][2]
    before_roi = cv2.cvtColor(before[128:164, 78:373], cv2.COLOR_BGR2GRAY)
    after_roi = cv2.cvtColor(after[128:164, 78:373], cv2.COLOR_BGR2GRAY)
    assert cv2.Laplacian(after_roi, cv2.CV_64F).var() < cv2.Laplacian(before_roi, cv2.CV_64F).var() / 10
    assert np.abs(after[220:300, 450:620].astype(float) - before[220:300, 450:620]).mean() < 3
    tracking = json.loads((output / "tracking.json").read_text())
    samples = tracking["tracks"][0]["samples"]
    assert samples[-1]["box"][0] > samples[0]["box"][0] + 20
    assert any(s["method"] == "flow" for s in samples)
    assert json.loads((output / "qc.json").read_text())["loudness"]["integrated_lufs"] is not None


@pytest.mark.integration
def test_backward_fill(moving_video, tmp_path):
    output = tmp_path / "backfill"
    process(moving_video, output, Config(scan_interval=4), MovingDetector(skip_first=True), run_qc=False)
    samples = json.loads((output / "tracking.json").read_text())["tracks"][0]["samples"]
    assert samples[0]["frame"] == 0
    assert samples[0]["method"] == "backfill"


@pytest.mark.integration
def test_no_urls(moving_video, tmp_path):
    class Empty:
        def detect(self, image):
            return []

    output = tmp_path / "empty"
    report = process(moving_video, output, detector=Empty(), run_qc=False)
    assert report["tracks"] == 0
    assert json.loads((output / "tracking.json").read_text())["tracks"] == []


@pytest.mark.integration
def test_cancellation_cleans_staging(moving_video, tmp_path):
    class Cancel:
        def detect(self, image):
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        process(moving_video, tmp_path / "cancel", detector=Cancel())
    assert not (tmp_path / "cancel").exists()
    assert not list(tmp_path.glob(".video-qc-*"))


def test_existing_output_and_missing_input(tmp_path):
    source = tmp_path / "source.mp4"
    source.touch()
    destination = tmp_path / "existing"
    destination.mkdir()
    with pytest.raises(FileExistsError):
        process(source, destination)
    with pytest.raises(FileNotFoundError):
        process(tmp_path / "missing.mp4", tmp_path / "new")


@pytest.mark.integration
def test_rotation_metadata(fixtures):
    metadata = probe(fixtures / "VID_20261012_115842.mp4")
    assert (metadata["width"], metadata["height"]) == (1280, 720)
    _, _, image = next(frames(Path(metadata["source"]), metadata))
    assert image.shape == (720, 1280, 3)
