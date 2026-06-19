"""Click captcha numpad buttons using templates and OCR JSON result."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time
from typing import Callable

import cv2
import mss
import numpy as np

from app_paths import APP_ROOT
from ocr_result_log import load_latest_ocr_result


ROOT = APP_ROOT
DEFAULT_NUMPAD_DIR = ROOT / "numpad"
DEFAULT_THRESHOLD = 0.82
EXTRA_BUTTONS = ("retry", "refresh", "reload")


def _match_template(
    frame_gray: np.ndarray,
    template: np.ndarray,
) -> tuple[float, tuple[int, int]]:
    if (
        template.shape[0] > frame_gray.shape[0]
        or template.shape[1] > frame_gray.shape[1]
    ):
        return 0.0, (0, 0)
    result = cv2.matchTemplate(frame_gray, template, cv2.TM_CCOEFF_NORMED)
    _min_val, score, _min_loc, location = cv2.minMaxLoc(result)
    return float(score), location


@dataclass(frozen=True)
class NumpadClickReport:
    result: str
    positions: dict[str, tuple[int, int]]
    clicks: tuple[tuple[str, int, int], ...]
    elapsed_seconds: float


def _read_gray_template(path: Path) -> np.ndarray | None:
    encoded = np.frombuffer(path.read_bytes(), dtype=np.uint8)
    image = cv2.imdecode(encoded, cv2.IMREAD_GRAYSCALE)
    return image


def _template_candidates(root: Path, name: str) -> list[Path]:
    patterns = [f"{name}.png", f"{name}.jpg", f"num{name}.png", f"num{name}.jpg"]
    if name.isdigit():
        patterns.extend([
            f"{name}.PNG",
            f"num{name}.PNG",
        ])
    return [root / pattern for pattern in patterns if (root / pattern).exists()]


def load_numpad_templates(
    numpad_dir: str | Path = DEFAULT_NUMPAD_DIR,
) -> dict[str, np.ndarray]:
    root = Path(numpad_dir)
    if not root.is_absolute():
        root = ROOT / root
    if not root.exists():
        raise FileNotFoundError(f"找不到 numpad 資料夾：{root}")

    templates: dict[str, np.ndarray] = {}
    for digit in "0123456789":
        paths = _template_candidates(root, digit)
        if not paths:
            continue
        image = _read_gray_template(paths[0])
        if image is not None:
            templates[digit] = image

    for alias in EXTRA_BUTTONS:
        paths = _template_candidates(root, alias)
        if not paths:
            continue
        image = _read_gray_template(paths[0])
        if image is not None:
            templates["retry"] = image
            break

    if len({key for key in templates if key.isdigit()}) < 10:
        missing = sorted(set("0123456789") - set(templates))
        raise FileNotFoundError(
            "numpad 缺少數字 template："
            + ", ".join(missing)
            + f"（資料夾：{root}）"
        )
    return templates


def locate_numpad_buttons(
    frame_gray: np.ndarray,
    templates: dict[str, np.ndarray],
    threshold: float = DEFAULT_THRESHOLD,
    offset_x: int = 0,
    offset_y: int = 0,
) -> dict[str, tuple[int, int]]:
    positions: dict[str, tuple[int, int]] = {}
    for name, template in templates.items():
        score, (x, y) = _match_template(frame_gray, template)
        if score < threshold:
            continue
        positions[name] = (
            offset_x + x + template.shape[1] // 2,
            offset_y + y + template.shape[0] // 2,
        )
    return positions


def capture_screen_gray() -> tuple[np.ndarray, int, int]:
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        frame = np.asarray(sct.grab(monitor))[:, :, :3]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return gray, int(monitor["left"]), int(monitor["top"])


def build_digit_click_plan(
    result: str,
    positions: dict[str, tuple[int, int]],
) -> list[tuple[str, int, int]]:
    if len(result) != 2 or not result.isdigit():
        raise ValueError("OCR result 必須係兩位數字")
    missing = [digit for digit in result if digit not in positions]
    if missing:
        raise RuntimeError(f"畫面搵唔到 numpad 數字：{missing}")
    return [(digit, *positions[digit]) for digit in result]


def click_numpad_result(
    result: str,
    click: Callable[[int, int], None],
    *,
    numpad_dir: str | Path = DEFAULT_NUMPAD_DIR,
    threshold: float = DEFAULT_THRESHOLD,
    click_interval: float = 0.35,
    log: Callable[[str], object] | None = None,
) -> NumpadClickReport:
    started = time.perf_counter()
    templates = load_numpad_templates(numpad_dir)
    frame_gray, offset_x, offset_y = capture_screen_gray()
    positions = locate_numpad_buttons(
        frame_gray,
        templates,
        threshold=threshold,
        offset_x=offset_x,
        offset_y=offset_y,
    )
    plan = build_digit_click_plan(result, positions)
    if log is not None:
        log(f"  numpad OCR result={result}, clicks={len(plan)}")
    clicks: list[tuple[str, int, int]] = []
    for index, (digit, x, y) in enumerate(plan):
        if log is not None:
            log(
                f"  numpad click {index + 1}/{len(plan)}: "
                f"digit={digit} at ({x}, {y})"
            )
        click(x, y)
        clicks.append((digit, x, y))
        if click_interval > 0 and index + 1 < len(plan):
            time.sleep(click_interval)
    return NumpadClickReport(
        result=result,
        positions=positions,
        clicks=tuple(clicks),
        elapsed_seconds=time.perf_counter() - started,
    )


def click_from_ocr_log(
    action: dict,
    engine_config: dict | None,
    click: Callable[[int, int], None],
    log: Callable[[str], object] | None = None,
    *,
    result_override: str | None = None,
) -> str:
    local_ocr = (engine_config or {}).get("local_ocr", {})
    captcha_cfg = local_ocr.get("captcha", {})
    output_dir = action.get(
        "result_log_dir",
        local_ocr.get("result_log_dir", "logs"),
    )
    numpad_dir = action.get(
        "numpad_dir",
        captcha_cfg.get("numpad_dir", "numpad"),
    )
    threshold = float(
        action.get("threshold", captcha_cfg.get("numpad_threshold", 0.82))
    )
    interval = max(
        0.0,
        float(
            action.get(
                "click_interval",
                captcha_cfg.get("click_interval", 0.35),
            )
        ),
    )
    result = result_override or load_latest_ocr_result(output_dir)
    report = click_numpad_result(
        result,
        click,
        numpad_dir=numpad_dir,
        threshold=threshold,
        click_interval=interval,
        log=log,
    )
    if log is not None:
        log(
            f"  numpad click done: {report.result} "
            f"({report.elapsed_seconds * 1000:.0f}ms)"
        )
    return report.result
