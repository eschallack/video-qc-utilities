import math
from dataclasses import asdict, dataclass
from typing import Protocol

import numpy as np


@dataclass(frozen=True)
class Config:
    scan_interval: int = 8
    ocr_max_side: int = 1600
    confidence: float = 0.45
    padding: int = 10
    blur_sigma: float = 18.0
    hold_seconds: float = 2.0
    lookback_seconds: float = 1.0
    threads: int = 2
    crf: int = 18
    preset: str = "fast"
    sideways: bool = True

    def __post_init__(self):
        if not all(
            math.isfinite(value)
            for value in (self.confidence, self.blur_sigma, self.hold_seconds, self.lookback_seconds)
        ):
            raise ValueError("Numeric settings must be finite")
        if self.scan_interval < 1 or self.ocr_max_side < 320 or self.threads < 1:
            raise ValueError("Scan interval/threads must be positive; OCR size must be >= 320")
        if not 0 <= self.confidence <= 1 or self.padding < 0:
            raise ValueError("Invalid confidence or padding")
        if (
            self.blur_sigma <= 0
            or self.hold_seconds < 0
            or self.lookback_seconds < 0
            or not 0 <= self.crf <= 51
        ):
            raise ValueError("Invalid blur strength, hold duration, or CRF")
        if self.preset not in {"ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow"}:
            raise ValueError("Unsupported encoding preset")

    def to_dict(self):
        return asdict(self)


@dataclass
class Detection:
    text: str
    confidence: float
    box: tuple[float, float, float, float]  # x, y, width, height in display pixels


class Detector(Protocol):
    def detect(self, image: np.ndarray) -> list[Detection]: ...
