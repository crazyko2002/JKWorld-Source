"""Local OCR helpers for captcha digit recognition."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import threading
import time
from typing import Any

import cv2
import mss
import numpy as np
from PIL import Image


@dataclass(frozen=True)
class LocalOcrResult:
    text: str | None
    votes: tuple[str, ...]
    winning_votes: int
    stable: bool
    elapsed_seconds: float

    @property
    def confidence(self) -> float:
        return self.winning_votes / max(1, len(self.votes))


def blue_difference_binary(
    image_bgr: np.ndarray,
    threshold: int,
) -> Image.Image:
    if image_bgr.ndim != 3 or image_bgr.shape[2] < 3:
        raise ValueError("OCR 圖片必須係 BGR/RGB color image")
    blue = image_bgr[:, :, 0].astype(np.int16)
    green = image_bgr[:, :, 1].astype(np.int16)
    red = image_bgr[:, :, 2].astype(np.int16)
    blue_background = (
        (blue - red > threshold)
        | (blue - green > threshold)
    )
    binary = np.where(blue_background, 255, 0).astype(np.uint8)
    return Image.fromarray(binary, mode="L")


def normalize_result(value: Any) -> str | None:
    text = str(value).strip().translate(str.maketrans({
        "o": "0", "O": "0", "i": "1", "I": "1",
    }))
    return text if len(text) == 2 and text.isdigit() else None


def normalize_one_digit(value: Any) -> str | None:
    text = str(value).strip().translate(str.maketrans({
        "o": "0", "O": "0", "i": "1", "I": "1",
        "l": "1", "L": "1",
    }))
    digits = "".join(character for character in text if character.isdigit())
    return digits if len(digits) == 1 else None


def classify_one_digit(
    image: np.ndarray,
    ocr,
    scales: tuple[int, ...] = (1, 2, 3, 4),
) -> str | None:
    """Keypad-style single digit OCR: gray + Otsu + ddddocr."""
    if image.ndim == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image
    for scale in scales:
        height, width = gray.shape[:2]
        resized = cv2.resize(
            gray,
            (max(16, width * scale), max(16, height * scale)),
            interpolation=cv2.INTER_CUBIC,
        )
        _threshold, binary = cv2.threshold(
            resized, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )
        for candidate in (binary, resized):
            digit = normalize_one_digit(
                ocr.classification(Image.fromarray(candidate))
            )
            if digit is not None:
                return digit
    return None


def red_channel_mask(
    image_bgr: np.ndarray,
    threshold: int = 80,
    *,
    close: bool = False,
) -> np.ndarray:
    """Dark digit mask from low red channel (blob-style captcha digits)."""
    red = image_bgr[:, :, 2]
    mask = (red < threshold).astype(np.uint8) * 255
    if close:
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    return mask


def normalize_digit_mask(
    mask: np.ndarray,
    size: tuple[int, int] = (32, 40),
) -> np.ndarray:
    points = cv2.findNonZero(mask)
    if points is None:
        return np.zeros((size[1], size[0]), dtype=np.uint8)
    x, y, width, height = cv2.boundingRect(points)
    glyph = mask[y:y + height, x:x + width]
    canvas = np.zeros((size[1], size[0]), dtype=np.uint8)
    scale = min(
        size[0] / max(1, width),
        size[1] / max(1, height),
    )
    new_width = max(1, int(width * scale))
    new_height = max(1, int(height * scale))
    resized = cv2.resize(glyph, (new_width, new_height), interpolation=cv2.INTER_AREA)
    offset_x = (size[0] - new_width) // 2
    offset_y = (size[1] - new_height) // 2
    canvas[
        offset_y:offset_y + new_height,
        offset_x:offset_x + new_width,
    ] = resized
    return canvas


def recognize_two_digits(
    image_bgr: np.ndarray,
    ocr,
    thresholds: tuple[int, ...] = (58, 60, 62, 64, 66),
    minimum_votes: int = 2,
) -> LocalOcrResult:
    """TRautoRace-style blue-difference binarization with majority vote."""
    started = time.perf_counter()
    votes = []
    for threshold in thresholds:
        result = normalize_result(
            ocr.classification(
                blue_difference_binary(image_bgr, threshold)
            )
        )
        if result is not None:
            votes.append(result)
    winner = Counter(votes).most_common(1)
    text = winner[0][0] if winner else None
    winning_votes = winner[0][1] if winner else 0
    stable = text is not None and winning_votes >= minimum_votes
    return LocalOcrResult(
        text=text if stable else None,
        votes=tuple(votes),
        winning_votes=winning_votes,
        stable=stable,
        elapsed_seconds=time.perf_counter() - started,
    )


def read_two_digits(
    image_bgr: np.ndarray,
    *,
    minimum_votes: int = 3,
) -> LocalOcrResult:
    """Public OCR-only API: pixels in, recognition result out."""
    return recognize_two_digits(
        image_bgr,
        get_ocr(),
        minimum_votes=minimum_votes,
    )


_OCR = None
_OCR_LOCK = threading.Lock()


def get_ocr():
    global _OCR
    with _OCR_LOCK:
        if _OCR is None:
            try:
                import ddddocr
            except ImportError as exc:
                raise RuntimeError(
                    "未安裝 ddddocr；請重新執行 run_advanced.ps1"
                ) from exc
            try:
                _OCR = ddddocr.DdddOcr(beta=True, show_ad=False)
            except TypeError:
                _OCR = ddddocr.DdddOcr(show_ad=False)
        return _OCR


def capture_screen_region(region: list[int] | tuple[int, int, int, int]):
    if len(region) != 4:
        raise ValueError("OCR region 格式必須係 [left, top, width, height]")
    left, top, width, height = (int(value) for value in region)
    if width < 2 or height < 2:
        raise ValueError("OCR region 太細")
    with mss.mss() as sct:
        frame = np.asarray(sct.grab({
            "left": left,
            "top": top,
            "width": width,
            "height": height,
        }))
    return frame[:, :, :3]
