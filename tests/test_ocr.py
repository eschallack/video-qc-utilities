import cv2
import numpy as np
import pytest

from video_qc.media import frames, probe
from video_qc.models import Config
from video_qc.ocr import RapidOCRDetector


@pytest.fixture(scope="module")
def ocr():
    return RapidOCRDetector(Config())


@pytest.mark.ocr
@pytest.mark.parametrize("name", ["115842", "115856", "115919"])
def test_supplied_video_ocr(fixtures, ocr, name):
    path = fixtures / f"VID_20261012_{name}.mp4"
    frame = next(image for _, seconds, image in frames(path, probe(path)) if seconds >= 2)
    result = ocr.detect(frame)
    assert any("freakonomics" in d.text.lower() for d in result)
    for detection in result:
        x, y, width, height = detection.box
        assert 0 <= x < frame.shape[1] and 0 <= y < frame.shape[0]
        assert width > 0 and height > 0


@pytest.mark.ocr
def test_blank_frame(ocr):
    assert ocr.detect(np.full((320, 640, 3), 255, np.uint8)) == []


@pytest.mark.ocr
def test_text_and_sideways(ocr):
    image = np.full((320, 640, 3), 255, np.uint8)
    cv2.putText(image, "www.example.com", (45, 150), cv2.FONT_HERSHEY_SIMPLEX, 1.3, (0, 0, 0), 2)
    upright = ocr.detect(image)
    sideways = ocr.detect(np.ascontiguousarray(np.rot90(image)))
    assert upright and sideways
    assert sideways[0].box[2] < sideways[0].box[3]
