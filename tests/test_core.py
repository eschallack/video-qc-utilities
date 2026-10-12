import cv2
import numpy as np
import pytest

from video_qc.models import Config
from video_qc.render import blur_frame, padded_box
from video_qc.tracking import move_box
from video_qc.urls import find_urls


@pytest.mark.parametrize(
    "text",
    [
        "Visit https://example.com/a?b=1",
        "www.freakonomics.com",
        "EXAMPLE.CO.UK",
        "See www . example . com today",
        "www.harpercollins.con",
        "wwww.harpercollins.con",
        "https://example.technology/path",
        "example.tv",
    ],
)
def test_urls(text):
    assert find_urls(text)


@pytest.mark.parametrize(
    "text", ["Ordinary text", "Version 1.2.3", "person@example.com", "scene.mp4", "3.14", "Chapter 10"]
)
def test_not_urls(text):
    assert find_urls(text) == []


def test_multiple_urls():
    assert len(find_urls("www.example.com and https://other.org")) == 2


@pytest.mark.parametrize(
    "values",
    [
        {"scan_interval": 0},
        {"confidence": 1.1},
        {"padding": -2},
        {"blur_sigma": 0},
        {"ocr_max_side": 20},
        {"threads": 0},
        {"hold_seconds": -1},
        {"crf": 52},
        {"preset": "bogus"},
    ],
)
def test_bad_config(values):
    with pytest.raises(ValueError):
        Config(**values)


def test_blur_locality_and_overlap():
    rng = np.random.default_rng(123)
    image = rng.integers(0, 255, (120, 200, 3), dtype=np.uint8)
    original = image.copy()
    config = Config(padding=0, blur_sigma=12)
    result = blur_frame(image, [(30, 30, 60, 30), (50, 30, 60, 30)], config)
    assert np.array_equal(image, original)
    assert np.array_equal(result[:20], image[:20])
    assert result[35:55, 55:75].std() < image[35:55, 55:75].std() / 5
    assert padded_box((-10, -10, 40, 40), 100, 100, 10) == (0, 0, 41, 41)
    assert np.array_equal(blur_frame(image, [(500, 500, 10, 10)], config), image)


def test_optical_flow_translation():
    image = np.zeros((200, 400), np.uint8)
    cv2.putText(image, "www.example.com", (30, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.8, 255, 2)
    moved = cv2.warpAffine(image, np.float32([[1, 0, 7], [0, 1, 4]]), (400, 200))
    box = move_box(image, moved, (28, 65, 250, 35))
    assert box is not None
    assert box[0] == pytest.approx(35, abs=1)
    assert box[1] == pytest.approx(69, abs=1)
    assert move_box(np.zeros_like(image), np.zeros_like(image), (10, 10, 20, 20)) is None
