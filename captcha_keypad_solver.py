"""Tales Runner verification-code dialog: detect, read, and click."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import time
from typing import Callable

import cv2
import mss
import numpy as np

from app_paths import APP_ROOT
from local_ocr_lab import (
    capture_screen_region,
    classify_one_digit,
    get_ocr,
    recognize_two_digits,
    red_channel_mask,
)
from random_keypad_solver import (
    ButtonBox,
    build_click_plan,
)


ROOT = APP_ROOT
DEFAULT_TEMPLATE = ROOT / "templates" / "captcha_reference.png"
DEFAULT_THRESHOLD = 0.82

# Reference dialog size for templates/captcha_reference.png (477x314).
DEFAULT_DIALOG_SIZE = (477, 314)
# Question strip position as ratios of the matched dialog size.
# The noisy two-digit strip inside the complete dialog screenshot.
# This matches the original tool's roughly 73x48 OCR crop.
QUESTION_REGION_RATIO = (152 / 477, 75 / 314, 79 / 477, 47 / 314)
QUESTION_TOP_SKIP_RATIO = 8 / 40
QUESTION_RED_THRESHOLDS = (78, 80, 82)
QUESTION_RED_WEIGHTED_THRESHOLDS = tuple(range(74, 90, 2))
DIGIT_TEMPLATE_SIZE = (34, 34)
MIN_QUESTION_HALF_SCORE = 0.01
MIN_QUESTION_TOTAL_SCORE = 0.06
MIN_WEIGHTED_VOTE_SCORE = 0.05
MIN_WEIGHTED_HALF_TOTAL = 0.3
CAPTCHA_MATCH_SCALES = (0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.15)
REPEATED_DIGIT_CLICK_INTERVAL = 0.45


@dataclass(frozen=True)
class CaptchaMatch:
    score: float
    left: int
    top: int
    width: int
    height: int

    @property
    def capture_region(self) -> tuple[int, int, int, int]:
        return self.left, self.top, self.width, self.height

    @property
    def question_region(self) -> tuple[int, int, int, int]:
        return question_region_for_dialog(self.width, self.height)


@dataclass(frozen=True)
class CaptchaSolveReport:
    answer: str
    keypad: dict[str, tuple[int, int]]
    match: CaptchaMatch
    elapsed_seconds: float


@dataclass(frozen=True)
class CaptchaReadReport:
    """OCR-only output. It never sends mouse or keyboard input."""

    answer: str
    keypad: dict[str, tuple[int, int]]
    match: CaptchaMatch
    elapsed_seconds: float


def question_region_for_dialog(
    width: int,
    height: int,
) -> tuple[int, int, int, int]:
    ratio_x, ratio_y, ratio_w, ratio_h = QUESTION_REGION_RATIO
    return (
        int(round(ratio_x * width)),
        int(round(ratio_y * height)),
        max(2, int(round(ratio_w * width))),
        max(2, int(round(ratio_h * height))),
    )


def detect_game_keypad_buttons(image_bgr: np.ndarray) -> list[ButtonBox]:
    """Find digit-like buttons on the blue keypad panel."""
    height, width = image_bgr.shape[:2]
    keypad_x = max(0, int(width * 0.48))
    panel = image_bgr[:, keypad_x:]
    blue, green, red = cv2.split(panel)
    blue_background = (blue > green + 10) & (blue > red + 5) & (blue > 100)
    mask = (~blue_background).astype(np.uint8) * 255
    mask = cv2.morphologyEx(
        mask, cv2.MORPH_OPEN, np.ones((3, 3), dtype=np.uint8)
    )
    contours, _hierarchy = cv2.findContours(
        mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    boxes: list[ButtonBox] = []
    for contour in contours:
        x, y, box_width, box_height = cv2.boundingRect(contour)
        area = cv2.contourArea(contour)
        if not (30 <= box_width <= 75 and 30 <= box_height <= 75):
            continue
        if area / (box_width * box_height) < 0.5:
            continue
        boxes.append(
            ButtonBox(
                x=keypad_x + x,
                y=y,
                width=box_width,
                height=box_height,
            )
        )
    boxes.sort(key=lambda box: (box.y // 20, box.x))
    return boxes


def _build_keypad_binary_templates(
    frame_bgr: np.ndarray,
    keypad: dict[str, tuple[int, int]],
) -> dict[str, np.ndarray]:
    """Otsu-outline templates from keypad buttons for question matching."""
    templates: dict[str, np.ndarray] = {}
    for digit, (center_x, center_y) in keypad.items():
        half = 18
        crop = frame_bgr[
            max(0, center_y - half):center_y + half,
            max(0, center_x - half):center_x + half,
        ]
        if crop.size == 0:
            continue
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        _threshold, binary = cv2.threshold(
            gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )
        templates[digit] = cv2.resize(
            binary,
            DIGIT_TEMPLATE_SIZE,
            interpolation=cv2.INTER_AREA,
        )
    if len(templates) < 10:
        raise RuntimeError(
            "Could not build keypad digit templates: "
            + "".join(sorted(templates))
        )
    return templates


def _score_mask_half(
    half_mask: np.ndarray,
    templates: dict[str, np.ndarray],
) -> dict[str, float]:
    resized = cv2.resize(
        half_mask,
        DIGIT_TEMPLATE_SIZE,
        interpolation=cv2.INTER_AREA,
    )
    return {
        digit: float(
            cv2.matchTemplate(resized, template, cv2.TM_CCOEFF_NORMED)[0, 0]
        )
        for digit, template in templates.items()
    }


def _best_digit_from_scores(
    scores: dict[str, float],
) -> tuple[str, float, float]:
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_digit, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else -1.0
    return best_digit, best_score, second_score


def _split_question_mask(mask: np.ndarray) -> int:
    width = mask.shape[1]
    projection = mask.sum(axis=0)
    search_start = max(1, width // 4)
    search_end = max(search_start + 1, (3 * width) // 4)
    return int(np.argmin(projection[search_start:search_end]) + search_start)


def _recognize_question_red_masks(
    question_bgr: np.ndarray,
    templates: dict[str, np.ndarray],
) -> str | None:
    """Red-channel blob digits split and matched to keypad Otsu templates."""
    candidates: list[tuple[str, float, float]] = []
    for threshold in QUESTION_RED_THRESHOLDS:
        mask = red_channel_mask(question_bgr, threshold=threshold)
        split = _split_question_mask(mask)
        left_scores = _score_mask_half(mask[:, :split], templates)
        right_scores = _score_mask_half(mask[:, split:], templates)
        left_digit, left_score, _left_margin = _best_digit_from_scores(left_scores)
        right_digit, right_score, _right_margin = _best_digit_from_scores(
            right_scores
        )
        total = left_score + right_score
        if (
            left_score >= MIN_QUESTION_HALF_SCORE
            and right_score >= MIN_QUESTION_HALF_SCORE
            and total >= MIN_QUESTION_TOTAL_SCORE
        ):
            candidates.append((f"{left_digit}{right_digit}", total, threshold))

    if not candidates:
        return None

    votes = Counter(answer for answer, _total, _threshold in candidates)
    if len(votes) == 1:
        return next(iter(votes))

    winner, _vote_count = votes.most_common(1)[0]
    tied = [
        candidate
        for candidate in candidates
        if candidate[0] == winner
    ]
    best = max(tied, key=lambda item: item[1])
    return best[0]


def _question_roi(question_bgr: np.ndarray) -> np.ndarray:
    top_skip = max(0, int(round(question_bgr.shape[0] * QUESTION_TOP_SKIP_RATIO)))
    return question_bgr[top_skip:, :]


def _recognize_question_weighted_vote(
    question_bgr: np.ndarray,
    templates: dict[str, np.ndarray],
) -> str | None:
    """Vote per digit across red thresholds and split positions."""
    left_weights: dict[str, float] = {}
    right_weights: dict[str, float] = {}
    roi = _question_roi(question_bgr)
    if roi.size == 0:
        return None

    for threshold in QUESTION_RED_WEIGHTED_THRESHOLDS:
        mask = red_channel_mask(roi, threshold=threshold, close=True)
        width = mask.shape[1]
        search_start = max(1, width // 4)
        search_end = max(search_start + 1, (3 * width) // 4)
        for split in range(search_start, search_end):
            left_scores = _score_mask_half(mask[:, :split], templates)
            right_scores = _score_mask_half(mask[:, split:], templates)
            left_digit, left_score, _left_margin = _best_digit_from_scores(left_scores)
            right_digit, right_score, _right_margin = _best_digit_from_scores(
                right_scores
            )
            if left_score >= MIN_WEIGHTED_VOTE_SCORE:
                left_weights[left_digit] = (
                    left_weights.get(left_digit, 0.0) + left_score
                )
            if right_score >= MIN_WEIGHTED_VOTE_SCORE:
                right_weights[right_digit] = (
                    right_weights.get(right_digit, 0.0) + right_score
                )

    if not left_weights or not right_weights:
        return None

    left_digit = max(left_weights, key=left_weights.get)
    right_digit = max(right_weights, key=right_weights.get)
    if (
        left_weights[left_digit] < MIN_WEIGHTED_HALF_TOTAL
        or right_weights[right_digit] < MIN_WEIGHTED_HALF_TOTAL
    ):
        return None
    return f"{left_digit}{right_digit}"


def _prep_digit_template(image_gray: np.ndarray) -> np.ndarray:
    resized = cv2.resize(image_gray, (34, 34), interpolation=cv2.INTER_AREA)
    _threshold, binary = cv2.threshold(
        resized, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )
    return binary


def _build_digit_templates(
    frame_bgr: np.ndarray,
    keypad: dict[str, tuple[int, int]],
) -> dict[str, np.ndarray]:
    templates: dict[str, np.ndarray] = {}
    for digit, (center_x, center_y) in keypad.items():
        half = 18
        crop = frame_bgr[
            max(0, center_y - half):center_y + half,
            max(0, center_x - half):center_x + half,
        ]
        if crop.size == 0:
            continue
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        templates[digit] = cv2.resize(gray, (34, 34), interpolation=cv2.INTER_AREA)
    if len(templates) < 10:
        raise RuntimeError(
            "Could not build digit templates from keypad: "
            + "".join(sorted(templates))
        )
    return templates


def _prepare_question_gray(question_bgr: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(question_bgr, cv2.COLOR_BGR2GRAY)
    return cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)


def _split_question_halves(
    question_gray: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    height, width = question_gray.shape[:2]
    dark = (question_gray < 120).astype(np.uint8)
    projection = dark.sum(axis=0)
    search_start = max(1, width // 4)
    search_end = max(search_start + 1, (3 * width) // 4)
    split = int(np.argmin(projection[search_start:search_end]) + search_start)
    return question_gray[:, :split], question_gray[:, split:]


def _score_half_against_templates(
    half_gray: np.ndarray,
    templates: dict[str, np.ndarray],
) -> dict[str, float]:
    resized = cv2.resize(
        half_gray,
        (34, 34),
        interpolation=cv2.INTER_AREA,
    )
    scores: dict[str, float] = {}
    for digit, template in templates.items():
        binary_score = float(
            cv2.matchTemplate(
                _prep_digit_template(resized),
                _prep_digit_template(template),
                cv2.TM_CCOEFF_NORMED,
            )[0, 0]
        )
        gray_score = float(
            cv2.matchTemplate(resized, template, cv2.TM_CCOEFF_NORMED)[0, 0]
        )
        scores[digit] = max(binary_score, gray_score)
    return scores


def _best_digit(scores: dict[str, float]) -> tuple[str, float, float]:
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_digit, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else -1.0
    return best_digit, best_score, second_score


def _match_digit(
    half_gray: np.ndarray,
    templates: dict[str, np.ndarray],
    minimum_score: float = 0.04,
    minimum_margin: float = 0.008,
) -> str:
    best_digit, best_score, second_score = _best_digit(
        _score_half_against_templates(half_gray, templates)
    )
    if best_score < minimum_score:
        raise RuntimeError(f"Captcha digit match too weak: {best_digit}={best_score:.3f}")
    if best_score - second_score < minimum_margin:
        raise RuntimeError(
            f"Captcha digit match ambiguous: {best_digit}={best_score:.3f}"
        )
    return best_digit


def _find_best_split_answer(
    question_gray: np.ndarray,
    templates: dict[str, np.ndarray],
) -> tuple[str, float]:
    height, width = question_gray.shape[:2]
    best_answer = ""
    best_total = -1.0
    search_start = max(1, width // 4)
    search_end = max(search_start + 1, (3 * width) // 4)
    for split in range(search_start, search_end):
        left_scores = _score_half_against_templates(
            question_gray[:, :split], templates
        )
        right_scores = _score_half_against_templates(
            question_gray[:, split:], templates
        )
        for left_digit, left_score in left_scores.items():
            for right_digit, right_score in right_scores.items():
                total = left_score + right_score
                if total > best_total:
                    best_total = total
                    best_answer = f"{left_digit}{right_digit}"
    if best_total < 0.08:
        raise RuntimeError(f"Captcha answer match too weak: {best_total:.3f}")
    return best_answer, best_total


def recognize_captcha_digits(
    frame_bgr: np.ndarray,
    question_region: tuple[int, int, int, int],
    keypad: dict[str, tuple[int, int]],
    ocr=None,
) -> str:
    ocr = ocr or get_ocr()
    x, y, width, height = question_region
    question_bgr = frame_bgr[y:y + height, x:x + width]

    # Primary path: the TRautoRace-style blue-background vote is both
    # faster and substantially more reliable for the noisy question strip.
    ocr_result = recognize_two_digits(question_bgr, ocr)
    if ocr_result.stable and ocr_result.text:
        return ocr_result.text

    binary_templates = _build_keypad_binary_templates(frame_bgr, keypad)
    red_answer = _recognize_question_red_masks(question_bgr, binary_templates)
    if red_answer is not None:
        return red_answer

    weighted_answer = _recognize_question_weighted_vote(
        question_bgr, binary_templates
    )
    if weighted_answer is not None:
        return weighted_answer

    gray_templates = _build_digit_templates(frame_bgr, keypad)
    question = _prepare_question_gray(question_bgr)
    answer, _total = _find_best_split_answer(question, gray_templates)
    return answer


def recognize_game_keypad(
    frame_bgr: np.ndarray,
    ocr=None,
) -> dict[str, tuple[int, int]]:
    ocr = ocr or get_ocr()
    mapping: dict[str, tuple[int, int]] = {}
    for box in detect_game_keypad_buttons(frame_bgr):
        margin = 4
        crop = frame_bgr[
            box.y + margin:box.y + box.height - margin,
            box.x + margin:box.x + box.width - margin,
        ]
        digit = classify_one_digit(crop, ocr)
        if digit is None:
            continue
        if digit in mapping:
            continue
        mapping[digit] = box.center
    if set(mapping) != set("0123456789"):
        raise RuntimeError(
            "Keypad OCR incomplete: " + "".join(sorted(mapping))
        )
    return mapping


def solve_captcha_frame(
    frame_bgr: np.ndarray,
    question_region: tuple[int, int, int, int] | None = None,
    ocr=None,
) -> tuple[str, dict[str, tuple[int, int]]]:
    if question_region is None:
        dialog_height, dialog_width = frame_bgr.shape[:2]
        question_region = question_region_for_dialog(dialog_width, dialog_height)
    keypad = recognize_game_keypad(frame_bgr, ocr)
    answer = recognize_captcha_digits(frame_bgr, question_region, keypad)
    return answer, keypad


def find_captcha_match(
    frame_gray: np.ndarray,
    template_gray: np.ndarray,
    threshold: float = DEFAULT_THRESHOLD,
    scales: tuple[float, ...] = CAPTCHA_MATCH_SCALES,
) -> CaptchaMatch | None:
    template_height, template_width = template_gray.shape[:2]
    best: CaptchaMatch | None = None
    for scale in scales:
        width = int(round(template_width * scale))
        height = int(round(template_height * scale))
        if width < 40 or height < 40:
            continue
        if width > frame_gray.shape[1] or height > frame_gray.shape[0]:
            continue
        scaled = (
            template_gray
            if scale == 1.0
            else cv2.resize(
                template_gray,
                (width, height),
                interpolation=cv2.INTER_AREA,
            )
        )
        result = cv2.matchTemplate(
            frame_gray, scaled, cv2.TM_CCOEFF_NORMED
        )
        _min_val, score, _min_loc, location = cv2.minMaxLoc(result)
        if score < threshold:
            continue
        candidate = CaptchaMatch(
            score=float(score),
            left=int(location[0]),
            top=int(location[1]),
            width=width,
            height=height,
        )
        if best is None or candidate.score > best.score:
            best = candidate
    return best


def load_default_template() -> np.ndarray | None:
    if not DEFAULT_TEMPLATE.exists():
        return None
    encoded = np.frombuffer(DEFAULT_TEMPLATE.read_bytes(), dtype=np.uint8)
    image = cv2.imdecode(encoded, cv2.IMREAD_GRAYSCALE)
    return image


def find_captcha_on_screen(
    threshold: float = DEFAULT_THRESHOLD,
    template_gray: np.ndarray | None = None,
) -> CaptchaMatch | None:
    template_gray = template_gray if template_gray is not None else load_default_template()
    if template_gray is None:
        return None
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        frame = np.asarray(sct.grab(monitor))[:, :, :3]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    match = find_captcha_match(
        gray,
        template_gray,
        threshold=threshold,
    )
    if match is None:
        return None
    return CaptchaMatch(
        score=match.score,
        left=int(monitor["left"]) + match.left,
        top=int(monitor["top"]) + match.top,
        width=match.width,
        height=match.height,
    )


def solve_captcha_match(
    match: CaptchaMatch,
    click: Callable[..., object],
    click_interval: float = 0.15,
    log: Callable[[str], object] | None = None,
) -> CaptchaSolveReport:
    started = time.perf_counter()
    report = read_captcha_match(match)
    answer = report.answer
    keypad = report.keypad
    left, top, _width, _height = match.capture_region
    plan = build_click_plan(answer, keypad)
    if log is not None:
        log(f"  captcha answer={answer}, clicks={len(plan)}")
        if len(plan) == 2 and plan[0] == plan[1]:
            log(
                f"  captcha warning: both digits map to the same button "
                f"(answer={answer})"
            )
    for index, (x, y) in enumerate(plan, start=1):
        screen_x = left + x
        screen_y = top + y
        if log is not None:
            log(
                f"  captcha click {index}/{len(plan)}: "
                f"digit={answer[index - 1]} at ({screen_x}, {screen_y})"
            )
        click(x=screen_x, y=screen_y)
        if index < len(plan):
            interval = _effective_click_interval(
                answer,
                plan,
                index - 1,
                click_interval,
            )
            if interval > 0:
                time.sleep(interval)
    return CaptchaSolveReport(
        answer=answer,
        keypad=keypad,
        match=match,
        elapsed_seconds=time.perf_counter() - started,
    )


def _effective_click_interval(
    answer: str,
    plan: list[tuple[int, int]],
    index: int,
    configured_interval: float,
) -> float:
    if index + 1 >= len(plan):
        return configured_interval
    repeated_digit = answer[index] == answer[index + 1]
    same_position = plan[index] == plan[index + 1]
    if repeated_digit or same_position:
        return max(configured_interval, REPEATED_DIGIT_CLICK_INTERVAL)
    return configured_interval


def read_captcha_match(match: CaptchaMatch) -> CaptchaReadReport:
    """Capture and recognise one matched dialog without clicking anything."""
    started = time.perf_counter()
    frame = capture_screen_region(match.capture_region)
    question_region = question_region_for_dialog(match.width, match.height)
    answer, keypad = solve_captcha_frame(
        frame, question_region=question_region
    )
    return CaptchaReadReport(
        answer=answer,
        keypad=keypad,
        match=match,
        elapsed_seconds=time.perf_counter() - started,
    )
