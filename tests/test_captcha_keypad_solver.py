"""Game captcha dialog is readable and solvable from the default reference."""

from pathlib import Path
import sys

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from captcha_keypad_solver import (  # noqa: E402
    DEFAULT_TEMPLATE,
    find_captcha_match,
    question_region_for_dialog,
    solve_captcha_frame,
)


def main() -> None:
    encoded = np.frombuffer(DEFAULT_TEMPLATE.read_bytes(), dtype=np.uint8)
    frame = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    assert frame is not None

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    match = find_captcha_match(gray, gray, threshold=0.99)
    assert match is not None
    assert match.score >= 0.99
    assert question_region_for_dialog(482, 318) == (154, 76, 80, 48)

    answer, keypad = solve_captcha_frame(frame)
    assert answer == "39", answer
    assert set(keypad) == set("0123456789")
    assert len(keypad) == 10

    plan = [keypad[digit] for digit in answer]
    assert len(plan) == 2
    assert plan[0] != plan[1], plan
    print(f"Captcha solve OK: answer={answer}, keypad={len(keypad)} buttons")


if __name__ == "__main__":
    main()
