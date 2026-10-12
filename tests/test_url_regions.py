import cv2
import numpy as np
import pytest

from video_qc.models import Config
from video_qc.ocr import RapidOCRDetector


@pytest.mark.ocr
def test_url_inside_sentence_keeps_other_words():
    image = np.full((240, 1000, 3), 255, np.uint8)
    cv2.putText(image, "Visit www.example.com today", (25, 120), cv2.FONT_HERSHEY_SIMPLEX, 1.3, (0, 0, 0), 2)
    detections = RapidOCRDetector(Config(sideways=False)).detect(image)
    assert len(detections) == 1
    assert detections[0].text == "www.example.com"
    x, _, width, _ = detections[0].box
    assert x > 110  # "Visit" remains outside the blur mask.
    assert x + width < 570  # "today" remains outside the blur mask.
