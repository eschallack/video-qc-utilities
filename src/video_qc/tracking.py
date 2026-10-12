from dataclasses import dataclass

import cv2
import numpy as np

from .models import Detection
from .ocr import _overlap


def box_polygon(box):
    x, y, w, h = box
    return np.array([[x, y], [x + w, y], [x + w, y + h], [x, y + h]], np.float32)


def polygon_box(polygon):
    low, high = polygon.min(axis=0), polygon.max(axis=0)
    return tuple(float(v) for v in (*low, *(high - low)))


def move_polygon(previous, current, polygon):
    """Pyramidal LK + RANSAC local affine motion; reject unreliable forward/backward flow."""
    h, w = previous.shape
    x, y, bw, bh = polygon_box(polygon)
    mask = np.zeros_like(previous)
    x0, y0 = max(0, int(x - 10)), max(0, int(y - 10))
    x1, y1 = min(w, int(x + bw + 10)), min(h, int(y + bh + 10))
    mask[y0:y1, x0:x1] = 255
    points = cv2.goodFeaturesToTrack(previous, 60, 0.01, 3, mask=mask)
    if points is None or len(points) < 4:
        return None
    moved, valid, _ = cv2.calcOpticalFlowPyrLK(previous, current, points, None, winSize=(25, 25), maxLevel=3)
    back, back_valid, _ = cv2.calcOpticalFlowPyrLK(
        current, previous, moved, None, winSize=(25, 25), maxLevel=3
    )
    good = valid.ravel().astype(bool) & back_valid.ravel().astype(bool)
    good &= np.linalg.norm(points - back, axis=2).ravel() < 1.5
    if good.sum() < 4:
        return None
    matrix, inliers = cv2.estimateAffinePartial2D(
        points[good], moved[good], method=cv2.RANSAC, ransacReprojThreshold=2
    )
    if matrix is None or inliers.sum() < 4:
        return None
    scale = np.linalg.norm(matrix[:, 0])
    if not 0.8 < scale < 1.25:
        return None
    # Axis-aligned output intentionally covers the rotated text conservatively.
    transformed = cv2.transform(polygon[None], matrix)[0]
    low, high = transformed.min(axis=0), transformed.max(axis=0)
    if high[0] < 0 or high[1] < 0 or low[0] >= w or low[1] >= h:
        return None
    return transformed


def move_box(previous, current, box):
    polygon = move_polygon(previous, current, box_polygon(box))
    return polygon_box(polygon) if polygon is not None else None


@dataclass
class Track:
    id: int
    detection: Detection
    last_seen: float
    method: str = "ocr"
    polygon: np.ndarray | None = None

    def __post_init__(self):
        self.polygon = box_polygon(self.detection.box)


class Tracker:
    def __init__(self, hold_seconds: float):
        self.active: list[Track] = []
        self.next_id = 1
        self.hold_seconds = hold_seconds

    def advance(self, previous, current, seconds):
        alive = []
        for track in self.active:
            if seconds - track.last_seen > self.hold_seconds:
                continue
            polygon = move_polygon(previous, current, track.polygon)
            if polygon is not None:
                track.polygon = polygon
                track.detection.box = polygon_box(polygon)
                track.method = "flow"
                alive.append(track)
        self.active = alive

    def update(self, detections, seconds):
        new = []
        used = set()
        for detection in detections:
            candidates = [
                t for t in self.active if t.id not in used and _overlap(t.detection.box, detection.box) > 0.2
            ]
            if candidates:
                track = max(candidates, key=lambda t: _overlap(t.detection.box, detection.box))
                track.detection = detection
                track.polygon = box_polygon(detection.box)
                track.last_seen = seconds
                track.method = "ocr"
            else:
                track = Track(self.next_id, detection, seconds)
                self.next_id += 1
                self.active.append(track)
                new.append(track)
            used.add(track.id)
        return new
