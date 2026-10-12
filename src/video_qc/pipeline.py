import json
import shutil
import tempfile
import time
from collections import deque
from fractions import Fraction
from pathlib import Path

import cv2
import numpy as np

from .media import frames, probe
from .models import Config, Detector
from .ocr import RapidOCRDetector
from .qc import inspect
from .render import render
from .store import TrackStore
from .tracking import Tracker, move_polygon, polygon_box


def process(
    source: str | Path,
    output: str | Path,
    config: Config | None = None,
    detector: Detector | None = None,
    progress=None,
    run_qc: bool = True,
    cancelled=None,
) -> dict:
    """Analyze + render an atomic result bundle. Existing destinations are never overwritten.

    Inject Detector to reuse a native/GPU OCR service or supply test detections.
    Progress receives {stage, frame, seconds, duration}; callbacks may raise to cancel.
    """
    source, output = Path(source).resolve(), Path(output).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")
    config = config or Config()
    metadata = probe(source)
    video = metadata["video"]
    if (
        video.get("color_transfer") in {"smpte2084", "arib-std-b67"}
        or int(video.get("bits_per_raw_sample", 8) or 8) > 8
    ):
        raise ValueError("Rendering currently supports 8-bit SDR only. Use a color-managed SDR export.")
    if metadata["width"] % 2 or metadata["height"] % 2:
        raise ValueError("H.264 preview rendering requires even frame dimensions")
    output.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    timings = {}
    detector = detector or RapidOCRDetector(config)

    def notify(stage, frame=0, seconds=0):
        if stage != "complete" and cancelled and cancelled():
            raise KeyboardInterrupt
        if progress:
            progress({"stage": stage, "frame": frame, "seconds": seconds, "duration": metadata["duration"]})

    with tempfile.TemporaryDirectory(prefix=".video-qc-", dir=output.parent) as temp:
        staging = Path(temp)
        store = TrackStore(staging / "tracking.sqlite")
        try:
            tracker = Tracker(config.hold_seconds)
            history = deque(
                maxlen=max(
                    config.scan_interval, round(float(Fraction(metadata["fps"])) * config.lookback_seconds)
                )
            )
            previous = None
            previous_thumb = None
            scans = count = flow_failures = 0
            stage_start = time.perf_counter()
            for index, seconds, image in frames(source, metadata):
                if cancelled and cancelled():
                    raise KeyboardInterrupt
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                # Tracking works at half resolution; exported coordinates remain full resolution.
                tracking_gray = cv2.resize(gray, (gray.shape[1] // 2, gray.shape[0] // 2))
                thumb = cv2.resize(gray, (64, 64))
                cut = previous is not None and np.mean(cv2.absdiff(thumb, previous_thumb)) > 55
                if cut:
                    tracker.active.clear()
                    history.clear()
                if previous is not None and not cut:
                    before = len(tracker.active)
                    tracker.advance(previous, tracking_gray, float(seconds))
                    flow_failures += before - len(tracker.active)
                if index % config.scan_interval == 0 or cut:
                    detections = detector.detect(image)
                    for d in detections:
                        d.box = tuple(v / 2 for v in d.box)
                    new = tracker.update(detections, float(seconds))
                    scans += 1
                    # New URLs are tracked backward through this bounded scan window.
                    for track in new:
                        polygon, back_image = track.polygon.copy(), tracking_gray
                        for back_index, back_seconds, back_gray in reversed(history):
                            polygon = move_polygon(back_image, back_gray, polygon)
                            if polygon is None:
                                break
                            box = polygon_box(polygon)
                            store.save(track, back_index, back_seconds, "backfill", tuple(v * 2 for v in box))
                            back_image = back_gray
                for track in tracker.active:
                    store.save(track, index, float(seconds), box=tuple(v * 2 for v in track.detection.box))
                history.append((index, float(seconds), tracking_gray))
                previous, previous_thumb = tracking_gray, thumb
                count = index + 1
                if index % 30 == 0:
                    store.db.commit()
                    notify("analyze", index, float(seconds))
            if count == 0:
                raise ValueError("Input contains no decodable video frames")
            timings["analysis_seconds"] = time.perf_counter() - stage_start
            metadata["frames"] = count
            store.db.commit()
            store.export(staging / "tracking.json", metadata, config.to_dict())
            from .fusion import export_lua

            export_lua(store, staging / "masks.fusion.lua", metadata, config)
            stage_start = time.perf_counter()
            render(source, staging / "blurred.mp4", metadata, store, config, notify, cancelled)
            timings["render_seconds"] = time.perf_counter() - stage_start
            notify("qc")
            qc = inspect(source, metadata, cancelled) if run_qc else {"notice": "QC skipped"}
            (staging / "qc.json").write_text(json.dumps(qc, indent=2), encoding="utf-8")
            tracks = store.db.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
            report = {
                "schema_version": 1,
                "source": str(source),
                "output": str(output),
                "frames": count,
                "tracks": tracks,
                "ocr_scans": scans,
                "tracking_losses": flow_failures,
                "config": config.to_dict(),
                "timings": timings,
                "elapsed_seconds": time.perf_counter() - started,
                "review_required": True,
                "warnings": [
                    "OCR may miss small, occluded, or briefly visible URLs. Review the full render.",
                    "Fusion masks assume matching display dimensions and a 1:1, unretimed clip.",
                ],
            }
            (staging / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        finally:
            store.close()
        if output.exists():
            raise FileExistsError(output)
        shutil.move(str(staging), str(output))
    notify("complete", count, metadata["duration"])
    return report
