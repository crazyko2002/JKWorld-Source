"""Local OCR voting accepts only stable two-digit results."""

from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import local_ocr_lab  # noqa: E402
from local_ocr_lab import (  # noqa: E402
    classify_one_digit,
    read_two_digits,
    recognize_two_digits,
)


class FakeOcr:
    def __init__(self):
        self.results = iter(["76", "76", "I6", "76", "7x"])

    def classification(self, _image):
        return next(self.results)


class FakeOneDigitOcr:
    def __init__(self):
        self.results = iter(["7", "11", "I", "1", "1", "lll", "x", "1"])

    def classification(self, _image):
        return next(self.results)


def main() -> None:
    image = np.zeros((48, 73, 3), dtype=np.uint8)
    image[:, :, 2] = 100
    result = recognize_two_digits(image, FakeOcr())

    assert result.text == "76"
    assert result.votes == ("76", "76", "16", "76")
    assert result.winning_votes == 3
    assert result.stable

    original = local_ocr_lab.get_ocr
    local_ocr_lab.get_ocr = lambda: FakeOcr()
    try:
        public_result = read_two_digits(image)
    finally:
        local_ocr_lab.get_ocr = original
    assert public_result.text == "76"
    assert public_result.confidence == 0.75
    one_digit_image = np.zeros((20, 12), dtype=np.uint8)
    assert classify_one_digit(one_digit_image, FakeOneDigitOcr()) == "1"
    print("Local OCR voting OK")


if __name__ == "__main__":
    main()
