"""Random keypad demo is visually detectable and solves by current layout."""

from pathlib import Path
import random
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from random_keypad_demo import (  # noqa: E402
    DemoChallenge,
    generate_challenge,
    render_challenge,
)
from random_keypad_solver import (  # noqa: E402
    build_click_plan,
    detect_button_boxes,
)


def main() -> None:
    first = generate_challenge(random.Random(42))
    second = generate_challenge(random.Random(43))
    assert sorted(first.layout) == list("0123456789")
    assert first.layout != second.layout
    assert len(first.answer) == 2 and first.answer.isdigit()

    challenge = DemoChallenge(
        answer="76",
        layout=("9", "3", "1", "7", "8", "0", "6", "5", "2", "4"),
    )
    image, _regions = render_challenge(challenge)
    boxes = detect_button_boxes(image)
    assert len(boxes) == 10, boxes

    centers = {
        digit: box.center
        for digit, box in zip(challenge.layout, boxes)
    }
    assert build_click_plan("76", centers) == [
        centers["7"], centers["6"],
    ]
    print("Random keypad demo detection and click plan OK")


if __name__ == "__main__":
    main()
