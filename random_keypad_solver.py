"""Visual solver restricted to the JK世界 Random Keypad Demo window."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import time
from typing import Callable

import cv2
import mss
import numpy as np
import pyautogui

from local_ocr_lab import classify_one_digit, get_ocr, normalize_result, recognize_two_digits
from random_keypad_demo import QUESTION_REGION, WINDOW_TITLE


@dataclass(frozen=True)
class ButtonBox:
    x: int
    y: int
    width: int
    height: int

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.width // 2, self.y + self.height // 2


@dataclass(frozen=True)
class SolveReport:
    answer: str
    keypad: dict[str, tuple[int, int]]
    elapsed_seconds: float


def detect_button_boxes(image_bgr: np.ndarray) -> list[ButtonBox]:
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    mask = cv2.inRange(gray, 225, 255)
    mask[:78, :] = 0
    mask[:, :190] = 0
    mask = cv2.morphologyEx(
        mask, cv2.MORPH_CLOSE, np.ones((5, 5), dtype=np.uint8)
    )
    contours, _hierarchy = cv2.findContours(
        mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    boxes = []
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        if 42 <= width <= 62 and 45 <= height <= 66:
            boxes.append(ButtonBox(x, y, width, height))
    boxes.sort(key=lambda box: (box.y // 20, box.x))
    return boxes



def recognize_keypad(
    image_bgr: np.ndarray,
    ocr=None,
) -> dict[str, tuple[int, int]]:
    ocr = ocr or get_ocr()
    boxes = detect_button_boxes(image_bgr)
    if len(boxes) != 10:
        raise RuntimeError(f"Expected 10 digit buttons, found {len(boxes)}")
    mapping: dict[str, tuple[int, int]] = {}
    for box in boxes:
        margin = 4
        crop = image_bgr[
            box.y + margin:box.y + box.height - margin,
            box.x + margin:box.x + box.width - margin,
        ]
        digit = classify_one_digit(crop, ocr)
        if digit is None:
            raise RuntimeError(f"Could not read button at {box.center}")
        if digit in mapping:
            raise RuntimeError(f"Duplicate keypad digit detected: {digit}")
        mapping[digit] = box.center
    if set(mapping) != set("0123456789"):
        raise RuntimeError(
            "Keypad OCR incomplete: " + "".join(sorted(mapping))
        )
    return mapping


def build_click_plan(
    answer: str,
    keypad: dict[str, tuple[int, int]],
) -> list[tuple[int, int]]:
    if len(answer) != 2 or not answer.isdigit():
        raise ValueError("Answer must contain exactly two digits")
    missing = [digit for digit in answer if digit not in keypad]
    if missing:
        raise ValueError(f"Missing keypad digits: {missing}")
    return [keypad[digit] for digit in answer]


def _client_region(hwnd: int) -> tuple[int, int, int, int]:
    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long), ("top", ctypes.c_long),
            ("right", ctypes.c_long), ("bottom", ctypes.c_long),
        ]

    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    rect = RECT()
    origin = POINT(0, 0)
    user32 = ctypes.windll.user32
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        raise ctypes.WinError()
    if not user32.ClientToScreen(hwnd, ctypes.byref(origin)):
        raise ctypes.WinError()
    return (
        int(origin.x), int(origin.y),
        int(rect.right - rect.left), int(rect.bottom - rect.top),
    )


def capture_demo() -> tuple[np.ndarray, tuple[int, int]]:
    hwnd = int(ctypes.windll.user32.FindWindowW(None, WINDOW_TITLE))
    if not hwnd:
        raise RuntimeError(f"Window not found: {WINDOW_TITLE}")
    left, top, width, height = _client_region(hwnd)
    with mss.mss() as sct:
        frame = np.asarray(sct.grab({
            "left": left, "top": top,
            "width": width, "height": height,
        }))[:, :, :3]
    return frame, (left, top)


def solve_frame(
    frame_bgr: np.ndarray,
    ocr=None,
    question_region: tuple[int, int, int, int] | None = None,
) -> tuple[str, dict[str, tuple[int, int]]]:
    ocr = ocr or get_ocr()
    x, y, width, height = question_region or QUESTION_REGION
    question = frame_bgr[y:y + height, x:x + width]
    result = recognize_two_digits(question, ocr)
    if not result.stable or not result.text:
        raise RuntimeError(
            f"Question OCR unstable: {result.votes}"
        )
    return result.text, recognize_keypad(frame_bgr, ocr)


def solve_demo(
    click: Callable[..., object] = pyautogui.click,
) -> SolveReport:
    started = time.perf_counter()
    frame, (left, top) = capture_demo()
    answer, keypad = solve_frame(frame)
    for x, y in build_click_plan(answer, keypad):
        click(x=left + x, y=top + y)
        time.sleep(0.12)
    return SolveReport(
        answer=answer,
        keypad=keypad,
        elapsed_seconds=time.perf_counter() - started,
    )
