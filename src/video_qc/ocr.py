import cv2
import numpy as np

from .models import Config, Detection
from .urls import find_urls


class RapidOCRDetector:
    """ONNX models ship with RapidOCR. One session per job, bounded CPU threads."""

    def __init__(self, config: Config):
        from rapidocr_onnxruntime import RapidOCR

        self.config = config
        self.engine = RapidOCR(
            intra_op_num_threads=config.threads,
            inter_op_num_threads=1,
            det_limit_side_len=min(config.ocr_max_side, 1280),
            det_limit_type="max",
            text_score=config.confidence,
        )

    def detect(self, image: np.ndarray) -> list[Detection]:
        h, w = image.shape[:2]
        scale = min(1.0, self.config.ocr_max_side / max(w, h))
        small = cv2.resize(image, (round(w * scale), round(h * scale))) if scale < 1 else image
        detections = []
        # Classifier handles 180 degrees. A second pass handles vertical signage.
        for turns in [0, 1] if self.config.sideways else [0]:
            rotated = np.ascontiguousarray(np.rot90(small, turns))
            result, _ = self.engine(rotated, return_word_box=True, text_score=self.config.confidence)
            for line in result or []:
                _, text, confidence = line[:3]
                urls = find_urls(text)
                if confidence < self.config.confidence or not urls:
                    continue
                for url in urls:
                    points = url_polygon(line, url)
                    if turns:
                        points = np.column_stack((small.shape[1] - 1 - points[:, 1], points[:, 0]))
                    points /= scale
                    low, high = points.min(axis=0), points.max(axis=0)
                    detection = Detection(url, float(confidence), (*low, *(high - low)))
                    if not any(_overlap(detection.box, d.box) > 0.45 for d in detections):
                        detections.append(detection)
        return detections


def url_polygon(line, url):
    """Use RapidOCR character boxes to keep surrounding sentence text readable."""
    if len(line) >= 5:
        boxes, characters = line[3], line[4]
        aligned = [
            (char, box)
            for word, box in zip(characters, boxes, strict=True)
            for char in word
            if not char.isspace()
        ]
        compact = "".join(char for char, _ in aligned).lower()
        target = "".join(url.split()).lower()
        start = compact.find(target)
        if start >= 0:
            return np.array([box for _, box in aligned[start : start + len(target)]], dtype=float).reshape(
                -1, 2
            )
    return np.array(line[0], dtype=float)


def _overlap(a, b):
    x, y = max(a[0], b[0]), max(a[1], b[1])
    endx, endy = min(a[0] + a[2], b[0] + b[2]), min(a[1] + a[3], b[1] + b[3])
    area = max(0, endx - x) * max(0, endy - y)
    return area / max(1, a[2] * a[3] + b[2] * b[3] - area)
