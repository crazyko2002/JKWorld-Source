"""Numpad click reads OCR JSON and clicks digit templates."""

import json
from pathlib import Path
import sys
import tempfile

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from numpad_clicker import (  # noqa: E402
    build_digit_click_plan,
    click_from_ocr_log,
    load_numpad_templates,
    locate_numpad_buttons,
)
from ocr_result_log import export_ocr_result  # noqa: E402


def _write_digit_template(path: Path, label: str) -> None:
    image = np.full((24, 24), 255, dtype=np.uint8)
    cv2.putText(
        image,
        label,
        (4, 18),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        0,
        2,
        cv2.LINE_AA,
    )
    cv2.imwrite(str(path), image)


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        numpad_dir = root / "numpad"
        log_dir = root / "logs"
        numpad_dir.mkdir()
        for digit in "0123456789":
            _write_digit_template(numpad_dir / f"{digit}.png", digit)
        _write_digit_template(numpad_dir / "retry.png", "R")
        export_ocr_result(result="31", elapsed_seconds=0.01, output_dir=log_dir)

        templates = load_numpad_templates(numpad_dir)
        assert len(templates) >= 10

        canvas = np.full((120, 400), 255, dtype=np.uint8)
        x = 10
        for digit in "0123456789":
            template = templates[digit]
            canvas[
                20:20 + template.shape[0],
                x:x + template.shape[1],
            ] = template
            x += template.shape[1] + 8

        positions = locate_numpad_buttons(canvas, templates, threshold=0.9)
        assert "3" in positions and "1" in positions
        plan = build_digit_click_plan("31", positions)
        assert [item[0] for item in plan] == ["3", "1"]

        import numpad_clicker as numpad_module

        numpad_module.capture_screen_gray = lambda: (canvas, 0, 0)
        calls: list[tuple[int, int]] = []
        answer = click_from_ocr_log(
            {
                "result_log_dir": str(log_dir),
                "numpad_dir": str(numpad_dir),
                "click_interval": 0.0,
            },
            {"local_ocr": {"result_log_dir": str(log_dir)}},
            lambda x, y: calls.append((x, y)),
            log=lambda _: None,
        )
        assert answer == "31"

        payload = json.loads((log_dir / "ocr_latest.json").read_text(encoding="utf-8"))
        assert payload["result"] == "31"
        print("Numpad click from OCR JSON OK")


if __name__ == "__main__":
    main()
