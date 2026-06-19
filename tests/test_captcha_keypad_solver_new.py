"""Second OCR sample (34) is readable and yields two distinct positions."""

from pathlib import Path
import sys

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from captcha_keypad_solver import solve_captcha_frame  # noqa: E402
from random_keypad_solver import build_click_plan  # noqa: E402

NEW_SAMPLE = Path(
    r"C:\Users\crazy\.cursor\projects\c-Users-crazy-OneDrive-Server\assets"
    r"\c__Users_crazy_AppData_Roaming_Cursor_User_workspaceStorage_empty-window_images"
    r"_image-6cb8e3f5-9ef6-4f0b-8f8f-dbaa59f43f55.png"
)


def main() -> None:
    if not NEW_SAMPLE.exists():
        print("Skip: new captcha sample not present")
        return

    encoded = np.frombuffer(NEW_SAMPLE.read_bytes(), dtype=np.uint8)
    frame = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    assert frame is not None

    answer, keypad = solve_captcha_frame(frame)
    assert answer == "34", answer
    assert set(keypad) == set("0123456789")

    plan = build_click_plan(answer, keypad)
    assert len(plan) == 2
    assert plan[0] != plan[1], plan
    print(f"New captcha solve OK: answer={answer}, clicks={plan}")


if __name__ == "__main__":
    main()
