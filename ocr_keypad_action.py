"""Captcha OCR keypad action for Advanced Flow."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np

from app_paths import APP_ROOT
from ocr_result_log import export_ocr_result
from captcha_keypad_solver import (
    CaptchaMatch,
    find_captcha_on_screen,
    load_default_template,
    read_captcha_match,
    solve_captcha_match,
)

ROOT = APP_ROOT

LogFn = Callable[[str], Any]
ClickFn = Callable[[int, int], None]


def read_ocr_keypad_action(
    action: dict[str, Any],
    engine_config: dict[str, Any] | None,
    log: LogFn = print,
    captcha_match: CaptchaMatch | None = None,
) -> str:
    """OCR-only action. Returns the digits and never clicks."""
    if captcha_match is None:
        local_ocr = (engine_config or {}).get("local_ocr", {})
        captcha_cfg = local_ocr.get("captcha", {})
        threshold = float(
            action.get("threshold", captcha_cfg.get("threshold", 0.82))
        )
        template_path = action.get("template") or captcha_cfg.get(
            "template", "templates/captcha_reference.png"
        )
        path = Path(str(template_path))
        if not path.is_absolute():
            path = ROOT / path
        template = _read_gray_image(path)
        if template is None:
            template = load_default_template()
        if template is None:
            raise ValueError("找不到 OCR reference image")
        captcha_match = find_captcha_on_screen(
            threshold=threshold, template_gray=template
        )
        if captcha_match is None:
            raise RuntimeError("未偵測到 OCR target")

    report = read_captcha_match(captcha_match)
    local_ocr = (engine_config or {}).get("local_ocr", {})
    output_dir = action.get(
        "result_log_dir",
        local_ocr.get("result_log_dir", "logs"),
    )
    export_ocr_result(
        result=report.answer,
        elapsed_seconds=report.elapsed_seconds,
        match_score=report.match.score,
        capture_region=report.match.capture_region,
        source="ocr_read",
        output_dir=output_dir,
    )
    log(
        f"  OCR result={report.answer}, "
        f"time={report.elapsed_seconds * 1000:.0f}ms, "
        f"log={output_dir}/ocr_latest.json"
    )
    return report.answer


def _read_gray_image(path: Path) -> np.ndarray | None:
    try:
        encoded = np.frombuffer(path.read_bytes(), dtype=np.uint8)
    except OSError:
        return None
    return cv2.imdecode(encoded, cv2.IMREAD_GRAYSCALE)


def run_ocr_keypad_action(
    action: dict[str, Any],
    engine_config: dict[str, Any] | None,
    click: ClickFn,
    log: LogFn = print,
    captcha_match: CaptchaMatch | None = None,
) -> str:
    local_ocr = (engine_config or {}).get("local_ocr", {})
    captcha_cfg = local_ocr.get("captcha", {})
    interval = max(
        0.0,
        float(
            action.get(
                "click_interval",
                captcha_cfg.get("click_interval", 0.15),
            )
        ),
    )
    if captcha_match is None:
        threshold = float(
            action.get(
                "threshold",
                captcha_cfg.get("threshold", 0.82),
            )
        )
        template_path = action.get("template") or captcha_cfg.get(
            "template", "templates/captcha_reference.png"
        )
        path = Path(str(template_path))
        if not path.is_absolute():
            path = ROOT / path
        template = _read_gray_image(path)
        if template is None:
            template = load_default_template()
        if template is None:
            raise ValueError(
                "找不到 captcha 參考圖；請放 templates/captcha_reference.png"
            )
        match = find_captcha_on_screen(
            threshold=threshold, template_gray=template
        )
        if match is None:
            raise RuntimeError("畫面未偵測到驗證碼視窗")
        captcha_match = match

    report = solve_captcha_match(
        captcha_match,
        click=lambda **kwargs: click(int(kwargs["x"]), int(kwargs["y"])),
        click_interval=interval,
        log=log,
    )
    log(
        f"  OCR keypad captcha：{report.answer} "
        f"({report.match.score:.1%}, "
        f"{report.elapsed_seconds * 1000:.0f}ms)"
    )
    return report.answer


def click_ocr_keypad_action(
    action: dict[str, Any],
    engine_config: dict[str, Any] | None,
    click: ClickFn,
    log: LogFn = print,
    result_override: str | None = None,
) -> str:
    """Read OCR result from logs/ocr_latest.json and click numpad templates."""
    from numpad_clicker import click_from_ocr_log

    return click_from_ocr_log(
        action,
        engine_config,
        click,
        log,
        result_override=result_override,
    )
